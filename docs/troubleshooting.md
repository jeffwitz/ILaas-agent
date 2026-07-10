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

If an old ILaaS proxy from another checkout is still running, `/health` may return HTTP 200 but without the expected `service` field. Current wrappers and `Ilaas-doctor` reject that stale proxy so it is not reused accidentally. Stop the old process, then rerun the agent wrapper.

## Qwen returns `Unterminated string`

The error can appear through LiteLLM as:

```text
OpenAIException - Unterminated string starting at ...
Received Model Group=qwen-3.6-35b-instruct
```

Qwen can still work for normal chat and simple tool calls, but this failure can happen when the upstream tool-call JSON is malformed. The local Codex and Claude proxies retry Qwen tool-call requests once with a stricter instruction requiring complete JSON tool arguments.

Also check for stale proxies on `4001` or `4002`; older proxies from temporary checkouts can keep listening and route requests through outdated code.

## Missing ILaaS key

Set the key during install:

```bash
ILAAS_API_KEY=... python install.py
```

The key is written only to the local LiteLLM config outside the repository.

## Llama models

`llama-3.1-8b` and `llama-3.3-70b` are not recommended for code-agent tool use in the current ILaaS/LiteLLM setup.

## Local security model

ILaaS Agent is built for a **single-user development machine**. The local services it starts are loopback-only:

- LiteLLM gateway on `127.0.0.1:4000`
- Codex Responses proxy on `127.0.0.1:4001`
- Claude Messages proxy on `127.0.0.1:4002`
- OpenRouter passthrough proxy on a dynamically chosen `127.0.0.1` port

They bind to `127.0.0.1` only, so they are not reachable from the network. However, they accept any loopback caller with a dummy bearer (`sk-local-dummy`), which means **any local process or local user can call them and spend ILaaS / OpenRouter tokens**. This is acceptable on a single-user machine where you trust your own processes; it is **not** appropriate on shared or multi-user hosts — do not run ILaaS Agent there.

The API keys themselves are never written into the Git checkout: the ILaaS key lives only in the LiteLLM config (`~/.config/litellm/ilaas-mistral.yaml`, `chmod 600`), and the provider keys live under `~/.config/ilaas-agent/keys/` (`chmod 600`). `Ilaas-doctor` reports which key source resolved per provider without printing the key value.

Optional shared-secret hardening (proxies checking the `authorization` header against `ILAAS_PROXY_SHARED_SECRET`) is tracked as a later improvement, not enabled today, to keep the proxies minimal.
