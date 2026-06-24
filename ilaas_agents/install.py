from __future__ import annotations

import argparse
import getpass
import os
import subprocess
import sys
from pathlib import Path

from . import config, models, paths, wrappers


def litellm_bin() -> str:
    venv = paths.litellm_venv()
    if paths.is_windows():
        return str(venv / "Scripts" / "litellm.exe")
    return str(venv / "bin" / "litellm")


def ensure_litellm(skip_install: bool) -> None:
    if skip_install:
        return
    venv = paths.litellm_venv()
    if not venv.exists():
        subprocess.check_call([sys.executable, "-m", "venv", str(venv)])
    pip = venv / ("Scripts/pip.exe" if paths.is_windows() else "bin/pip")
    subprocess.check_call([str(pip), "install", "-U", "pip", "litellm[proxy]"])


def resolve_api_key(args: argparse.Namespace) -> tuple[str, str]:
    existing = models.extract_existing_settings(paths.litellm_config_path())
    api_base = args.api_base or (existing[0] if existing else models.DEFAULT_API_BASE)
    api_key = os.environ.get(args.api_key_env or "ILAAS_API_KEY")
    if not api_key and existing:
        api_key = existing[1]
    if not api_key and not args.non_interactive:
        api_key = getpass.getpass("ILaaS API key: ").strip()
    if not api_key:
        raise SystemExit("Missing ILaaS API key. Set ILAAS_API_KEY or run interactively.")
    return api_base, api_key


def run_install(args: argparse.Namespace) -> None:
    ensure_litellm(args.skip_litellm_install)
    api_base, api_key = resolve_api_key(args)
    model_ids = models.fetch_models(api_base, api_key)
    if models.DEFAULT_ALIAS_TARGET not in model_ids:
        raise SystemExit(f"Default alias target unavailable on ILaaS: {models.DEFAULT_ALIAS_TARGET}")

    models.write_litellm_config(paths.litellm_config_path(), api_base, api_key, model_ids)
    models.write_codex_catalog(paths.model_catalog_path(), model_ids)
    config.write_codex_config(paths.codex_config_path(), paths.model_catalog_path())
    wrapper_dir = Path(args.prefix).expanduser() / "bin" if args.prefix else None
    installed = wrappers.install_wrappers(wrapper_dir)

    print(f"Installed LiteLLM config: {paths.litellm_config_path()}")
    print(f"Installed Codex config: {paths.codex_config_path()}")
    print(f"Installed model catalog: {paths.model_catalog_path()}")
    for path in installed:
        print(f"Installed wrapper: {path}")
    hint = wrappers.path_hint(wrapper_dir)
    if hint:
        print(f"PATH warning: {hint}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Install ILaaS local code-agent tooling.")
    parser.add_argument("--non-interactive", action="store_true")
    parser.add_argument("--api-key-env", default="ILAAS_API_KEY")
    parser.add_argument("--api-base", default=None)
    parser.add_argument("--skip-litellm-install", action="store_true")
    parser.add_argument("--prefix", default=None, help="Install wrappers into PREFIX/bin instead of the platform default bin directory.")
    parser.add_argument("--force", action="store_true", help="Accepted for idempotent reinstall workflows; generated files are overwritten safely.")
    args = parser.parse_args()
    run_install(args)
