# CdC — ILaaS Agent Improvement Plan (v2)

Status: proposed. Supersedes the roadmap sections of the existing `CdC.md`
(which documented the initial build; this document plans the evolution).

Audit basis: full clone at commit `552503a` (34 commits), 78 unit tests
passing locally, CI green pipeline reviewed.

---

## 0. Assessment Summary

### What is solid (do not regress)

- **S1. Zero-dependency core.** All portable logic is stdlib Python; wrappers
  are 5-line shell shims. Keep this constraint for the runtime path.
- **S2. Signal / process discipline.** `processes.py` handles SIGINT ownership
  (child owns Ctrl-C, parent ignores during teardown, post-fork reset,
  Popen-handle reaping). This is correct and well-commented; treat as frozen.
- **S3. CI breadth.** Compile, `bash -n`, unittest, package install smoke,
  Sphinx `-W`, isolated-clone check. Keep all steps.
- **S4. Secret hygiene.** LiteLLM config chmod 0600, keys never in repo,
  `.gitignore` covers legacy key files, `CODEX.md` documents a pre-commit scan.
- **S5. Isolation.** Dedicated `CODEX_HOME`, `ILAAS_*_HOME` overrides for
  hermetic testing, hermetic unit tests.
- **S6. Harness versioning.** Agents, hooks, and MCP template live in
  `harness/` and are deployed by the CLI; a clone reproduces the setup.

### Defect inventory (drives the tickets below)

| ID | Severity | Finding |
| --- | --- | --- |
| D1 | P0 | Root-level `claude_ilaas_messages_proxy.py` and `codex_ilaas_responses_proxy.py` are **stale divergent copies** of `proxies/*` (missing `UpstreamHTTPError`, Qwen retry, service-name health field). Only `proxies/` is executed by `runners.py`; CI compiles both; `CODEX.md`/`CdC.md` still reference the root copies. The `codex-ilaas-responses-proxy` root shim adds a third entry point. |
| D2 | P0 | Personal absolute defaults `/home/jeff/Code/clef_api/{Ilaas.txt, GLM5.2.md, OPEN_ROUTER.md}` hardcoded in `install.py`, `glm52.py`, `openrouter.py` and documented in README / quickstart / provider docs. Repo is not usable as-is by anyone else. |
| D3 | P0 | No `LICENSE` file. Public repository is legally unreusable. |
| D4 | P1 | No true streaming in the two ILaaS proxies: upstream forced to `stream: false`, whole completion buffered under a hard 180 s timeout, then replayed as synthetic one-shot SSE. Long generations fail; interactive UX is frozen per turn. (The OpenRouter passthrough proxy *does* stream; only the ILaaS translation proxies are affected.) |
| D5 | P1 | Messages-proxy fidelity gaps: image and thinking blocks dropped silently; `tool_choice` ignored (always `auto` when tools present); `max_tokens` silently clamped to `ILAAS_CLAUDE_MAX_TOKENS` (default 4096); `stop_sequence` never reported as stop reason; `count_tokens` is `len(json)//4`. |
| D6 | P1 | OpenRouter tier catalog resolved by *most-recent-mtime* glob over `openrouter-*.json` — implicit global state; switching models silently changes tier routing for later sessions. |
| D7 | P1 | Qwen malformed-tool-JSON retry keyed on the literal substring `"Unterminated string"` + `qwen-` prefix; brittle, provider-specific, and doubles the cost of the failed call. Duplicated in both proxies. |
| D8 | P1 | Threat model of local ports undocumented: LiteLLM :4000 and the proxies accept any loopback client with a dummy key, so any local process/user can spend ILaaS tokens. Acceptable on single-user machines, must be stated (and optionally mitigated). |
| D9 | P2 | Identity system-prompt injected into **every** request ("If asked which model is active…") in both the Messages proxy and the OpenRouter proxy; permanent context pollution for a rarely-needed answer. Not opt-outable. |
| D10 | P2 | `tiers.assign_tier` name-regex heuristic (`70b|medium|max…`) is fragile and undocumented for users; no CLI to inspect/override tier assignment per model. |
| D11 | P2 | Tooling below the maintainer's usual standard elsewhere: no `ruff` config, no type-checking step (annotations are already largely present), no coverage reporting. Root proxies are untyped/unlinted legacy style. |
| D12 | P2 | Packaging identity split: PyPI name `ilaas-code-agents`, repo `ILaas-agent`, console script `ilaas-agent`; wheel ships `ilaas_agents` + `proxies` but **not** `harness/` assets nor wrappers, so "package-first install" advertised in README is incomplete. Static `version = 0.1.0`, no tags/releases. |
| D13 | P2 | `scripts/token_economy.py` prices hardcoded at top of file; no test coverage for the pricing/aggregation logic. |
| D14 | P2 | Docs drift: existing `CdC.md` describes the initial build and no longer matches the tree (harness, tiers, OpenRouter/GLM families); quickstart embeds personal paths (covered by D2 but needs a doc pass of its own). |

