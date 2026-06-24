from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from . import paths


@dataclass
class StartedProcess:
    name: str
    process: subprocess.Popen
    pid_file: Path | None = None


class ProcessManager:
    def __init__(self) -> None:
        self.started: list[StartedProcess] = []

    def port_open(self, host: str, port: int) -> bool:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            return False

    def wait_for_port(self, name: str, host: str, port: int, attempts: int = 80) -> None:
        for _ in range(attempts):
            if self.port_open(host, port):
                return
            time.sleep(0.25)
        raise SystemExit(f"timed out waiting for {name} on {host}:{port}")

    def start(
        self,
        name: str,
        argv: list[str],
        log_path: Path,
        pid_file: Path | None = None,
        env: dict[str, str] | None = None,
        detach: bool = False,
    ) -> subprocess.Popen:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        pid_file.parent.mkdir(parents=True, exist_ok=True) if pid_file else None
        log = log_path.open("ab")
        popen_kwargs = {"stdout": log, "stderr": subprocess.STDOUT, "env": env}
        if detach:
            if paths.is_windows():
                popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
            else:
                popen_kwargs["start_new_session"] = True
        process = subprocess.Popen(argv, **popen_kwargs)
        if pid_file:
            pid_file.write_text(str(process.pid))
        self.started.append(StartedProcess(name=name, process=process, pid_file=pid_file))
        return process

    def cleanup(self, keep: bool = False) -> None:
        if keep:
            return
        for item in reversed(self.started):
            terminate_pid(item.process.pid)
            if item.pid_file and item.pid_file.exists():
                item.pid_file.unlink(missing_ok=True)


def terminate_pid(pid: int, timeout: float = 5.0) -> None:
    try:
        if paths.is_windows():
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except OSError:
        return

    deadline = time.time() + timeout
    while time.time() < deadline:
        if not pid_alive(pid):
            return
        time.sleep(0.1)
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def pid_file(name: str) -> Path:
    return paths.runtime_dir() / f"{name}.pid"


def read_pid(name: str) -> int | None:
    path = pid_file(name)
    if not path.exists():
        return None
    try:
        return int(path.read_text().strip())
    except ValueError:
        return None


def python_executable() -> str:
    return sys.executable or "python3"
