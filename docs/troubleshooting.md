# Troubleshooting

## Codex returns `tokens used 0`

Do not point Codex directly at LiteLLM `/v1/responses`. Use `Ilaas-codex`, which starts the local Responses proxy on port `4001`.

## Model metadata warning in Codex

Run:

```bash
python -m ilaas_agents.cli refresh-models
```

Then verify `~/.codex-ilaas/config.toml` references the generated model catalog.

## Bubblewrap warning on Linux

The generated ILaaS Codex config uses:

```toml
sandbox_mode = "danger-full-access"
```

This avoids Codex bubblewrap user namespace issues on systems where AppArmor blocks unprivileged namespaces.

## Port already in use

Check:

```bash
Ilaas-servers status
```

Stop project-managed persistent proxies:

```bash
Ilaas-servers stop
```

If a service was started outside this project, stop it manually.

The wrappers verify the expected HTTP endpoint before reusing an open port. If another service is listening on `4000`, `4001`, or `4002`, the wrapper exits instead of silently using it. Use `LITELLM_PORT`, `RESPONSES_PORT`, or `CLAUDE_ILAAS_PORT` to choose alternate ports.

## Missing ILaaS key

Set the key during install:

```bash
ILAAS_API_KEY=... python install.py
```

The key is written only to the local LiteLLM config outside the repository.

## Llama models

`llama-3.1-8b` and `llama-3.3-70b` are not recommended for code-agent tool use in the current ILaaS/LiteLLM setup.
