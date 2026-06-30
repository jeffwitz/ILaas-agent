from __future__ import annotations

import argparse
import sys

from . import deps, doctor, glm52, models, openrouter, paths, runners, smoke
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

    if len(sys.argv) >= 2 and sys.argv[1] in {"glm52-codex", "glm52-claude", "glm52-opencode"}:
        command = sys.argv[1].removeprefix("glm52-")
        argv = sys.argv[2:]
        if command == "codex":
            raise SystemExit(glm52.run_codex(argv))
        if command == "claude":
            raise SystemExit(glm52.run_claude(argv))
        raise SystemExit(glm52.run_opencode(argv))

    if len(sys.argv) >= 2 and sys.argv[1] in {
        "openrouter-codex",
        "openrouter-claude",
        "openrouter-opencode",
    }:
        command = sys.argv[1].removeprefix("openrouter-")
        argv = sys.argv[2:]
        if command == "codex":
            raise SystemExit(openrouter.run_codex(argv))
        if command == "claude":
            raise SystemExit(openrouter.run_claude(argv))
        raise SystemExit(openrouter.run_opencode(argv))

    parser = argparse.ArgumentParser(description="ILaaS code-agent helper CLI.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("install")
    sub.add_parser("doctor")
    sub.add_parser("refresh-models")

    servers = sub.add_parser("servers")
    servers.add_argument("action", choices=["start", "stop", "status", "logs"])

    deps_parser = sub.add_parser("deps", help="Detect or install external code-agent CLI dependencies.")
    deps_sub = deps_parser.add_subparsers(dest="deps_action", required=True)
    deps_sub.add_parser("status")
    deps_install = deps_sub.add_parser("install")
    deps_install.add_argument("agents", nargs="*", choices=["all", "codex", "claude", "opencode"], default=["all"])

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
    elif args.command == "deps":
        if args.deps_action == "status":
            deps.print_status()
            raise SystemExit(0)
        deps.install_agents(args.agents)
        raise SystemExit(0)
    elif args.command == "smoke":
        raise SystemExit(smoke.run(args))
    else:
        parser.error("unknown command")


if __name__ == "__main__":
    main()
