"""The start script of the container of the template, run with fake commands.

``brevia`` and ``uvicorn`` are replaced by a bash script that records what it is
asked and the signals it receives, so the modes, the stop and the exit codes are
checked without Docker, a database or a model.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import time
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.unit,
    pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash"),
]

TEMPLATE = Path(__file__).parents[2] / "template" / "bin" / "start.jinja"

# One fake for both commands: it records its start, its stop and its end. It ends on
# its own with FAKE_<NAME>_EXIT; on TERM it waits FAKE_STOP_SECONDS and exits with
# FAKE_<NAME>_TERM_CODE (0 by default).
FAKE = """#!/usr/bin/env bash
name=$(basename "$0")
upper=${name^^}
echo "$name start $*" >> "$FAKE_LOG"
on_term() {
    echo "$name term" >> "$FAKE_LOG"
    sleep "${FAKE_STOP_SECONDS:-0}"
    echo "$name end" >> "$FAKE_LOG"
    code="FAKE_${upper}_TERM_CODE"
    exit "${!code:-0}"
}
trap on_term TERM
code="FAKE_${upper}_EXIT"
if [[ -n "${!code:-}" ]]; then
    sleep 0.3
    echo "$name end" >> "$FAKE_LOG"
    exit "${!code}"
fi
while true; do sleep 0.05; done
"""


class Container:
    """The rendered start script with the fake commands first on the PATH."""

    def __init__(self, tmp_path: Path) -> None:
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        for name in ("brevia", "uvicorn"):
            fake = bin_dir / name
            fake.write_text(FAKE, encoding="utf-8")
            fake.chmod(0o755)
        self.script = tmp_path / "start"
        # The only variable of the template; rendered by hand, so the tests do not
        # need Jinja, which only the documentation group installs.
        text = TEMPLATE.read_text(encoding="utf-8").replace(
            "{{ package_name }}", "myapp"
        )
        assert "{{" not in text
        assert "{%" not in text
        self.script.write_text(text, encoding="utf-8")
        self.script.chmod(0o755)
        self.log = tmp_path / "log"
        self.log.touch()
        # PORT and APP_MODE of the shell running the tests would change the commands.
        inherited = {
            k: v for k, v in os.environ.items() if k not in ("PORT", "APP_MODE")
        }
        self.env = {
            **inherited,
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "FAKE_LOG": str(self.log),
        }

    def start(self, **env: str) -> subprocess.Popen[str]:
        return subprocess.Popen(  # noqa: S603  (the script of the test)
            [str(self.script)],
            env={**self.env, **env},
            stderr=subprocess.PIPE,
            text=True,
        )

    def lines(self) -> list[str]:
        return self.log.read_text(encoding="utf-8").splitlines()

    def wait_for_lines(self, *expected: str) -> None:
        deadline = time.monotonic() + 5
        while not all(line in self.lines() for line in expected):
            assert time.monotonic() < deadline, self.lines()
            time.sleep(0.02)


@pytest.fixture
def container(tmp_path: Path) -> Container:
    return Container(tmp_path)


WORKER = "brevia start worker myapp.application:create"
API = "uvicorn start myapp.api:app --host 0.0.0.0 --port 8000"


def test_an_unknown_mode_is_refused(container: Container) -> None:
    process = container.start(APP_MODE="web")

    assert process.wait(timeout=5) == 64
    assert process.stderr is not None
    assert "unknown APP_MODE 'web'" in process.stderr.read()
    assert container.lines() == []


@pytest.mark.parametrize(
    ("mode", "line"),
    [
        ("migrate", "brevia start db upgrade"),
        ("worker", WORKER),
        ("api", "uvicorn start myapp.api:app --host 0.0.0.0 --port 9000"),
    ],
)
def test_a_single_mode_runs_its_command_in_place_of_the_script(
    container: Container, mode: str, line: str
) -> None:
    process = container.start(
        APP_MODE=mode, PORT="9000", FAKE_BREVIA_EXIT="5", FAKE_UVICORN_EXIT="5"
    )

    # The exit code is the command's own: the script has become the command.
    assert process.wait(timeout=5) == 5
    assert container.lines()[0] == line


def test_a_stop_reaches_both_and_waits_for_their_end(container: Container) -> None:
    process = container.start(FAKE_STOP_SECONDS="1")
    container.wait_for_lines(WORKER, API)

    process.send_signal(signal.SIGTERM)
    time.sleep(0.5)
    assert process.poll() is None  # the processes are still stopping

    assert process.wait(timeout=5) == 0
    assert {"brevia term", "brevia end", "uvicorn term", "uvicorn end"} <= set(
        container.lines()
    )


@pytest.mark.parametrize("stop", [signal.SIGTERM, signal.SIGINT])
def test_ending_with_the_code_of_the_signal_is_a_normal_stop(
    container: Container, stop: signal.Signals
) -> None:
    process = container.start(FAKE_UVICORN_TERM_CODE="143")
    container.wait_for_lines(WORKER, API)

    process.send_signal(stop)

    assert process.wait(timeout=5) == 0
    assert {"brevia term", "uvicorn term"} <= set(container.lines())


def test_a_failure_while_stopping_is_reported(container: Container) -> None:
    process = container.start(FAKE_BREVIA_TERM_CODE="2")
    container.wait_for_lines(WORKER, API)

    process.send_signal(signal.SIGTERM)

    assert process.wait(timeout=5) == 2


def test_a_worker_that_fails_stops_the_api(container: Container) -> None:
    process = container.start(FAKE_BREVIA_EXIT="3")

    assert process.wait(timeout=5) == 3
    assert "uvicorn term" in container.lines()
    assert process.stderr is not None
    assert "the worker exited with 3, stopping the api" in process.stderr.read()


def test_a_process_that_ends_on_its_own_with_0_is_an_error(
    container: Container,
) -> None:
    process = container.start(FAKE_UVICORN_EXIT="0")

    assert process.wait(timeout=5) == 1
    assert "brevia term" in container.lines()
