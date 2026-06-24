import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
