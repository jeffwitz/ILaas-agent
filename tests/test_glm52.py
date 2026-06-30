import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ilaas_agents import glm52


class Glm52Test(unittest.TestCase):
    def test_api_key_prefers_environment(self):
        with mock.patch.dict(os.environ, {"GLM52_API_KEY": "secret"}, clear=False):
            self.assertEqual(glm52.api_key(), "secret")

    def test_opencode_config_uses_glm52_provider(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            payload = json.loads(glm52.opencode_config_content())
        self.assertEqual(payload["model"], "glm52/glm-5.2")
        self.assertEqual(payload["provider"]["glm52"]["options"]["baseURL"], glm52.DEFAULT_OPENAI_BASE_URL)
        self.assertIn("glm-5.2", payload["provider"]["glm52"]["models"])

    def test_codex_catalog_contains_glm52_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = glm52.codex_catalog_path(Path(tmp) / "catalog.json")
            payload = json.loads(path.read_text())
        model = payload["models"][0]
        self.assertEqual(model["slug"], "glm-5.2")
        self.assertEqual(model["context_window"], 200000)

    def test_run_claude_uses_anthropic_endpoint_and_token(self):
        with mock.patch.dict(
            os.environ,
            {"GLM52_API_KEY": "secret", "ANTHROPIC_API_KEY": "old-key"},
            clear=True,
        ), mock.patch("ilaas_agents.glm52.subprocess.call", return_value=0) as call:
            self.assertEqual(glm52.run_claude(["-p", "hello"]), 0)
        command = call.call_args.args[0]
        env = call.call_args.kwargs["env"]
        self.assertEqual(command, ["claude", "-p", "hello"])
        self.assertNotIn("ANTHROPIC_API_KEY", env)
        self.assertEqual(env["ANTHROPIC_AUTH_TOKEN"], "secret")
        self.assertEqual(env["ANTHROPIC_DEFAULT_SONNET_MODEL"], "glm-5.2")

    def test_run_opencode_injects_provider_config(self):
        with mock.patch.dict(os.environ, {"GLM52_API_KEY": "secret"}, clear=True), mock.patch(
            "ilaas_agents.glm52.subprocess.call", return_value=0
        ) as call:
            self.assertEqual(glm52.run_opencode(["run", "hello"]), 0)
        env = call.call_args.kwargs["env"]
        self.assertEqual(call.call_args.args[0], ["opencode", "run", "hello"])
        self.assertEqual(json.loads(env["OPENCODE_CONFIG_CONTENT"])["model"], "glm52/glm-5.2")

    def test_run_codex_uses_local_responses_adapter(self):
        manager = mock.Mock()
        with mock.patch.dict(os.environ, {"GLM52_API_KEY": "secret"}, clear=True), mock.patch(
            "ilaas_agents.glm52.ProcessManager", return_value=manager
        ), mock.patch("ilaas_agents.glm52.available_port", return_value=4567), mock.patch(
            "ilaas_agents.glm52.start_codex_proxy"
        ) as start_proxy, mock.patch(
            "ilaas_agents.glm52.codex_catalog_path", return_value=Path("/tmp/glm52-catalog.json")
        ), mock.patch("ilaas_agents.glm52.subprocess.call", return_value=0) as call:
            self.assertEqual(glm52.run_codex(["exec", "hello"]), 0)
        start_proxy.assert_called_once_with(manager, "127.0.0.1", 4567)
        command = call.call_args.args[0]
        self.assertEqual(command[-2:], ["exec", "hello"])
        self.assertIn('model="glm-5.2"', command)
        self.assertIn('model_providers.glm52.wire_api="responses"', command)
        self.assertIn('model_catalog_json="/tmp/glm52-catalog.json"', command)
        manager.cleanup.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
