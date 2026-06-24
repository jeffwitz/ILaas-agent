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


if __name__ == "__main__":
    unittest.main()
