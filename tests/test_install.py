import argparse
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ilaas_agents import install


class InstallTest(unittest.TestCase):
    def test_prefix_installs_wrappers_under_prefix_bin(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefix = Path(tmp) / "prefix"
            args = argparse.Namespace(
                skip_litellm_install=True,
                api_base="https://example.invalid/v1",
                api_key_env="ILAAS_API_KEY",
                non_interactive=True,
                prefix=str(prefix),
                force=True,
            )
            with mock.patch.dict("os.environ", {"ILAAS_API_KEY": "dummy"}, clear=False), \
                 mock.patch("ilaas_agents.models.fetch_models", return_value=["mistral-medium-latest", "qwen-3.6-35b-instruct"]), \
                 mock.patch("ilaas_agents.paths.litellm_config_path", return_value=Path(tmp) / "litellm.yaml"), \
                 mock.patch("ilaas_agents.paths.model_catalog_path", return_value=Path(tmp) / "catalog.json"), \
                 mock.patch("ilaas_agents.paths.codex_config_path", return_value=Path(tmp) / "config.toml"):
                with contextlib.redirect_stdout(io.StringIO()):
                    install.run_install(args)
            self.assertTrue((prefix / "bin" / "Ilaas-codex").exists())
            self.assertTrue((prefix / "bin" / "Ilaas-doctor").exists())


if __name__ == "__main__":
    unittest.main()
