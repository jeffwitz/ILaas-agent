#!/usr/bin/env python3
import argparse
import json
import time
import uuid
import urllib.error
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def text_from_content(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    return ""


def chat_messages_from_responses(payload):
    messages = []
    selected_model = payload.get("model", "ilaas-default")
    system_parts = [
        "Selected ILaaS model slug: "
        + str(selected_model)
        + ". If asked which model is selected, answer with this slug. "
        + "Do not claim to be Mistral unless the selected model slug starts with mistral or is the legacy alias mistral-ilaas."
    ]
    instructions = payload.get("instructions")
    if isinstance(instructions, str) and instructions.strip():
        system_parts.append(instructions)

    for item in payload.get("input", []):
        if not isinstance(item, dict):
            continue

        item_type = item.get("type")
        if item_type == "function_call":
            messages.append({
                "role": "assistant",
                "content": "",
                "tool_calls": [{
                    "id": item.get("call_id") or item.get("id") or ("call_" + uuid.uuid4().hex),
                    "type": "function",
                    "function": {
                        "name": item.get("name", ""),
                        "arguments": item.get("arguments", "{}"),
                    },
                }],
            })
            continue
        if item_type == "function_call_output":
            messages.append({
                "role": "tool",
                "tool_call_id": item.get("call_id", ""),
                "content": item.get("output", ""),
            })
            continue

        role = item.get("role", "user")
        if role == "developer":
            role = "system"
        elif role not in {"system", "user", "assistant", "tool"}:
            role = "user"

        content = text_from_content(item.get("content", ""))
        if content and role == "system":
            system_parts.append(content)
        elif content:
            messages.append({"role": role, "content": content})

    if not messages and isinstance(payload.get("input"), str):
        messages.append({"role": "user", "content": payload["input"]})

    if system_parts:
        messages.insert(0, {"role": "system", "content": "\n\n".join(system_parts)})

    return messages or [{"role": "user", "content": ""}]


def chat_tools_from_responses(payload):
    tools = []
    for tool in payload.get("tools", []):
        if not isinstance(tool, dict) or tool.get("type") != "function":
            continue
        name = tool.get("name")
        if not name:
            continue
        function = {
            "name": name,
            "description": tool.get("description", ""),
            "parameters": tool.get("parameters", {"type": "object", "properties": {}}),
        }
        tools.append({"type": "function", "function": function})
    return tools


def responses_usage(chat_usage):
    chat_usage = chat_usage or {}
    input_tokens = int(chat_usage.get("prompt_tokens") or 0)
    output_tokens = int(chat_usage.get("completion_tokens") or 0)
    total_tokens = int(chat_usage.get("total_tokens") or input_tokens + output_tokens)
    return {
        "input_tokens": input_tokens,
        "input_tokens_details": {
            "cached_tokens": (chat_usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)
        },
        "output_tokens": output_tokens,
        "output_tokens_details": {"reasoning_tokens": 0},
        "total_tokens": total_tokens,
    }


def sse_line(data):
    return f"data: {json.dumps(data, ensure_ascii=False, separators=(',', ':'))}\n\n".encode("utf-8")


def response_object(response_id, model, status, output, usage=None):
    obj = {
        "id": response_id,
        "created_at": int(time.time()),
        "model": model,
        "object": "response",
        "output": output,
        "parallel_tool_calls": False,
        "tool_choice": "auto",
        "tools": [],
        "status": status,
    }
    if usage is not None:
        obj["usage"] = usage
    return obj


def function_call_output_from_chat(tool_call):
    function = tool_call.get("function") or {}
    call_id = tool_call.get("id") or ("call_" + uuid.uuid4().hex)
    return {
        "type": "function_call",
        "id": "fc_" + uuid.uuid4().hex,
        "call_id": call_id,
        "status": "completed",
        "name": function.get("name", ""),
        "arguments": function.get("arguments", "{}"),
    }


class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    upstream_base = "http://127.0.0.1:4000/v1"

    def send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self.send_json(HTTPStatus.OK, {"ok": True})
            return
        self.send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_POST(self):
        if self.path != "/v1/responses":
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "only /v1/responses is supported"})
            return

        try:
            content_length = int(self.headers.get("content-length", "0"))
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
            chat_response = self.call_chat_completions(payload)
            self.write_responses_result(payload, chat_response)
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            self.send_json(error.code, {"error": body})
        except Exception as error:
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(error)})

    def call_chat_completions(self, payload):
        chat_payload = {
            "model": payload.get("model", "ilaas-default"),
            "messages": chat_messages_from_responses(payload),
            "stream": False,
        }

        if payload.get("max_output_tokens") is not None:
            chat_payload["max_tokens"] = payload["max_output_tokens"]
        elif payload.get("max_completion_tokens") is not None:
            chat_payload["max_tokens"] = payload["max_completion_tokens"]

        if payload.get("temperature") is not None:
            chat_payload["temperature"] = payload["temperature"]
        if payload.get("top_p") is not None:
            chat_payload["top_p"] = payload["top_p"]

        tools = chat_tools_from_responses(payload)
        if tools:
            chat_payload["tools"] = tools
            chat_payload["tool_choice"] = "auto"

        headers = {
            "content-type": "application/json",
            "authorization": self.headers.get("authorization", "Bearer sk-local-dummy"),
        }
        request = urllib.request.Request(
            self.upstream_base + "/chat/completions",
            data=json.dumps(chat_payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=180) as response:
            return json.loads(response.read().decode("utf-8"))

    def write_chunked(self, chunk):
        self.wfile.write(f"{len(chunk):X}\r\n".encode("ascii"))
        self.wfile.write(chunk)
        self.wfile.write(b"\r\n")
        self.wfile.flush()

    def write_responses_result(self, request_payload, chat_response):
        stream = bool(request_payload.get("stream", False))
        response_id = "resp_" + uuid.uuid4().hex
        message_id = "msg_" + uuid.uuid4().hex
        model = request_payload.get("model", chat_response.get("model", "ilaas-default"))

        choice = (chat_response.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        text = message.get("content") or ""
        usage = responses_usage(chat_response.get("usage"))
        tool_calls = message.get("tool_calls") or []
        output = []
        if text or not tool_calls:
            output.append({
                "type": "message",
                "id": message_id,
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": text, "annotations": []}],
            })
        output.extend(function_call_output_from_chat(tool_call) for tool_call in tool_calls)

        if not stream:
            self.send_json(HTTPStatus.OK, response_object(response_id, model, "completed", output, usage))
            return

        self.send_response(HTTPStatus.OK)
        self.send_header("content-type", "text/event-stream; charset=utf-8")
        self.send_header("cache-control", "no-cache")
        self.send_header("x-accel-buffering", "no")
        self.send_header("transfer-encoding", "chunked")
        self.end_headers()

        in_progress = response_object(response_id, model, "in_progress", [])
        self.write_chunked(sse_line({"type": "response.created", "response": in_progress}))
        self.write_chunked(sse_line({"type": "response.in_progress", "response": in_progress}))
        for index, item in enumerate(output):
            if item["type"] == "message":
                self.write_message_item(index, item)
            elif item["type"] == "function_call":
                self.write_function_call_item(index, item)
        self.write_chunked(sse_line({
            "type": "response.completed",
            "response": response_object(response_id, model, "completed", output, usage),
        }))
        self.write_chunked(b"data: [DONE]\n\n")
        self.wfile.write(b"0\r\n\r\n")
        self.wfile.flush()

    def write_message_item(self, index, item):
        item_id = item["id"]
        text = item["content"][0]["text"]
        self.write_chunked(sse_line({
            "type": "response.output_item.added",
            "output_index": index,
            "item": {"id": item_id, "type": "message", "role": "assistant", "status": "in_progress", "content": []},
        }))
        self.write_chunked(sse_line({
            "type": "response.content_part.added",
            "item_id": item_id,
            "output_index": index,
            "content_index": 0,
            "part": {"type": "output_text", "text": "", "annotations": []},
        }))
        if text:
            self.write_chunked(sse_line({
                "type": "response.output_text.delta",
                "item_id": item_id,
                "output_index": index,
                "content_index": 0,
                "delta": text,
            }))
        self.write_chunked(sse_line({
            "type": "response.output_text.done",
            "item_id": item_id,
            "output_index": index,
            "content_index": 0,
            "text": text,
        }))
        self.write_chunked(sse_line({
            "type": "response.content_part.done",
            "item_id": item_id,
            "output_index": index,
            "content_index": 0,
            "part": {"type": "output_text", "text": text, "annotations": []},
        }))
        self.write_chunked(sse_line({
            "type": "response.output_item.done",
            "output_index": index,
            "sequence_number": index + 1,
            "item": item,
        }))

    def write_function_call_item(self, index, item):
        added_item = dict(item)
        added_item["arguments"] = ""
        self.write_chunked(sse_line({
            "type": "response.output_item.added",
            "output_index": index,
            "item": added_item,
        }))
        arguments = item.get("arguments", "")
        if arguments:
            self.write_chunked(sse_line({
                "type": "response.function_call_arguments.delta",
                "item_id": item["id"],
                "output_index": index,
                "delta": arguments,
            }))
        self.write_chunked(sse_line({
            "type": "response.function_call_arguments.done",
            "item_id": item["id"],
            "output_index": index,
            "arguments": arguments,
        }))
        self.write_chunked(sse_line({
            "type": "response.output_item.done",
            "output_index": index,
            "sequence_number": index + 1,
            "item": item,
        }))

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args), flush=True)


def main():
    parser = argparse.ArgumentParser(description="Minimal Codex Responses API proxy for ILaaS through LiteLLM chat completions.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4001)
    parser.add_argument("--upstream", default="http://127.0.0.1:4000/v1")
    args = parser.parse_args()

    ProxyHandler.upstream_base = args.upstream.rstrip("/")
    server = ThreadingHTTPServer((args.host, args.port), ProxyHandler)
    print(f"listening on http://{args.host}:{args.port}/v1/responses -> {ProxyHandler.upstream_base}/chat/completions", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
