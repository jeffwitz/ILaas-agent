# CODEX.md - ILaaS Agent Repo Notes

## Current State

This repository packages the local ILaaS integration for code agents:

- Codex CLI through a local Responses API compatibility proxy.
- Claude Code through a local Anthropic Messages API compatibility proxy.
- OpenCode through an OpenAI-compatible provider injected with `OPENCODE_CONFIG_CONTENT`.

The repository has already been pushed to:

```text
https://github.com/jeffwitz/ILaas-agent.git
```

Check current validated commits with:

```bash
git log --oneline --decorate -5
```

## Important Security Rule

Never commit a real ILaaS API key.

The generated local LiteLLM config contains the key and lives outside the repo:

```text
~/.config/litellm/ilaas-mistral.yaml
```

Before committing, run a quick scan such as:

```bash
rg -n "94cd|api_key:|Bearer [A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9]{20,}" .
```

Placeholders such as `TA_CLE_ILAAS_ICI` and `sk-local-dummy` are allowed.

## Main Commands

Install or refresh local configuration:

```bash
python install.py --non-interactive --skip-litellm-install
python -m ilaas_agents.cli refresh-models
```

Diagnostics:

```bash
Ilaas-doctor
python -m ilaas_agents.cli doctor
```

Server management:

```bash
Ilaas-servers status
Ilaas-servers start
Ilaas-servers stop
Ilaas-servers logs
```

Agent commands:

```bash
Ilaas-codex exec --skip-git-repo-check "Réponds exactement: OK"
Ilaas-claude -p --model qwen-3.6-35b-instruct "Réponds exactement: OK"
Ilaas-opencode run --model qwen-3.6-35b-instruct "Réponds exactement: OK"
```

Model listing:

```bash
Ilaas-claude --list-models
Ilaas-opencode --list-models
```

## Validated Locally

Validated on Linux:

```text
Codex CLI: OK, Responses proxy, tokens consumed.
Claude Code: OK with qwen-3.6-35b-instruct.
OpenCode: OK with qwen-3.6-35b-instruct and Read tool.
Ilaas-doctor: OK, with HTTP checks for LiteLLM and available proxies.
Ilaas-servers: start/status/stop OK for persistent proxy processes.
```

Known warning:

```text
Claude proxy port 4002 can be WARN in doctor when it is not running.
This is acceptable because the agent wrapper can start it on demand.
```

## Architecture

Core package:

```text
ilaas_agents/
  cli.py          shared entrypoint
  paths.py        OS-aware paths
  models.py       ILaaS model refresh and catalog generation
  config.py       Codex config generation
  install.py      installer
  wrappers.py     wrapper generation
  processes.py    portable process and port helpers
  runners.py      Codex / Claude / OpenCode runners and servers command
  doctor.py       diagnostics
```

Compatibility proxies:

```text
proxies/codex_ilaas_responses_proxy.py
proxies/claude_ilaas_messages_proxy.py
```

Root wrappers are intentionally thin:

```text
Ilaas-codex
Ilaas-claude
Ilaas-opencode
Ilaas-doctor
Ilaas-servers
```

They call:

```bash
python3 -m ilaas_agents.cli <command>
```

## Models

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

Reason: they may answer simple chat prompts, but their tool-calling path is weak or broken in the tested LiteLLM/ILaaS setups.

## Current CdC Progress

Done:

- Initial GitHub repo pushed.
- Multi-agent Python package created.
- Linux wrappers working.
- Install script working in non-interactive reuse mode.
- Model refresh working.
- Codex/Claude/OpenCode runners centralized in Python.
- Persistent server management added.
- `Ilaas-doctor` and `Ilaas-servers` wrappers added.

Partial:

- Multi-OS support: paths and wrappers are designed for Windows/macOS, but only Linux is validated.
- Doctor: checks files, commands, ports, LiteLLM `/v1/models`, and proxy `/health`; it does not run token-consuming prompts by default.
- Installer: still lacks `--prefix` and `--force` from the CdC.

Not done yet:

- Detailed `docs/*.md` files.
- Unit tests under `tests/`.
- GitHub Actions CI.
- Clean clone installation test with isolated home/config.
- macOS validation.
- Windows native validation.

## Recommended Next Implementation Steps

1. Add unit tests for `paths`, `models`, `wrappers`, and `opencode_config_content`.
2. Add smoke-test commands that intentionally consume a few tokens, separate from `doctor`.
3. Add `--prefix` and `--force` to `install.py`.
4. Create docs:
   - `docs/codex.md`
   - `docs/claude-code.md`
   - `docs/opencode.md`
   - `docs/windows.md`
   - `docs/troubleshooting.md`
5. Add GitHub Actions for syntax/unit tests without requiring an ILaaS key.
6. Test install from a fresh clone in `/tmp`.

## Development Checks

Run before commit:

```bash
python3 -m py_compile install.py ilaas_agents/*.py proxies/*.py
bash -n Ilaas-codex Ilaas-claude Ilaas-opencode Ilaas-doctor Ilaas-servers install.sh
Ilaas-doctor
Ilaas-opencode run --model qwen-3.6-35b-instruct "Réponds exactement: OK"
```

Optional token-consuming checks:

```bash
Ilaas-codex exec --skip-git-repo-check "Réponds exactement: OK"
Ilaas-claude -p --model qwen-3.6-35b-instruct "Réponds exactement: OK"
```

## Commit / Push

Use normal Git workflow:

```bash
git status --short --branch
git add ...
git commit -m "..."
git push
```
