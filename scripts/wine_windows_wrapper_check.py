#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ilaas_agents import wrappers  # noqa: E402


def run(argv: list[str], cwd: Path | None = None) -> str:
    print("+", " ".join(argv), flush=True)
    try:
        return subprocess.check_output(argv, cwd=cwd, text=True, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as error:
        if error.output:
            print(error.output, end="", flush=True)
        raise


def wine_path(path: Path) -> str:
    output = run(["winepath", "-w", str(path)])
    candidates = [line.strip() for line in output.splitlines() if re.match(r"^[A-Za-z]:\\", line.strip())]
    if not candidates:
        raise SystemExit(f"winepath did not return a Windows path for {path}: {output}")
    return candidates[-1]


def quoted(value: str) -> str:
    if '"' in value:
        raise ValueError(f"cannot quote Windows cmd value containing double quote: {value}")
    return f'"{value}"'


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a Wine-based smoke test for generated Windows .cmd wrappers.")
    parser.add_argument("--keep", action="store_true", help="Keep the temporary check directory.")
    args = parser.parse_args()

    if not shutil.which("wine") or not shutil.which("winepath"):
        raise SystemExit("wine and winepath are required for this check")

    workdir = Path(tempfile.mkdtemp(prefix="ilaas-wine-wrapper-"))
    try:
        wrapper_dir = workdir / "wrappers"
        fake_bin = workdir / "fake-bin"
        log_path = workdir / "python-calls.log"
        wrapper_dir.mkdir()
        fake_bin.mkdir()

        (fake_bin / "python.cmd").write_text(
            "@echo off\r\n"
            "echo PYTHONPATH=%PYTHONPATH%>> \"%ILAAS_FAKE_PYTHON_LOG%\"\r\n"
            "echo ARGS=%*>> \"%ILAAS_FAKE_PYTHON_LOG%\"\r\n"
            "exit /b 0\r\n"
        )

        with mock.patch("ilaas_agents.paths.is_windows", return_value=True):
            installed = wrappers.install_wrappers(wrapper_dir)

        expected_cmds = [wrapper_dir / f"{name}.cmd" for name in wrappers.POSIX_NAMES]
        missing = [path for path in expected_cmds if path not in installed or not path.exists()]
        if missing:
            raise SystemExit("missing generated .cmd wrappers: " + ", ".join(str(path) for path in missing))

        fake_bin_win = wine_path(fake_bin)
        log_win = wine_path(log_path)

        for name in wrappers.POSIX_NAMES:
            log_path.unlink(missing_ok=True)
            command = name.removeprefix("Ilaas-")
            cmd_win = wine_path(wrapper_dir / f"{name}.cmd")
            runner = workdir / f"run-{name}.cmd"
            runner.write_text(
                "@echo off\r\n"
                f"set \"ILAAS_FAKE_PYTHON_LOG={log_win}\"\r\n"
                f"set \"PATH={fake_bin_win};%PATH%\"\r\n"
                f"call {quoted(cmd_win)} --probe value\r\n"
                "exit /b %ERRORLEVEL%\r\n"
            )
            run(["wine", "cmd", "/d", "/c", wine_path(runner)], cwd=workdir)
            log_text = log_path.read_text()
            expected_args = f"ARGS=-m ilaas_agents.cli {command} --probe value"
            if expected_args not in log_text:
                raise SystemExit(f"{name}.cmd did not call expected CLI args: {expected_args}")
            if "PYTHONPATH=" not in log_text:
                raise SystemExit(f"{name}.cmd did not set PYTHONPATH")

        print(f"Wine Windows .cmd wrapper checks OK: {workdir}", flush=True)
    finally:
        if args.keep:
            print(f"Kept check directory: {workdir}", flush=True)
        else:
            shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    main()
