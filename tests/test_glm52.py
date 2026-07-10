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

    def test_api_key_uses_default_external_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            token_file = Path(tmp, "GLM5.2.md")
            token_file.write_text("glm-external-secret\n")
            with mock.patch.dict(os.environ, {}, clear=True), mock.patch(
                "ilaas_agents.glm52.DEFAULT_TOKEN_FILE", token_file
            ):
                self.assertEqual(glm52.api_key(), "glm-external-secret")

    def test_api_key_prefers_explicit_file_over_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            explicit_file = Path(tmp, "explicit.txt")
            explicit_file.write_text("explicit-secret\n")
            default_file = Path(tmp, "default.txt")
            default_file.write_text("default-secret\n")
            with mock.patch.dict(os.environ, {"GLM52_TOKEN_FILE": str(explicit_file)}, clear=True), mock.patch(
                "ilaas_agents.glm52.DEFAULT_TOKEN_FILE", default_file
            ):
                self.assertEqual(glm52.api_key(), "explicit-secret")

    def test_api_key_falls_back_to_legacy(self):
        with tempfile.TemporaryDirectory() as tmp:
            legacy_file = Path(tmp, "GLM5.2.md")
            legacy_file.write_text("legacy-secret\n")
            missing_default = Path(tmp, "missing.token")
            with mock.patch.dict(os.environ, {}, clear=True), mock.patch(
                "ilaas_agents.glm52.DEFAULT_TOKEN_FILE", missing_default
            ), mock.patch(
                "ilaas_agents.paths.legacy_key_file", return_value=legacy_file
            ), mock.patch("ilaas_agents.paths.warn_legacy_key") as warn:
                self.assertEqual(glm52.api_key(), "legacy-secret")
                warn.assert_called_once_with("glm52")

    def test_api_key_missing_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {}, clear=True), mock.patch(
                "ilaas_agents.glm52.DEFAULT_TOKEN_FILE", Path(tmp, "missing.token")
            ), mock.patch("ilaas_agents.paths.legacy_key_file", return_value=None):
                with self.assertRaises(SystemExit):
                    glm52.api_key()

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
        ), mock.patch("ilaas_agents.glm52.foreground_call", return_value=0) as call:
            self.assertEqual(glm52.run_claude(["-p", "hello"]), 0)
        command = call.call_args.args[0]
        env = call.call_args.kwargs["env"]
        self.assertEqual(command, ["claude", "-p", "hello"])
        self.assertNotIn("ANTHROPIC_API_KEY", env)
        self.assertEqual(env["ANTHROPIC_AUTH_TOKEN"], "secret")
        self.assertEqual(env["ANTHROPIC_DEFAULT_SONNET_MODEL"], "glm-5.2")

    def test_run_opencode_injects_provider_config(self):
        with mock.patch.dict(os.environ, {"GLM52_API_KEY": "secret"}, clear=True), mock.patch(
            "ilaas_agents.glm52.foreground_call", return_value=0
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
        ), mock.patch("ilaas_agents.glm52.foreground_call", return_value=0) as call:
            self.assertEqual(glm52.run_codex(["exec", "hello"]), 0)
        start_proxy.assert_called_once_with(manager, "127.0.0.1", 4567)
        command = call.call_args.args[0]
        self.assertEqual(command[-2:], ["exec", "hello"])
        self.assertIn('model="glm-5.2"', command)
        self.assertIn('model_providers.glm52.wire_api="responses"', command)
        self.assertIn('model_catalog_json="/tmp/glm52-catalog.json"', command)
        env = call.call_args.kwargs["env"]
        self.assertTrue(env["CODEX_HOME"].endswith(".codex-glm52"))
        self.assertFalse(env["CODEX_HOME"].endswith("/.codex"))  # never the user's real Codex
        manager.cleanup.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
