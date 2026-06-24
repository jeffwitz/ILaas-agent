from __future__ import annotations

import os
import platform
from pathlib import Path


APP_NAME = "ilaas-code-agents"


def system() -> str:
    return platform.system().lower()


def is_windows() -> bool:
    return system().startswith("win")


def home() -> Path:
    return Path.home()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def config_home() -> Path:
    if is_windows():
        return Path(os.environ.get("APPDATA", home() / "AppData/Roaming"))
    return Path(os.environ.get("XDG_CONFIG_HOME", home() / ".config"))


def cache_home() -> Path:
    if is_windows():
        return Path(os.environ.get("LOCALAPPDATA", home() / "AppData/Local"))
    if system() == "darwin":
        return home() / "Library/Caches"
    return Path(os.environ.get("XDG_CACHE_HOME", home() / ".cache"))


def bin_dir() -> Path:
    if is_windows():
        return Path(os.environ.get("LOCALAPPDATA", home() / "AppData/Local")) / "Programs" / "IlaasCodeAgents" / "bin"
    return home() / ".local" / "bin"


def litellm_config_path() -> Path:
    return config_home() / "litellm" / "ilaas-mistral.yaml"


def codex_home() -> Path:
    return home() / ".codex-ilaas"


def codex_config_path() -> Path:
    return codex_home() / "config.toml"


def model_catalog_path() -> Path:
    return codex_home() / "model-catalogs" / "ilaas-mistral.json"


def log_dir() -> Path:
    return cache_home() / APP_NAME / "logs"


def runtime_dir() -> Path:
    return cache_home() / APP_NAME / "run"


def litellm_venv() -> Path:
    if is_windows():
        return home() / ".venvs" / "litellm"
    return home() / ".venvs" / "litellm"
