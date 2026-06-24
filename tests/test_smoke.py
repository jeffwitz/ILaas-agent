import argparse
import contextlib
import io
import unittest
from unittest import mock

from ilaas_agents import smoke


class SmokeTest(unittest.TestCase):
    def test_smoke_all_calls_all_agents(self):
        args = argparse.Namespace(agent="all", model="qwen-3.6-35b-instruct", tool_test=False)
        with mock.patch("ilaas_agents.smoke.run_agent", return_value=0) as run_agent:
            with contextlib.redirect_stdout(io.StringIO()):
                status = smoke.run(args)
        self.assertEqual(status, 0)
        self.assertEqual(run_agent.call_count, 3)

    def test_claude_tool_test_adds_read_permissions(self):
        with mock.patch("ilaas_agents.runners.run_claude", return_value=0) as run_claude:
            with contextlib.redirect_stdout(io.StringIO()):
                status = smoke.run_agent("claude", "qwen-3.6-35b-instruct", True)
        self.assertEqual(status, 0)
        argv = run_claude.call_args.args[0]
        self.assertIn("--allowedTools", argv)
        self.assertIn("Read", argv)


if __name__ == "__main__":
    unittest.main()
