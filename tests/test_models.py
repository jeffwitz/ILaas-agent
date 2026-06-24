import json
import tempfile
import unittest
from pathlib import Path

from ilaas_agents import models


class ModelsTest(unittest.TestCase):
    def test_model_entries_include_aliases_first(self):
        entries = models.model_entries(["qwen-3.6-35b-instruct", "mistral-medium-latest"])
        self.assertEqual(entries[0], ("ilaas-default", "mistral-medium-latest"))
        self.assertEqual(entries[1], ("mistral-ilaas", "mistral-medium-latest"))
        self.assertIn(("qwen-3.6-35b-instruct", "qwen-3.6-35b-instruct"), entries)

    def test_codex_catalog_contains_expected_slugs(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "catalog.json"
            models.write_codex_catalog(path, ["qwen-3.6-35b-instruct", "llama-3.1-8b"])
            payload = json.loads(path.read_text())
        slugs = [item["slug"] for item in payload["models"]]
        self.assertIn("ilaas-default", slugs)
        self.assertIn("mistral-ilaas", slugs)
        self.assertIn("qwen-3.6-35b-instruct", slugs)
        llama = next(item for item in payload["models"] if item["slug"] == "llama-3.1-8b")
        self.assertIn("Not recommended", llama["description"])


if __name__ == "__main__":
    unittest.main()