---

## 1. Lot A — Repository correctness (P0)

### Ticket A1 — Deduplicate the proxies

**Problem.** D1.

**Actions.**
1. Delete root `claude_ilaas_messages_proxy.py`, `codex_ilaas_responses_proxy.py`,
   and the `codex-ilaas-responses-proxy` shim. If external muscle memory
   requires them, replace each with a 3-line re-exec of the `proxies/` file,
   never a copy.
2. Update `CODEX.md`, `CdC.md`, `docs/interfaces.md` references.
3. Remove the root files from the CI compile list and from the
   `python -m py_compile` line in README "Development Checks".

**Acceptance.**
- `git grep -l "claude_ilaas_messages_proxy" -- ':!proxies' ':!tests'` returns
  only docs that explicitly say `proxies/…`.
- CI green; `diff` divergence impossible by construction (single source).

### Ticket A2 — Portable default key locations

**Problem.** D2.

**Actions.**
1. Introduce `paths.keys_dir()` → `${ILAAS_KEYS_DIR:-~/.config/ilaas-agent/keys}`.
2. New defaults: `keys_dir()/ilaas.token`, `keys_dir()/glm52.token`,
   `keys_dir()/openrouter.token`. Env overrides (`*_TOKEN_FILE`, `*_API_KEY`)
   keep precedence, unchanged.
3. Backward compatibility: if the new default is absent and the legacy
   `/home/jeff/...` path exists **on this machine**, read it and print a
   one-line deprecation notice. Remove the fallback after one release.
4. Scrub README, quickstart, `docs/ilaas.md`, `docs/openrouter.md` of the
   personal paths; document the new layout and `chmod 600` expectation.
5. `Ilaas-doctor`: add a check reporting which key source was resolved
   (env / file path) without printing the key.

**Acceptance.**
- `git grep "/home/jeff"` returns nothing.
- Fresh-user flow works: `export ILAAS_API_KEY=… && python3 install.py` and
  file-based flow both pass `Ilaas-doctor`.
- Unit tests cover the resolution precedence (env > explicit file > default).

### Ticket A3 — License

**Problem.** D3.

**Actions.** Choose a license (MIT or Apache-2.0 recommended for tooling;
Apache-2.0 if patent grant matters), add `LICENSE`, set
`project.license` in `pyproject.toml`, mention it in README.

**Acceptance.** GitHub displays the license badge; `pip show` reports it.

---

## 2. Lot B — Proxy quality (P1)

### Ticket B1 — True SSE streaming in the ILaaS proxies

**Problem.** D4. This is the highest-value UX change in the repo.

**Actions.**
1. In `proxies/claude_ilaas_messages_proxy.py`: when the client asks
   `stream: true`, send `stream: true` upstream, parse the Chat Completions
   SSE incrementally (stdlib: iterate the response socket line-by-line), and
   translate deltas on the fly to Anthropic events
   (`message_start`, `content_block_start/delta/stop` for text and
   `input_json_delta` for tool calls, `message_delta`, `message_stop`).
   Keep the existing buffered path for `stream: false`.
2. Same for the Codex Responses proxy with Responses-API events.
3. Replace the fixed 180 s `urlopen` timeout with: connect timeout ~10 s +
   inter-chunk idle timeout (env `ILAAS_PROXY_IDLE_TIMEOUT`, default 120 s);
   no total-duration cap while chunks flow.
4. Error mapping mid-stream: upstream failure after `message_start` must emit
   a terminal `error`/`message_stop` event, not a truncated socket.
5. Tests: fake upstream `ThreadingHTTPServer` emitting scripted SSE (happy
   path, tool-call deltas split across chunks, mid-stream error, idle
   timeout). This is the main test investment of the plan.

