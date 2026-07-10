from __future__ import annotations

import os
import platform
import sys
from pathlib import Path


APP_NAME = "ilaas-code-agents"

# Personal absolute paths from the original build. Kept only as a deprecation
# fallback so existing author setups keep working one release beyond the move
# to keys_dir(); see CdC-ilaas-agent-v2.md ticket A2. Do not extend.
LEGACY_KEY_FILES = {
    "ilaas": Path("/home/jeff/Code/clef_api/Ilaas.txt"),
    "glm52": Path("/home/jeff/Code/clef_api/GLM5.2.md"),
    "openrouter": Path("/home/jeff/Code/clef_api/OPEN_ROUTER.md"),
}


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


def codex_home_openrouter() -> Path:
    """Isolated Codex home for the OpenRouter bridge (never the user's ~/.codex)."""
    return env_path("OPENROUTER_CODEX_HOME", home() / ".codex-openrouter")


def codex_home_glm52() -> Path:
    """Isolated Codex home for the GLM 5.2 bridge (never the user's ~/.codex)."""
    return env_path("GLM52_CODEX_HOME", home() / ".codex-glm52")


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


def claude_openrouter_home() -> Path:
    """Config home used by the openrouter/GLM Claude Code launchers."""
    return env_path("CLAUDE_OPENROUTER_HOME", home() / ".claude_openrouter")


def token_economy_script() -> Path:
    return repo_root() / "scripts" / "token_economy.py"


def keys_dir() -> Path:
    """Directory holding provider token files. Override with ILAAS_KEYS_DIR."""
    return env_path("ILAAS_KEYS_DIR", config_home() / "ilaas-agent" / "keys")


def key_file(provider: str) -> Path:
    """Default token file for a provider (ilaas/glm52/openrouter)."""
    return keys_dir() / f"{provider}.token"


def legacy_key_file(provider: str) -> Path | None:
    """Hardcoded personal path, kept only for the deprecation fallback."""
    return LEGACY_KEY_FILES.get(provider)


def warn_legacy_key(provider: str) -> None:
    """Print a one-line deprecation notice when a legacy key path is used."""
    print(
        f"ilaas-agent: using legacy {provider} key at {legacy_key_file(provider)}; "
        f"move it to {key_file(provider)} (removed next release).",
        file=sys.stderr,
    )
