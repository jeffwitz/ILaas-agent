import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ilaas_agents import doctor


class DoctorKeySourceTest(unittest.TestCase):
    def test_env_source_wins(self):
        with mock.patch.dict("os.environ", {"ILAAS_API_KEY": "secret"}, clear=True):
            label, ok, detail = doctor.key_source("ilaas")
        self.assertTrue(ok)
        self.assertIn("env ILAAS_API_KEY", detail)

    def test_explicit_file_source_reports_existence(self):
        with mock.patch.dict("os.environ", {"OPENROUTER_TOKEN_FILE": "/abs/missing-key"}, clear=True):
            label, ok, detail = doctor.key_source("openrouter")
        self.assertEqual(detail, "file /abs/missing-key")
        self.assertFalse(ok)  # the file does not exist

    def test_default_file_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            default_file = Path(tmp, "ilaas.token")
            default_file.write_text("k\n")
            with mock.patch.dict("os.environ", {}, clear=True), mock.patch(
                "ilaas_agents.paths.key_file", return_value=default_file
            ):
                label, ok, detail = doctor.key_source("ilaas")
        self.assertTrue(ok)
        self.assertEqual(detail, f"file {default_file}")

    def test_legacy_source_marked_deprecated(self):
        with tempfile.TemporaryDirectory() as tmp:
            legacy_file = Path(tmp, "Ilaas.txt")
            legacy_file.write_text("k\n")
            missing_default = Path(tmp, "missing.token")
            with mock.patch.dict("os.environ", {}, clear=True), mock.patch(
                "ilaas_agents.paths.key_file", return_value=missing_default
            ), mock.patch("ilaas_agents.paths.legacy_key_file", return_value=legacy_file):
                label, ok, detail = doctor.key_source("ilaas")
        self.assertTrue(ok)
        self.assertIn("legacy file", detail)
        self.assertIn("deprecated", detail)

    def test_missing_source(self):
        missing_default = Path("/nonexistent/ilaas-doctor-default.token")
        with mock.patch.dict("os.environ", {}, clear=True), mock.patch(
            "ilaas_agents.paths.key_file", return_value=missing_default
        ), mock.patch("ilaas_agents.paths.legacy_key_file", return_value=None):
            label, ok, detail = doctor.key_source("glm52")
        self.assertFalse(ok)
        self.assertIn("not set", detail)


if __name__ == "__main__":
    unittest.main()
