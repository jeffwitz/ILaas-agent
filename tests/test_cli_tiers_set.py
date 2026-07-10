import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ilaas_agents import cli, tiers


class TiersSetCliTest(unittest.TestCase):
    def test_set_pins_slug_to_tier(self):
        catalog = {"models": [{"slug": "my-slug"}, {"slug": "other-model"}]}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "catalog.json"
            path.write_text(json.dumps(catalog))
            argv = ["ilaas-agent", "tiers", "set", "--provider", "ilaas", "supervisor", "my-slug"]
            with mock.patch.dict(os.environ, {"ILAAS_MODEL_CATALOG": str(path)}), \
                 mock.patch("sys.argv", argv):
                with self.assertRaises(SystemExit) as ctx:
                    cli.main()
            self.assertEqual(ctx.exception.code, 0)
            # reload so catalog_path picks up the same env
            with mock.patch.dict(os.environ, {"ILAAS_MODEL_CATALOG": str(path)}):
                self.assertEqual(tiers.resolve("ilaas", "supervisor"), "my-slug")
            payload = json.loads(path.read_text())
            entry = next(m for m in payload["models"] if m["slug"] == "my-slug")
            self.assertEqual(entry["tier"], "supervisor")

    def test_set_rejects_unknown_tier(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "catalog.json"
            path.write_text(json.dumps({"models": [{"slug": "x"}]}))
            argv = ["ilaas-agent", "tiers", "set", "--provider", "ilaas", "bogus", "x"]
            with mock.patch.dict(os.environ, {"ILAAS_MODEL_CATALOG": str(path)}), \
                 mock.patch("sys.argv", argv):
                with self.assertRaises(SystemExit) as ctx:
                    cli.main()
            self.assertNotEqual(ctx.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
