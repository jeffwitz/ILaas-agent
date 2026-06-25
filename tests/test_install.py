import argparse
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ilaas_agents import install


class InstallTest(unittest.TestCase):
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
