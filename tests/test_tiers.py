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


class OpenRouterActiveCatalogTest(unittest.TestCase):
    def _cache_env(self, tmp):
        return {"ILAAS_CACHE_HOME": str(Path(tmp) / "cache"), "OPENROUTER_TIER_CATALOG": ""}

    def test_state_file_is_authoritative(self):
        catalog_payload = {"models": [{"slug": "z-ai/glm-5.2", "tier": "supervisor"}]}
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, self._cache_env(tmp), clear=False):
                cat_dir = tiers.paths.cache_home() / tiers.paths.APP_NAME
                cat_dir.mkdir(parents=True)
                cat = cat_dir / "openrouter-glm-5.2.json"
                cat.write_text(json.dumps(catalog_payload))
                tiers.set_active_catalog("openrouter", cat)
                self.assertEqual(tiers.catalog_path("openrouter"), cat)
                self.assertIn("active state file", tiers.catalog_source("openrouter"))
                self.assertEqual(tiers.resolve("openrouter", "supervisor"), "z-ai/glm-5.2")

    def test_env_override_beats_state_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, self._cache_env(tmp), clear=False):
                cat_dir = tiers.paths.cache_home() / tiers.paths.APP_NAME
                cat_dir.mkdir(parents=True)
                state_cat = cat_dir / "openrouter-state.json"
                state_cat.write_text("{}")
                tiers.set_active_catalog("openrouter", state_cat)
                env_cat = cat_dir / "openrouter-env.json"
                env_cat.write_text("{}")
                with mock.patch.dict(os.environ, {"OPENROUTER_TIER_CATALOG": str(env_cat)}):
                    self.assertEqual(tiers.catalog_path("openrouter"), env_cat)
                    self.assertIn("env", tiers.catalog_source("openrouter"))

    def test_mtime_fallback_adopts_newest_into_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, self._cache_env(tmp), clear=False):
                cat_dir = tiers.paths.cache_home() / tiers.paths.APP_NAME
                cat_dir.mkdir(parents=True)
                a = cat_dir / "openrouter-a.json"
                b = cat_dir / "openrouter-b.json"
                a.write_text("{}")
                b.write_text("{}")
                os.utime(a, (1, 1))
                os.utime(b, (10, 10))
                # before any catalog_path call, source is the mtime fallback
                self.assertIn("mtime fallback", tiers.catalog_source("openrouter"))
                self.assertEqual(tiers.catalog_path("openrouter"), b)
                state = tiers.active_catalog_path()
                self.assertTrue(state.is_file())
                self.assertEqual(Path(json.loads(state.read_text())["catalog"]), b)

    def test_resolve_with_source_env_and_catalog(self):
        catalog = {"models": [{"slug": "model-supervisor", "tier": "supervisor"}]}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "catalog.json"
            path.write_text(json.dumps(catalog))
            with mock.patch.dict(os.environ, {"ILAAS_MODEL_CATALOG": str(path)}):
                slug, source = tiers.resolve_with_source("ilaas", "supervisor")
                self.assertEqual(slug, "model-supervisor")
                self.assertEqual(source, "catalog")
            with mock.patch.dict(os.environ, {"ILAAS_MODEL_CATALOG": str(path), "ILAAS_TIER_SUPERVISOR_MODEL": "env-model"}):
                slug, source = tiers.resolve_with_source("ilaas", "supervisor")
                self.assertEqual(slug, "env-model")
                self.assertIn("env", source)


if __name__ == "__main__":
    unittest.main()
