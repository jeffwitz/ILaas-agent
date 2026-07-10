#!/usr/bin/env python3
"""Compteur d'économie de tokens pour les sessions Claude Code.

Lit les transcripts .jsonl de ~/.claude/projects/ et ventile les tokens
(et un coût estimé) par *rôle* de modèle : superviseur, délégué-pro,
délégué-flash, modèles ILaaS bon marché, premium Anthropic.

Le but : rendre visible l'économie de la stratégie multi-tiers/délégation
qui, sinon, n'est que supposée.

Usage:
    python3 token_economy.py                 # projet courant (cwd) — défaut
    python3 token_economy.py --all           # tous les projets
    python3 token_economy.py --project <nom> # un projet précis (nom du dossier)
    python3 token_economy.py --by-session    # détail par fichier de session (projet courant)

Les prix et le mapping rôle<-modèle sont éditables ci-dessous.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

DEFAULT_PROJECTS_DIR = Path(
    os.environ.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude"))
) / "projects"

# --- Mapping rôle <- modèle (motifs regex, premier match gagne) -------------
# Ajuste librement à ton setup.
ROLE_PATTERNS = [
    ("superviseur",     r"glm-5(\.|\b|$)|glm5|claude-.*opus|opus-4"),
    ("delegue-pro",     r"deepseek-v4-pro|deepseek.*pro|claude.*sonnet|sonnet"),
    ("delegue-flash",   r"deepseek-v4-flash|deepseek.*flash|haiku"),
    ("ilaas-bon-marche", r"claude-ilaas-|ilaas"),
    ("premium-anthropic", r"anthropic/claude|claude-4\."),
]

# --- Prix indicatifs en USD / 1M tokens (input, cache_read, output) ---------
# /!\ VALEURS À VÉRIFIER ET ÉDITER : approximatives, juste pour l'ordre de grandeur.
# cache_read est facturé ~10% de l'input chez la plupart des fournisseurs.
# La table est éditable sans toucher au code via
# ~/.config/ilaas-agent/prices.json (voir prices_config_path / load_prices).
DEFAULT_PRICE_ENTRIES = [
    # modele (motif regex) : (input, cache_read, output)  -- USD / 1M tokens
    # cache_read = input faute de tarif de hit de cache communiqué (à ajuster si remise).
    {"pattern": r"glm-5\.2|glm5\.2",          "input": 0.93,  "cache_read": 0.93,  "output": 3.00},
    {"pattern": r"deepseek-v4-pro",           "input": 0.435, "cache_read": 0.435, "output": 0.87},
    {"pattern": r"deepseek-v4-flash",         "input": 0.098, "cache_read": 0.098, "output": 0.196},
    {"pattern": r"claude-opus",               "input": 15.0,  "cache_read": 1.50,  "output": 75.0},
    {"pattern": r"anthropic/claude.*sonnet",  "input": 3.00,  "cache_read": 0.30,  "output": 15.0},
    {"pattern": r"claude-ilaas-|ilaas",       "input": 0.0,   "cache_read": 0.0,   "output": 0.0},  # passerelle locale / forfait
    {"pattern": r"<synthetic>",               "input": 0.0,   "cache_read": 0.0,   "output": 0.0},
]

# --- "Stratégie basique" = tout sur le superviseur premium ------------------
# Prix de référence pour le contrefactuel : ce que coûterait CHAQUE token
# s'il avait été traité par le superviseur premier-prix (par défaut: Opus),
# sans tiers ILaaS ni délégation. (input, cache_read, output) USD / 1M.
DEFAULT_BASELINE = {"input": 15.0, "cache_read": 1.50, "output": 75.0, "name": "Opus seul (aucune délégation, aucun tier ILaaS)"}


def prices_config_path() -> Path:
    """Où lire la table de prix optionnelle (~/.config/ilaas-agent/prices.json)."""
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return Path(base) / "ilaas-agent" / "prices.json"


def load_prices() -> tuple[list[dict], dict]:
    """Charge les prix depuis prices.json si présent, sinon les defaults embarqués.

    Format JSON : {"baseline": {"input":..,"cache_read":..,"output":..,"name":..},
    "prices": [{"pattern": "..", "input":.., "cache_read":.., "output":..}, ...]}.
    Une liste seule est interprétée comme les prix (baseline par défaut).
    """
    entries = list(DEFAULT_PRICE_ENTRIES)
    baseline = dict(DEFAULT_BASELINE)
    path = prices_config_path()
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            print(f"token_economy: failed to load {path}: {error}", file=sys.stderr)
            return entries, baseline
        if isinstance(data, list):
            entries = data
        elif isinstance(data, dict):
            if isinstance(data.get("prices"), list):
                entries = data["prices"]
            if isinstance(data.get("baseline"), dict):
                baseline.update(data["baseline"])
    return entries, baseline


PRICES, _loaded_baseline = load_prices()
BASELINE_PRICE = (_loaded_baseline["input"], _loaded_baseline["cache_read"], _loaded_baseline["output"])
BASELINE_NAME = _loaded_baseline["name"]


def role_of(model: str) -> str:
    m = (model or "").lower()
    for role, pat in ROLE_PATTERNS:
        if re.search(pat, m):
            return role
    return "autre"


def price_of(model: str):
    m = (model or "").lower()
    for entry in PRICES:
        if re.search(entry["pattern"], m):
            return (entry["input"], entry["cache_read"], entry["output"])
    return None  # inconnu -> coût n/a


def iter_assistant_usages(fn: str):
    is_sub = "/subagents/" in fn.replace(os.sep, "/")
    with open(fn, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            if o.get("type") != "assistant":
                continue
            msg = o.get("message") or {}
            usage = msg.get("usage") or {}
            if not usage:
                continue
            yield {
                "model": msg.get("model") or "?",
                "sidechain": bool(o.get("isSidechain", False)) or is_sub,
                "input": int(usage.get("input_tokens") or 0),
                "cache_read": int(usage.get("cache_read_input_tokens") or 0),
                "cache_create": int(usage.get("cache_creation_input_tokens") or 0),
                "output": int(usage.get("output_tokens") or 0),
            }


def cost(u) -> float | None:
    p = price_of(u["model"])
    if p is None:
        return None
    pin, pcr, pout = p
    return (
        u["input"] * pin
        + u["cache_read"] * pcr
        + (u["cache_create"] * pin)  # création de cache ~ tarif input
        + u["output"] * pout
    ) / 1_000_000


def fmt(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def fmt_usd(c) -> str:
    return "n/a" if c is None else f"${c:,.4f}"


def aggregate(files):
    by_model = defaultdict(lambda: defaultdict(int))
    by_role = defaultdict(lambda: defaultdict(float))
    side = defaultdict(lambda: defaultdict(int))
    # baseline/actual ne portent que sur les modèles prixés, pour que les deux
    # termes de l'économie soient cohérents (sinon un modèle sans prix gonflait
    # le baseline sans contrepartie côté actual -> économie surestimée).
    stats = {
        "baseline": 0.0, "actual": 0.0,
        "unp_in": 0, "unp_cread": 0, "unp_ccreate": 0, "unp_out": 0, "unp_msgs": 0,
    }
    for fn in files:
        for u in iter_assistant_usages(fn):
            tot_in = u["input"] + u["cache_read"] + u["cache_create"]
            bm = by_model[u["model"]]
            bm["msgs"] += 1
            bm["fresh"] += u["input"]
            bm["cread"] += u["cache_read"]
            bm["ccreate"] += u["cache_create"]
            bm["in"] += tot_in
            bm["out"] += u["output"]
            r = by_role[role_of(u["model"])]
            r["msgs"] += 1
            r["fresh"] += u["input"]
            r["cread"] += u["cache_read"]
            r["ccreate"] += u["cache_create"]
            r["in"] += tot_in
            r["out"] += u["output"]
            c = cost(u)
            if c is None:
                stats["unp_in"] += u["input"]
                stats["unp_cread"] += u["cache_read"]
                stats["unp_ccreate"] += u["cache_create"]
                stats["unp_out"] += u["output"]
                stats["unp_msgs"] += 1
            else:
                bm["cost"] += c
                r["cost"] += c
                stats["actual"] += c
                pin, pcr, pout = BASELINE_PRICE
                stats["baseline"] += (
                    u["input"] * pin + u["cache_create"] * pin
                    + u["cache_read"] * pcr + u["output"] * pout
                ) / 1_000_000
            key = "sidechain" if u["sidechain"] else "main"
            side[key]["in"] += tot_in
            side[key]["out"] += u["output"]
            side[key]["msgs"] += 1
    return by_model, by_role, side, stats


def economy(by_role, stats):
    """Contrefactuel : coût réel vs 'stratégie basique' (tout sur Opus).

    baseline = chaque token (frais, cache_create, cache_read, output) — mais
    uniquement des modèles prixés — facturé au tarif du superviseur premium.
    Le gain est la différence. Les tokens sans prix sont exclus des DEUX termes
    (et signalés à part) pour ne pas gonfler l'économie affichée.
    """
    baseline = stats["baseline"]
    actual = stats["actual"]
    sup_in = by_role.get("superviseur", {}).get("in", 0)
    tot_in = sum(r["in"] for r in by_role.values()) or 1
    offloaded = tot_in - sup_in
    saved = baseline - actual
    pct = 100 * saved / baseline if baseline else 0.0
    return {
        "baseline": baseline, "actual": actual, "saved": saved, "pct": pct,
        "offloaded": offloaded, "tot_in": tot_in, "out": stats.get("out", 0),
        "unp_in": stats["unp_in"], "unp_msgs": stats["unp_msgs"],
    }


def print_economy(e, scope):
    print(f"\n=== Économie vs stratégie basique — {scope} ===")
    print(f"Référence basique : {BASELINE_NAME}")
    print(f"  coût basique (tout sur Opus) : {fmt_usd(e['baseline']):>14s}")
    print(f"  coût réel (tiers + délégués) : {fmt_usd(e['actual']):>14s}")
    print(f"  ÉCONOMIE                     : {fmt_usd(e['saved']):>14s}   ({e['pct']:.1f} %)")
    print(f"  tokens déchargés du superviseur : {fmt(int(e['offloaded']))} / {fmt(int(e['tot_in']))} d'input")
    if e["unp_msgs"]:
        print(f"  /!\\ {e['unp_msgs']} msgs ({fmt(e['unp_in'])} tok) sans prix : "
              f"exclus du baseline ET de l'actual -> économie sous-estimée (à ajouter dans PRICES)")
    print("  (prix indicatifs — édite PRICES / BASELINE_PRICE pour un chiffre fiable)")


def report(title, by_model, by_role, side):
    print(f"\n=== {title} ===")
    print(f"\n{'modèle':40s} {'msgs':>5s} {'frais':>12s} {'cache_rd':>13s} "
          f"{'out':>11s} {'coût~':>11s}")
    print("-" * 96)
    for model, d in sorted(by_model.items(), key=lambda x: -x[1]["in"]):
        print(f"{model:40s} {int(d['msgs']):>5d} {fmt(int(d['fresh'])):>12s} "
              f"{fmt(int(d['cread'])):>13s} {fmt(int(d['out'])):>11s} {fmt_usd(d.get('cost')):>11s}")

    print(f"\n{'rôle':20s} {'msgs':>5s} {'frais':>12s} {'cache_rd':>13s} "
          f"{'out':>11s} {'coût~':>11s}")
    print("-" * 76)
    tot_in = sum(r["in"] for r in by_role.values()) or 1
    for role, d in sorted(by_role.items(), key=lambda x: -x[1]["in"]):
        print(f"{role:20s} {int(d['msgs']):>5d} {fmt(int(d['fresh'])):>12s} "
              f"{fmt(int(d['cread'])):>13s} {fmt(int(d['out'])):>11s} {fmt_usd(d.get('cost')):>11s}")

    # Économie : part de l'input portée hors superviseur
    sup_in = by_role.get("superviseur", {}).get("in", 0)
    deleg_in = tot_in - sup_in
    print("\nRépartition de l'input (le coût récurrent du contexte) :")
    print(f"  superviseur            : {100*sup_in/tot_in:5.1f} %  ({fmt(int(sup_in))} tok)")
    print(f"  délégué hors superviseur: {100*deleg_in/tot_in:5.1f} %  ({fmt(int(deleg_in))} tok)")

    if side.get("sidechain", {}).get("msgs"):
        s, m = side["sidechain"], side["main"]
        tin = (s["in"] + m["in"]) or 1
        print("\nSplit sidechain (sous-agents réellement spawné) :")
        print(f"  main loop : {fmt(m['in'])} in / {fmt(m['out'])} out  ({m['msgs']} msgs)")
        print(f"  sidechain : {fmt(s['in'])} in / {fmt(s['out'])} out  ({s['msgs']} msgs)  "
              f"-> {100*s['in']/tin:.1f}% de l'input absorbé par les délégués")
    else:
        print("\n(aucun message sidechain : pas de sous-agent spawné dans ces sessions)")


def main():
    ap = argparse.ArgumentParser(description="Compteur d'économie de tokens Claude Code.")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--all", action="store_true", help="tous les projets")
    g.add_argument("--project", help="nom du dossier projet sous ~/.claude/projects")
    ap.add_argument("--by-session", action="store_true", help="détail par fichier de session")
    ap.add_argument("--economy", action="store_true",
                    help="n'affiche que le bilan d'économie compact (pour la commande /economy)")
    ap.add_argument("--projects-dir", default=str(DEFAULT_PROJECTS_DIR),
                    help="dossier des transcripts (défaut: $CLAUDE_CONFIG_DIR/projects ou ~/.claude/projects)")
    args = ap.parse_args()

    projects_dir = Path(args.projects_dir).expanduser()
    if not projects_dir.is_dir():
        raise SystemExit(f"dossier de transcripts introuvable: {projects_dir}")

    if args.all:
        dirs = [p for p in projects_dir.iterdir() if p.is_dir()]
    elif args.project:
        dirs = [projects_dir / args.project]
    else:
        # Sans argument : projet courant (cwd) uniquement — la "session par défaut".
        # Convention Claude Code : tout caractère non alphanumérique (dont '_' et '/')
        # est remplacé par '-' dans le slug du dossier de transcripts.
        slug = "-" + re.sub(r"[^A-Za-z0-9.-]", "-", str(Path.cwd()).strip("/"))
        cand = projects_dir / slug
        if not cand.is_dir():
            raise SystemExit(f"projet {slug} introuvable sous {projects_dir} "
                             f"(lance avec --all pour tous les projets)")
        dirs = [cand]

    files = []
    for d in dirs:
        files += sorted(str(p) for p in Path(d).rglob("*.jsonl"))
    if not files:
        raise SystemExit("aucun transcript .jsonl trouvé.")

    scope = "tous projets" if (args.all or len(dirs) > 1) else dirs[0].name

    if args.economy:
        bm, br, sd, stats = aggregate(files)
        print(f"{len(files)} session(s), {len(dirs)} projet(s).")
        print_economy(economy(br, stats), scope)
        return

    print(f"{len(files)} session(s), {len(dirs)} projet(s).")
    print("NB: prix indicatifs éditables dans PRICES — vérifie-les avant de citer un coût.")

    if args.by_session:
        for fn in files:
            bm, br, sd, _ = aggregate([fn])
            report(Path(fn).name, bm, br, sd)
    else:
        bm, br, sd, _ = aggregate(files)
        report(f"cumul — {scope}", bm, br, sd)


if __name__ == "__main__":
    main()
