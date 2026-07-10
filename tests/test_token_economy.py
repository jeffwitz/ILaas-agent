import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# Import scripts/token_economy.py (not a package).
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import token_economy  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "data" / "economy_session.jsonl"


class LoadPricesTest(unittest.TestCase):
    def test_defaults_when_no_config(self):
        with mock.patch.object(token_economy, "prices_config_path", return_value=Path("/nonexistent/prices.json")):
            entries, baseline = token_economy.load_prices()
        self.assertEqual(entries, token_economy.DEFAULT_PRICE_ENTRIES)
        self.assertEqual(baseline["input"], token_economy.DEFAULT_BASELINE["input"])
        self.assertEqual(baseline["name"], token_economy.DEFAULT_BASELINE["name"])

    def test_override_from_json(self):
        custom = {
            "baseline": {"input": 1.0, "cache_read": 0.1, "output": 2.0, "name": "custom baseline"},
            "prices": [{"pattern": "foo", "input": 0.1, "cache_read": 0.1, "output": 0.2}],
        }
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "prices.json"
            cfg.write_text(json.dumps(custom))
            with mock.patch.object(token_economy, "prices_config_path", return_value=cfg):
                entries, baseline = token_economy.load_prices()
        self.assertEqual(entries, custom["prices"])
        self.assertEqual(baseline["name"], "custom baseline")
        self.assertEqual(baseline["output"], 2.0)

    def test_list_only_json_treated_as_prices(self):
        custom = [{"pattern": "only", "input": 1.0, "cache_read": 0.0, "output": 2.0}]
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "prices.json"
            cfg.write_text(json.dumps(custom))
            with mock.patch.object(token_economy, "prices_config_path", return_value=cfg):
                entries, _ = token_economy.load_prices()
        self.assertEqual(entries, custom)


class PriceOfTest(unittest.TestCase):
    def test_known_models(self):
        self.assertEqual(token_economy.price_of("glm-5.2"), (0.93, 0.93, 3.00))
        self.assertEqual(token_economy.price_of("claude-opus-4"), (15.0, 1.50, 75.0))
        self.assertEqual(token_economy.price_of("claude-ilaas-qwen"), (0.0, 0.0, 0.0))

    def test_unknown_model_is_none(self):
        self.assertIsNone(token_economy.price_of("unknown-model"))


class EconomyMathTest(unittest.TestCase):
    def setUp(self):
        # Isolate from any host prices.json so the math is deterministic.
        self._prices = token_economy.PRICES
        self._baseline = token_economy.BASELINE_PRICE
        token_economy.PRICES = list(token_economy.DEFAULT_PRICE_ENTRIES)
        token_economy.BASELINE_PRICE = (
            token_economy.DEFAULT_BASELINE["input"],
            token_economy.DEFAULT_BASELINE["cache_read"],
            token_economy.DEFAULT_BASELINE["output"],
        )

    def tearDown(self):
        token_economy.PRICES = self._prices
        token_economy.BASELINE_PRICE = self._baseline

    def test_aggregate_costs_and_baseline(self):
        by_model, by_role, side, stats = token_economy.aggregate([str(FIXTURE)])
        # glm-5.2: (1000*0.93 + 500*3.00)/1e6 = 0.00243
        # claude-opus: (2000*15 + 1000*75)/1e6 = 0.105 ; unknown-model: no price
        self.assertAlmostEqual(stats["actual"], 0.00243 + 0.105, places=6)
        # baseline (Opus 15/1.5/75): glm 0.0525 + opus 0.105
        self.assertAlmostEqual(stats["baseline"], 0.0525 + 0.105, places=6)
        # unknown-model tokens counted as unpinned
        self.assertEqual(stats["unp_msgs"], 1)
        self.assertEqual(stats["unp_in"], 999)
        self.assertEqual(by_model["glm-5.2"]["msgs"], 1)
        self.assertEqual(by_model["claude-opus"]["msgs"], 1)

    def test_economy_savings(self):
        by_model, by_role, side, stats = token_economy.aggregate([str(FIXTURE)])
        eco = token_economy.economy(by_role, stats)
        self.assertAlmostEqual(eco["baseline"], stats["baseline"], places=6)
        self.assertAlmostEqual(eco["actual"], stats["actual"], places=6)
        self.assertAlmostEqual(eco["saved"], stats["baseline"] - stats["actual"], places=6)
        self.assertGreater(eco["saved"], 0)


if __name__ == "__main__":
    unittest.main()
