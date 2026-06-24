from __future__ import annotations

import shutil
import socket
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

from . import deps, paths


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


def http_json_ok(label: str, url: str) -> tuple[str, bool, str]:
    try:
        request = urllib.request.Request(url, headers={"authorization": "Bearer sk-local-dummy"})
        with urllib.request.urlopen(request, timeout=5) as response:
            response.read()
            return (label, 200 <= response.status < 300, f"{response.status} {url}")
    except urllib.error.HTTPError as error:
        return (label, False, f"{error.code} {url}")
    except Exception as error:
        return (label, False, f"{url} ({error})")


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
    for key, ok, detail in deps.runtime_statuses():
        checks.append((key, ok, detail))
    for key, ok, detail in deps.agent_statuses():
        checks.append((key, ok, detail))

    if port_open("127.0.0.1", 4000):
        checks.append(http_json_ok("LiteLLM /v1/models", "http://127.0.0.1:4000/v1/models"))
    if port_open("127.0.0.1", 4001):
        checks.append(http_json_ok("Codex proxy /health", "http://127.0.0.1:4001/health"))
    if port_open("127.0.0.1", 4002):
        checks.append(http_json_ok("Claude proxy /health", "http://127.0.0.1:4002/health"))

    failed = 0
    for label, ok, detail in checks:
        status = "OK" if ok else "WARN"
        if not ok and label in {"LiteLLM config", "Codex config", "Model catalog", "Wrapper dir", "LiteLLM /v1/models"}:
            failed += 1
        print(f"[{status}] {label}: {detail}")
    return 0 if failed == 0 else 1
