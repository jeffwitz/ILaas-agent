import unittest
import tempfile
from pathlib import Path
from unittest import mock

from ilaas_agents import paths


class PathsTest(unittest.TestCase):
    def test_repo_root_contains_project_files(self):
        root = paths.repo_root()
        self.assertTrue((root / "install.py").exists())
        self.assertTrue((root / "ilaas_agents").is_dir())

    def test_generated_paths_are_absolute(self):
        expected = [
            paths.litellm_config_path(),
            paths.codex_config_path(),
            paths.model_catalog_path(),
            paths.log_dir(),
            paths.runtime_dir(),
            paths.bin_dir(),
        ]
        for item in expected:
            self.assertIsInstance(item, Path)
            self.assertTrue(item.is_absolute())

    def test_environment_overrides(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env = {
                "ILAAS_HOME": str(root / "home"),
                "ILAAS_CONFIG_HOME": str(root / "config"),
                "ILAAS_CACHE_HOME": str(root / "cache"),
                "ILAAS_BIN_DIR": str(root / "bin"),
                "ILAAS_LITELLM_CONFIG": str(root / "custom-litellm.yaml"),
                "ILAAS_CODEX_HOME": str(root / "custom-codex"),
                "ILAAS_MODEL_CATALOG": str(root / "custom-catalog.json"),
                "ILAAS_LITELLM_VENV": str(root / "custom-venv"),
            }
            with mock.patch.dict("os.environ", env, clear=False):
                self.assertEqual(paths.home(), root / "home")
                self.assertEqual(paths.config_home(), root / "config")
                self.assertEqual(paths.cache_home(), root / "cache")
                self.assertEqual(paths.bin_dir(), root / "bin")
                self.assertEqual(paths.litellm_config_path(), root / "custom-litellm.yaml")
                self.assertEqual(paths.codex_home(), root / "custom-codex")
                self.assertEqual(paths.model_catalog_path(), root / "custom-catalog.json")
                self.assertEqual(paths.litellm_venv(), root / "custom-venv")

    def test_keys_dir_default_under_config_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict("os.environ", {"ILAAS_CONFIG_HOME": tmp}, clear=False):
                self.assertEqual(paths.keys_dir(), Path(tmp) / "ilaas-agent" / "keys")
                self.assertEqual(paths.key_file("ilaas"), Path(tmp) / "ilaas-agent" / "keys" / "ilaas.token")
                self.assertEqual(paths.key_file("glm52"), Path(tmp) / "ilaas-agent" / "keys" / "glm52.token")
                self.assertEqual(paths.key_file("openrouter"), Path(tmp) / "ilaas-agent" / "keys" / "openrouter.token")

    def test_keys_dir_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict("os.environ", {"ILAAS_KEYS_DIR": tmp}, clear=False):
                self.assertEqual(paths.keys_dir(), Path(tmp))
                self.assertEqual(paths.key_file("ilaas"), Path(tmp) / "ilaas.token")

    def test_legacy_key_files_known_providers(self):
        for provider in ("ilaas", "glm52", "openrouter"):
            self.assertIsNotNone(paths.legacy_key_file(provider))
        self.assertIsNone(paths.legacy_key_file("unknown"))


if __name__ == "__main__":
    unittest.main()
