from __future__ import annotations

import os
import platform
from pathlib import Path


APP_NAME = "ilaas-code-agents"


def system() -> str:
    return platform.system().lower()


def is_windows() -> bool:
    return system().startswith("win")


def env_path(name: str, fallback: Path) -> Path:
    value = os.environ.get(name)
    return Path(value).expanduser() if value else fallback


def home() -> Path:
    return env_path("ILAAS_HOME", Path.home())


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def config_home() -> Path:
    if os.environ.get("ILAAS_CONFIG_HOME"):
        return Path(os.environ["ILAAS_CONFIG_HOME"]).expanduser()
    if is_windows():
        return Path(os.environ.get("APPDATA", home() / "AppData/Roaming"))
    return Path(os.environ.get("XDG_CONFIG_HOME", home() / ".config"))


def cache_home() -> Path:
    if os.environ.get("ILAAS_CACHE_HOME"):
        return Path(os.environ["ILAAS_CACHE_HOME"]).expanduser()
    if is_windows():
        return Path(os.environ.get("LOCALAPPDATA", home() / "AppData/Local"))
    if system() == "darwin":
        return home() / "Library/Caches"
    return Path(os.environ.get("XDG_CACHE_HOME", home() / ".cache"))


def bin_dir() -> Path:
    if os.environ.get("ILAAS_BIN_DIR"):
        return Path(os.environ["ILAAS_BIN_DIR"]).expanduser()
    if is_windows():
        return Path(os.environ.get("LOCALAPPDATA", home() / "AppData/Local")) / "Programs" / "IlaasCodeAgents" / "bin"
    return home() / ".local" / "bin"


def litellm_config_path() -> Path:
    return env_path("ILAAS_LITELLM_CONFIG", config_home() / "litellm" / "ilaas-mistral.yaml")


def codex_home() -> Path:
    return env_path("ILAAS_CODEX_HOME", home() / ".codex-ilaas")


def codex_config_path() -> Path:
    return codex_home() / "config.toml"


def model_catalog_path() -> Path:
    return env_path("ILAAS_MODEL_CATALOG", codex_home() / "model-catalogs" / "ilaas-mistral.json")


def log_dir() -> Path:
    return cache_home() / APP_NAME / "logs"


def runtime_dir() -> Path:
    return cache_home() / APP_NAME / "run"


def litellm_venv() -> Path:
    return env_path("ILAAS_LITELLM_VENV", home() / ".venvs" / "litellm")
