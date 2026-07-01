#!/usr/bin/env python3
"""Compteur d'économie de tokens pour les sessions Claude Code.

Lit les transcripts .jsonl de ~/.claude/projects/ et ventile les tokens
(et un coût estimé) par *rôle* de modèle : superviseur, délégué-pro,
délégué-flash, modèles ILaaS bon marché, premium Anthropic.

Le but : rendre visible l'économie de la stratégie multi-tiers/délégation
qui, sinon, n'est que supposée.

Usage:
    python3 token_economy.py                 # projet courant (cwd)
    python3 token_economy.py --all           # tous les projets
    python3 token_economy.py --project <nom> # un projet précis (nom du dossier)
    python3 token_economy.py --by-session    # détail par fichier de session

Les prix et le mapping rôle<-modèle sont éditables ci-dessous.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
from collections import defaultdict
from pathlib import Path

DEFAULT_PROJECTS_DIR = Path(
    os.environ.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude"))
) / "projects"

# --- Mapping rôle <- modèle (motifs regex, premier match gagne) -------------
# Ajuste librement à ton setup.
ROLE_PATTERNS = [
    ("superviseur",     r"glm-5|glm5|claude-opus|opus-4"),
    ("delegue-pro",     r"deepseek-v4-pro|deepseek.*pro|claude.*sonnet|sonnet"),
    ("delegue-flash",   r"deepseek-v4-flash|deepseek.*flash|haiku"),
    ("ilaas-bon-marche", r"claude-ilaas-|ilaas"),
    ("premium-anthropic", r"anthropic/claude|claude-4\."),
]

# --- Prix indicatifs en USD / 1M tokens (input, cache_read, output) ---------
# /!\ VALEURS À VÉRIFIER ET ÉDITER : approximatives, juste pour l'ordre de grandeur.
# cache_read est facturé ~10% de l'input chez la plupart des fournisseurs.
PRICES = {
    # modele (motif regex) : (input, cache_read, output)  -- USD / 1M tokens
    # cache_read = input faute de tarif de hit de cache communiqué (à ajuster si remise).
    r"glm-5\.2|glm5\.2":          (0.93,  0.93,  3.00),
    r"deepseek-v4-pro":           (0.435, 0.435, 0.87),
    r"deepseek-v4-flash":         (0.098, 0.098, 0.196),
    r"claude-opus":               (15.0,  1.50,  75.0),
    r"anthropic/claude.*sonnet":  (3.00,  0.30,  15.0),
    r"claude-ilaas-|ilaas":       (0.0,   0.0,   0.0),   # passerelle locale / forfait
    r"<synthetic>":               (0.0,   0.0,   0.0),
}

# --- "Stratégie basique" = tout sur le superviseur premium ------------------
# Prix de référence pour le contrefactuel : ce que coûterait CHAQUE token
# s'il avait été traité par le superviseur premier-prix (par défaut: Opus),
# sans tiers ILaaS ni délégation. (input, cache_read, output) USD / 1M.
BASELINE_PRICE = (15.0, 1.50, 75.0)
BASELINE_NAME = "Opus seul (aucune délégation, aucun tier ILaaS)"


def role_of(model: str) -> str:
    m = (model or "").lower()
    for role, pat in ROLE_PATTERNS:
        if re.search(pat, m):
            return role
    return "autre"


def price_of(model: str):
    m = (model or "").lower()
    for pat, price in PRICES.items():
        if re.search(pat, m):
            return price
    return None  # inconnu -> coût n/a


def iter_assistant_usages(fn: str):
    is_sub = "/subagents/" in fn.replace(os.sep, "/")
    for line in open(fn, encoding="utf-8"):
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
    cost_known = True
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
                cost_known = False
            else:
                bm["cost"] += c
                r["cost"] += c
            key = "sidechain" if u["sidechain"] else "main"
            side[key]["in"] += tot_in
            side[key]["out"] += u["output"]
            side[key]["msgs"] += 1
    return by_model, by_role, side, cost_known


def economy(by_role):
    """Contrefactuel : coût réel vs 'stratégie basique' (tout sur Opus).

    baseline = chaque token (frais, cache_create, cache_read, output) facturé
    au tarif du superviseur premium. Le gain est la différence.
    """
    pin, pcr, pout = BASELINE_PRICE
    fresh = sum(r["fresh"] for r in by_role.values())
    cread = sum(r["cread"] for r in by_role.values())
    ccreate = sum(r["ccreate"] for r in by_role.values())
    out = sum(r["out"] for r in by_role.values())
    baseline = (fresh * pin + ccreate * pin + cread * pcr + out * pout) / 1_000_000
    actual = sum(r.get("cost", 0.0) for r in by_role.values())
    sup_in = by_role.get("superviseur", {}).get("in", 0)
    tot_in = sum(r["in"] for r in by_role.values()) or 1
    offloaded = tot_in - sup_in
    saved = baseline - actual
    pct = 100 * saved / baseline if baseline else 0.0
    return {
        "baseline": baseline, "actual": actual, "saved": saved, "pct": pct,
        "offloaded": offloaded, "tot_in": tot_in, "out": out,
    }


def print_economy(e, scope):
    print(f"\n=== Économie vs stratégie basique — {scope} ===")
    print(f"Référence basique : {BASELINE_NAME}")
    print(f"  coût basique (tout sur Opus) : {fmt_usd(e['baseline']):>14s}")
    print(f"  coût réel (tiers + délégués) : {fmt_usd(e['actual']):>14s}")
    print(f"  ÉCONOMIE                     : {fmt_usd(e['saved']):>14s}   ({e['pct']:.1f} %)")
    print(f"  tokens déchargés du superviseur : {fmt(int(e['offloaded']))} / {fmt(int(e['tot_in']))} d'input")
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
    print(f"\nRépartition de l'input (le coût récurrent du contexte) :")
    print(f"  superviseur            : {100*sup_in/tot_in:5.1f} %  ({fmt(int(sup_in))} tok)")
    print(f"  délégué hors superviseur: {100*deleg_in/tot_in:5.1f} %  ({fmt(int(deleg_in))} tok)")

    if side.get("sidechain", {}).get("msgs"):
        s, m = side["sidechain"], side["main"]
        tin = (s["in"] + m["in"]) or 1
        print(f"\nSplit sidechain (sous-agents réellement spawné) :")
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
        slug = "-" + str(Path.cwd()).strip("/").replace("/", "-")
        cand = projects_dir / slug
        dirs = [cand] if cand.is_dir() else [p for p in projects_dir.iterdir() if p.is_dir()]
        if not cand.is_dir():
            print(f"(projet {slug} introuvable, bascule sur --all)")

    files = []
    for d in dirs:
        files += sorted(str(p) for p in Path(d).rglob("*.jsonl"))
    if not files:
        raise SystemExit("aucun transcript .jsonl trouvé.")

    scope = "tous projets" if (args.all or len(dirs) > 1) else dirs[0].name

    if args.economy:
        bm, br, sd, _ = aggregate(files)
        print(f"{len(files)} session(s), {len(dirs)} projet(s).")
        print_economy(economy(br), scope)
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
