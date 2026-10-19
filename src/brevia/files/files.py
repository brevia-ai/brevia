"""Files of runs: inputs downloaded from allowed URLs, outputs saved with the run.

An activity receives its input files as :class:`FileSource` values in its input: a URL
of an allowed host, or a local path for trusted code. ``ctx.files.local_path(source)``
downloads or copies the file into a work folder of the run, checks its size, type and
fingerprint, and returns its path. The work folder is removed when the run ends, also
when it fails: inputs are not kept.

``ctx.files.save(name, content)`` writes an output in the folder of the run and returns
its :class:`FileRef`. The same name gives the same file: a job that starts again after
an interruption replaces it, without duplicates. Outputs are read through the handle of
their job, with the access policy of the caller.

Layout under ``BREVIA_FILES_ROOT``, shared by the processes that run and read jobs::

    work/<run_id>/<n>/<name>    inputs of a run in progress, removed at its end
    runs/<run_id>/<name>        outputs of a run

The daily cleanup removes the work folders left by a stopped process, one day after
their last change, and the outputs of a run ``retention_days`` after the last output
it saved.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import mimetypes
import os
import shutil
import tempfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, BinaryIO, NamedTuple, Self

import httpx2
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from brevia.access.access import Caller
from brevia.errors import FileTooLarge, InvalidInput, NotFound, Unavailable, cause_types
from brevia.files.documents import Document, check_readable, read_document

if TYPE_CHECKING:
    from brevia.config.settings import BreviaSettings

MAX_NAME_LENGTH = 200
"""Longest file name."""

PARTIAL_PREFIX = ".partial-"
"""Prefix of the files being written, reserved: no file of a run may start with it."""

CHUNK = 1024 * 1024
"""Bytes read and written at a time."""

DOWNLOAD_TIMEOUT = 60.0
"""Seconds allowed to each network operation of a download (connect, read)."""

MAX_REDIRECTS = 5
"""Redirects followed by a download, each to an allowed host."""

DEFAULT_EXTENSIONS = ".pdf,.docx,.xlsx,.pptx,.txt,.md,.csv,.json"
"""Extensions of the input files accepted by default."""

WORK_GRACE = timedelta(days=1)
"""Age after which a work folder left by a stopped process is removed."""

logger = logging.getLogger(__name__)

_transport: httpx2.AsyncBaseTransport | None = None  # replaced by tests


class _UrlsWithoutQuery(logging.Filter):
    """Removes query, credentials and fragment from the URLs that ``httpx2`` logs.

    ``httpx2`` logs each request with its URL at the ``INFO`` level; the URL of an
    input file may carry a temporary signature in its query.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(
                _without_query(item) if isinstance(item, httpx2.URL) else item
                for item in record.args
            )
        return True


def _without_query(url: httpx2.URL) -> str:
    return str(url.copy_with(query=None, fragment=None, userinfo=b""))


def guard_http_logs() -> None:
    """Install the filter of the URLs logged by ``httpx2``. Repeatable."""
    http = logging.getLogger("httpx2")
    if not any(isinstance(item, _UrlsWithoutQuery) for item in http.filters):
        http.addFilter(_UrlsWithoutQuery())


guard_http_logs()


def checked_name(name: str) -> str:
    """``name`` if it can name a file in a folder of Brevia.

    Raises:
        InvalidInput: ``name`` is blank, longer than :data:`MAX_NAME_LENGTH`, holds a
            path separator or a NUL character, is ``.`` or ``..``, or starts with the
            reserved :data:`PARTIAL_PREFIX`.
    """
    if (
        not isinstance(name, str)
        or not name.strip()
        or len(name) > MAX_NAME_LENGTH
        or any(character in name for character in "/\\\x00")
        or name in (".", "..")
        or name.startswith(PARTIAL_PREFIX)
    ):
        raise InvalidInput(
            "A file name must be a single non-blank name of at most "
            f"{MAX_NAME_LENGTH} characters, without path separators and not starting "
            f"with {PARTIAL_PREFIX!r}",
        )
    return name


def _mime(name: str) -> str:
    return mimetypes.guess_type(name)[0] or "application/octet-stream"


