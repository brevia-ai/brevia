"""Files of runs: inputs downloaded from allowed hosts or copied, outputs saved.

Downloads go through a fake HTTP transport: no network is used.
"""

from __future__ import annotations

import asyncio
import errno
import hashlib
import logging
import os
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx2
import pytest
from conftest import project_brevia
from memory_store import MemoryStore
from pydantic import BaseModel, ValidationError
from summary_example import NoConfig

from brevia import (
    Brevia,
    Caller,
    FileRef,
    FileSource,
    FileStore,
    FileTooLarge,
    InvalidInput,
    NotFound,
    RunContext,
    RunFiles,
    Unavailable,
)
from brevia.files.retention import clean

pytestmark = pytest.mark.unit

HOST = "files.example.org"
CONTENT = b"%PDF-1.7 synthetic document"
DIGEST = hashlib.sha256(CONTENT).hexdigest()
SECRET_QUERY = "signature=temporary-secret"  # noqa: S105 - test data

Handler = Callable[[httpx2.Request], httpx2.Response]


def serve(routes: dict[str, httpx2.Response]) -> Handler:
    def handle(request: httpx2.Request) -> httpx2.Response:
        response = routes.get(f"{request.url.host}{request.url.path}")
        return response if response is not None else httpx2.Response(404)

    return handle


@pytest.fixture
def http(monkeypatch: pytest.MonkeyPatch) -> dict[str, httpx2.Response]:
    """Responses of the fake web by ``host/path``."""
    routes: dict[str, httpx2.Response] = {
        f"{HOST}/report.pdf": httpx2.Response(200, content=CONTENT)
    }
    monkeypatch.setattr(
        "brevia.files.files._transport", httpx2.MockTransport(serve(routes))
    )
    return routes


@pytest.fixture
def store(tmp_path: Path) -> FileStore:
    return FileStore(tmp_path / "files", allowed_hosts=frozenset({HOST}))


def source(path: str = "/report.pdf", host: str = HOST, **values: Any) -> FileSource:
    url = f"https://{host}{path}?{SECRET_QUERY}"
    return FileSource.model_validate({"name": "report.pdf", "url": url, **values})


# ---------- sources ----------


def test_a_source_has_either_a_url_or_a_path() -> None:
    for values in ({}, {"url": f"https://{HOST}/a.pdf", "path": "/data/a.pdf"}):
        with pytest.raises(ValidationError, match="either url or path"):
            FileSource.model_validate({"name": "a.pdf", **values})
    for name in ("", "../a.pdf", "a/b.pdf", "a\\b.pdf", "a\x00.pdf", ".."):
        with pytest.raises(ValidationError):
            FileSource(name=name, path=Path("/data/a.pdf"))
    with pytest.raises(ValidationError, match="sha256"):
        FileSource(name="a.pdf", path=Path("/data/a.pdf"), sha256="ABC")


@pytest.mark.parametrize(
    ("bad", "error"),
    [
        (source(host="evil.example.org"), InvalidInput),
        (
            FileSource.model_validate({"name": "r.pdf", "url": f"http://{HOST}/r"}),
            InvalidInput,
        ),
        (source(name="script.sh"), InvalidInput),
        (source(size=51 * 1024 * 1024), FileTooLarge),
    ],
)
def test_sources_that_cannot_be_read_are_refused_at_once(
    store: FileStore, bad: FileSource, error: type[Exception]
) -> None:
    with pytest.raises(error) as caught:
        store.check_source(bad, None)
    assert SECRET_QUERY not in str(caught.value.to_dict())  # type: ignore[attr-defined]


def test_local_paths_are_only_for_trusted_code(store: FileStore) -> None:
    local = FileSource(name="report.pdf", path=Path("/data/report.pdf"))
    store.check_source(local, None)
    with pytest.raises(InvalidInput, match="trusted code"):
        store.check_source(local, Caller("backend"))


# ---------- downloads ----------


