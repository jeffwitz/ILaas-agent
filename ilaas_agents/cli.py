from __future__ import annotations

import argparse
import sys

from . import deps, doctor, glm52, models, openrouter, paths, runners, smoke, tiers
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

    tiers_parser = sub.add_parser("tiers", help="Manage tier-to-model mappings per provider.")
    tiers_parser.add_argument("action", choices=["list", "suggest", "apply"])
    tiers_parser.add_argument("--provider", choices=["ilaas", "glm52", "openrouter"], required=True)
    tiers_parser.add_argument("--tier", action="append", metavar="tier=slug")

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
    elif args.command == "tiers":
        if args.action == "list":
            for tier in tiers.TIERS:
                resolved = tiers.resolve(args.provider, tier)
                print(f"{args.provider} {tier}: {resolved or '(unset)'}")
            print(f"catalog: {tiers.catalog_path(args.provider)}")
            raise SystemExit(0)
        if args.action == "suggest":
            mapping = tiers.suggest(args.provider)
            for tier in tiers.TIERS:
                print(f"{args.provider} {tier}: {mapping.get(tier, '(none)')}")
            raise SystemExit(0)
        # action == "apply"
        if args.tier:
            mapping = {}
            for entry in args.tier:
                if "=" not in entry:
                    raise SystemExit(f"Invalid --tier format '{entry}': expected tier=slug (e.g. --tier supervisor=qwen-3.6-35b-instruct)")
                key, _, val = entry.partition("=")
                key, val = key.strip(), val.strip()
                if not key or not val:
                    raise SystemExit(f"Invalid --tier format '{entry}': both tier and slug must be non-empty")
                if key not in tiers.TIERS:
                    raise SystemExit(f"Unknown tier '{key}'; expected one of: {', '.join(tiers.TIERS)}")
                mapping[key] = val
        else:
            mapping = None
        counts = tiers.apply(args.provider, mapping)
        print(f"Applied tiers to {args.provider} catalog: {counts}")
        raise SystemExit(0)
    else:
        parser.error("unknown command")


if __name__ == "__main__":
    main()
