import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from ilaas_agents import harness


class HarnessTest(unittest.TestCase):
    def test_codebase_memory_bin_env_wins(self):
        with mock.patch.dict(os.environ, {"CODEBASE_MEMORY_MCP_BIN": "/custom/cbm"}, clear=False):
            self.assertEqual(harness.codebase_memory_bin(), "/custom/cbm")

    def test_codebase_memory_bin_returns_none_when_missing(self):
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch(
            "ilaas_agents.harness.shutil.which", return_value=None
        ), mock.patch("ilaas_agents.harness.paths.home", return_value=Path("/nonexistent/home")):
            self.assertIsNone(harness.codebase_memory_bin())

    def test_render_replaces_placeholder(self):
        rendered = harness._render('BIN="__CODEBASE_MEMORY_BIN__"', "/path/to/cbm")
        self.assertEqual(rendered, 'BIN="/path/to/cbm"')

    def test_render_no_placeholder_passthrough(self):
        self.assertEqual(harness._render("no placeholder here", "/x"), "no placeholder here")

    @contextmanager
    def _fake_layout(self):
        tmp = Path(tempfile.mkdtemp())
        or_home = tmp / "claude_openrouter"
        claude_home = tmp / "claude"
        or_home.mkdir()
        claude_home.mkdir()
        with mock.patch("ilaas_agents.harness.paths.home", return_value=tmp):
            yield (or_home, claude_home)

    def test_install_harness_deploys_agents_hooks_and_mcp(self):
        with self._fake_layout() as (or_home, claude_home):
            deployed = harness.install_harness(
                openrouter_home=or_home, claude_home=claude_home, bin_path="/fake/cbm"
            )
            # agents deployed into the openrouter home
            self.assertTrue(any(p.endswith("ctx-pro.md") for p in deployed["agents"]))
            self.assertTrue(any(p.endswith("code-pro.md") for p in deployed["agents"]))
            self.assertTrue(any(p.endswith("code-flash.md") for p in deployed["agents"]))
            for p in deployed["agents"]:
                self.assertIn(str(or_home / "agents"), p)
            # hooks deployed into ~/.claude/hooks, rendered + executable
            gate = claude_home / "hooks" / "cbm-code-discovery-gate"
            self.assertTrue(gate.exists())
            self.assertIn("/fake/cbm", gate.read_text())
            self.assertTrue(gate.stat().st_mode & 0o111)
            reminder = claude_home / "hooks" / "cbm-session-reminder"
            self.assertTrue(reminder.exists())
            # mcp config rendered with the bin path
            mcp = json.loads((claude_home / ".mcp.json").read_text())
            self.assertEqual(mcp["mcpServers"]["codebase-memory-mcp"]["command"], "/fake/cbm")
            # symlinks created from the openrouter home
            self.assertTrue((or_home / "hooks").is_symlink())
            self.assertTrue((or_home / ".mcp.json").is_symlink())

    def test_install_harness_idempotent(self):
        with self._fake_layout() as (or_home, claude_home):
            harness.install_harness(openrouter_home=or_home, claude_home=claude_home, bin_path="/fake/cbm")
            deployed2 = harness.install_harness(
                openrouter_home=or_home, claude_home=claude_home, bin_path="/fake/cbm2"
            )
            # second install rewrites files (new bin path) without duplicating symlinks
            gate = (claude_home / "hooks" / "cbm-code-discovery-gate").read_text()
            self.assertIn("/fake/cbm2", gate)
            self.assertEqual(deployed2["symlinks"], [])  # symlinks already existed

    def test_install_harness_raises_when_bin_missing(self):
        with self._fake_layout() as (or_home, claude_home):
            with mock.patch.dict(os.environ, {}, clear=True), mock.patch(
                "ilaas_agents.harness.shutil.which", return_value=None
            ):
                with self.assertRaises(SystemExit):
                    harness.install_harness(
                        openrouter_home=or_home, claude_home=claude_home, bin_path=None
                    )


if __name__ == "__main__":
    unittest.main()
