# Changelog

All notable changes to ILaaS Agent are recorded here. The format is
loosely based on [Keep a Changelog](https://keepachangelog.com/), and the
project adheres to [Semantic Versioning](https://semver.org/).

## [0.1.0] — 2026-07-10

First addressed release: the validated local ILaaS / OpenRouter code-agent
tooling, cloned and run from the repository.

### Added
- Local LiteLLM gateway and adapters for Codex CLI (Responses), Claude Code
  (Messages), and OpenCode (OpenAI-compatible).
- GLM 5.2 and OpenRouter direct-API launchers alongside the ILaaS path.
- Per-provider tier map (supervisor / coder / small) with `tiers`
  list/show/suggest/apply/set CLI and an explicit active-catalog state file.
- True token-by-token SSE streaming in both ILaaS proxies (text deltas and
  tool-call argument fragments forwarded live), with inter-chunk idle
  timeout and mid-stream error mapping.
- Portable key locations under `~/.config/ilaas-agent/keys/` with a
  deprecation fallback to legacy paths; `Ilaas-doctor` reports the resolved
  key source per provider.
- Configurable retry policy (`proxies/retry_policy.py`, overridable via
  `~/.config/ilaas-agent/retry-policies.json`) and token-economy pricing
  (`~/.config/ilaas-agent/prices.json`).
- GLM-supervisor + DeepSeek-coder harness (agents, hooks, MCP) deployed by
  `ilaas-agent harness install`.
- GPL-2.0-or-later license.

### Installation

Repo-first: `git clone` is the supported path; `pip install .` is a
development convenience (the wheel does not ship the `harness/` assets or
wrapper templates).

[0.1.0]: https://github.com/jeffwitz/ILaas-agent/releases/tag/v0.1.0
