"""L14 SubprocessCommandRunner.

One test runs a real process, using the interpreter already running the suite so it
needs nothing installed. The rest assert containment.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from tto_testgen.adapters.command_runner import SubprocessCommandRunner
from tto_testgen.ports.commands import CommandResult, CommandRunner


@pytest.fixture()
def runner(tmp_path):
    return SubprocessCommandRunner(workspace_root=tmp_path)


def test_it_satisfies_the_port(runner):
    assert isinstance(runner, CommandRunner)


# --- it really runs processes -----------------------------------------------------

def test_a_real_command_runs_and_reports_its_output(runner, tmp_path):
    result = runner.run([sys.executable, "-c", "print('hello')"], cwd=tmp_path, timeout_s=30)
    assert result.succeeded
    assert result.exit_code == 0
    assert "hello" in result.stdout
    assert result.duration_ms >= 0


def test_a_non_zero_exit_is_reported_not_raised(runner, tmp_path):
    """A compilation failure is information the report carries, not an exception."""
    result = runner.run([sys.executable, "-c", "raise SystemExit(3)"], cwd=tmp_path, timeout_s=30)
    assert not result.succeeded
    assert result.exit_code == 3
    assert not result.timed_out


def test_stderr_is_captured(runner, tmp_path):
    result = runner.run(
        [sys.executable, "-c", "import sys; sys.stderr.write('boom')"],
        cwd=tmp_path, timeout_s=30,
    )
    assert "boom" in result.stderr


def test_the_command_runs_in_the_given_directory(runner, tmp_path):
    (tmp_path / "marker.txt").write_text("x", encoding="utf-8")
    result = runner.run(
        [sys.executable, "-c", "import os; print(os.path.exists('marker.txt'))"],
        cwd=tmp_path, timeout_s=30,
    )
    assert "True" in result.stdout


# --- containment --------------------------------------------------------------------

def test_a_metacharacter_is_an_argument_not_a_command(runner, tmp_path):
    """`shell=False` means there is no shell to interpret it.

    Without this, a path containing `;` or `&&` would become executable - which is
    the single failure mode the argv-only port exists to remove.
    """
    result = runner.run(
        [sys.executable, "-c", "import sys; print(sys.argv[1])", "; rm -rf /"],
        cwd=tmp_path, timeout_s=30,
    )
    assert result.succeeded
    assert "; rm -rf /" in result.stdout


def test_an_empty_argv_is_refused(runner, tmp_path):
    with pytest.raises(ValueError):
        runner.run([], cwd=tmp_path, timeout_s=30)


def test_a_timeout_is_distinguished_from_a_failure(runner, tmp_path):
    """A tool that was absent is skipped; one that ran and did not finish is failed.

    Folding a timeout into `skipped` would tell the operator their machine lacks
    Node when it does not.
    """
    result = runner.run(
        [sys.executable, "-c", "import time; time.sleep(10)"], cwd=tmp_path, timeout_s=1
    )
    assert result.timed_out
    assert result.exit_code is None
    assert not result.succeeded
    assert "timed out" in result.summary()


# --- output bounds ------------------------------------------------------------------

def test_long_output_is_truncated_and_says_so(tmp_path):
    runner = SubprocessCommandRunner(workspace_root=tmp_path, output_limit_bytes=200)
    result = runner.run(
        [sys.executable, "-c", "print('x' * 5000)"], cwd=tmp_path, timeout_s=30
    )
    assert result.truncated
    assert "truncated at 200 bytes" in result.stdout
    assert len(result.stdout) < 1000


def test_short_output_is_not_marked_truncated(runner, tmp_path):
    result = runner.run([sys.executable, "-c", "print('ok')"], cwd=tmp_path, timeout_s=30)
    assert not result.truncated


def test_output_is_sanitised(tmp_path):
    """npm reports registry URLs; a proxy failure can carry an Authorization header;
    tsc reports absolute paths naming the operator's home directory."""
    runner = SubprocessCommandRunner(workspace_root=tmp_path)
    result = runner.run(
        [sys.executable, "-c", r"print('failed at /Users/someone/secret/project')"],
        cwd=tmp_path, timeout_s=30,
    )
    assert "/Users/someone" not in result.stdout


# --- availability ---------------------------------------------------------------------

def test_availability_resolves_on_path(runner):
    assert runner.is_available(Path(sys.executable).name) or runner.is_available("python3")
    assert not runner.is_available("definitely-not-a-real-executable-xyz")


def test_the_result_records_what_was_run(runner, tmp_path):
    result = runner.run([sys.executable, "-c", "pass"], cwd=tmp_path, timeout_s=30)
    assert result.argv == (sys.executable, "-c", "pass")
    assert isinstance(result, CommandResult)
