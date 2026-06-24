# Compatibility and Limits

ILaaS Agent is a pragmatic bridge, not a full reimplementation of every native agent API.

## Tested Architecture

```text
ILaaS
  <- LiteLLM /v1/chat/completions
    <- Codex Responses proxy
    <- Claude Messages proxy
    <- OpenCode OpenAI-compatible provider
```

The reliable upstream path validated for ILaaS is Chat Completions. The local proxies translate the agent-specific protocol shapes into that path.

## Minimal Proxy Scope

The Codex and Claude Code proxies are intentionally minimal:

- Codex `/v1/responses` is translated to LiteLLM `/v1/chat/completions`.
- Claude `/v1/messages` is translated to LiteLLM `/v1/chat/completions`.
- Common text output and basic tool-call flows are supported.
- The Codex proxy calls upstream with `stream: false` and emits a Responses-shaped result to Codex.
- The proxies are not complete OpenAI Responses or Anthropic Messages implementations.
- Native token-by-token streaming semantics are not guaranteed.

This is enough for the tested agent workflows, but it should be treated as a compatibility layer rather than a drop-in API server.

## Version Matrix

Current validation is Linux-first.

| Component | Status |
| --- | --- |
| Codex CLI | Tested with `wire_api = "responses"` and `supports_websockets = false`; originally debugged against Codex CLI `v0.141.0`. |
| Claude Code | Tested through the local Anthropic Messages proxy with ILaaS model slugs rewritten to `claude-ilaas-<slug>`. |
| OpenCode | Tested through an OpenAI-compatible provider generated with `OPENCODE_CONFIG_CONTENT`. |
| LiteLLM | Installed in a dedicated local virtual environment by `install.py`; exact upstream versions should be recorded for release builds. |
| Linux | Validated locally. |
| macOS | Designed but not yet validated end to end. |
| Windows WSL2 | Recommended Windows path, pending full validation. |
| Windows native | Wrapper generation exists, but native agent behavior is not yet validated. |

## Port Checks

Default local ports:

```text
LiteLLM      127.0.0.1:4000
Codex proxy 127.0.0.1:4001
Claude proxy 127.0.0.1:4002
```

If a port is already open, ILaaS Agent verifies the expected HTTP endpoint before reusing it:

- LiteLLM: `/v1/models`
- Codex proxy: `/health`
- Claude proxy: `/health`

If another service owns the port, stop that service or set `LITELLM_PORT`, `RESPONSES_PORT`, or `CLAUDE_ILAAS_PORT`.

## Codex Sandbox

The installer writes a Codex sandbox mode to `~/.codex-ilaas/config.toml`.

By default, this project keeps:

```toml
sandbox_mode = "danger-full-access"
```

That default avoids Linux bubblewrap/AppArmor user namespace failures seen with Codex on some systems, but it disables Codex filesystem sandboxing. To choose a safer mode when your system supports it:

```bash
python3 install.py --codex-sandbox-mode workspace-write
python3 install.py --codex-sandbox-mode read-only
```

You can also set:

```bash
export ILAAS_CODEX_SANDBOX_MODE=workspace-write
```

## Recommended Hardening Before Public Releases

- Add opt-in integration tests for tool-call round trips and upstream errors.
- Record the tested LiteLLM, Codex CLI, Claude Code, and OpenCode versions for each release.
- Package the Python code so installed wrappers do not depend on keeping the Git clone in place.
- Validate macOS, WSL2, and Windows native behavior separately.
