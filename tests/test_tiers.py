import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ilaas_agents import tiers


class TiersTest(unittest.TestCase):
    def test_assign_tier_glm52_single_model(self):
        self.assertEqual(tiers.assign_tier("glm52", "glm-5.2"), "supervisor")

    def test_assign_tier_ilaas_name_heuristic(self):
        self.assertEqual(tiers.assign_tier("ilaas", "ilaas-default"), "supervisor")
        self.assertEqual(tiers.assign_tier("ilaas", "llama-3.1-8b-instruct"), "small")
        self.assertEqual(tiers.assign_tier("ilaas", "qwen-3.6-35b-instruct"), "supervisor")
        self.assertEqual(tiers.assign_tier("ilaas", "some-other-model"), "coder")

    def test_assign_tier_openrouter_metadata(self):
        meta_full = {
            "context_length": 200000,
            "supported_parameters": ["tools"],
            "architecture": {"output_modalities": ["text"]},
        }
        self.assertEqual(tiers.assign_tier("openrouter", "any-model", meta_full), "supervisor")

        meta_small_ctx = {
            "context_length": 32000,
            "supported_parameters": ["tools"],
            "architecture": {"output_modalities": ["text"]},
        }
        self.assertEqual(tiers.assign_tier("openrouter", "any-model", meta_small_ctx), "small")

        meta_no_tools = {"supported_parameters": []}
        self.assertEqual(tiers.assign_tier("openrouter", "any-model", meta_no_tools), "small")

        meta_coder = {
            "context_length": 128000,
            "supported_parameters": ["tools"],
            "architecture": {"output_modalities": ["text"]},
        }
        self.assertEqual(tiers.assign_tier("openrouter", "any-model", meta_coder), "coder")

    def test_resolve_env_override_wins(self):
        with mock.patch.dict(os.environ, {"ILAAS_TIER_SUPERVISOR_MODEL": "env-model"}):
            self.assertEqual(tiers.resolve("ilaas", "supervisor"), "env-model")

    def test_resolve_returns_none_when_no_catalog(self):
        with tempfile.TemporaryDirectory() as tmp:
            nonexistent = Path(tmp) / "nonexistent.json"
            with mock.patch.dict(os.environ, {"ILAAS_MODEL_CATALOG": str(nonexistent)}):
                self.assertIsNone(tiers.resolve("ilaas", "supervisor"))

    def test_resolve_reads_catalog_tier_field(self):
        catalog = {
            "models": [
                {"slug": "model-supervisor", "tier": "supervisor"},
                {"slug": "model-coder", "tier": "coder"},
                {"slug": "model-small", "tier": "small"},
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "catalog.json"
            path.write_text(json.dumps(catalog))
            with mock.patch.dict(os.environ, {"ILAAS_MODEL_CATALOG": str(path)}):
                self.assertEqual(tiers.resolve("ilaas", "supervisor"), "model-supervisor")
                self.assertEqual(tiers.resolve("ilaas", "coder"), "model-coder")
                self.assertEqual(tiers.resolve("ilaas", "small"), "model-small")

    def test_apply_writes_tier_field(self):
        catalog = {
            "models": [
                {"slug": "qwen-3.6-35b-instruct"},
                {"slug": "llama-3.1-8b-instruct"},
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "catalog.json"
            path.write_text(json.dumps(catalog))
            with mock.patch.dict(os.environ, {"ILAAS_MODEL_CATALOG": str(path)}):
                counts = tiers.apply("ilaas")
                # re-read catalog
                payload = json.loads(path.read_text())
                for entry in payload["models"]:
                    self.assertIn("tier", entry)
                self.assertIsInstance(counts["supervisor"], int)
                self.assertIsInstance(counts["coder"], int)
                self.assertIsInstance(counts["small"], int)

    def test_unknown_tier_raises(self):
        with self.assertRaises(SystemExit):
            tiers.resolve("ilaas", "bogus")

    def test_unknown_provider_resolve_returns_none(self):
        self.assertIsNone(tiers.resolve("nope", "supervisor"))


if __name__ == "__main__":
    unittest.main()
