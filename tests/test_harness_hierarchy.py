import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ilaas_agents import harness


_HIERARCHY = {
    "provider": "openrouter",
    "model_prefix": "claude-openrouter-",
    "supervisor": {
        "tier": "supervisor",
        "default_slug": "z-ai/glm-5.2",
        "display": "GLM 5.2",
    },
    "agents": {
        "ctx-pro": {
            "tier": "coder",
            "default_slug": "deepseek/deepseek-v4-pro",
            "display": "DeepSeek V4 Pro",
            "role": "verbose MCP/graph synthesis (read-only)",
        },
        "code-pro": {
            "tier": "coder",
            "default_slug": "deepseek/deepseek-v4-pro",
            "display": "DeepSeek V4 Pro",
            "role": "implementation / refactor / tests",
        },
        "code-flash": {
            "tier": "small",
            "default_slug": "deepseek/deepseek-v4-flash",
            "display": "DeepSeek V4 Flash",
            "role": "trivial mechanical edits",
        },
    },
}


class HierarchyLoadingTest(unittest.TestCase):
    def test_load_hierarchy_returns_supervisor_and_agents(self):
        with mock.patch.object(harness, "HIERARCHY_PATH", Path(__file__)):
            pass  # Cannot mock HIERARCHY_PATH directly since it's a module constant used at call time.
        # Instead, write a temp file and point to it.
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(_HIERARCHY, f)
            tmp_path = f.name
        try:
            with mock.patch.object(harness, "HIERARCHY_PATH", Path(tmp_path)):
                hierarchy = harness.load_hierarchy()
            self.assertIn("supervisor", hierarchy)
            self.assertEqual(hierarchy["supervisor"]["display"], "GLM 5.2")
            self.assertEqual(len(hierarchy["agents"]), 3)
            self.assertIn("ctx-pro", hierarchy["agents"])
            self.assertIn("code-pro", hierarchy["agents"])
            self.assertIn("code-flash", hierarchy["agents"])
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_load_hierarchy_missing_file_raises_systemexit(self):
        with mock.patch.object(harness, "HIERARCHY_PATH", Path("/nonexistent/hierarchy.json")):
            with self.assertRaises(SystemExit):
                harness.load_hierarchy()

    def test_load_hierarchy_invalid_json_raises_systemexit(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("not valid json {{{")
            tmp_path = f.name
        try:
            with mock.patch.object(harness, "HIERARCHY_PATH", Path(tmp_path)):
                with self.assertRaises(SystemExit):
                    harness.load_hierarchy()
        finally:
            Path(tmp_path).unlink(missing_ok=True)


class ResolveAgentModelTest(unittest.TestCase):
    def test_resolve_agent_model_catalog_none_falls_back_to_default_slug(self):
        with mock.patch("ilaas_agents.harness.tiers.resolve", return_value=None):
            model = harness.resolve_agent_model(_HIERARCHY, "ctx-pro")
        self.assertEqual(model, "claude-openrouter-deepseek/deepseek-v4-pro")

    def test_resolve_agent_model_catalog_overrides_slug(self):
        with mock.patch("ilaas_agents.harness.tiers.resolve", return_value="custom/slug"):
            model = harness.resolve_agent_model(_HIERARCHY, "ctx-pro")
        self.assertEqual(model, "claude-openrouter-custom/slug")

    def test_resolve_agent_model_code_pro(self):
        with mock.patch("ilaas_agents.harness.tiers.resolve", return_value=None):
            model = harness.resolve_agent_model(_HIERARCHY, "code-pro")
        self.assertEqual(model, "claude-openrouter-deepseek/deepseek-v4-pro")

    def test_resolve_agent_model_code_flash(self):
        with mock.patch("ilaas_agents.harness.tiers.resolve", return_value=None):
            model = harness.resolve_agent_model(_HIERARCHY, "code-flash")
        self.assertEqual(model, "claude-openrouter-deepseek/deepseek-v4-flash")


class ResolveSupervisorDisplayTest(unittest.TestCase):
    def test_resolve_supervisor_display(self):
        self.assertEqual(harness.resolve_supervisor_display(_HIERARCHY), "GLM 5.2")


class RenderRosterTest(unittest.TestCase):
    def test_render_roster_contains_supervisor_and_agents(self):
        roster = harness.render_roster(_HIERARCHY)
        self.assertIn("supervisor", roster)
        self.assertIn("ctx-pro", roster)
        self.assertIn("code-pro", roster)
        self.assertIn("code-flash", roster)
        self.assertIn("GLM 5.2", roster)
        self.assertIn("DeepSeek V4 Pro", roster)
        self.assertIn("DeepSeek V4 Flash", roster)
        self.assertIn("verbose MCP/graph synthesis", roster)
        self.assertIn("implementation / refactor / tests", roster)
        self.assertIn("trivial mechanical edits", roster)


class AgentRenderingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(str(self.tmp), ignore_errors=True)

    def _write_agent_template(self, name: str, model_line: str, body: str = "body content\n") -> Path:
        src = self.tmp / f"{name}.md"
        src.write_text(f"---\nname: {name}\n{model_line}\ncolor: cyan\n---\n\n{body}")
        return src

    def _agent_placeholders(self, name: str) -> dict[str, str]:
        with mock.patch("ilaas_agents.harness.tiers.resolve", return_value=None):
            model = harness.resolve_agent_model(_HIERARCHY, name)
        return {
            "__MODEL__": model,
            "__SELF_DISPLAY__": _HIERARCHY["agents"][name]["display"],
            "__SUPERVISOR_DISPLAY__": harness.resolve_supervisor_display(_HIERARCHY),
        }

    def test_agent_rendered_with_concrete_model_no_placeholder(self):
        src = self._write_agent_template("ctx-pro", "model: __MODEL__")
        dst = self.tmp / "out" / "ctx-pro.md"
        placeholders = self._agent_placeholders("ctx-pro")
        harness._install_file(src, dst, bin_path=None, placeholders=placeholders)
        content = dst.read_text()
        self.assertIn("model: claude-openrouter-deepseek/deepseek-v4-pro", content)
        self.assertNotIn("__MODEL__", content)

    def test_agent_rendered_with_self_and_supervisor_display(self):
        body = (
            "description: Uses __SELF_DISPLAY__.\n"
            "Supervisor is __SUPERVISOR_DISPLAY__.\n"
        )
        src = self._write_agent_template("ctx-pro", "model: __MODEL__", body=body)
        dst = self.tmp / "out" / "ctx-pro.md"
        placeholders = self._agent_placeholders("ctx-pro")
        harness._install_file(src, dst, bin_path=None, placeholders=placeholders)
        content = dst.read_text()
        self.assertIn("model: claude-openrouter-deepseek/deepseek-v4-pro", content)
        self.assertIn("DeepSeek V4 Pro", content)
        self.assertIn("GLM 5.2", content)
        self.assertNotIn("__MODEL__", content)
        self.assertNotIn("__SELF_DISPLAY__", content)
        self.assertNotIn("__SUPERVISOR_DISPLAY__", content)

    def test_agent_rendered_no_residual_placeholders(self):
        """Each agent's rendered output must have zero residual placeholders."""
        body = (
            "description: Uses __SELF_DISPLAY__.\n"
            "Supervisor is __SUPERVISOR_DISPLAY__.\n"
        )
        for name in ("ctx-pro", "code-pro", "code-flash"):
            with self.subTest(agent=name):
                src = self._write_agent_template(name, "model: __MODEL__", body=body)
                dst = self.tmp / "out" / f"{name}.md"
                placeholders = self._agent_placeholders(name)
                harness._install_file(src, dst, bin_path=None, placeholders=placeholders)
                content = dst.read_text()
                self.assertNotIn("__SELF_DISPLAY__", content)
                self.assertNotIn("__SUPERVISOR_DISPLAY__", content)
                self.assertNotIn("__MODEL__", content)
                self.assertIn(f"model: claude-openrouter-", content)
                self.assertIn(_HIERARCHY["agents"][name]["display"], content)
                self.assertIn(_HIERARCHY["supervisor"]["display"], content)

    def test_hook_rendered_with_roster_and_supervisor_display(self):
        src = self.tmp / "hook.sh"
        src.write_text("supervisor: __SUPERVISOR_DISPLAY__\n__ROSTER__\n")
        dst = self.tmp / "out" / "hook.sh"
        roster = harness.render_roster(_HIERARCHY)
        display = harness.resolve_supervisor_display(_HIERARCHY)
        harness._install_file(
            src, dst, bin_path=None, executable=True,
            placeholders={"__ROSTER__": roster, "__SUPERVISOR_DISPLAY__": display},
        )
        content = dst.read_text()
        self.assertIn("GLM 5.2", content)
        self.assertIn("ctx-pro", content)
        self.assertIn("code-pro", content)
        self.assertIn("code-flash", content)
        self.assertNotIn("__ROSTER__", content)
        self.assertNotIn("__SUPERVISOR_DISPLAY__", content)


if __name__ == "__main__":
    unittest.main()