class FileSource(BaseModel):
    """An input file of a run: a URL of an allowed host, or a local path.

    ``name`` is descriptive and gives the type of the file by its extension; it never
    becomes a path of the server. ``sha256`` and ``size``, when given, are checked
    against the content. A local ``path`` is accepted only from trusted code (runs
    and jobs without a caller), for scripts and tests.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1, max_length=MAX_NAME_LENGTH)
    url: HttpUrl | None = None
    path: Path | None = None
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    size: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _one_location(self) -> Self:
        try:
            checked_name(self.name)
        except InvalidInput as exc:
            raise ValueError(exc.message) from None
        if (self.url is None) == (self.path is None):
            raise ValueError("give either url or path")
        return self


class FileRef(BaseModel):
    """An output file of a run, saved by ``ctx.files.save``.

    It identifies the file by its run and name, without a path or a URL; the content
    is read with :meth:`brevia.RunHandle.file`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    name: str
    mime: str
    size: int
    sha256: str


@dataclass(frozen=True)
class FileStore:
    """Where the files of runs are kept, and which input files are accepted.

    Args:
        root: Folder of the files; Brevia creates ``work`` and ``runs`` in it.
        max_bytes: Largest input file.
        allowed_extensions: Extensions of the input files accepted, lowercase with
            the dot (``.pdf``).
        allowed_hosts: Host names input files may be downloaded from; empty allows
            no download.
        retention_days: Days the outputs of a run are kept after the last one it
            saved; ``0`` keeps them without limit.
    """

    root: Path
    max_bytes: int = 50 * 1024 * 1024
    allowed_extensions: frozenset[str] = field(
        default_factory=lambda: _names(DEFAULT_EXTENSIONS)
    )
    allowed_hosts: frozenset[str] = frozenset()
    retention_days: int = 30

    @classmethod
    def from_settings(cls, settings: BreviaSettings) -> FileStore | None:
        """Store of ``BREVIA_FILES_*``, or ``None`` without ``BREVIA_FILES_ROOT``."""
        if settings.files_root is None:
            return None
        return cls(
            root=settings.files_root,
            max_bytes=settings.files_max_bytes,
            allowed_extensions=_names(settings.files_allowed_extensions),
            allowed_hosts=_names(settings.files_allowed_hosts),
            retention_days=settings.files_retention_days,
        )

    def clean(self, now: datetime, *, dry_run: bool = False) -> FilesCleaned:
        """Remove the expired folders and count them; with ``dry_run``, only count.

        A work folder is removed :data:`WORK_GRACE` after its last change, so that the
        inputs of a run that lasts longer than that may be removed while it runs; the
        outputs of a run, ``retention_days`` after the last one it saved, never with
        ``0``. A folder that disappears meanwhile (a run that ends) is skipped; one
        that cannot be removed is counted as failed and logged, and the others are
        removed anyway.
        """
        work = _unchanged_since(self.root / "work", now - WORK_GRACE)
        outputs = (
            []
            if self.retention_days == 0
            else _unchanged_since(
                self.root / "runs", now - timedelta(days=self.retention_days)
            )
        )
        if dry_run:
            return FilesCleaned(len(work), len(outputs))
        removed = {"work": 0, "outputs": 0}
        failed = 0
        for kind, folders in (("work", work), ("outputs", outputs)):
            for folder in folders:
                outcome = _remove(folder)
                if outcome is True:
                    removed[kind] += 1
                elif outcome is False:
                    failed += 1
        return FilesCleaned(removed["work"], removed["outputs"], failed)

    def output_path(self, run_id: str, name: str) -> Path:
        """Path of the output ``name`` of ``run_id``.

        Raises:
            NotFound: The run has no such output.
        """
        try:
            path = self.root / "runs" / run_id / checked_name(name)
        except InvalidInput:
            raise NotFound("File not found", {"name": name}) from None
        if not path.is_file():
            raise NotFound("File not found", {"name": name})
        return path

    def check_source(self, source: FileSource, caller: Caller | None) -> None:
        """Refuse at once a source that the run could not read.

        Raises:
            InvalidInput: A local path from a caller, a URL that is not ``https`` or
                not of an allowed host, a file size over the limit, or an extension
                not allowed.
        """
        if source.path is not None and caller is not None:
            raise InvalidInput(
                "Local paths are accepted only from trusted code", {"name": source.name}
            )
        if source.url is not None:
            self._check_url(httpx2.URL(str(source.url)), source.name)
        if source.size is not None and source.size > self.max_bytes:
            raise FileTooLarge(
                f"The file is larger than {self.max_bytes} bytes",
                {"name": source.name, "max_bytes": self.max_bytes},
            )
        extension = Path(source.name).suffix.lower()
        if extension not in self.allowed_extensions:
            raise InvalidInput(
                f"Files of type {extension or '(none)'!r} are not accepted",
                {"name": source.name, "allowed": sorted(self.allowed_extensions)},
            )

    def _check_url(self, url: httpx2.URL, name: str) -> None:
        # The URL is not repeated in errors: it may carry a temporary signature.
        if url.scheme != "https" or url.host.lower() not in self.allowed_hosts:
            raise InvalidInput(
                "Files are downloaded only with https from an allowed host",
                {"name": name},
            )