**Acceptance.**
- Tokens appear incrementally in Claude Code / Codex CLI.
- A generation longer than 180 s completes.
- New streaming tests pass in CI without network access.

**Risk note.** Incremental translation of tool-call argument deltas is the
hard part (arguments arrive as partial JSON strings). Acceptable first
iteration: stream text deltas live, buffer tool-call arguments per call and
emit the `input_json_delta` once complete — already a large UX win.

### Ticket B2 — Messages-proxy fidelity

**Problem.** D5.

**Actions.**
1. Honor `tool_choice` (map `auto`/`any`/`tool:{name}` to Chat Completions
   `auto`/`required`/`{"type":"function","function":{"name":…}}`).
2. Stop dropping modalities silently: on image or thinking blocks, log one
   warning per request and insert a `[unsupported block omitted: image]`
   text marker so the model and the user know.
3. Make the 4096 cap visible: keep the clamp but log when it applies; raise
   the default (8192) after checking ILaaS-side limits.
4. Report `stop_sequence` when `finish_reason == "stop"` with a matched
   client `stop_sequences` entry (best effort).
5. `count_tokens`: keep the heuristic but label it — return the estimate and
   log that it is approximate. (A real tokenizer would break the zero-dep
   constraint; not worth it.)

**Acceptance.** Unit tests for each mapping; a Claude Code session with a
forced tool choice behaves as forced.

### Ticket B3 — Retry policy consolidation

**Problem.** D7.

**Actions.**
1. Extract a single `retry_policy.py` in `proxies/` (shared via import) with
   a declarative table: `(model_prefix, error_substring) → corrective system
   message`, loaded from an optional JSON at
   `~/.config/ilaas-agent/retry-policies.json`.
2. Add a per-request budget: at most one retry; log the retry with model +
   trigger so failures are diagnosable.
3. Long term: evaluate moving this to LiteLLM's own retry/fallback hooks and
   deleting the proxy-side code.

**Acceptance.** The Qwen behavior is preserved by the default table; the
substring lives in exactly one place; tests cover match / no-match / single
retry.

### Ticket B4 — Explicit active tier catalog

**Problem.** D6.

**Actions.**
1. Replace the mtime-glob selection with an explicit state file
   `cache/ilaas-agent/openrouter-active.json` (`{"catalog": "openrouter-<slug>.json"}`)
   written by the launcher when a model is selected.
2. `ilaas-agent tiers show [provider]` prints resolved tier → slug with the
   source of each (env / catalog / default). Extend the existing CLI.
3. Keep `OPENROUTER_TIER_CATALOG` override untouched.

**Acceptance.** Alternating `openrouter-codex -m A` then `-m B` then
launching `openrouter-claude` uses the documented resolution, not the newest
file; `tiers show` output matches actual routing.

### Ticket B5 — Document (and optionally harden) the local threat model

**Problem.** D8.

**Actions.**
1. Add a "Local security model" section in `docs/troubleshooting.md` or a new
   `docs/security.md`: loopback-only binding, but any local process can use
   the ports; multi-user machines should not run this.
2. Optional hardening (behind `ILAAS_PROXY_SHARED_SECRET`): proxies check the
   `authorization` header against the secret and the launchers inject it.
   Off by default to preserve simplicity.

**Acceptance.** Doc merged; if the secret is implemented, a test proves a
wrong bearer gets 401 and launchers still work end-to-end.

---

## 3. Lot C — Engineering hygiene (P2)

### Ticket C1 — Lint + type-check in CI

**Problem.** D11.

**Actions.**
1. `ruff` config in `pyproject.toml` (line length, `from __future__` import
  enforcement, no unused). Fix the fallout once.
2. `mypy --strict` (or pyright) on `ilaas_agents/`; `proxies/` may start at
   non-strict. Annotations are mostly present already; expected cost is low.
3. Add both to CI before the unit-test step. Optionally add `coverage run -m
   unittest` + threshold (start at current level, ratchet).

**Acceptance.** CI fails on lint/type regressions; zero suppressions without
a comment.

### Ticket C2 — Packaging identity and completeness

**Problem.** D12.

**Actions.**
1. Decide the installation story: **repo-first** (git clone is the supported
   path; the wheel is a dev convenience) — recommend this, it matches
   reality. State it in README and remove "future package-first installs"
   phrasing, or:
