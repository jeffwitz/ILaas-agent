# ILaaS Agent

Installable local tooling to use ILaaS models with code agents:

- Codex CLI
- Claude Code
- OpenCode

The current implementation uses LiteLLM as the local OpenAI-compatible gateway, plus small compatibility proxies where an agent expects a different API shape.

```text
ILaaS
  <- LiteLLM /v1/chat/completions
    <- Codex Responses proxy for Codex CLI
    <- Claude Messages proxy for Claude Code
    <- OpenCode OpenAI-compatible provider directly
```

## Quick Start

```bash
git clone https://github.com/jeffwitz/ILaas-agent.git
cd ILaas-agent
python install.py
```

The installer never writes API keys into the repository. Provide the ILaaS key with:

```bash
ILAAS_API_KEY=... python install.py
```

or enter it interactively when prompted.

After installation:

```bash
Ilaas-codex exec --skip-git-repo-check "Réponds exactement: OK"
Ilaas-claude -p --model qwen-3.6-35b-instruct "Réponds exactement: OK"
Ilaas-opencode run --model qwen-3.6-35b-instruct "Réponds exactement: OK"
```

## Shared CLI

The wrappers call a shared Python CLI:

```bash
python -m ilaas_agents.cli doctor
python -m ilaas_agents.cli refresh-models
python -m ilaas_agents.cli servers status
python -m ilaas_agents.cli servers start
python -m ilaas_agents.cli servers stop
```

`servers start` launches LiteLLM plus the Codex and Claude compatibility proxies as persistent background services. The agent wrappers can also start only what they need for a single run.

## Model Refresh

```bash
python -m ilaas_agents.cli refresh-models
```

This updates:

```text
~/.config/litellm/ilaas-mistral.yaml
~/.codex-ilaas/model-catalogs/ilaas-mistral.json
```

## Recommended Models

For code-agent use:

```text
qwen-3.6-35b-instruct
mistral-medium-latest
gemma-4-31b
```

Currently not recommended for code agents:

```text
llama-3.1-8b
llama-3.3-70b
```

They may answer simple chat prompts, but their tool-calling path is weak or broken in the tested LiteLLM/ILaaS setups.

## Status

The Linux path is validated locally with the Python runners:

```text
Codex CLI -> OK, Responses proxy, tokens consumed
Claude Code -> OK with qwen-3.6-35b-instruct
OpenCode -> OK with qwen-3.6-35b-instruct and Read tool
```

Windows native support is planned but should be considered experimental until tested. On Windows, WSL2 is the recommended path for now.

See [CdC.md](CdC.md) for the full implementation plan.
