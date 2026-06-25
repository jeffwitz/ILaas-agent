import tempfile
import unittest
from pathlib import Path

from ilaas_agents import wrappers


class WrappersTest(unittest.TestCase):
    def test_posix_wrapper_uses_shared_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = wrappers.write_posix_wrapper(Path(tmp), "Ilaas-opencode")
            text = path.read_text()
        self.assertIn("python3 -m ilaas_agents.cli opencode", text)
        self.assertIn("PYTHONPATH", text)

    def test_doctor_and_servers_are_installed_names(self):
        self.assertIn("Ilaas-doctor", wrappers.POSIX_NAMES)
        self.assertIn("Ilaas-servers", wrappers.POSIX_NAMES)

    def test_expected_wrapper_paths_are_posix_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            expected = wrappers.expected_wrapper_paths(Path(tmp))
        self.assertIn(Path(tmp) / "Ilaas-codex", expected)
        self.assertIn(Path(tmp) / "Ilaas-servers", expected)


if __name__ == "__main__":
    unittest.main()