2. If package-first is wanted later: ship `harness/` and wrapper templates as
   package data, generate wrappers from the installed package, align names
   (`ilaas-agent` everywhere), derive version from git tags
   (`setuptools-scm`), and start tagging releases.
3. Either way: create a `v0.1.0` git tag now so the current validated state
   is addressable, and add a minimal `CHANGELOG.md`.

**Acceptance.** README installation story is unambiguous; a tag exists;
`pip install .` behavior matches what the docs claim.

### Ticket C3 — Identity injection made opt-out

**Problem.** D9.

**Actions.** Wrap both injection sites behind
`ILAAS_INJECT_MODEL_IDENTITY` (default `1` to preserve behavior); document
the trade-off (accurate self-identification vs. per-request context cost).

**Acceptance.** With the env var at `0`, the upstream payload contains no
injected instruction (unit test on `inject_model_identity` /
`chat_messages_from_anthropic`).

### Ticket C4 — Tier tooling

**Problem.** D10.

**Actions.**
1. `ilaas-agent tiers set <provider> <tier> <slug>` writing the catalog
   (thin wrapper over `tiers.apply` with an explicit mapping).
2. Document the heuristic table in `docs/tiers.md` (it currently lives only
   in code) and mark it as fallback, not source of truth.

**Acceptance.** A user can pin `coder` to a slug without editing JSON by
hand; `tiers show` (B4) reflects it.

### Ticket C5 — Token-economy config + tests

**Problem.** D13.

**Actions.** Move the price table to
`~/.config/ilaas-agent/prices.json` with the current values as embedded
defaults; add unit tests for session parsing and economy math (fixture
transcripts in `tests/data/`).

**Acceptance.** Editing the JSON changes the report without touching code;
tests cover at least one multi-model session fixture.

### Ticket C6 — Documentation pass

**Problem.** D14.

**Actions.**
1. Rewrite `CdC.md` as a short pointer: initial-build record moved to
   `docs/history.md` (or archived), this document becomes the living plan.
2. Quickstart / provider docs updated for A2 paths.
3. Add a one-screen architecture diagram (ports 4000/4001/4002/4012, which
   process starts what, persistent vs per-session) in `docs/interfaces.md`.

**Acceptance.** No doc references a file or path that does not exist; Sphinx
`-W` still green.

---

## 4. Lot D — Later / exploratory (unscheduled)

- **D-1. Windows native validation.** `install.ps1` and the wine check exist;
  promote Windows from "planned" only after a real pass (process groups,
  `taskkill` path, PowerShell wrappers).
- **D-2. Prompt-caching awareness.** The Messages proxy strips
  `cache_control`; if ILaaS/LiteLLM ever support caching, forwarding it is
  a direct cost win for the supervisor tier.
- **D-3. LiteLLM-native replacement of the Codex proxy.** LiteLLM has been
  growing Responses-API support; re-evaluate periodically whether
  `codex_ilaas_responses_proxy.py` can be deleted.
- **D-4. Harness metrics.** `token_economy.py` measures cost; nothing yet
  measures delegation *quality* (how often the supervisor delegates, subagent
  failure rate). A small transcript analyzer would guide tier tuning.

---

## 5. Sequencing and effort

| Order | Tickets | Rationale | Rough effort |
| --- | --- | --- | --- |
| 1 | A1, A2, A3 | Unblocks external users; near-zero risk | 0.5–1 day |
| 2 | B1 | Largest UX gain; largest risk — do while the codebase is small | 2–4 days incl. tests |
| 3 | B2, B3, B4 | Fidelity + determinism; builds on B1's test harness | 1–2 days |
| 4 | B5, C1, C2 | Posture + hygiene; C1 before further feature work | 1 day |
| 5 | C3–C6 | Comfort and documentation | 1–2 days |
| — | Lot D | Opportunistic | — |

## 6. Non-goals (explicit)

- No runtime dependency additions (FastAPI, httpx, tiktoken): the zero-dep
  stdlib constraint is a feature of this repo and B1 is feasible within it.
- No rewrite of `processes.py` signal handling (S2 frozen).
- No attempt at full Anthropic/OpenAI API completeness; the proxies remain
  *minimal compatibility layers* — the goal of Lot B is honesty and
  robustness within that scope, not coverage.