async def test_a_download_is_checked_and_kept_until_the_run_ends(
    store: FileStore, http: dict[str, httpx2.Response]
) -> None:
    files = RunFiles(store, "run-1")
    wanted = source(sha256=DIGEST, size=len(CONTENT))
    path = await files.local_path(wanted)
    assert path.read_bytes() == CONTENT
    assert path.name == "report.pdf"  # readers that need the extension find it
    assert path.is_relative_to(store.root / "work" / "run-1")
    del http[f"{HOST}/report.pdf"]
    assert await files.local_path(wanted) == path  # once per run
    await files.close()
    assert not (store.root / "work" / "run-1").exists()


async def test_redirects_are_followed_only_to_allowed_hosts(
    store: FileStore, http: dict[str, httpx2.Response]
) -> None:
    http[f"{HOST}/moved.pdf"] = httpx2.Response(
        302, headers={"location": "/report.pdf"}
    )
    http[f"{HOST}/away.pdf"] = httpx2.Response(
        302, headers={"location": "https://evil.example.org/report.pdf"}
    )
    http[f"{HOST}/nowhere.pdf"] = httpx2.Response(302)
    http[f"{HOST}/loop.pdf"] = httpx2.Response(302, headers={"location": "/loop.pdf"})
    files = RunFiles(store, "run-1")
    assert (await files.local_path(source("/moved.pdf"))).read_bytes() == CONTENT
    for path in ("/away.pdf", "/nowhere.pdf", "/loop.pdf"):
        with pytest.raises(InvalidInput):
            await files.local_path(source(path))


@pytest.mark.parametrize(
    ("values", "error"),
    [
        ({"sha256": "0" * 64}, InvalidInput),
        ({"size": len(CONTENT) + 1}, InvalidInput),
        ({}, FileTooLarge),
    ],
)
async def test_a_download_that_does_not_match_leaves_no_file(
    tmp_path: Path,
    http: dict[str, httpx2.Response],
    values: dict[str, Any],
    error: type[Exception],
) -> None:
    limit = len(CONTENT) - 1 if error is FileTooLarge else 1024
    store = FileStore(tmp_path, max_bytes=limit, allowed_hosts=frozenset({HOST}))
    with pytest.raises(error):
        await RunFiles(store, "run-1").local_path(source(**values))
    assert [p for p in (tmp_path / "work").rglob("*") if p.is_file()] == []


@pytest.mark.parametrize(
    ("status", "error", "retryable"),
    [(404, InvalidInput, False), (403, InvalidInput, False), (503, Unavailable, True)],
)
async def test_server_errors_are_retryable_and_refusals_are_not(
    store: FileStore,
    http: dict[str, httpx2.Response],
    status: int,
    error: type[Exception],
    retryable: bool,
) -> None:
    http[f"{HOST}/report.pdf"] = httpx2.Response(status)
    with pytest.raises(error) as caught:
        await RunFiles(store, "run-1").local_path(source())
    assert caught.value.retryable is retryable  # type: ignore[attr-defined]
    assert SECRET_QUERY not in str(caught.value.to_dict())  # type: ignore[attr-defined]


