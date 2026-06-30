import unittest

from proxies.openrouter_anthropic_proxy import anthropic_models, inject_model_identity


class OpenRouterAnthropicProxyTest(unittest.TestCase):
    def test_anthropic_models_filters_for_text_tool_models(self):
        payload = {
            "data": [
                {
                    "id": "z-ai/glm-5.2",
                    "name": "GLM 5.2",
                    "created": 123,
                    "architecture": {"output_modalities": ["text"]},
                    "supported_parameters": ["tools"],
                },
                {
                    "id": "image/only",
                    "name": "Image",
                    "architecture": {"output_modalities": ["image"]},
                    "supported_parameters": [],
                },
            ]
        }
        result = anthropic_models(payload)
        self.assertEqual([item["id"] for item in result["data"]], ["claude-openrouter-z-ai/glm-5.2"])
        self.assertEqual(result["data"][0]["display_name"], "OpenRouter · GLM 5.2")
        self.assertEqual(result["data"][0]["created_at"], "1970-01-01T00:02:03Z")

    def test_inject_model_identity_handles_system_blocks(self):
        result = inject_model_identity(
            {
                "model": "claude-openrouter-z-ai/glm-5.2",
                "system": [{"type": "text", "text": "Original"}],
            }
        )
        self.assertEqual(result["model"], "z-ai/glm-5.2")
        self.assertEqual(result["system"][0]["text"], "Original")
        self.assertIn("answer exactly 'z-ai/glm-5.2'", result["system"][1]["text"])


if __name__ == "__main__":
    unittest.main()
