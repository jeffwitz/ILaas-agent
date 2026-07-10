# Interface Principles

ILaaS exposes an OpenAI-compatible API. In practice, the reliable path validated for the available ILaaS models is Chat Completions:

```text
https://llm.ilaas.fr/v1/chat/completions
```

The local architecture standardizes everything around LiteLLM:

```text
Agent CLI
  -> local compatibility layer when needed
  -> LiteLLM http://127.0.0.1:4000/v1/chat/completions
  -> ILaaS
```

## Architecture at a glance

```text
                          ILaaS path (persistent)                 direct API paths (per-session)
          ┌────────────────────────────────────────────┐   ┌─────────────────────────────────────┐
          │ LiteLLM gateway   127.0.0.1:4000  (persist)│   │ GLM 5.2 Z.AI        api.z.ai        │
          │   ├─ Codex Responses proxy  4001 (session) │   │ OpenRouter          openrouter.ai  │
          │   │    Codex CLI ──>/v1/responses           │   │   └─ Anthropic proxy 4012 (session)│
          │   ├─ Claude Messages proxy 4002 (session)  │   │        Claude Code ──>/v1/messages  │
          │   │    Claude Code ──>/v1/messages          │   │                                     │
          │   └─ OpenCode ──>/v1/chat/completions       │   │ OpenCode ──> provider (glm52|openr) │
          └────────────────────────────────────────────┘   └─────────────────────────────────────┘
```

- **Persistent**: `Ilaas-servers` keeps the LiteLLM gateway on port `4000` across sessions; it is the only long-lived service and the only one that holds the ILaaS key at runtime.
- **Per-session**: the `4001` Responses, `4002` Messages, and `4012` OpenRouter-Anthropic proxies are started on demand by the matching launcher and stopped when it exits. The GLM 5.2 and OpenRouter direct paths talk to the provider over HTTPS with no local gateway.
- `Ilaas-doctor` checks all four ports and the resolved key sources; see {doc}`troubleshooting` for the local security model.

## Why LiteLLM

## Why LiteLLM

LiteLLM provides one local OpenAI-compatible endpoint and one model registry. The generated LiteLLM config contains every ILaaS model exposed by `/v1/models`, plus stable aliases:

```text
ilaas-default -> mistral-medium-latest
mistral-ilaas -> mistral-medium-latest
```

The ILaaS key is stored only in the local LiteLLM config, not in the repository.

## Codex CLI

Codex CLI uses OpenAI's Responses API shape. Direct LiteLLM `/v1/responses` was not sufficient in the prototype: real Codex requests produced empty output and `tokens used 0`, while LiteLLM `/v1/chat/completions` worked.

The project therefore runs a local Responses proxy:

```text
Codex CLI
  -> http://127.0.0.1:4001/v1/responses
  -> http://127.0.0.1:4000/v1/chat/completions
  -> ILaaS
```

The generated Codex config uses:

```toml
wire_api = "responses"
supports_websockets = false
```

The Responses proxy is intentionally minimal. It translates the subset needed by the tested Codex workflows into Chat Completions; it is not a complete OpenAI Responses implementation.

## Claude Code

Claude Code expects the Anthropic Messages API, not OpenAI Chat Completions. The project therefore runs a local Messages proxy:

```text
Claude Code
  -> http://127.0.0.1:4002/v1/messages
  -> http://127.0.0.1:4000/v1/chat/completions
  -> ILaaS
```

Models are exposed to Claude Code as:

```text
claude-ilaas-<ilaas-slug>
```

The wrapper accepts raw ILaaS slugs such as `qwen-3.6-35b-instruct` and rewrites them automatically.

The Messages proxy is intentionally minimal. It supports the tested Claude Code flows, but it is not a complete Anthropic Messages implementation.

## OpenCode

OpenCode supports custom OpenAI-compatible providers. It can talk to LiteLLM directly, without an extra protocol proxy:

```text
OpenCode
  -> provider ilaas
  -> http://127.0.0.1:4000/v1/chat/completions
  -> ILaaS
```

The wrapper injects an `OPENCODE_CONFIG_CONTENT` provider using `@ai-sdk/openai-compatible`. OpenCode model names use:

```text
ilaas/<ilaas-slug>
```

The wrapper accepts raw ILaaS slugs and rewrites them automatically.

## Shared Model Catalog

The refresh command queries ILaaS `/v1/models` and updates both LiteLLM and Codex metadata:

```bash
python3 -m ilaas_agents.cli refresh-models
```

Generated files:

```text
~/.config/litellm/ilaas-mistral.yaml
~/.codex-ilaas/model-catalogs/ilaas-mistral.json
```

Claude and OpenCode wrappers read the same catalog for model listing and configuration generation.