async def test_an_unreachable_host_is_unavailable(
    store: FileStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError(f"cannot connect to {request.url}")

    monkeypatch.setattr("brevia.files.files._transport", httpx2.MockTransport(refuse))
    with pytest.raises(Unavailable) as caught:
        await RunFiles(store, "run-1").local_path(source())
    assert caught.value.retryable
    assert SECRET_QUERY not in str(caught.value.to_dict())
    assert caught.value.__cause__ is None


async def test_a_local_path_is_copied_and_checked(
    store: FileStore, tmp_path: Path
) -> None:
    original = tmp_path / "report.pdf"
    original.write_bytes(CONTENT)
    files = RunFiles(store, "run-1")
    path = await files.local_path(FileSource(name="report.pdf", path=original))
    assert path != original
    assert path.read_bytes() == CONTENT
    with pytest.raises(NotFound):
        await files.local_path(FileSource(name="a.pdf", path=tmp_path / "missing"))


async def test_without_a_file_store_files_are_unavailable() -> None:
    files = RunFiles(None, "run-1")
    with pytest.raises(Unavailable, match="BREVIA_FILES_ROOT"):
        await files.local_path(source())
    with pytest.raises(Unavailable):
        await files.save("out.txt", b"x")
    await files.close()  # nothing to remove


async def test_logged_urls_keep_no_query(
    store: FileStore,
    http: dict[str, httpx2.Response],
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="httpx2"):
        await RunFiles(store, "run-1").local_path(source())
    assert f"https://{HOST}/report.pdf" in caplog.text  # the request is still logged
    assert SECRET_QUERY not in caplog.text


async def test_a_redirect_to_an_invalid_url_is_a_failure_of_the_server(
    store: FileStore, http: dict[str, httpx2.Response]
) -> None:
    # httpx2 refuses the malformed location itself (a protocol error), so the run
    # gets a Brevia error, not an internal one.
    http[f"{HOST}/broken.pdf"] = httpx2.Response(
        302, headers={"location": "http://[::1"}
    )
    with pytest.raises(Unavailable) as caught:
        await RunFiles(store, "run-1").local_path(source("/broken.pdf"))
    assert caught.value.retryable


async def test_a_download_left_running_is_stopped_when_the_run_ends(
    store: FileStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    started, finished = asyncio.Event(), asyncio.Event()

    async def respond(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/slow.pdf":
            started.set()
            await asyncio.sleep(30)
            finished.set()
        return httpx2.Response(404)

    monkeypatch.setattr("brevia.files.files._transport", httpx2.MockTransport(respond))
    files = RunFiles(store, "run-1")
    # One read fails at once; the activity ends without waiting for the other.
    slow = asyncio.ensure_future(files.local_path(source("/slow.pdf")))
    with pytest.raises(InvalidInput):
        await files.local_path(source("/missing.pdf"))
    await started.wait()
    await asyncio.wait_for(files.close(), 5)
    assert slow.cancelled() or isinstance(slow.exception(), asyncio.CancelledError)
    assert not finished.is_set()
    assert not (store.root / "work" / "run-1").exists()


async def test_concurrent_reads_get_their_own_files(
    store: FileStore, http: dict[str, httpx2.Response]
) -> None:
    http[f"{HOST}/a/report.pdf"] = httpx2.Response(200, content=b"first")
    http[f"{HOST}/b/report.pdf"] = httpx2.Response(200, content=b"second")
    files = RunFiles(store, "run-1")
    first, second = await asyncio.gather(
        files.local_path(source("/a/report.pdf")),
        files.local_path(source("/b/report.pdf")),
    )
    assert first != second  # the same name, two files
    assert (first.read_bytes(), second.read_bytes()) == (b"first", b"second")


async def test_concurrent_reads_of_one_source_download_it_once(
    store: FileStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    requests: list[str] = []

    def count(request: httpx2.Request) -> httpx2.Response:
        requests.append(request.url.path)
        return httpx2.Response(200, content=CONTENT)

    monkeypatch.setattr("brevia.files.files._transport", httpx2.MockTransport(count))
    files = RunFiles(store, "run-1")
    paths = await asyncio.gather(*(files.local_path(source()) for _ in range(3)))
    assert len(set(paths)) == 1
    assert requests == ["/report.pdf"]


# ---------- outputs ----------


async def test_outputs_are_saved_with_their_fingerprint_and_replaced_by_name(
    store: FileStore,
) -> None:
    files = RunFiles(store, "run-1")
    first = await files.save("report.md", b"first")
    assert first == FileRef(
        run_id="run-1",
        name="report.md",
        mime="text/markdown",
        size=5,
        sha256=hashlib.sha256(b"first").hexdigest(),
    )

    # A job that starts again saves the same name: the file is replaced, not doubled.
    def write(path: Path) -> None:
        path.write_bytes(b"second")

    second = await files.save("report.md", write)
    assert second.size == 6
    folder = store.root / "runs" / "run-1"
    assert [p.name for p in folder.iterdir()] == ["report.md"]
    assert store.output_path("run-1", "report.md").read_bytes() == b"second"
    assert (await files.save("x.bin", b"", mime="application/x-test")).mime == (
        "application/x-test"
    )


async def test_a_failed_writer_leaves_the_earlier_output(store: FileStore) -> None:
    files = RunFiles(store, "run-1")
    await files.save("report.md", b"first")

    def broken(path: Path) -> None:
        path.write_bytes(b"half")
        raise RuntimeError("writer failed")

    with pytest.raises(RuntimeError):
        await files.save("report.md", broken)
    folder = store.root / "runs" / "run-1"
    assert [p.name for p in folder.iterdir()] == ["report.md"]
    assert (folder / "report.md").read_bytes() == b"first"


async def test_an_output_written_while_the_run_ends_is_not_published(
    store: FileStore,
) -> None:
    files = RunFiles(store, "run-1")
    started, release = threading.Event(), threading.Event()

    def slow(path: Path) -> None:
        started.set()
        release.wait(5)
        path.write_bytes(b"late")

    saving = asyncio.ensure_future(files.save("report.md", slow))
    await asyncio.to_thread(started.wait, 5)
    saving.cancel()  # the run is cancelled, or times out, while the thread writes
    with pytest.raises(asyncio.CancelledError):
        await saving
    closing = asyncio.ensure_future(files.close())
    await asyncio.sleep(0.05)
    assert not closing.done()  # waits for the thread before removing anything
    release.set()
    await closing
    folder = store.root / "runs" / "run-1"
    assert list(folder.iterdir()) == []  # neither published nor left partial
    with pytest.raises(RuntimeError, match="has ended"):
        await files.save("report.md", b"after")


@pytest.mark.parametrize("name", ["", "../x", "a/b", "..", "a\x00", ".partial-x"])
async def test_output_names_are_single_names(store: FileStore, name: str) -> None:
    with pytest.raises(InvalidInput):
        await RunFiles(store, "run-1").save(name, b"x")
    with pytest.raises(NotFound):
        store.output_path("run-1", name)


# ---------- in a run ----------


class CopyRequest(BaseModel):
    document: FileSource


class CopyResult(BaseModel):
    output: FileRef
    work: str


async def copy_document(request: CopyRequest, ctx: RunContext) -> CopyResult:
    path = await ctx.files.local_path(request.document)
    ref = await ctx.files.save(f"copy-{request.document.name}", path.read_bytes())
    return CopyResult(output=ref, work=path.parent.parent.name)


async def copy_then_fail(request: CopyRequest, ctx: RunContext) -> CopyResult:
    await ctx.files.local_path(request.document)
    raise InvalidInput("the document is not a report")


def register(app: Brevia) -> None:
    for name, function in (("test.copy", copy_document), ("test.fail", copy_then_fail)):
        app.register_activity(
            name=name,
            version="1",
            function=function,
            input_type=CopyRequest,
            output_type=CopyResult,
            config_type=NoConfig,
        )


async def test_a_run_reads_its_inputs_and_keeps_only_its_outputs(
    tmp_path: Path, store: FileStore, http: dict[str, httpx2.Response]
) -> None:
    async with project_brevia(tmp_path, MemoryStore(), files=store) as app:
        register(app)
        result = await app.run("test.copy", {"document": source().model_dump()})
        assert isinstance(result, CopyResult)
        assert result.output.sha256 == DIGEST
        assert result.work == result.output.run_id
        work = store.root / "work"
        assert list(work.iterdir()) == []  # inputs are not kept
        output = store.output_path(result.output.run_id, "copy-report.pdf")
        assert output.read_bytes() == CONTENT
        with pytest.raises(InvalidInput):
            await app.run("test.fail", {"document": source().model_dump()})
        assert list((store.root / "work").iterdir()) == []


async def test_a_run_refuses_inputs_it_could_not_read(
    tmp_path: Path, store: FileStore
) -> None:
    async with project_brevia(tmp_path, MemoryStore(), files=store) as app:
        register(app)
        local = {"name": "report.pdf", "path": str(tmp_path / "report.pdf")}
        with pytest.raises(InvalidInput, match="trusted code"):
            await app.run("test.copy", {"document": local}, caller=Caller("backend"))
        far = source(host="evil.example.org").model_dump()
        with pytest.raises(InvalidInput):
            await app.run("test.copy", {"document": far})
    async with project_brevia(tmp_path, MemoryStore()) as app:
        register(app)
        with pytest.raises(Unavailable, match="BREVIA_FILES_ROOT"):
            await app.run("test.copy", {"document": source().model_dump()})


# ---------- cleanup ----------

NOW = datetime(2026, 10, 16, 3, 0, tzinfo=UTC)


def folder(
    parent: Path, name: str, days_ago: float, inside: float | None = None
) -> Path:
    """A folder with one file, changed ``days_ago`` (the file ``inside`` days ago)."""
    path = parent / name
    path.mkdir(parents=True)
    item = path / "file.bin"
    item.write_bytes(b"x")
    for target, age in (
        (item, days_ago if inside is None else inside),
        (path, days_ago),
    ):
        stamp = (NOW - timedelta(days=age)).timestamp()
        os.utime(target, (stamp, stamp))
    return path


def test_the_cleanup_removes_leftover_work_and_expired_outputs(tmp_path: Path) -> None:
    store = FileStore(tmp_path, retention_days=30)
    folder(tmp_path / "work", "stopped", 2)
    folder(tmp_path / "work", "running", 0.5)
    folder(tmp_path / "work", "touched", 3, inside=0.1)  # a file changed recently
    folder(tmp_path / "runs", "expired", 31)
    folder(tmp_path / "runs", "kept", 29)
    assert store.clean(NOW, dry_run=True) == (1, 1, 0)
    assert len(list((tmp_path / "work").iterdir())) == 3  # a dry run removes nothing
    assert store.clean(NOW) == (1, 1, 0)
    assert sorted(p.name for p in (tmp_path / "work").iterdir()) == [
        "running",
        "touched",
    ]
    assert [p.name for p in (tmp_path / "runs").iterdir()] == ["kept"]
    assert FileStore(tmp_path / "empty").clean(NOW) == (0, 0, 0)


def test_outputs_may_be_kept_without_limit(tmp_path: Path) -> None:
    folder(tmp_path / "work", "stopped", 2)
    folder(tmp_path / "runs", "old", 3650)
    # Inputs are temporary copies: their leftovers go also when outputs are kept.
    assert FileStore(tmp_path, retention_days=0).clean(NOW) == (1, 0, 0)
    assert (tmp_path / "runs" / "old").exists()


async def test_the_daily_cleanup_includes_the_files(tmp_path: Path) -> None:
    store = FileStore(tmp_path, retention_days=7)
    folder(tmp_path / "runs", "expired", 8)
    cleaned = await clean(MemoryStore(), None, 30, now=NOW, files=store)
    assert (cleaned.work_folders, cleaned.output_folders) == (0, 1)
    assert not (tmp_path / "runs" / "expired").exists()


def test_a_folder_that_disappears_during_the_scan_is_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gone = folder(tmp_path / "work", "ending", 2)
    folder(tmp_path / "work", "stopped", 2)
    stat = Path.stat

    def vanishing(path: Path, *args: Any, **kwargs: Any) -> os.stat_result:
        if path != gone and path.is_relative_to(gone):  # its run ends meanwhile
            raise FileNotFoundError(errno.ENOENT, "No such file", str(path))
        return stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", vanishing)
    assert FileStore(tmp_path).clean(NOW) == (1, 0, 0)
    monkeypatch.undo()
    assert [p.name for p in (tmp_path / "work").iterdir()] == ["ending"]


@pytest.mark.skipif(os.geteuid() == 0, reason="root removes files without permission")
async def test_a_folder_that_cannot_be_removed_is_counted_and_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    locked = folder(tmp_path / "runs", "locked", 40)
    folder(tmp_path / "runs", "expired", 40)
    locked.chmod(0o500)  # its file cannot be deleted
    try:
        with caplog.at_level(logging.WARNING):
            cleaned = await clean(
                MemoryStore(), None, 30, now=NOW, files=FileStore(tmp_path)
            )
    finally:
        locked.chmod(0o700)
    assert (cleaned.output_folders, cleaned.files_failed) == (1, 1)
    assert locked.exists()
    assert not (tmp_path / "runs" / "expired").exists()
    assert "Folder of files not removed" in caplog.text
    assert "1 folders not removed" in caplog.text
