"""The :class:`Brevia` application object: lifecycle, activity registration and runs."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any, Self

from pydantic import BaseModel, ValidationError

from brevia.access.access import AccessPolicy, Caller
from brevia.config.configuration import (
    path_in_schema,
    unknown_fields,
)
from brevia.config.customization import (
    ConfigurationState,
    PromptRevision,
    PromptState,
    checked_prompt_text,
    configuration_state,
    prompt_state,
    reset_values,
    revision,
    sha256,
    template_of,
    updated_values,
)
from brevia.config.project import ProjectSettings, load_project
from brevia.config.prompts import load_prompt
from brevia.config.settings import BreviaSettings
from brevia.db.customizations import NO_PROMPT
from brevia.db.feedback import FeedbackRecord
from brevia.db.jobs import JobStatus
from brevia.db.runs import NewRun
from brevia.db.store import SqlStore, Store
from brevia.db.values import storable_json
from brevia.errors import (
    BreviaError,
    Forbidden,
    IdempotencyConflict,
    InvalidInput,
    NotFound,
    Unavailable,
    Unsupported,
    validation_details,
)
from brevia.files.files import FileStore, check_sources
from brevia.jobs.backend import DbosBackend, JobBackend
from brevia.jobs.handle import JobPage, JobState, RunHandle
from brevia.jobs.runtime import JobRuntime
from brevia.jobs.service import JobService
from brevia.models import fake
from brevia.models.limits import RunLimits
from brevia.models.providers import hold_providers, release_providers
from brevia.models.spec import ModelSpec, check_capabilities
from brevia.runs.activities import NAME, Activity, ActivityFunction, Capture, Mode
from brevia.runs.context import RunContext
from brevia.runs.execution import (
    Executor,
    check_key,
    recorded_input,
    recorded_snapshot,
    resolved,
    snapshot,
    validated_input,
)
from brevia.runs.feedback import Correction, Feedback, FeedbackRequest

logger = logging.getLogger(__name__)

_MODES: frozenset[Mode] = frozenset({"direct", "job"})


def _check_importable(name: str, *types: type[BaseModel]) -> None:
    """Refuse types that a job cannot record: its steps are pickled by reference.

    Raises:
        ValueError: A type is defined inside a function.
    """
    local = [t.__qualname__ for t in types if "<locals>" in t.__qualname__]
    if local:
        raise ValueError(
            f"Activity {name!r} supports jobs: its input, output and configuration "
            f"types must be defined at module level, not {local}"
        )


class Brevia:
    """Entry point of a project that uses Brevia.

    Applications create it with :meth:`from_settings`, register their activities and
    start it with :meth:`start` (or ``async with``) before running them.

    Args:
        project: Validated project settings.
        project_dir: Directory against which prompt paths are resolved.
        store: Store of the records in the database; internal, chosen by
            :meth:`from_settings`.
        record_direct_runs: Record each direct run and its model calls.
        jobs: Durable state of jobs; internal, chosen by :meth:`from_settings`.
            Without it, activities can only run directly.
        app_version: Version of the application, recorded in the snapshot of each
            run; ``BREVIA_APP_VERSION`` with :meth:`from_settings`.
        access: Which runs a caller may read and act on, and who may change
            customisations; ``per-caller`` without administrators by default,
            ``BREVIA_ACCESS_POLICY`` and ``BREVIA_ACCESS_ADMINS`` with
            :meth:`from_settings`.
        files: Where the files of runs are kept, and which inputs are accepted;
            ``BREVIA_FILES_*`` with :meth:`from_settings`. Without it, runs cannot
            use files.
    """

    def __init__(
        self,
        project: ProjectSettings,
        *,
        project_dir: Path,
        store: Store,
        record_direct_runs: bool = True,
        jobs: JobBackend | None = None,
        app_version: str | None = None,
        access: AccessPolicy | None = None,
        files: FileStore | None = None,
    ) -> None:
        self.project = project
        self.access = access or AccessPolicy()
        self.files = files
        self.app_version = app_version
        self.project_dir = project_dir
        self._store = store
        self._record_direct_runs = record_direct_runs
        self._jobs_backend = jobs
        self._activities: dict[str, Activity] = {}
        # Runs prepared by direct runs and jobs; its outcome writes are awaited by
        # stop().
        self._executor = Executor(store)
        # The only view of this instance that the job modules use.
        self._job_runtime = (
            None
            if jobs is None
            else JobRuntime(
                project=project,
                store=store,
                executor=self._executor,
                backend=jobs,
                activity=self._activity,
                check_started=self._check_started,
                access=self.access,
                files=files,
            )
        )
        self._jobs = (
            None if self._job_runtime is None else JobService(self._job_runtime)
        )
        self._jobs_started = False
        self._holds_providers = False
        self._started = False
        # start() and stop() wait on each other, so that one engine exists at most.
        self._lifecycle = asyncio.Lock()

    @classmethod
    def from_settings(cls, settings: BreviaSettings | None = None) -> Brevia:
        """Create Brevia from the installation settings and the project file.

        Settings are read from the environment and ``.env`` when not given. Prompt
        paths are resolved from the directory of the project file. The database is
        not contacted until :meth:`start`. Logging is not configured here: the
        application calls :func:`brevia.configure_logging`.

        With ``BREVIA_FAKE_MODELS=true``, a fake answers every model call of the
        process with an output generated from the schema, and no provider is called
        (see :mod:`brevia.testing`).

        Raises:
            pydantic.ValidationError: The settings are missing or not valid, for
                example without ``BREVIA_DATABASE_URL``.
            Unavailable: The project file cannot be read or is not valid.
        """
        # Required settings come from the environment, which mypy cannot see.
        settings = settings or BreviaSettings()  # type: ignore[call-arg]
        if settings.fake_models:
            fake.install_default(fake.from_schema())
            logger.warning("Fake models in use: no model provider is called")
        path = settings.project_file.resolve()
        return cls(
            load_project(path),
            project_dir=path.parent,
            store=SqlStore(settings),
            record_direct_runs=settings.record_direct_runs,
            jobs=DbosBackend.from_settings(settings),
            app_version=settings.app_version,
            access=AccessPolicy.from_names(
                settings.access_policy, settings.access_admins
            ),
            files=FileStore.from_settings(settings),
        )

    async def start(self) -> None:
        """Connect to the database and check that its schema is migrated.

        Migrations are not applied here: they are an explicit step of a release,
        ``brevia db upgrade``. When an activity supports jobs, the state of jobs is
        checked too: register activities before starting.

        Raises:
            RuntimeError: Brevia is already started.
            Unavailable: The database cannot be reached or its schema is not at the
                revision of this version of Brevia.
        """
        async with self._lifecycle:
            if self._started:
                raise RuntimeError("Brevia is already started")
            await self._store.start()
            backend = self._jobs_backend
            if backend is not None and any(
                "job" in a.modes for a in self._activities.values()
            ):
                try:
                    await backend.start()
                except BaseException:
                    await self._store.stop()
                    raise
                self._jobs_started = True
            hold_providers()
            self._holds_providers = True
            self._started = True

    async def stop(self) -> None:
        """Close the database and model provider connections. Calling it again does
        nothing.

        New runs are refused at once; outcome writes already under way are awaited.
        Call it when runs have ended: a run still in progress cannot record its
        outcome and fails with ``Unavailable``.
        """
        async with self._lifecycle:
            self._started = False
            await self._executor.drain()
            try:
                if self._jobs_started and self._jobs_backend is not None:
                    self._jobs_started = False
                    await self._jobs_backend.stop()
            finally:
                try:
                    if self._holds_providers:
                        self._holds_providers = False
                        await release_providers()
                finally:
                    await self._store.stop()

    async def check(self) -> None:
        """Check, now, that Brevia is started and its database answers with the
        migrated schema: the readiness of an application, as used by
        ``GET /health/ready``.

        Raises:
            Unavailable: Brevia is not started, the database cannot be reached or
                its schema is not at the revision of this version of Brevia.
        """
        if not self._started:
            raise Unavailable("Brevia is not started")
        await self._store.check()

    def _check_started(self) -> None:
        if not self._started:
            raise RuntimeError("Brevia is not started: call `await brevia.start()`")

    def _check_customizer(self, caller: Caller | None) -> None:
        if not self.access.allows_everything(caller):
            raise Forbidden("Only administrators may change customisations")

    # ---------- customisations ----------

    async def configuration(self, activity: str) -> ConfigurationState:
        """Configuration of an activity: defaults, customisation and effective values.

        Raises:
            RuntimeError: Brevia is not started.
            NotFound: The activity is not registered.
            Unavailable: The database cannot be read.
        """
        self._check_started()
        registered = self._activity(activity)
        custom = await self._store.customizations(activity)
        return configuration_state(registered, custom.configuration)

    async def customize_configuration(
        self,
        activity: str,
        values: Mapping[str, Any],
        *,
        expected_version: int | None = None,
        author: str | None = None,
        caller: Caller | None = None,
    ) -> ConfigurationState:
        """Customise some fields of the configuration of an activity.

        The given fields are set and the others keep their customisation; nested
        models are composed field by field. The change applies to the next runs.

        Args:
            activity: Name of the activity.
            values: Values by field name, on customisable paths only.
            expected_version: Version read before the change; when given, the change
                is refused if the customisation was changed meanwhile.
            author: Who makes the change, recorded with it.
            caller: The application that asks for the change; under the
                ``per-caller`` policy only administrators may make it.

        Raises:
            RuntimeError: Brevia is not started.
            Forbidden: The access policy does not let ``caller`` change
                customisations.
            NotFound: The activity is not registered.
            InvalidInput: Unknown or non-customisable fields, or values that make the
                configuration invalid.
            VersionConflict: ``expected_version`` is no longer current.
            Unavailable: The database cannot be used.
        """
        self._check_started()
        self._check_customizer(caller)
        registered = self._activity(activity)
        stored = await self._store.save_configuration(
            activity,
            lambda current: updated_values(registered, current, values),
            expected_version=expected_version,
            author=author,
            now=datetime.now(UTC),
        )
        return configuration_state(registered, stored)

    async def reset_configuration(
        self,
        activity: str,
        fields: Iterable[str] | None = None,
        *,
        expected_version: int | None = None,
        author: str | None = None,
        caller: Caller | None = None,
    ) -> ConfigurationState:
        """Return some fields, or the whole configuration, to the project defaults.

        Args:
            activity: Name of the activity.
            fields: Dotted paths to reset; all of them when not given.
            expected_version: Version read before the change, checked when given.
            author: Who makes the change, recorded with it.
            caller: The application that asks for the change; under the
                ``per-caller`` policy only administrators may make it.

        Raises:
            RuntimeError: Brevia is not started.
            Forbidden: The access policy does not let ``caller`` change
                customisations.
            NotFound: The activity is not registered.
            InvalidInput: A field is not in the schema or may not be reset.
            VersionConflict: ``expected_version`` is no longer current.
            Unavailable: The database cannot be used.
        """
        self._check_started()
        self._check_customizer(caller)
        registered = self._activity(activity)
        if isinstance(fields, str):
            raise InvalidInput("Fields to reset must be a list of paths, not a string")
        paths = None if fields is None else list(fields)
        stored = await self._store.save_configuration(
            activity,
            lambda current: reset_values(registered, current, paths),
            expected_version=expected_version,
            author=author,
            now=datetime.now(UTC),
        )
        return configuration_state(registered, stored)

    async def prompt(self, activity: str, name: str) -> PromptState:
        """A prompt of an activity: file text, customisation and effective text.

        Raises:
            RuntimeError: Brevia is not started.
            NotFound: The activity or the prompt is not declared.
            Unavailable: The database cannot be read.
        """
        self._check_started()
        registered = self._activity(activity)
        template_of(registered, name)
        custom = await self._store.customizations(activity)
        return prompt_state(registered, name, custom.prompts.get(name, NO_PROMPT))

    async def customize_prompt(
        self,
        activity: str,
        name: str,
        text: str,
        *,
        expected_version: int | None = None,
        author: str | None = None,
        caller: Caller | None = None,
    ) -> PromptState:
        """Replace the text of a prompt for the next runs, keeping its history.

        To restore an earlier revision, customise the prompt with its text.

        Args:
            activity: Name of the activity.
            name: Name of the prompt.
            text: New text, with exactly the variables of the prompt file.
            expected_version: Version read before the change, checked when given.
            author: Who makes the change, recorded with it.
            caller: The application that asks for the change; under the
                ``per-caller`` policy only administrators may make it.

        Raises:
            RuntimeError: Brevia is not started.
            Forbidden: The access policy does not let ``caller`` change
                customisations.
            NotFound: The activity or the prompt is not declared.
            InvalidInput: The text is blank or its variables differ from the file.
            VersionConflict: ``expected_version`` is no longer current.
            Unavailable: The database cannot be used.
        """
        self._check_started()
        self._check_customizer(caller)
        registered = self._activity(activity)
        checked_prompt_text(template_of(registered, name), text)
        stored = await self._store.save_prompt(
            activity,
            name,
            text,
            operation="customize",
            sha256=sha256(text),
            expected_version=expected_version,
            author=author,
            now=datetime.now(UTC),
        )
        return prompt_state(registered, name, stored)

    async def reset_prompt(
        self,
        activity: str,
        name: str,
        *,
        expected_version: int | None = None,
        author: str | None = None,
        caller: Caller | None = None,
    ) -> PromptState:
        """Return a prompt to the text of its file; the history is kept.

        Raises:
            RuntimeError: Brevia is not started.
            Forbidden: The access policy does not let ``caller`` change
                customisations.
            NotFound: The activity or the prompt is not declared.
            VersionConflict: ``expected_version`` is no longer current.
            Unavailable: The database cannot be used.
        """
        self._check_started()
        self._check_customizer(caller)
        registered = self._activity(activity)
        template_of(registered, name)
        stored = await self._store.save_prompt(
            activity,
            name,
            None,
            operation="reset",
            sha256=None,
            expected_version=expected_version,
            author=author,
            now=datetime.now(UTC),
        )
        return prompt_state(registered, name, stored)

    async def prompt_history(self, activity: str, name: str) -> list[PromptRevision]:
        """Changes of a prompt, the most recent first.

        Raises:
            RuntimeError: Brevia is not started.
            NotFound: The activity or the prompt is not declared.
            Unavailable: The database cannot be read.
        """
        self._check_started()
        template_of(self._activity(activity), name)
        return [revision(r) for r in await self._store.prompt_history(activity, name)]

    async def __aenter__(self) -> Self:
        await self.start()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.stop()

    @property
    def activities(self) -> Mapping[str, Activity]:
        """Registered activities, by name (read-only)."""
        return MappingProxyType(self._activities)

    def register_activity(
        self,
        *,
        name: str,
        version: str,
        function: ActivityFunction,
        input_type: type[BaseModel],
        output_type: type[BaseModel],
        config_type: type[BaseModel],
        prompts: Mapping[str, str | Path] | None = None,
        overridable: Iterable[str] = (),
        customizable: Iterable[str] = (),
        modes: Iterable[Mode] = ("direct",),
        limits: RunLimits | None = None,
        capture: Capture = "metadata",
    ) -> Activity:
        """Register an activity.

        Prompt files are read now, once: files are immutable during the life of the
        process. The project defaults of the activity are validated now, so that a
        configuration error stops the application at start-up.

        Args:
            name: Unique dotted name, for example ``"document.summarize"``.
            version: Version of the contract.
            function: ``async def f(request, ctx) -> output``.
            input_type: Schema of the input.
            output_type: Schema of the output.
            config_type: Schema of the configuration; defaults come from the schema
                and from the ``[activities."<name>"]`` table of the project file.
            prompts: Prompt files by name, relative to the project directory.
            overridable: Dotted configuration paths a request may override; a path
                allows its children.
            customizable: Dotted configuration paths that may be customised in the
                database for every new run; a path allows its children.
            modes: Supported modes: ``"direct"`` for :meth:`run`, ``"job"`` for
                :meth:`submit`. Job activities need types defined at module level.
            limits: Per-run limits; the project limits when not given.
            capture: ``"full"`` also records the instructions, the user text and the
                output of each model call, kept for ``[traces] retention_days``;
                ``"metadata"`` records their usage only.

        Raises:
            ValueError: The name, the modes, the capture, the overridable or the
                customisable paths are not valid, or the name is already registered.
            Unavailable: A prompt file cannot be read, the project defaults do not
                match the configuration schema, or the default model is not declared
                or uses options it does not support.
        """
        if not NAME.fullmatch(name):
            raise ValueError(f"Activity name {name!r} is not a valid dotted name")
        if name in self._activities:
            raise ValueError(f"Activity {name!r} is already registered")
        declared_modes = frozenset(modes)
        if not declared_modes or not declared_modes <= _MODES:
            raise ValueError(f"Activity modes must be a non-empty subset of {_MODES}")
        if capture not in ("metadata", "full"):
            raise ValueError("Capture must be 'metadata' or 'full'")
        allowed = frozenset(overridable)
        unknown = sorted(
            path for path in allowed if not path_in_schema(config_type, path)
        )
        if unknown:
            raise ValueError(f"Overridable paths not in the configuration: {unknown}")
        custom = frozenset(customizable)
        unknown = sorted(
            path for path in custom if not path_in_schema(config_type, path)
        )
        if unknown:
            raise ValueError(f"Customisable paths not in the configuration: {unknown}")
        if "job" in declared_modes:
            _check_importable(name, input_type, output_type, config_type)
        defaults = dict(self.project.activities.get(name, {}))
        self._check_defaults(name, config_type, defaults)
        templates = {
            prompt: load_prompt(prompt, self.project_dir / path)
            for prompt, path in (prompts or {}).items()
        }
        activity = Activity(
            name=name,
            version=version,
            function=function,
            input_type=input_type,
            output_type=output_type,
            config_type=config_type,
            defaults=MappingProxyType(defaults),
            overridable=allowed,
            customizable=custom,
            prompts=MappingProxyType(templates),
            modes=declared_modes,
            limits=limits or self.project.limits,
            capture=capture,
        )
        self._activities[name] = activity
        return activity

    def _check_defaults(
        self, name: str, config_type: type[BaseModel], defaults: dict[str, Any]
    ) -> None:
        """Validate the project defaults of an activity, including its default model.

        Raises:
            Unavailable: Unknown or invalid fields, or a default model that is not
                declared in the project or uses options it does not support.
        """
        unknown = unknown_fields(config_type, defaults)
        if unknown:
            raise Unavailable(
                f"Project defaults of activity {name!r} contain unknown fields",
                {"unknown": sorted(unknown)},
            )
        try:
            config = config_type.model_validate(defaults, by_alias=True, by_name=True)
        except ValidationError as exc:
            raise Unavailable(
                f"Project defaults of activity {name!r} are not valid",
                validation_details(exc),
            ) from exc
        model = getattr(config, "model", None)
        spec = ModelSpec(model=model) if isinstance(model, str) else model
        if not isinstance(spec, ModelSpec):
            return
        info = self.project.models.get(spec.model)
        if info is None:
            raise Unavailable(
                f"Default model of activity {name!r} is not declared in the project",
                {"model": spec.model},
            )
        try:
            check_capabilities(spec, info)
        except Unsupported as exc:
            raise Unavailable(
                f"Default model of activity {name!r}: {exc.message}", exc.details
            ) from exc

    def _activity(self, name: str) -> Activity:
        try:
            return self._activities[name]
        except KeyError:
            raise NotFound(
                f"Activity {name!r} is not registered", {"activity": name}
            ) from None

    async def run(
        self,
        name: str,
        request: BaseModel | Mapping[str, Any],
        overrides: Mapping[str, Any] | None = None,
        *,
        run_id: str | None = None,
        caller: Caller | None = None,
    ) -> BaseModel:
        """Run an activity directly and return its validated output.

        A direct run does not survive a restart of the process; use a job for that.
        Unless disabled in the settings, the run is recorded in the database at its
        start, and its outcome and model calls at its end.

        Args:
            name: Name of the activity.
            request: Input, as an instance of the input schema or as a mapping.
            overrides: Configuration overrides; only declared paths are allowed.
            run_id: Identifier of the run, a new UUID as a string, to know it
                before the run ends, for example to add feedback; a new one is chosen
                when not given. It is the ``run_id`` of the logs, of
                :class:`RunContext` and of :meth:`add_feedback`.
            caller: The application that asks for the run, recorded with it;
                ``None`` for trusted code in the process.

        Raises:
            RuntimeError: Brevia is not started.
            NotFound: The activity is not registered.
            Unsupported: The activity does not support direct runs.
            InvalidInput: The input or the configuration is not valid, or
                ``run_id`` is not a UUID.
            Unavailable: The customisations cannot be read, or a stored
                customisation is no longer valid for the code.
            OverrideNotAllowed: The request overrides a field that is not allowed.
            BreviaError: Any error raised by the activity, for example
                ``OutputInvalid``, ``LimitExceeded`` or ``ProviderError``, with the
                ``run_id`` of the run in its details.
            InternalError: The activity failed unexpectedly or returned an output
                that does not match its schema.
            Unavailable: The run or its outcome cannot be recorded, for example with
                a ``run_id`` already used; the output is not returned when its
                outcome cannot be recorded.
        """
        self._check_started()
        key = _new_run_id(run_id)
        activity = self._activity(name)
        if "direct" not in activity.modes:
            raise Unsupported(
                f"Activity {name!r} does not support direct runs", {"activity": name}
            )
        payload = validated_input(activity, request)
        check_sources(self.files, payload, caller)
        overrides = dict(overrides or {})
        config, prompts = await resolved(self._store, activity, overrides)
        values = snapshot(
            self.project, self.app_version, activity, config, overrides, prompts
        )
        if self._record_direct_runs:
            await self._store.create_run(
                NewRun(
                    id=key,
                    activity=name,
                    activity_version=activity.version,
                    mode="direct",
                    input=recorded_input(activity, payload),
                    snapshot=recorded_snapshot(activity, values),
                    started_at=datetime.now(UTC),
                    caller=None if caller is None else caller.name,
                    end_user=None if caller is None else caller.end_user,
                )
            )
        # Created after the first write, so that waiting for a database connection
        # does not consume the time budget of the run.
        ctx: RunContext[Any] = RunContext(
            run_id=str(key), config=config, snapshot=values, files=self.files
        )
        try:
            return await self._executor.run(
                activity, payload, ctx, overrides, record=self._record_direct_runs
            )
        except BreviaError as exc:
            # The run exists from here: its identifier lets the caller find it in the
            # logs and send feedback on it.
            exc.details.setdefault("run_id", str(key))
            raise

    async def submit(
        self,
        name: str,
        request: BaseModel | Mapping[str, Any],
        overrides: Mapping[str, Any] | None = None,
        *,
        idempotency_key: str | None = None,
        caller: Caller | None = None,
    ) -> RunHandle:
        """Submit a job: record it and queue it for a worker, then return at once.

        The handle is returned only once the job is recorded and queued, together.
        The input, the overrides and the configuration are checked now; the worker
        reads the customisations and prompts again when the job starts, and uses them
        until the job ends, also if it starts again after an interruption.

        Args:
            name: Name of the activity, registered with the ``"job"`` mode.
            request: Input, as an instance of the input schema or as a mapping.
            overrides: Configuration overrides; only declared paths are allowed, and
                they must have a JSON form.
            idempotency_key: With the same key and the same request, the same job is
                returned, in any status; with the same key and a different request,
                ``IdempotencyConflict`` is raised. A key is scoped to its caller: the
                same key of another caller gives another job.
            caller: The application that submits the job, recorded with it;
                ``None`` for trusted code in the process.

        Raises:
            RuntimeError: Brevia is not started, or has no job backend.
            NotFound: The activity is not registered.
            Unsupported: The activity does not support jobs.
            InvalidInput: The input, the overrides or the idempotency key are not
                valid, or have no JSON form.
            OverrideNotAllowed: The request overrides a field that is not allowed.
            IdempotencyConflict: The key was used for a different request.
            Unavailable: The job cannot be recorded or queued.
        """
        self._check_started()
        service = self._job_service()
        return await service.submit(
            name, request, overrides, idempotency_key, caller=caller
        )

    def job(self, run_id: str, *, caller: Caller | None = None) -> RunHandle:
        """Handle of the job ``run_id``; the job is read by the methods of the handle.

        Args:
            run_id: Identifier of the job.
            caller: The application that asks for the job; under the ``per-caller``
                policy, the methods of the handle find only its own jobs.

        Raises:
            RuntimeError: Brevia has no job backend.
            NotFound: ``run_id`` is not a job identifier.
        """
        return self._job_service().handle(run_id, caller)

    async def jobs(
        self,
        *,
        activity: str | None = None,
        status: JobStatus | None = None,
        idempotency_key: str | None = None,
        limit: int = 20,
        cursor: str | None = None,
        caller: Caller | None = None,
    ) -> JobPage:
        """A page of jobs, newest first, with the filters given.

        Under the ``per-caller`` policy a caller lists only its own jobs; trusted
        code, administrators and the ``shared`` policy list every job. Before the
        list, the active jobs it may show and that the engine has ended are recorded
        as ended, as when a job is read: the filter and the pages see their statuses.

        Args:
            activity: Only the jobs of this activity.
            status: Only the jobs in this status.
            idempotency_key: Only the jobs submitted with this key.
            limit: Most jobs in the page, from 1 to 100.
            cursor: ``next_cursor`` of the previous page; the filters must be the
                same as for that page.
            caller: The application that asks for the list.

        Raises:
            RuntimeError: Brevia is not started, or has no job backend.
            InvalidInput: The limit or the cursor are not valid.
            Unavailable: The jobs cannot be read.
        """
        return await self._job_service().page(
            caller,
            activity=activity,
            status=status,
            idempotency_key=idempotency_key,
            limit=limit,
            cursor=cursor,
        )

    async def find_job(
        self, activity: str, idempotency_key: str, *, caller: Caller | None = None
    ) -> JobState | None:
        """The job that ``caller`` submitted for ``activity`` with
        ``idempotency_key``, or ``None``; it does not submit anything.

        A key is scoped to its caller, as in :meth:`submit`: the key of another
        caller is not found, also by an administrator.

        Raises:
            RuntimeError: Brevia is not started, or has no job backend.
            Unavailable: The job cannot be read.
        """
        return await self._job_service().find(activity, idempotency_key, caller)

    async def add_feedback(
        self,
        run_id: str,
        feedback: FeedbackRequest | Mapping[str, Any],
        *,
        idempotency_key: str | None = None,
        caller: Caller | None = None,
    ) -> Feedback:
        """Add feedback to a run, direct or job: corrections of its output, or a
        rating. Earlier feedback and the output of the run are kept.

        Args:
            run_id: Identifier of the run; a direct run has one only when direct
                runs are recorded.
            feedback: The feedback, as a :class:`FeedbackRequest` or a mapping.
            idempotency_key: With the same key, the same caller and the same run, the
                feedback already recorded is returned instead of a new one, so that a
                repeated submission is recorded once; with different feedback,
                ``IdempotencyConflict`` is raised.
            caller: The application that adds it, recorded with its end user; under
                the ``per-caller`` policy only on its own runs.

        Raises:
            RuntimeError: Brevia is not started.
            NotFound: There is no such recorded run, or the caller may not see it.
            InvalidInput: The feedback or the idempotency key is not valid, or the
                feedback holds a NUL character.
            IdempotencyConflict: The key was used for different feedback.
            Unavailable: The feedback cannot be recorded.
        """
        self._check_started()
        request = _feedback_request(feedback)
        check_key(idempotency_key)
        try:
            key = uuid.UUID(run_id)
        except (ValueError, TypeError, AttributeError):
            raise NotFound("Run not found", {"run_id": str(run_id)}) from None
        owner = await self._store.run_owner(key)
        if owner is None or not self.access.sees(caller, owner.caller):
            raise NotFound("Run not found", {"run_id": run_id})
        record = FeedbackRecord(
            id=uuid.uuid4(),
            run_id=key,
            kind=request.kind,
            source=request.source,
            items=[item.model_dump() for item in request.items],
            rating=request.rating,
            comment=request.comment,
            external_ref=request.external_ref,
            created_at=datetime.now(UTC),
            caller=None if caller is None else caller.name,
            end_user=None if caller is None else caller.end_user,
            idempotency_key=idempotency_key,
        )
        stored, created = await self._store.add_feedback(record)
        if not created and _feedback_content(stored) != _feedback_content(record):
            raise IdempotencyConflict(
                "The idempotency key was used for different feedback",
                {"feedback_id": str(stored.id)},
            )
        return Feedback(
            kind=stored.kind,
            source=stored.source,
            items=[Correction.model_validate(item) for item in stored.items],
            rating=stored.rating,
            comment=stored.comment,
            external_ref=None
            if stored.external_ref is None
            else dict(stored.external_ref),
            id=str(stored.id),
            run_id=str(stored.run_id),
            caller=stored.caller,
            end_user=stored.end_user,
            created_at=stored.created_at,
        )

    def _job_service(self) -> JobService:
        if self._jobs is None:
            raise RuntimeError(
                "Jobs need a job backend: create Brevia with from_settings"
            )
        if self._started and not self._jobs_started:
            raise RuntimeError(
                "No activity supported jobs when Brevia started: register activities "
                "before `start()`"
            )
        return self._jobs


def _feedback_request(feedback: FeedbackRequest | Mapping[str, Any]) -> FeedbackRequest:
    """``feedback`` validated, with text that PostgreSQL accepts.

    Raises:
        InvalidInput: It is not valid or holds a NUL character.
    """
    # An instance is validated again from its data: its lists stay mutable after it
    # was created, so a valid instance may have been changed into an invalid one.
    data = feedback.model_dump() if isinstance(feedback, BaseModel) else feedback
    try:
        request = FeedbackRequest.model_validate(data)
    except ValidationError as exc:
        # Not chained: the message of a ValidationError quotes the values.
        raise InvalidInput(
            "The feedback is not valid", validation_details(exc)
        ) from None
    try:
        storable_json(request.model_dump())
    except ValueError as exc:
        # The reason only (no JSON form, NUL character), never the value.
        raise InvalidInput(f"The feedback cannot be recorded: {exc}") from None
    return request


def _feedback_content(record: FeedbackRecord) -> tuple[Any, ...]:
    """What a repeated submission must ask for again: the feedback and its author."""
    return (
        record.kind,
        record.source,
        [dict(item) for item in record.items],
        record.rating,
        record.comment,
        None if record.external_ref is None else dict(record.external_ref),
        record.end_user,
    )


def _new_run_id(run_id: str | None) -> uuid.UUID:
    """The identifier of a new direct run: ``run_id`` when given, or a new one.

    Raises:
        InvalidInput: ``run_id`` is not a UUID.
    """
    if run_id is None:
        return uuid.uuid4()
    try:
        return uuid.UUID(run_id)
    except (ValueError, TypeError, AttributeError):
        raise InvalidInput("The run identifier must be a UUID") from None
