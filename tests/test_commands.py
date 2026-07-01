import os
import tempfile
import unittest
from pathlib import Path

from ilaas_agents import commands, paths


class EconomyCommandTest(unittest.TestCase):
    def test_content_embeds_script_path_and_no_hardcoded_home(self):
        script = Path("/opt/repo/scripts/token_economy.py")
        text = commands.economy_command_content(script)
        self.assertIn(str(script), text)
        self.assertIn("--economy", text)
        # Portable: the projects dir is not hardcoded to a user home.
        self.assertNotIn("/.claude_openrouter/projects", text)
        self.assertIn("$CLAUDE_CONFIG_DIR/projects", text)

    def test_frontmatter_allows_only_the_script(self):
        text = commands.economy_command_content(Path("/opt/repo/scripts/token_economy.py"))
        self.assertIn("allowed-tools: Bash(python3 /opt/repo/scripts/token_economy.py:*)", text)

    def test_install_writes_into_openrouter_commands_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["ILAAS_HOME"] = tmp
            try:
                target = commands.install_economy_command()
            finally:
                del os.environ["ILAAS_HOME"]
            self.assertTrue(target.is_file())
            self.assertEqual(target, Path(tmp) / ".claude_openrouter" / "commands" / "economy.md")
            self.assertIn("token_economy.py", target.read_text())

    def test_command_path_follows_openrouter_home_override(self):
        os.environ["CLAUDE_OPENROUTER_HOME"] = "/custom/home"
        try:
            self.assertEqual(
                commands.economy_command_path(),
                Path("/custom/home") / "commands" / "economy.md",
            )
            self.assertEqual(paths.claude_openrouter_home(), Path("/custom/home"))
        finally:
            del os.environ["CLAUDE_OPENROUTER_HOME"]


if __name__ == "__main__":
    unittest.main()
