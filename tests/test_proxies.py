import json
import unittest
from http import HTTPStatus

from proxies import claude_ilaas_messages_proxy as claude_proxy
from proxies import codex_ilaas_responses_proxy as codex_proxy


class Recorder:
    def __init__(self):
        self.status = None
        self.payload = None

    def send_json(self, status, payload):
        self.status = status
        self.payload = payload


class ProxyTranslationTest(unittest.TestCase):
    def test_codex_request_tool_call_round_trip_to_chat_messages(self):
        payload = {
            "model": "qwen-3.6-35b-instruct",
            "instructions": "Be concise.",
            "tools": [
                {
                    "type": "function",
                    "name": "read_file",
                    "description": "Read a file",
                    "parameters": {"type": "object", "properties": {"path": {"type": "string"}}},
                }
            ],
            "input": [
                {"role": "developer", "content": [{"type": "input_text", "text": "Use tools."}]},
                {"role": "user", "content": [{"type": "input_text", "text": "Read README.md"}]},
                {"type": "function_call", "call_id": "call_1", "name": "read_file", "arguments": "{\"path\":\"README.md\"}"},
                {"type": "function_call_output", "call_id": "call_1", "output": "README content"},
            ],
        }

        messages = codex_proxy.chat_messages_from_responses(payload)
        tools = codex_proxy.chat_tools_from_responses(payload)

        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("qwen-3.6-35b-instruct", messages[0]["content"])
        self.assertEqual(messages[1], {"role": "user", "content": "Read README.md"})
        self.assertEqual(messages[2]["role"], "assistant")
        self.assertEqual(messages[2]["tool_calls"][0]["id"], "call_1")
        self.assertEqual(messages[3], {"role": "tool", "tool_call_id": "call_1", "content": "README content"})
        self.assertEqual(tools[0]["function"]["name"], "read_file")

    def test_codex_chat_tool_call_becomes_responses_function_call(self):
        recorder = Recorder()
        chat_response = {
            "model": "qwen-3.6-35b-instruct",
            "choices": [
                {
                    "message": {
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {"name": "read_file", "arguments": "{\"path\":\"README.md\"}"},
                            }
                        ],
                    }
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13},
        }

        codex_proxy.ProxyHandler.write_responses_result(
            recorder,
            {"model": "qwen-3.6-35b-instruct", "stream": False},
            chat_response,
        )

        self.assertEqual(recorder.status, HTTPStatus.OK)
        self.assertEqual(recorder.payload["output"][0]["type"], "function_call")
        self.assertEqual(recorder.payload["output"][0]["call_id"], "call_1")
        self.assertEqual(recorder.payload["usage"]["total_tokens"], 13)

    def test_codex_qwen_tool_json_error_is_retryable(self):
        from proxies import retry_policy

        payload = {"model": "qwen-3.6-35b-instruct", "tools": [{"type": "function"}]}
        self.assertIsNotNone(
            retry_policy.match(payload, "OpenAIException - Unterminated string starting at: line 1 column 9")
        )
        self.assertIsNone(
            retry_policy.match(
                {"model": "mistral-medium-latest", "tools": [{"type": "function"}]},
                "OpenAIException - Unterminated string starting at: line 1 column 9",
            )
        )

    def test_claude_request_tool_result_round_trip_to_chat_messages(self):
        payload = {
            "model": "claude-ilaas-qwen-3.6-35b-instruct",
            "system": "You are concise.",
            "tools": [
                {
                    "name": "read_file",
                    "description": "Read a file",
                    "input_schema": {"type": "object", "$schema": "http://json-schema.org/draft-07/schema#"},
                }
            ],
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": "Read README.md"}]},
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_1",
                            "name": "read_file",
                            "input": {"path": "README.md"},
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "tool_result", "tool_use_id": "toolu_1", "content": "README content"}
                    ],
                },
            ],
        }

        messages = claude_proxy.chat_messages_from_anthropic(payload)
        tools = claude_proxy.chat_tools_from_anthropic(payload)

        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("qwen-3.6-35b-instruct", messages[0]["content"])
        self.assertEqual(messages[1], {"role": "user", "content": "Read README.md"})
        self.assertEqual(messages[2]["tool_calls"][0]["id"], "toolu_1")
        self.assertEqual(messages[3], {"role": "tool", "tool_call_id": "toolu_1", "content": "README content"})
        self.assertNotIn("$schema", json.dumps(tools[0]["function"]["parameters"]))

    def test_claude_chat_tool_call_becomes_anthropic_tool_use(self):
        recorder = Recorder()
        chat_response = {
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {"name": "read_file", "arguments": "{\"path\":\"README.md\"}"},
                            }
                        ],
                    },
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 3},
        }

        claude_proxy.ProxyHandler.write_anthropic_result(
            recorder,
            {"model": "claude-ilaas-qwen-3.6-35b-instruct", "stream": False},
            chat_response,
        )

        self.assertEqual(recorder.status, HTTPStatus.OK)
        self.assertEqual(recorder.payload["stop_reason"], "tool_use")
        self.assertEqual(recorder.payload["content"][0]["type"], "tool_use")
        self.assertEqual(recorder.payload["content"][0]["input"], {"path": "README.md"})

    def test_claude_qwen_tool_json_error_is_retryable(self):
        from proxies import retry_policy

        payload = {"model": "qwen-3.6-35b-instruct", "tools": [{"type": "function"}]}
        self.assertIsNotNone(
            retry_policy.match(payload, "OpenAIException - Unterminated string starting at: line 1 column 9")
        )


if __name__ == "__main__":
    unittest.main()
