# Token Economy Counter

`scripts/token_economy.py` measures how much the multi-tier / delegation strategy
actually saves, instead of assuming it. It reads the Claude Code session
transcripts (`*.jsonl`) of a config home and breaks the token spend down by
**model role**, then compares the real cost against a *baseline strategy* where
every token runs on the premium supervisor (Opus).

It exists because the saving was previously only theoretical: the tier-map
({doc}`tiers`) and the subagent delegation (`ctx-pro` / `code-pro` / `code-flash`)
are designed to be cheap, but nothing reported the realized number.

## What it reads

Transcripts live under a config home's `projects/` directory:

```text
~/.claude/projects/                 # the default Claude Code config home
~/.claude_openrouter/projects/      # the openrouter/GLM launchers config home
```

The counter walks the tree **recursively**, so it also picks up delegated
subagent transcripts stored in `<session>/subagents/agent-*.jsonl`. Those files
hold the tokens handled by the delegated models and are what makes the delegation
economy visible. Any usage coming from a `subagents/` file (or flagged
`isSidechain`) is counted as *delegated* rather than *supervisor*.

## Usage

```bash
# Compact economy headline (what the /economy command shows)
python3 scripts/token_economy.py --economy --all \
  --projects-dir ~/.claude_openrouter/projects

# Full breakdown by model and by role (fresh vs cache_read, sidechain split)
python3 scripts/token_economy.py --all \
  --projects-dir ~/.claude_openrouter/projects

# One project, or per session
python3 scripts/token_economy.py --project -home-jeff-Code-Codex-Mistral
python3 scripts/token_economy.py --by-session
```

Flags:

| Flag | Effect |
|---|---|
| `--all` | aggregate every project in the transcripts dir |
| `--project <name>` | a single project (the `projects/` sub-directory name) |
| `--by-session` | one report per session file |
| `--economy` | only the compact savings headline |
| `--projects-dir <path>` | which transcripts to read (default: `$CLAUDE_CONFIG_DIR/projects`, else `~/.claude/projects`) |

## Pricing

Prices are USD per 1M tokens. The defaults are embedded in `scripts/token_economy.py` (`DEFAULT_PRICE_ENTRIES` and `DEFAULT_BASELINE`) and can be overridden **without editing code** by writing a JSON file to `~/.config/ilaas-agent/prices.json`:

```json
{
  "baseline": {"input": 15.0, "cache_read": 1.50, "output": 75.0, "name": "Opus seul"},
  "prices": [
    {"pattern": "glm-5\\.2|glm5\\.2", "input": 0.93, "cache_read": 0.93, "output": 3.00},
    {"pattern": "claude-opus",        "input": 15.0, "cache_read": 1.50, "output": 75.0}
  ]
}
```

- `prices` — a list of `{pattern, input, cache_read, output}` per model, matched by regex; first match wins. A bare JSON list is also accepted (prices only, default baseline).
- `baseline` — the "basic strategy" reference (default: Opus alone, no delegation, no ILaaS tier).

`cache_read` defaults to the input rate when a provider's cache-hit discount is
unknown; lower it if your provider bills cached reads more cheaply. Because the
supervisor's recurring context is mostly `cache_read`, this rate dominates the
real cost — set it accurately before quoting a figure.

## Reading the output

- **Economy headline** — baseline cost vs real cost, the saving in `$` and `%`,
  and how many input tokens were offloaded from the supervisor.
- **By role** — `superviseur` (GLM 5.2 / Opus), `delegue-pro` (DeepSeek V4 Pro),
  `delegue-flash` (DeepSeek V4 Flash), `ilaas-bon-marche`. The supervisor's
  `cache_read` column is the recurring cost of re-sending its growing context
  each turn — the metric the delegation strategy targets.
- **Sidechain split** — share of input absorbed by delegated subagents. Empty
  means no subagent ran in those sessions (e.g. a plain `~/.claude` run without
  the `ctx-pro`/`code-*` agents); run under `~/.claude_openrouter` to exercise
  delegation.

## The `/economy` command

`install.py` deploys a Claude Code slash command so the report is available from
**any directory** in sessions started by the openrouter/GLM launchers (those set
`CLAUDE_CONFIG_DIR=~/.claude_openrouter`). The command is generated in code
(`ilaas_agents/commands.py`) and written to:

```text
~/.claude_openrouter/commands/economy.md      ($CLAUDE_OPENROUTER_HOME/commands)
```

The generator embeds the absolute script path at install time and relies on the
script's default projects directory (`$CLAUDE_CONFIG_DIR/projects`), so the
command needs no hardcoded home and stays portable. Invoke it as `/economy`
(optionally `/economy --by-session`).

Re-generate it without a full reinstall:

```bash
python3 -c "from ilaas_agents import commands; commands.install_economy_command()"
```
