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


if __name__ == "__main__":
    unittest.main()