class FilesCleaned(NamedTuple):
    """Folders of files removed by a cleanup, or that would be with a dry run."""

    work: int
    outputs: int
    failed: int = 0


def _unchanged_since(parent: Path, before: datetime) -> list[Path]:
    """The folders of ``parent`` with nothing changed in them after ``before``."""
    try:
        entries = list(parent.iterdir())
    except FileNotFoundError:
        return []
    limit = before.timestamp()
    found = []
    for folder in entries:
        changed = _last_change(folder) if folder.is_dir() else None
        if changed is not None and changed < limit:
            found.append(folder)
    return found


def _last_change(folder: Path) -> float | None:
    """Time of the last change in ``folder``, or ``None`` if it disappears meanwhile,
    for example because its run ends and removes it."""
    try:
        latest = folder.stat().st_mtime
        for item in folder.rglob("*"):
            latest = max(latest, item.stat().st_mtime)
    except FileNotFoundError:
        return None
    return latest


def _remove(folder: Path) -> bool | None:
    """Remove ``folder``: ``True`` if removed, ``False`` if it could not be, ``None``
    if it had already disappeared."""
    errors: list[str] = []

    def failure(function: Callable[..., Any], path: str, exc: BaseException) -> None:
        if not isinstance(exc, FileNotFoundError):
            errors.append(type(exc).__name__)

    if not folder.exists():
        return None
    shutil.rmtree(folder, onexc=failure)
    if errors or folder.exists():
        logger.warning(
            "Folder of files not removed: %s (%s)",
            folder,
            ", ".join(sorted(set(errors))) or "still present",
        )
        return False
    return True


def _names(value: str) -> frozenset[str]:
    return frozenset(item.strip().lower() for item in value.split(",") if item.strip())


def file_sources(value: Any) -> Iterator[FileSource]:
    """The file sources inside an input: in fields, lists and mappings, at any depth."""
    if isinstance(value, FileSource):
        yield value
    elif isinstance(value, BaseModel):
        for name in type(value).model_fields:
            yield from file_sources(getattr(value, name))
    elif isinstance(value, dict):
        for item in value.values():
            yield from file_sources(item)
    elif isinstance(value, list | tuple | set | frozenset):
        for item in value:
            yield from file_sources(item)


def check_sources(
    store: FileStore | None, payload: BaseModel, caller: Caller | None
) -> None:
    """Check the file sources of an input before the run is accepted.

    Raises:
        Unavailable: The input has files and no file store is configured.
        InvalidInput: See :meth:`FileStore.check_source`.
        FileTooLarge: A declared size is over the limit.
    """
    for source in file_sources(payload):
        if store is None:
            raise Unavailable("Files are not configured: set BREVIA_FILES_ROOT")
        store.check_source(source, caller)


@dataclass
class _Local:
    """The local copy of a source: its path, chosen before any wait, and its lock."""

    path: Path
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    ready: bool = False


