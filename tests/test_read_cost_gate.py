import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ilaas_agents import harness


class EnsurePreToolUseMatcherTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(str(self.tmp), ignore_errors=True)

    def _settings_path(self) -> Path:
        return self.tmp / "settings.json"

    def _write_settings(self, data: dict) -> Path:
        p = self._settings_path()
        p.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return p

    def test_adds_matcher_when_absent(self):
        sp = self._write_settings({"hooks": {"PreToolUse": []}})
        result = harness._ensure_pre_tool_use_matcher(sp, "Read", "/hooks/read-gate")
        self.assertTrue(result)
        data = json.loads(sp.read_text())
        pre = data["hooks"]["PreToolUse"]
        self.assertEqual(len(pre), 1)
        self.assertEqual(pre[0]["matcher"], "Read")
        self.assertEqual(pre[0]["hooks"][0]["command"], "/hooks/read-gate")

    def test_idempotent_does_not_duplicate(self):
        sp = self._write_settings({
            "hooks": {
                "PreToolUse": [
                    {"matcher": "Read", "hooks": [{"type": "command", "command": "/hooks/read-gate"}]},
                ],
            },
        })
        result = harness._ensure_pre_tool_use_matcher(sp, "Read", "/hooks/read-gate")
        self.assertFalse(result)
        data = json.loads(sp.read_text())
        self.assertEqual(len(data["hooks"]["PreToolUse"]), 1)

    def test_matcher_present_unchanged(self):
        sp = self._write_settings({
            "hooks": {
                "PreToolUse": [
                    {"matcher": "Grep|Glob", "hooks": [{"type": "command", "command": "/hooks/gate"}]},
                    {"matcher": "Read", "hooks": [{"type": "command", "command": "/hooks/read-gate"}]},
                ],
            },
        })
        result = harness._ensure_pre_tool_use_matcher(sp, "Read", "/hooks/read-gate")
        self.assertFalse(result)
        data = json.loads(sp.read_text())
        self.assertEqual(len(data["hooks"]["PreToolUse"]), 2)

    def test_missing_file_returns_false(self):
        sp = self._settings_path()
        result = harness._ensure_pre_tool_use_matcher(sp, "Read", "/hooks/read-gate")
        self.assertFalse(result)

    def test_invalid_json_returns_false(self):
        sp = self._settings_path()
        sp.write_text("not json {{{")
        result = harness._ensure_pre_tool_use_matcher(sp, "Read", "/hooks/read-gate")
        self.assertFalse(result)

    def test_creates_hooks_and_pre_tool_use_when_absent(self):
        sp = self._write_settings({})
        result = harness._ensure_pre_tool_use_matcher(sp, "Read", "/hooks/read-gate")
        self.assertTrue(result)
        data = json.loads(sp.read_text())
        self.assertEqual(data["hooks"]["PreToolUse"][0]["matcher"], "Read")


class RtkBinTest(unittest.TestCase):
    def test_env_wins(self):
        with mock.patch.dict(os.environ, {"RTK_BIN": "/custom/rtk"}, clear=False):
            self.assertEqual(harness.rtk_bin(), "/custom/rtk")

    def test_returns_none_when_missing(self):
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch(
            "ilaas_agents.harness.shutil.which", return_value=None
        ), mock.patch("ilaas_agents.harness.paths.home", return_value=Path("/nonexistent/home")):
            self.assertIsNone(harness.rtk_bin())


@unittest.skipUnless(shutil.which("jq"), "jq required for read-cost-gate tests")
class ReadCostGateHookTest(unittest.TestCase):
    HOOK = Path(__file__).resolve().parents[1] / "harness" / "hooks" / "cbm-read-cost-gate"

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(str(self.tmp), ignore_errors=True)

    def _run_hook(self, file_path: str) -> str:
        stdin = json.dumps({"tool_name": "Read", "tool_input": {"file_path": file_path}})
        result = subprocess.run(
            ["bash", str(self.HOOK)],
            input=stdin,
            capture_output=True,
            text=True,
            timeout=10,
        )
        # Hook always exits 0
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        return result.stdout

    def test_large_py_triggers_warning(self):
        f = self.tmp / "big.py"
        f.write_text("\n".join(f"line {i}" for i in range(501)) + "\n")
        out = self._run_hook(str(f))
        data = json.loads(out)
        self.assertEqual(data["decision"], "approve")
        self.assertIn("WARNING", data["additionalContext"])
        self.assertIn("501 lines", data["additionalContext"])

    def test_small_py_silent(self):
        f = self.tmp / "small.py"
        f.write_text("\n".join(f"line {i}" for i in range(10)))
        out = self._run_hook(str(f))
        self.assertEqual(out.strip(), "")

    def test_md_file_silent(self):
        f = self.tmp / "readme.md"
        f.write_text("\n".join(f"line {i}" for i in range(500)))
        out = self._run_hook(str(f))
        self.assertEqual(out.strip(), "")

    def test_test_file_silent(self):
        f = self.tmp / "tests" / "test_big.py"
        f.parent.mkdir()
        f.write_text("\n".join(f"line {i}" for i in range(500)))
        out = self._run_hook(str(f))
        self.assertEqual(out.strip(), "")

    def test_missing_file_silent(self):
        out = self._run_hook("/nonexistent/file.py")
        self.assertEqual(out.strip(), "")

    def test_empty_tool_input_silent(self):
        stdin = json.dumps({"tool_name": "Read", "tool_input": {}})
        result = subprocess.run(
            ["bash", str(self.HOOK)],
            input=stdin,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "")


class ReadCostGateHookInstallTest(unittest.TestCase):
    def test_install_harness_registers_read_matcher(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            or_home = tmp_path / "claude_openrouter"
            claude_home = tmp_path / "claude"
            or_home.mkdir()
            claude_home.mkdir()

            # Pre-create settings.json with Grep|Glob matcher (simulating existing deploy).
            settings = claude_home / "settings.json"
            settings.write_text(json.dumps({
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Grep|Glob",
                            "hooks": [{"type": "command", "command": str(claude_home / "hooks" / "cbm-code-discovery-gate"), "timeout": 5}],
                        },
                    ],
                },
            }, indent=2) + "\n")

            # Also create or_home settings.json for the openrouter side.
            or_settings = or_home / "settings.json"
            or_settings.write_text(json.dumps({"hooks": {}}, indent=2) + "\n")

            with mock.patch("ilaas_agents.harness.paths.home", return_value=tmp_path), mock.patch(
                "ilaas_agents.harness.rtk_bin", return_value="/fake/rtk"
            ):
                deployed = harness.install_harness(
                    openrouter_home=or_home, claude_home=claude_home, bin_path="/fake/cbm"
                )

            # Verify Read matcher was added to both settings.
            for sp in (settings, or_settings):
                data = json.loads(sp.read_text())
                pre = data["hooks"]["PreToolUse"]
                matchers = [e["matcher"] for e in pre if isinstance(e, dict)]
                self.assertIn("Read", matchers, f"Read matcher missing in {sp}")

            self.assertIn(str(settings), deployed.get("settings", []))
            self.assertIn(str(or_settings), deployed.get("settings", []))


if __name__ == "__main__":
    unittest.main()