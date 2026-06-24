import contextlib
import io
import unittest
from unittest import mock

from ilaas_agents import deps


class DepsTest(unittest.TestCase):
    def test_missing_agents_selects_missing_only(self):
        def fake_status(spec):
            return (spec.key == "codex", "ok" if spec.key == "codex" else "missing")
        with mock.patch("ilaas_agents.deps.tool_status", side_effect=fake_status):
            missing = deps.missing_agents(["all"])
        self.assertEqual([item.key for item in missing], ["claude", "opencode"])

    def test_install_agents_uses_official_packages(self):
        def fake_status(spec):
            return (False, "missing")
        with mock.patch("ilaas_agents.deps.tool_status", side_effect=fake_status), \
             mock.patch("ilaas_agents.deps.npm_available", return_value=True), \
             mock.patch("subprocess.check_call") as check_call:
            with contextlib.redirect_stdout(io.StringIO()):
                deps.install_agents(["codex", "claude", "opencode"])
        commands = [call.args[0] for call in check_call.call_args_list]
        self.assertIn(["npm", "install", "-g", "@openai/codex"], commands)
        self.assertIn(["npm", "install", "-g", "@anthropic-ai/claude-code"], commands)
        self.assertIn(["npm", "install", "-g", "opencode-ai"], commands)


if __name__ == "__main__":
    unittest.main()
