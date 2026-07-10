import os
import unittest
from unittest import mock

from proxies import claude_ilaas_messages_proxy as claude_proxy
from proxies import codex_ilaas_responses_proxy as codex_proxy


class ToolChoiceMappingTest(unittest.TestCase):
    def test_auto_default(self):
        self.assertEqual(claude_proxy.chat_tool_choice_from_anthropic({"tool_choice": {"type": "auto"}}), "auto")
        self.assertEqual(claude_proxy.chat_tool_choice_from_anthropic({}), "auto")

    def test_any_maps_to_required(self):
        self.assertEqual(claude_proxy.chat_tool_choice_from_anthropic({"tool_choice": {"type": "any"}}), "required")

    def test_tool_maps_to_named_function(self):
        result = claude_proxy.chat_tool_choice_from_anthropic({"tool_choice": {"type": "tool", "name": "read_file"}})
        self.assertEqual(result, {"type": "function", "function": {"name": "read_file"}})

    def test_none_maps_to_none(self):
        self.assertEqual(claude_proxy.chat_tool_choice_from_anthropic({"tool_choice": {"type": "none"}}), "none")


class UnsupportedBlockTest(unittest.TestCase):
    def test_image_block_replaced_by_marker(self):
        content = [
            {"type": "text", "text": "see this"},
            {"type": "image", "source": {"data": "..."}},
        ]
        text = claude_proxy.text_from_anthropic_content(content)
        self.assertIn("[unsupported block omitted: image]", text)
        self.assertIn("see this", text)

    def test_thinking_block_replaced_by_marker(self):
        text = claude_proxy.text_from_anthropic_content([{"type": "thinking", "thinking": "secret"}])
        self.assertIn("[unsupported block omitted: thinking]", text)


class ResolveStopTest(unittest.TestCase):
    def test_tool_use_wins(self):
        reason, seq = claude_proxy.resolve_stop("tool_calls", "x", ["STOP"], True)
        self.assertEqual(reason, "tool_use")
        self.assertIsNone(seq)

    def test_length_maps_to_max_tokens(self):
        reason, _ = claude_proxy.resolve_stop("length", "x", [], False)
        self.assertEqual(reason, "max_tokens")

    def test_stop_sequence_matched(self):
        reason, seq = claude_proxy.resolve_stop("stop", "hello STOP world", ["STOP"], False)
        self.assertEqual(reason, "stop_sequence")
        self.assertEqual(seq, "STOP")

    def test_stop_without_match_is_end_turn(self):
        reason, seq = claude_proxy.resolve_stop("stop", "nothing here", ["STOP"], False)
        self.assertEqual(reason, "end_turn")
        self.assertIsNone(seq)


class MaxTokensClampTest(unittest.TestCase):
    def _handler(self):
        return claude_proxy.ProxyHandler.__new__(claude_proxy.ProxyHandler)

    def test_clamps_and_keeps_tool_choice(self):
        handler = self._handler()
        payload = {
            "model": "claude-ilaas-test",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 999999,
            "tools": [{"name": "read_file", "input_schema": {"type": "object"}}],
            "tool_choice": {"type": "tool", "name": "read_file"},
        }
        chat = handler.build_chat_payload(payload)
        self.assertLessEqual(chat["max_tokens"], claude_proxy.MAX_OUTPUT_TOKENS)
        self.assertEqual(chat["tool_choice"], {"type": "function", "function": {"name": "read_file"}})

    def test_default_max_tokens_is_8192(self):
        self.assertGreaterEqual(claude_proxy.MAX_OUTPUT_TOKENS, 8192)


class IdentityInjectionOptOutTest(unittest.TestCase):
    def test_claude_injection_default_on(self):
        messages = claude_proxy.chat_messages_from_anthropic(
            {"model": "claude-ilaas-qwen-3.6-35b-instruct", "messages": [{"role": "user", "content": "hi"}]}
        )
        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("Selected ILaaS model slug", messages[0]["content"])

    def test_claude_injection_disabled(self):
        with mock.patch.dict(os.environ, {"ILAAS_INJECT_MODEL_IDENTITY": "0"}):
            messages = claude_proxy.chat_messages_from_anthropic(
                {"model": "claude-ilaas-qwen-3.6-35b-instruct", "messages": [{"role": "user", "content": "hi"}]}
            )
        # no system message at all when identity injection is off and no other system content
        self.assertTrue(all(m["role"] != "system" for m in messages))

    def test_codex_injection_disabled(self):
        with mock.patch.dict(os.environ, {"ILAAS_INJECT_MODEL_IDENTITY": "0"}):
            messages = codex_proxy.chat_messages_from_responses(
                {"model": "qwen-3.6-35b-instruct", "input": [{"role": "user", "content": [{"type": "input_text", "text": "hi"}]}]}
            )
        self.assertTrue(all(m["role"] != "system" for m in messages))


if __name__ == "__main__":
    unittest.main()
