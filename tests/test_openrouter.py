import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ilaas_agents import openrouter


class OpenRouterTest(unittest.TestCase):
    def test_api_key_prefers_environment(self):
        with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-secret"}, clear=False):
            self.assertEqual(openrouter.api_key(), "sk-or-secret")

    def test_api_key_supports_underscored_filename(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "OPEN_ROUTER.md").write_text("sk-or-file-secret\n")
            with mock.patch.dict(os.environ, {}, clear=True), mock.patch(
                "ilaas_agents.openrouter.DEFAULT_TOKEN_FILE", Path(tmp) / "missing-external-token"
            ), mock.patch(
                "ilaas_agents.openrouter.paths.repo_root", return_value=Path(tmp)
            ):
                self.assertEqual(openrouter.api_key(), "sk-or-file-secret")

    def test_api_key_uses_default_external_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            token_file = Path(tmp, "OPEN_ROUTER.md")
            token_file.write_text("sk-or-external-secret\n")
            with mock.patch.dict(os.environ, {}, clear=True), mock.patch(
                "ilaas_agents.openrouter.DEFAULT_TOKEN_FILE", token_file
            ):
                self.assertEqual(openrouter.api_key(), "sk-or-external-secret")

    def test_default_models_use_openrouter_aliases(self):
        # Isolate the tier catalog so resolution falls back to the built-in
        # defaults instead of reading whatever is in the user's real cache.
        with mock.patch.dict(os.environ, {"OPENROUTER_TIER_CATALOG": "/nonexistent/or-tiers.json"}, clear=True):
            self.assertEqual(openrouter.codex_model(), "~openai/gpt-latest")
            self.assertEqual(openrouter.claude_model(), "z-ai/glm-5.2")
            self.assertEqual(openrouter.opencode_model(), "~openai/gpt-latest")

    def test_run_codex_uses_direct_responses_provider(self):
        with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-secret", "OPENROUTER_TIER_CATALOG": "/nonexistent/or-tiers.json"}, clear=True), mock.patch(
            "ilaas_agents.openrouter.codex_catalog_path", return_value=Path("/tmp/openrouter-catalog.json")
        ), mock.patch(
            "ilaas_agents.openrouter.foreground_call", return_value=0
        ) as call:
            self.assertEqual(openrouter.run_codex(["exec", "hello"]), 0)
        command = call.call_args.args[0]
        self.assertEqual(command[-2:], ["exec", "hello"])
        self.assertIn('model="~openai/gpt-latest"', command)
        self.assertIn('model_providers.openrouter.base_url="https://openrouter.ai/api/v1"', command)
        self.assertIn('model_providers.openrouter.wire_api="responses"', command)
        self.assertIn('model_catalog_json="/tmp/openrouter-catalog.json"', command)
        env = call.call_args.kwargs["env"]
        self.assertEqual(env["OPENROUTER_API_KEY"], "sk-or-secret")
        self.assertTrue(env["CODEX_HOME"].endswith(".codex-openrouter"))
        self.assertFalse(env["CODEX_HOME"].endswith("/.codex"))  # never the user's real Codex

    def test_codex_catalog_uses_openrouter_metadata(self):
        metadata = [
            {
                "id": "z-ai/glm-5.2",
                "name": "GLM 5.2",
                "context_length": 1048576,
                "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
                "supported_parameters": ["tools"],
            },
            {
                "id": "openai/gpt-5.3-codex",
                "name": "GPT 5.3 Codex",
                "context_length": 400000,
                "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
                "supported_parameters": ["tools"],
            },
            {
                "id": "image/only",
                "name": "Image only",
                "architecture": {"output_modalities": ["image"]},
                "supported_parameters": [],
            },
        ]
        with tempfile.TemporaryDirectory() as tmp, mock.patch(
            "ilaas_agents.openrouter.fetch_models", return_value=metadata
        ):
            path = openrouter.codex_catalog_path("z-ai/glm-5.2", Path(tmp) / "catalog.json")
            models = json.loads(path.read_text())["models"]
        self.assertEqual([model["slug"] for model in models], ["z-ai/glm-5.2", "openai/gpt-5.3-codex"])
        self.assertEqual(models[0]["context_window"], 1048576)
        self.assertIn("answer exactly 'z-ai/glm-5.2'", models[0]["base_instructions"])

    def test_selected_codex_model_reads_cli_override(self):
        self.assertEqual(
            openrouter.selected_codex_model(["-m", "z-ai/glm-5.2", "exec", "hello"]),
            "z-ai/glm-5.2",
        )

    def test_remove_pinned_openrouter_claude_model_preserves_other_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / ".claude_openrouter"
            home.mkdir()
            settings = home / "settings.json"
            settings.write_text(json.dumps({"model": "claude-openrouter-z-ai/glm-5.2", "theme": "auto"}))
            with mock.patch("ilaas_agents.openrouter.paths.claude_openrouter_home", return_value=home):
                openrouter.remove_pinned_openrouter_claude_model()
            payload = json.loads(settings.read_text())
        self.assertNotIn("model", payload)
        self.assertEqual(payload["theme"], "auto")

    def test_run_claude_uses_anthropic_skin(self):
        manager = mock.Mock()
        with mock.patch.dict(
            os.environ,
            {"OPENROUTER_API_KEY": "sk-or-secret", "ANTHROPIC_API_KEY": "old-key", "OPENROUTER_TIER_CATALOG": "/nonexistent/or-tiers.json"},
            clear=True,
        ), mock.patch("ilaas_agents.openrouter.ProcessManager", return_value=manager), mock.patch(
            "ilaas_agents.openrouter.available_port", return_value=4568
        ), mock.patch(
            "ilaas_agents.openrouter.start_claude_proxy"
        ) as start_proxy, mock.patch(
            "ilaas_agents.openrouter.foreground_call", return_value=0
        ) as call:
            self.assertEqual(openrouter.run_claude(["-p", "hello"]), 0)
        env = call.call_args.kwargs["env"]
        start_proxy.assert_called_once_with(manager, "127.0.0.1", 4568)
        self.assertEqual(env["ANTHROPIC_BASE_URL"], "http://127.0.0.1:4568")
        self.assertEqual(env["ANTHROPIC_AUTH_TOKEN"], "sk-or-secret")
        self.assertEqual(env["ANTHROPIC_API_KEY"], "")
        self.assertEqual(env["ANTHROPIC_MODEL"], "z-ai/glm-5.2")
        self.assertEqual(env["CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY"], "1")
        # Tier routing: GLM 5.2 supervises (opus/fable), DeepSeek codes (sonnet/haiku).
        self.assertEqual(env["ANTHROPIC_DEFAULT_OPUS_MODEL"], "z-ai/glm-5.2")
        self.assertEqual(env["ANTHROPIC_DEFAULT_FABLE_MODEL"], "z-ai/glm-5.2")
        self.assertEqual(env["ANTHROPIC_DEFAULT_SONNET_MODEL"], "deepseek/deepseek-v4-pro")
        self.assertEqual(env["ANTHROPIC_DEFAULT_HAIKU_MODEL"], "deepseek/deepseek-v4-flash")
        self.assertNotIn("CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", env)
        manager.cleanup.assert_called_once_with()

    def test_rewrite_opencode_model_args(self):
        args = openrouter.rewrite_opencode_model_args(["run", "--model", "z-ai/glm-5.2", "hello"])
        self.assertEqual(args, ["run", "--model", "openrouter/z-ai/glm-5.2", "hello"])

    def test_opencode_config_uses_builtin_provider(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            payload = json.loads(openrouter.opencode_config_content())
        self.assertEqual(payload["model"], "openrouter/~openai/gpt-latest")
        self.assertNotIn("provider", payload)


if __name__ == "__main__":
    unittest.main()
