from __future__ import annotations

import argparse
import os
import subprocess
import sys

from . import doctor, models, paths
from .install import main as install_main


def refresh_models() -> None:
    existing = models.extract_existing_settings(paths.litellm_config_path())
    if not existing:
        raise SystemExit(f"Missing LiteLLM config or API key: {paths.litellm_config_path()}")
    api_base, api_key = existing
    model_ids = models.fetch_models(api_base, api_key)
    models.write_litellm_config(paths.litellm_config_path(), api_base, api_key, model_ids)
    models.write_codex_catalog(paths.model_catalog_path(), model_ids)
    print(f"Refreshed {len(model_ids)} ILaaS models plus aliases.")
    for model_id in model_ids:
        print(model_id)


def exec_root_script(name: str, argv: list[str]) -> int:
    script = paths.repo_root() / f"Ilaas-{name}"
    if paths.is_windows():
        raise SystemExit(f"Windows native runner for {name} is not implemented yet. Use WSL2 for now.")
    if not script.exists():
        raise SystemExit(f"Missing script: {script}")
    os.execv(str(script), [str(script), *argv])
    return 127


def main() -> None:
    parser = argparse.ArgumentParser(description="ILaaS code-agent helper CLI.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("install")
    sub.add_parser("doctor")
    sub.add_parser("refresh-models")
    for name in ["codex", "claude", "opencode"]:
        p = sub.add_parser(name)
        p.add_argument("args", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    if args.command == "install":
        sys.argv = [sys.argv[0]]
        install_main()
    elif args.command == "doctor":
        raise SystemExit(doctor.run())
    elif args.command == "refresh-models":
        refresh_models()
    elif args.command in {"codex", "claude", "opencode"}:
        raise SystemExit(exec_root_script(args.command, args.args))
    else:
        parser.error("unknown command")


if __name__ == "__main__":
    main()
