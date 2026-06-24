from __future__ import annotations

import shutil
import socket
import subprocess
from pathlib import Path

from . import paths


def port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def command_version(command: str) -> str | None:
    if not shutil.which(command):
        return None
    try:
        output = subprocess.check_output([command, "--version"], stderr=subprocess.STDOUT, text=True, timeout=10)
        return output.strip().splitlines()[0] if output.strip() else "installed"
    except Exception:
        return "installed"


def exists(label: str, path: Path) -> tuple[str, bool, str]:
    return (label, path.exists(), str(path))


def run() -> int:
    checks: list[tuple[str, bool, str]] = [
        ("LiteLLM config", paths.litellm_config_path().exists(), str(paths.litellm_config_path())),
        ("Codex config", paths.codex_config_path().exists(), str(paths.codex_config_path())),
        ("Model catalog", paths.model_catalog_path().exists(), str(paths.model_catalog_path())),
        ("Wrapper dir", paths.bin_dir().exists(), str(paths.bin_dir())),
        ("LiteLLM port 4000", port_open("127.0.0.1", 4000), "127.0.0.1:4000"),
        ("Codex proxy port 4001", port_open("127.0.0.1", 4001), "127.0.0.1:4001"),
        ("Claude proxy port 4002", port_open("127.0.0.1", 4002), "127.0.0.1:4002"),
    ]
    for command in ["codex", "claude", "opencode"]:
        version = command_version(command)
        checks.append((command, version is not None, version or "not found"))

    failed = 0
    for label, ok, detail in checks:
        status = "OK" if ok else "WARN"
        if not ok and label in {"LiteLLM config", "Codex config", "Model catalog", "Wrapper dir"}:
            failed += 1
        print(f"[{status}] {label}: {detail}")
    return 0 if failed == 0 else 1