class RunFiles:
    """The files of one run, available to its activity as ``ctx.files``.

    Work done in threads (copies of local paths, outputs written by a function) cannot
    be stopped: when the run is cancelled or times out, Brevia waits for it to end
    before it removes the work folder, and an output whose run has ended is not
    published.
    """

    def __init__(self, store: FileStore | None, run_id: str) -> None:
        self._store = store
        self._run_id = run_id
        self._local: dict[FileSource, _Local] = {}
        self._threads: set[asyncio.Task[Any]] = set()
        self._downloads: set[asyncio.Task[None]] = set()
        self._closed = False

    def _configured(self) -> FileStore:
        if self._store is None:
            raise Unavailable("Files are not configured: set BREVIA_FILES_ROOT")
        if self._closed:
            raise RuntimeError("The run has ended: its files can no longer be used")
        return self._store

    @property
    def _work(self) -> Path:
        return self._configured().root / "work" / self._run_id

    async def _in_thread[T](self, work: Callable[[], T]) -> T:
        """Run ``work`` in a thread that a cancellation of the run does not abandon.

        The cancellation reaches the caller at once; the thread goes on until it ends,
        and :meth:`close` waits for it.
        """
        task = asyncio.ensure_future(asyncio.to_thread(work))
        self._threads.add(task)
        task.add_done_callback(self._threads.discard)
        return await asyncio.shield(task)

    async def local_path(self, source: FileSource) -> Path:
        """Path of a local copy of ``source``, valid until the run ends.

        The file is downloaded, or copied from a local path, once per run, also when
        it is asked by concurrent calls; its size, type and, when given, fingerprint
        are checked. Two sources with the same name get two different paths. Do not
        modify the file.

        Raises:
            Unavailable: Files are not configured, or the host cannot be reached or
                answered with a server error (worth retrying).
            InvalidInput: The source is not allowed, the server refused the file,
                or its content differs from the declared size or fingerprint.
            FileTooLarge: The file is larger than allowed.
        """
        store = self._configured()
        store.check_source(source, None)
        local = self._local.get(source)
        if local is None:
            # Chosen before any wait, so that concurrent calls never share a path.
            local = _Local(self._work / str(len(self._local)) / source.name)
            self._local[source] = local
        async with local.lock:
            if not local.ready:
                local.path.parent.mkdir(parents=True, exist_ok=True)
                if source.path is not None:
                    path = source.path
                    await self._in_thread(lambda: self._copy(source, path, local.path))
                else:
                    await self._tracked_download(source, local.path)
                local.ready = True
        return local.path

    async def read(self, source: FileSource) -> Document:
        """Text of ``source`` with its structure, read in a thread.

        The file is obtained as with :meth:`local_path`, then read with
        :func:`brevia.read_document`; the document takes the name of the source.

        Raises:
            Unavailable: As for :meth:`local_path`.
            InvalidInput: As for :meth:`local_path`, or the file cannot be read.
            FileTooLarge: The file is larger than allowed.
            Unsupported: The extension is not a readable format.
        """
        # Checked first, so that a file that cannot be read is not downloaded.
        check_readable(source.name)
        path = await self.local_path(source)
        return await self._in_thread(lambda: read_document(path, name=source.name))

    def _copy(self, source: FileSource, path: Path, target: Path) -> None:
        try:
            stream = path.open("rb")
        except OSError:
            raise NotFound("Input file not found", {"name": source.name}) from None
        with stream, _Checked(self._configured(), source, target) as checked:
            for chunk in iter(lambda: stream.read(CHUNK), b""):
                checked.add(chunk)

    async def _tracked_download(self, source: FileSource, target: Path) -> None:
        """Download in a task that :meth:`close` cancels and waits for, also when the
        caller does not wait for it (for example a ``gather`` that ended early)."""
        task = asyncio.ensure_future(self._download(source, target))
        self._downloads.add(task)
        task.add_done_callback(self._downloads.discard)
        await task

    async def _download(self, source: FileSource, target: Path) -> None:
        store = self._configured()
        url = httpx2.URL(str(source.url))
        try:
            async with httpx2.AsyncClient(
                transport=_transport,
                follow_redirects=False,
                timeout=httpx2.Timeout(DOWNLOAD_TIMEOUT),
            ) as client:
                for _ in range(MAX_REDIRECTS + 1):
                    store._check_url(url, source.name)
                    async with client.stream("GET", url) as response:
                        if response.is_redirect:
                            location = response.headers.get("location")
                            if not location:
                                break
                            url = url.join(location)
                            continue
                        _check_status(response.status_code, source.name)
                        with _Checked(store, source, target) as checked:
                            async for chunk in response.aiter_bytes(CHUNK):
                                checked.add(chunk)
                        return
        except httpx2.HTTPError as exc:
            raise Unavailable(
                "The file cannot be downloaded",
                {"name": source.name, "cause": cause_types(exc)},
            ) from None
        raise InvalidInput(
            "The file cannot be downloaded: too many redirects, or one without a "
            "location",
            {"name": source.name},
        )

    async def save(
        self,
        name: str,
        content: bytes | Callable[[Path], None],
        *,
        mime: str | None = None,
    ) -> FileRef:
        """Save an output of the run and return its reference.

        ``content`` is the bytes of the file, or a function that writes the file at
        the path it receives (for libraries that save to a path); it runs in a
        thread. The file replaces any earlier output with the same name, at once:
        readers see the old file or the new one, never a partial one. If the run is
        cancelled or times out while the file is written, the file is not published.

        Raises:
            Unavailable: Files are not configured.
            InvalidInput: ``name`` is not a single valid file name.
        """
        folder = self._configured().root / "runs" / self._run_id
        checked_name(name)
        partial, digest, size = await self._in_thread(
            lambda: _write_partial(folder, content)
        )
        if self._closed:  # the run ended while the thread wrote: do not publish
            partial.unlink(missing_ok=True)
            raise RuntimeError("The run has ended: its files can no longer be used")
        os.replace(partial, folder / name)
        return FileRef(
            run_id=self._run_id,
            name=name,
            mime=mime or _mime(name),
            size=size,
            sha256=digest,
        )

    async def close(self) -> None:
        """End the files of the run: stop its downloads, wait for its threads, then
        remove the work folder and any output left unfinished. Called when the run
        ends.

        If the wait is cancelled too, what is left is removed by the daily cleanup.
        """
        self._closed = True
        for download in self._downloads:
            download.cancel()
        pending = self._downloads | self._threads
        if pending:
            await asyncio.wait(pending)
        self._local.clear()
        if self._store is None:
            return
        root = self._store.root
        shutil.rmtree(root / "work" / self._run_id, ignore_errors=True)
        for partial in (root / "runs" / self._run_id).glob(f"{PARTIAL_PREFIX}*"):
            partial.unlink(missing_ok=True)


