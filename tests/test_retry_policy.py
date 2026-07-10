import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from proxies import retry_policy


class RetryPolicyMatchTest(unittest.TestCase):
    def setUp(self):
        # Always start from the built-in default table, ignoring any host config.
        retry_policy._RULES = list(retry_policy.DEFAULT_RULES)

    def test_match_qwen_tools_unterminated(self):
        rule = retry_policy.match(
            {"model": "qwen-3.6-35b-instruct", "tools": [{"type": "function"}]},
            "OpenAIException - Unterminated string starting at: line 1 column 9",
        )
        self.assertIsNotNone(rule)
        self.assertEqual(rule["model_prefix"], "qwen-")

    def test_no_match_wrong_model(self):
        rule = retry_policy.match(
            {"model": "mistral-medium-latest", "tools": [{"type": "function"}]},
            "Unterminated string",
        )
        self.assertIsNone(rule)

    def test_no_match_without_tools(self):
        rule = retry_policy.match({"model": "qwen-3.6-35b-instruct"}, "Unterminated string")
        self.assertIsNone(rule)

    def test_no_match_wrong_substring(self):
        rule = retry_policy.match(
            {"model": "qwen-3.6-35b-instruct", "tools": [{"type": "function"}]},
            "some other error",
        )
        self.assertIsNone(rule)


class RetryPayloadTest(unittest.TestCase):
    def setUp(self):
        retry_policy._RULES = list(retry_policy.DEFAULT_RULES)

    def test_prepends_corrective_system_message(self):
        payload = {"model": "qwen-3.6-35b-instruct", "messages": [{"role": "user", "content": "hi"}], "tools": [{"type": "function"}]}
        rule = retry_policy.match(payload, "Unterminated string")
        new = retry_policy.retry_payload(payload, rule)
        self.assertEqual(new["messages"][0]["role"], "system")
        self.assertIn("valid JSON", new["messages"][0]["content"])
        self.assertEqual(new["messages"][1:], payload["messages"])
        # original payload is untouched
        self.assertEqual(len(payload["messages"]), 1)


class RetryPolicyOverrideTest(unittest.TestCase):
    def test_override_loaded_from_json(self):
        custom = [{"model_prefix": "mistral-", "requires_tools": False, "error_substring": "boom", "corrective_message": "fix it"}]
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "ilaas-agent" / "retry-policies.json"
            cfg.parent.mkdir(parents=True)
            cfg.write_text(json.dumps(custom))
            with mock.patch("proxies.retry_policy.config_path", return_value=cfg):
                rules = retry_policy.reload_rules()
        self.assertEqual(rules, custom)
        self.assertIsNotNone(retry_policy.match({"model": "mistral-medium"}, "boom"))
        # default qwen rule no longer present after override
        self.assertIsNone(retry_policy.match({"model": "qwen-x", "tools": [{}]}, "Unterminated string"))


class SingleRetryBudgetTest(unittest.TestCase):
    """The proxy retries at most once: a matching failure triggers one retry,
    and a second failure on the retry is surfaced to the client."""

    def setUp(self):
        retry_policy._RULES = list(retry_policy.DEFAULT_RULES)

    def test_call_chat_completions_retries_once_then_raises(self):
        from proxies import claude_ilaas_messages_proxy as claude_proxy

        handler = claude_proxy.ProxyHandler.__new__(claude_proxy.ProxyHandler)
        attempts = {"n": 0}

        def fake_upstream(path, payload):
            attempts["n"] += 1
            raise claude_proxy.UpstreamHTTPError(500, "Unterminated string")

        handler.upstream_json = fake_upstream
        payload = {
            "model": "qwen-3.6-35b-instruct",
            "messages": [{"role": "user", "content": "use a tool"}],
            "tools": [{"name": "read_file", "input_schema": {"type": "object"}}],
        }
        with self.assertRaises(claude_proxy.UpstreamHTTPError):
            handler.call_chat_completions(payload)
        # one original attempt + one retry = 2 total, not more
        self.assertEqual(attempts["n"], 2)


if __name__ == "__main__":
    unittest.main()
