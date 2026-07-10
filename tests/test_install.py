import argparse
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ilaas_agents import install


class InstallTest(unittest.TestCase):
    def _args(self, **overrides):
        base = dict(api_base=None, api_key_env="ILAAS_API_KEY", api_key_file=None, non_interactive=True)
        base.update(overrides)
        return argparse.Namespace(**base)

    def test_resolve_api_key_supports_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            token_file = Path(tmp, "Ilaas.txt")
            token_file.write_text("ilaas-file-secret\n")
            args = self._args(api_key_file=str(token_file))
            with mock.patch.dict("os.environ", {}, clear=True), mock.patch(
                "ilaas_agents.models.extract_existing_settings", return_value=None
            ):
                self.assertEqual(install.resolve_api_key(args), ("https://llm.ilaas.fr/v1", "ilaas-file-secret"))

    def test_resolve_api_key_env_wins_over_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            token_file = Path(tmp, "Ilaas.txt")
            token_file.write_text("from-file\n")
            args = self._args(api_key_file=str(token_file))
            with mock.patch.dict("os.environ", {"ILAAS_API_KEY": "from-env"}, clear=True), mock.patch(
                "ilaas_agents.models.extract_existing_settings", return_value=None
            ):
                _, api_key = install.resolve_api_key(args)
                self.assertEqual(api_key, "from-env")

    def test_resolve_api_key_uses_default_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            default_file = Path(tmp, "ilaas.token")
            default_file.write_text("default-secret\n")
            args = self._args()
            with mock.patch.dict("os.environ", {}, clear=True), mock.patch(
                "ilaas_agents.models.extract_existing_settings", return_value=None
            ), mock.patch("ilaas_agents.install.DEFAULT_ILAAS_TOKEN_FILE", default_file):
                _, api_key = install.resolve_api_key(args)
                self.assertEqual(api_key, "default-secret")

    def test_resolve_api_key_legacy_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            legacy_file = Path(tmp, "Ilaas.txt")
            legacy_file.write_text("legacy-secret\n")
            missing_default = Path(tmp, "missing.token")
            args = self._args()
            with mock.patch.dict("os.environ", {}, clear=True), mock.patch(
                "ilaas_agents.models.extract_existing_settings", return_value=None
            ), mock.patch("ilaas_agents.install.DEFAULT_ILAAS_TOKEN_FILE", missing_default), mock.patch(
                "ilaas_agents.paths.legacy_key_file", return_value=legacy_file
            ), mock.patch("ilaas_agents.paths.warn_legacy_key") as warn:
                _, api_key = install.resolve_api_key(args)
                self.assertEqual(api_key, "legacy-secret")
                warn.assert_called_once_with("ilaas")

    def test_isolated_install_writes_under_overridden_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prefix = root / "prefix"
            env = {
                "ILAAS_API_KEY": "dummy",
                "ILAAS_HOME": str(root / "home"),
                "ILAAS_CONFIG_HOME": str(root / "config"),
                "ILAAS_CACHE_HOME": str(root / "cache"),
            }
            args = argparse.Namespace(
                skip_litellm_install=True,
                api_base="https://example.invalid/v1",
                api_key_env="ILAAS_API_KEY",
                non_interactive=True,
                prefix=str(prefix),
                force=True,
                codex_sandbox_mode="workspace-write",
                check_agent_deps=False,
                install_agent_deps=False,
                install_agent=None,
            )
            with mock.patch.dict("os.environ", env, clear=False), \
                 mock.patch("ilaas_agents.models.fetch_models", return_value=["mistral-medium-latest", "qwen-3.6-35b-instruct"]):
                with contextlib.redirect_stdout(io.StringIO()):
                    install.run_install(args)
            self.assertTrue((root / "config" / "litellm" / "ilaas-mistral.yaml").exists())
            self.assertTrue((root / "home" / ".codex-ilaas" / "config.toml").exists())
            self.assertTrue((root / "home" / ".codex-ilaas" / "model-catalogs" / "ilaas-mistral.json").exists())
            self.assertTrue((prefix / "bin" / "Ilaas-codex").exists())
            self.assertTrue((prefix / "bin" / "Ilaas-doctor").exists())
            self.assertTrue((prefix / "bin" / "glm52-codex").exists())
            self.assertTrue((prefix / "bin" / "glm52-claude").exists())
            self.assertTrue((prefix / "bin" / "glm52-opencode").exists())
            self.assertTrue((prefix / "bin" / "openrouter-codex").exists())
            self.assertTrue((prefix / "bin" / "openrouter-claude").exists())
            self.assertTrue((prefix / "bin" / "openrouter-opencode").exists())
            codex_config = (root / "home" / ".codex-ilaas" / "config.toml").read_text()
            self.assertIn('sandbox_mode = "workspace-write"', codex_config)

    def test_force_install_backs_up_generated_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prefix = root / "prefix"
            env = {
                "ILAAS_API_KEY": "dummy",
                "ILAAS_HOME": str(root / "home"),
                "ILAAS_CONFIG_HOME": str(root / "config"),
                "ILAAS_CACHE_HOME": str(root / "cache"),
            }
            litellm_config = root / "config" / "litellm" / "ilaas-mistral.yaml"
            codex_config = root / "home" / ".codex-ilaas" / "config.toml"
            catalog = root / "home" / ".codex-ilaas" / "model-catalogs" / "ilaas-mistral.json"
            wrapper = prefix / "bin" / "Ilaas-codex"
            for path, text in [
                (litellm_config, "old litellm"),
                (codex_config, "old codex"),
                (catalog, "old catalog"),
                (wrapper, "old wrapper"),
            ]:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
            args = argparse.Namespace(
                skip_litellm_install=True,
                api_base="https://example.invalid/v1",
                api_key_env="ILAAS_API_KEY",
                non_interactive=True,
                prefix=str(prefix),
                force=True,
                codex_sandbox_mode="danger-full-access",
                check_agent_deps=False,
                install_agent_deps=False,
                install_agent=None,
            )
            with mock.patch.dict("os.environ", env, clear=False), \
                 mock.patch("ilaas_agents.models.fetch_models", return_value=["mistral-medium-latest"]):
                with contextlib.redirect_stdout(io.StringIO()):
                    install.run_install(args)
            backup_texts = []
            for path in [litellm_config, codex_config, catalog, wrapper]:
                backups = list(path.parent.glob(path.name + ".bak-*"))
                self.assertEqual(len(backups), 1)
                backup_texts.append(backups[0].read_text())
            self.assertIn("old litellm", backup_texts)
            self.assertIn("old codex", backup_texts)
            self.assertIn("old catalog", backup_texts)
            self.assertIn("old wrapper", backup_texts)


if __name__ == "__main__":
    unittest.main()
