# Models

Refresh the model list from ILaaS with:

```bash
python -m ilaas_agents.cli refresh-models
```

Generated files:

```text
~/.config/litellm/ilaas-mistral.yaml
~/.codex-ilaas/model-catalogs/ilaas-mistral.json
```

Aliases:

```text
ilaas-default -> mistral-medium-latest
mistral-ilaas -> mistral-medium-latest
```

Recommended for code-agent use:

```text
qwen-3.6-35b-instruct
mistral-medium-latest
gemma-4-31b
```

Not recommended for code-agent tool use:

```text
llama-3.1-8b
llama-3.3-70b
```

They may be usable for simple chat, but current tool-calling behavior is not reliable enough for agentic code editing.

## Model tiers

Each catalog entry carries a `tier` field (`supervisor` / `coder` / `small`) that lets launchers pick the most capable model for supervision and the most efficient for code, per provider. See {doc}`tiers` for the resolve precedence, CLI management, and heuristics.