def _write_partial(
    folder: Path, content: bytes | Callable[[Path], None]
) -> tuple[Path, str, int]:
    """Write an output apart, in ``folder``; return its path, fingerprint and size."""
    folder.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(dir=folder, prefix=PARTIAL_PREFIX)
    os.close(descriptor)
    partial = Path(name)
    try:
        if isinstance(content, bytes):
            partial.write_bytes(content)
        else:
            content(partial)
        digest, size = _digest(partial)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    return partial, digest, size


class _Checked:
    """A file written in a temporary path, moved to its target once checked."""

    def __init__(self, store: FileStore, source: FileSource, target: Path) -> None:
        self._store, self._source, self._target = store, source, target
        self._digest = hashlib.sha256()
        self._size = 0
        self._stream: BinaryIO

    def __enter__(self) -> Self:
        descriptor, self._partial = tempfile.mkstemp(
            dir=self._target.parent, prefix=PARTIAL_PREFIX
        )
        self._stream = os.fdopen(descriptor, "wb")
        return self

    def add(self, chunk: bytes) -> None:
        self._size += len(chunk)
        if self._size > self._store.max_bytes:
            raise FileTooLarge(
                f"The file is larger than {self._store.max_bytes} bytes",
                {"name": self._source.name, "max_bytes": self._store.max_bytes},
            )
        self._digest.update(chunk)
        self._stream.write(chunk)

    def __exit__(self, kind: type[BaseException] | None, *_: object) -> None:
        self._stream.close()
        try:
            if kind is None:
                self._verify()
                os.replace(self._partial, self._target)
        finally:
            if os.path.exists(self._partial):
                os.unlink(self._partial)

    def _verify(self) -> None:
        source = self._source
        if (source.size is not None and source.size != self._size) or (
            source.sha256 is not None and source.sha256 != self._digest.hexdigest()
        ):
            raise InvalidInput(
                "The content of the file differs from its declared size or fingerprint",
                {"name": source.name},
            )


def _check_status(status: int, name: str) -> None:
    if status < 400:
        return
    if status >= 500 or status in (408, 429):
        raise Unavailable(
            f"The file cannot be downloaded now (HTTP {status})",
            {"name": name, "status_code": status},
        )
    raise InvalidInput(
        f"The file cannot be downloaded (HTTP {status})",
        {"name": name, "status_code": status},
    )


def _digest(path: Path) -> tuple[str, int]:
    digest, size = hashlib.sha256(), 0
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(CHUNK), b""):
            digest.update(block)
            size += len(block)
    return digest.hexdigest(), size
