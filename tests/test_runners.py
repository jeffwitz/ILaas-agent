import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ilaas_agents import runners


class RunnersTest(unittest.TestCase):
    def test_rewrite_opencode_model_args(self):
        args = runners.rewrite_opencode_model_args(["run", "--model", "qwen-3.6-35b-instruct", "hi"])
        self.assertEqual(args, ["run", "--model", "ilaas/qwen-3.6-35b-instruct", "hi"])

    def test_rewrite_claude_model_args(self):
        args, selected = runners.rewrite_claude_model_args(["-p", "--model", "qwen-3.6-35b-instruct", "hi"])
        self.assertEqual(selected, "claude-ilaas-qwen-3.6-35b-instruct")
        self.assertIn("claude-ilaas-qwen-3.6-35b-instruct", args)

    def test_opencode_config_content_uses_catalog(self):
        with tempfile.TemporaryDirectory() as tmp:
            catalog = Path(tmp) / "catalog.json"
            catalog.write_text(json.dumps({"models": [{"slug": "qwen-3.6-35b-instruct", "display_name": "Qwen", "context_window": 1234}]}))
            with mock.patch.dict(os.environ, {"ILAAS_MODEL_CATALOG": str(catalog)}, clear=False):
                content = runners.opencode_config_content(runners.RuntimeConfig())
        payload = json.loads(content)
        self.assertEqual(payload["provider"]["ilaas"]["models"]["qwen-3.6-35b-instruct"]["limit"]["context"], 1234)

    def test_existing_codex_proxy_port_must_match_health_endpoint(self):
        manager = mock.Mock()
        manager.port_open.return_value = True
        with mock.patch("ilaas_agents.runners.http_json_ok", return_value=False):
            with self.assertRaises(SystemExit) as context:
                runners.ensure_codex_proxy(manager, runners.RuntimeConfig())
        self.assertIn("expected ILaaS service", str(context.exception))

    def test_existing_codex_proxy_port_is_reused_when_health_matches(self):
        manager = mock.Mock()
        manager.port_open.return_value = True
        with mock.patch("ilaas_agents.runners.http_json_ok", return_value=True):
            runners.ensure_codex_proxy(manager, runners.RuntimeConfig())
        manager.start.assert_not_called()


if __name__ == "__main__":
    unittest.main()
