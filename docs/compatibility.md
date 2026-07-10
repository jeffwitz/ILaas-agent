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
- The proxies are not complete OpenAI Responses or Anthropic Messages implementations.
- Both the Claude Messages and Codex Responses proxies stream token-by-token when the client requests `stream: true` (text deltas and tool-call argument fragments are forwarded live); the buffered single-completion path is kept for `stream: false`. An inter-chunk idle timeout (`ILAAS_PROXY_IDLE_TIMEOUT`, default 120 s) guards the streamed path; there is no total-duration cap while chunks flow.

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
- Codex proxy: `/health` with `service=ilaas-codex-responses-proxy`
- Claude proxy: `/health` with `service=ilaas-claude-messages-proxy`

If another service owns the port, stop that service or set `LITELLM_PORT`, `RESPONSES_PORT`, or `CLAUDE_ILAAS_PORT`.

Older ILaaS proxies that only return `{"ok": true}` are treated as stale and are not reused.

## Qwen Tool JSON Retry

`qwen-3.6-35b-instruct` can occasionally trigger a LiteLLM/OpenAI-compatible error when a generated tool-call argument string is malformed:

```text
Unterminated string starting at ...
```

For Qwen requests with tools, the Codex and Claude proxies retry once with an extra instruction requiring complete valid JSON tool arguments. If the retry also fails, the upstream error is returned.

The retry rules are declarative and shared by both proxies in `proxies/retry_policy.py`: a rule matches by model prefix, whether the request carries tools, and an error-body substring. The default table holds only the Qwen rule above; override or extend it by writing a JSON list of rule objects to `~/.config/ilaas-agent/retry-policies.json` (keys: `model_prefix`, `requires_tools`, `error_substring`, `corrective_message`). Each request retries at most once, and the retry is logged with the model and trigger.

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
- Add HTTP-level integration tests for streaming SSE and upstream error responses.
- Record the tested LiteLLM, Codex CLI, Claude Code, and OpenCode versions for each release.
- Complete package-first installation so generated wrappers do not depend on keeping the Git clone in place.
- Validate macOS, WSL2, and Windows native behavior separately.
