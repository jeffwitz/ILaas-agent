from __future__ import annotations

import argparse
import sys

from . import doctor, models, paths, runners, smoke
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


def main() -> None:
    if len(sys.argv) >= 2 and sys.argv[1] == "install":
        sys.argv = [sys.argv[0], *sys.argv[2:]]
        install_main()
        return

    if len(sys.argv) >= 2 and sys.argv[1] in {"codex", "claude", "opencode"}:
        command = sys.argv[1]
        argv = sys.argv[2:]
        if command == "codex":
            raise SystemExit(runners.run_codex(argv))
        if command == "claude":
            raise SystemExit(runners.run_claude(argv))
        raise SystemExit(runners.run_opencode(argv))

    parser = argparse.ArgumentParser(description="ILaaS code-agent helper CLI.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("install")
    sub.add_parser("doctor")
    sub.add_parser("refresh-models")

    servers = sub.add_parser("servers")
    servers.add_argument("action", choices=["start", "stop", "status", "logs"])
    smoke.add_parser(sub)

    args = parser.parse_args()

    if args.command == "install":
        install_main()
    elif args.command == "doctor":
        raise SystemExit(doctor.run())
    elif args.command == "refresh-models":
        refresh_models()
    elif args.command == "servers":
        raise SystemExit(runners.servers(args.action))
    elif args.command == "smoke":
        raise SystemExit(smoke.run(args))
    else:
        parser.error("unknown command")


if __name__ == "__main__":
    main()
