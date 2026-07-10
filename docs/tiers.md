# Model Tiers (supervisor / coder / small)

Each provider exposes a **tier-map** that picks a concrete model per role, so the most capable model supervises while the most efficient one handles routine code. The complexity routing itself is left to each agent's native multi-tier behavior — ILaaS Agent only configures *which model fills each tier*.

## Tiers

| Tier | Role | Where it lands |
|---|---|---|
| `supervisor` | Most intelligent | Claude `opus`/`fable`, OpenCode `model`, Codex main model |
| `coder` | Efficient workhorse | Claude `sonnet` |
| `small` | Trivial / cheap | Claude `haiku`, OpenCode `small_model` |

Claude Code and OpenCode already route between their tiers internally depending on the task; Codex has a single model slot, so it runs the `supervisor` model for the whole agentic loop.

### OpenRouter Claude Code defaults

For `openrouter-claude`, the Claude Code tier slots default to a GLM-supervises / DeepSeek-codes split:

| Claude slot | Tier | Default model |
|---|---|---|
| `ANTHROPIC_DEFAULT_OPUS_MODEL` | supervisor | `z-ai/glm-5.2` |
| `ANTHROPIC_DEFAULT_FABLE_MODEL` | supervisor | `z-ai/glm-5.2` |
| `ANTHROPIC_DEFAULT_SONNET_MODEL` | coder | `deepseek/deepseek-v4-pro` |
| `ANTHROPIC_DEFAULT_HAIKU_MODEL` | small | `deepseek/deepseek-v4-flash` |

Override any slot with `OPENROUTER_TIER_CODER_MODEL` / `OPENROUTER_TIER_SMALL_MODEL` / `OPENROUTER_TIER_SUPERVISOR_MODEL`, or via `tiers apply`.

## Where the tier-map lives

The tier is a field **on each catalog entry** (`"tier": "supervisor"`), per provider. There is one catalog per provider:

```text
ilaas       -> ~/.codex-ilaas/model-catalogs/ilaas-mistral.json   ($ILAAS_MODEL_CATALOG)
glm52       -> <cache>/ilaas-code-agents/glm52-model-catalog.json
openrouter  -> <cache>/ilaas-code-agents/openrouter-<slug>.json   ($OPENROUTER_TIER_CATALOG)
```

For OpenRouter the catalog is per selected model (`openrouter-<slug>.json`). The launcher records which one is active in an explicit state file `<cache>/ilaas-code-agents/openrouter-active.json` (`{"catalog": "<path>"}`) when `openrouter-codex` runs with a selected model. Resolution order for the OpenRouter catalog is: `$OPENROUTER_TIER_CATALOG` env > the active state file > the most-recently-written `openrouter-*.json` (adopted into the state file on first read) > the `openrouter-tiers.json` default. Inspect the chosen catalog and its source with `tiers show`.

When no tier is configured, every launcher falls back to its existing hardcoded default — enabling tiers is opt-in and never changes default behavior.

## Resolve precedence

For a given `(provider, tier)`, `tiers.resolve` checks, in order:

1. Environment variable `{PROVIDER}_TIER_{TIER}_MODEL` — e.g. `ILAAS_TIER_SUPERVISOR_MODEL`, `OPENROUTER_TIER_CODER_MODEL`.
2. The first catalog entry whose `tier` field matches.
3. `None` → the caller falls back to its provider default.

`tiers show --provider <p>` prints each resolved tier slug together with its source (`env` / `catalog` / `unset`) and the resolved catalog path with its own source.

## Manage tiers from the CLI

```bash
# Show the currently resolved tier mapping
python3 -m ilaas_agents.cli tiers list --provider ilaas

# Suggest a tier mapping from the catalog (heuristic: name for ILaaS,
# context_length + tool support for OpenRouter, trivial for GLM 5.2)
python3 -m ilaas_agents.cli tiers suggest --provider ilaas

# Write the tier field onto every catalog entry (idempotent).
# Without --tier, every entry is classified heuristically.
python3 -m ilaas_agents.cli tiers apply --provider ilaas

# Pin a specific slug to a tier (repeatable)
python3 -m ilaas_agents.cli tiers apply --provider openrouter \
  --tier supervisor=z-ai/glm-5.2 \
  --tier small=<light-model>
```

`apply` requires the catalog to exist — generate it first with `refresh-models` (ILaaS) or by running the matching launcher once (GLM 5.2 / OpenRouter write their catalog on demand).

## Heuristics

- **GLM 5.2**: single model, every tier maps to `glm-5.2`.
- **OpenRouter**: metadata-based — `tools` support + text output required; `context_length >= 200000` → `supervisor`, `< 64000` → `small`, otherwise `coder`. No tools → `small`.
- **ILaaS**: name-based (the `/v1/models` endpoint only exposes ids) — `ilaas-default`/`mistral-ilaas`/`medium`/`70b`/`3.6-35b` → `supervisor`; `8b`/`3b`/`mini`/`tiny`/`small` → `small`; otherwise `coder`.

Override any heuristic with `tiers apply --tier ...` or the environment variables above.

## Why per provider

The free models available on ILaaS are not the same as on OpenRouter, so a single global tier-map cannot work. The tier-map is keyed by provider, and each provider's catalog carries its own tier assignments. Edit the catalog (or set the env vars) when a free model appears or disappears; no code change required.
