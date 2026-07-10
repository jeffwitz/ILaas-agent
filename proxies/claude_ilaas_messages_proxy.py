#!/usr/bin/env python3
import argparse
import http.client
import json
import os
import socket
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    from proxies import retry_policy
except ImportError:  # running as a standalone script (proxies/ not on path)
    import retry_policy


MODEL_PREFIX = "claude-ilaas-"
DEFAULT_MODEL = "ilaas-default"
MAX_OUTPUT_TOKENS = int(os.environ.get("ILAAS_CLAUDE_MAX_TOKENS", "8192"))
SERVICE_NAME = "ilaas-claude-messages-proxy"
# Anthropic content blocks the Chat Completions upstream cannot represent;
# replaced with a text marker so the model and user know they were dropped.
UNSUPPORTED_BLOCK_TYPES = {"image", "thinking", "redacted_thinking"}
# Connect to upstream once; then allow up to IDLE_TIMEOUT seconds between
# SSE chunks. No total-duration cap while chunks keep flowing (B1).
CONNECT_TIMEOUT = 10
IDLE_TIMEOUT = int(os.environ.get("ILAAS_PROXY_IDLE_TIMEOUT", "120"))


class UpstreamHTTPError(Exception):
    def __init__(self, code, body):
        super().__init__(body)
        self.code = code
        self.body = body


def strip_model_prefix(model):
    if isinstance(model, str) and model.startswith(MODEL_PREFIX):
        return model[len(MODEL_PREFIX):]
    return model or DEFAULT_MODEL


def prefixed_model(model):
    model = strip_model_prefix(model)
    return MODEL_PREFIX + model


def chat_tool_choice_from_anthropic(payload):
    """Map Anthropic tool_choice to the Chat Completions tool_choice field."""
    choice = payload.get("tool_choice")
    if not isinstance(choice, dict):
        return "auto"
    kind = choice.get("type")
    if kind == "any":
        return "required"
    if kind == "tool":
        name = choice.get("name")
        if name:
            return {"type": "function", "function": {"name": name}}
    if kind == "none":
        return "none"
    return "auto"


def text_from_anthropic_content(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type")
            if block_type == "text" and isinstance(block.get("text"), str):
                parts.append(block["text"])
            elif block_type == "tool_result":
                tool_content = block.get("content", "")
                if isinstance(tool_content, str):
                    parts.append(tool_content)
                elif isinstance(tool_content, list):
                    parts.append(text_from_anthropic_content(tool_content))
            elif block_type in UNSUPPORTED_BLOCK_TYPES:
                print(f"claude proxy: unsupported {block_type} block omitted", flush=True)
                parts.append(f"[unsupported block omitted: {block_type}]")
        return "\n".join(part for part in parts if part)
    return ""


def chat_messages_from_anthropic(payload):
    messages = []
    system_parts = []
    selected_model = payload.get("model", DEFAULT_MODEL)
    selected_model_instruction = (
        "Selected ILaaS model slug: "
        + str(strip_model_prefix(selected_model))
        + ". If asked which ILaaS model is selected, answer with this slug. "
        + "Do not claim the selected ILaaS model is Claude or Mistral unless the selected model slug says so."
    )

    system = payload.get("system")
    if isinstance(system, str) and system.strip():
        system_parts.append(system)
    elif isinstance(system, list):
        text = text_from_anthropic_content(system)
        if text:
            system_parts.append(text)

    system_parts.append(selected_model_instruction)

    for item in payload.get("messages", []):
        if not isinstance(item, dict):
            continue
        role = item.get("role", "user")
        content = item.get("content", "")

        if role == "assistant" and isinstance(content, list):
            text_parts = []
            tool_calls = []
            for block in content:
                if not isinstance(block, dict):
                    continue
                block_type = block.get("type")
                if block_type == "text" and isinstance(block.get("text"), str):
                    text_parts.append(block["text"])
                elif block_type == "tool_use":
                    tool_calls.append({
                        "id": block.get("id") or "toolu_" + uuid.uuid4().hex,
                        "type": "function",
                        "function": {
                            "name": block.get("name", ""),
                            "arguments": json.dumps(block.get("input", {}), ensure_ascii=False),
                        },
                    })
            message = {"role": "assistant", "content": "\n".join(text_parts)}
            if tool_calls:
                message["tool_calls"] = tool_calls
            messages.append(message)
            continue

        if role == "user" and isinstance(content, list):
            pending_text = []
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_result":
                    if pending_text:
                        messages.append({"role": "user", "content": "\n".join(pending_text)})
                        pending_text = []
                    messages.append({
                        "role": "tool",
                        "tool_call_id": block.get("tool_use_id", ""),
                        "content": text_from_anthropic_content(block.get("content", "")),
                    })
                elif block.get("type") == "text" and isinstance(block.get("text"), str):
                    pending_text.append(block["text"])
            if pending_text:
                messages.append({"role": "user", "content": "\n".join(pending_text)})
            continue

        content_text = text_from_anthropic_content(content)
        if content_text:
            messages.append({"role": "assistant" if role == "assistant" else "user", "content": content_text})

    if system_parts:
        messages.insert(0, {"role": "system", "content": "\n\n".join(system_parts)})
    return messages or [{"role": "user", "content": ""}]


def sanitize_schema(value):
    if isinstance(value, dict):
        return {k: sanitize_schema(v) for k, v in value.items() if k != "$schema"}
    if isinstance(value, list):
        return [sanitize_schema(item) for item in value]
    return value


def chat_tools_from_anthropic(payload):
    tools = []
    for tool in payload.get("tools", []) or []:
        if not isinstance(tool, dict):
            continue
        name = tool.get("name")
        if not name:
            continue
        tools.append({
            "type": "function",
            "function": {
                "name": name,
                "description": tool.get("description", ""),
                "parameters": sanitize_schema(tool.get("input_schema", {"type": "object", "properties": {}})),
            },
        })
    return tools


def anthropic_usage(chat_usage):
    chat_usage = chat_usage or {}
    return {
        "input_tokens": int(chat_usage.get("prompt_tokens") or 0),
        "output_tokens": int(chat_usage.get("completion_tokens") or 0),
    }


def estimate_tokens(payload):
    text = json.dumps(payload.get("messages", []), ensure_ascii=False) + json.dumps(payload.get("system", ""), ensure_ascii=False)
    return max(1, len(text) // 4)


def anthropic_message(response_id, model, content, stop_reason, usage):
    return {
        "id": response_id,
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": usage,
    }


def resolve_stop(finish_reason, text, stop_sequences, has_tool_calls):
    """Best-effort Anthropic stop_reason/stop_sequence from a Chat Completions
    finish_reason. Stop-sequence detection is approximate: the upstream may
    strip the matched sequence from the text, so absence does not rule it out."""
    if has_tool_calls:
        return "tool_use", None
    if finish_reason == "length":
        return "max_tokens", None
    if finish_reason == "stop" and stop_sequences:
        for seq in stop_sequences:
            if seq and isinstance(text, str) and seq in text:
                return "stop_sequence", seq
    return "end_turn", None


def sse(data):
    return f"event: {data['type']}\ndata: {json.dumps(data, ensure_ascii=False, separators=(',', ':'))}\n\n".encode("utf-8")


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

    def request_path(self):
        return urllib.parse.urlparse(self.path).path

    def do_HEAD(self):
        self.send_response(HTTPStatus.OK)
        self.send_header("content-length", "0")
        self.end_headers()

    def do_GET(self):
        path = self.request_path()
        if path == "/health":
            self.send_json(HTTPStatus.OK, {"ok": True, "service": SERVICE_NAME})
            return
        if path == "/v1/models":
            self.send_json(HTTPStatus.OK, self.models_response())
            return
        self.send_json(HTTPStatus.NOT_FOUND, {"error": {"type": "not_found_error", "message": "not found"}})

    def do_POST(self):
        try:
            content_length = int(self.headers.get("content-length", "0"))
            payload = json.loads(self.rfile.read(content_length).decode("utf-8") or "{}")
            path = self.request_path()
            if path == "/v1/messages/count_tokens":
                print("claude proxy: count_tokens is a len//4 heuristic, not a real tokenizer", flush=True)
                self.send_json(HTTPStatus.OK, {"input_tokens": estimate_tokens(payload)})
                return
            if path == "/v1/messages":
                if payload.get("stream"):
                    self.handle_streaming_messages(payload)
                else:
                    chat_response = self.call_chat_completions(payload)
                    self.write_anthropic_result(payload, chat_response)
                return
            self.send_json(HTTPStatus.NOT_FOUND, {"error": {"type": "not_found_error", "message": "only /v1/messages is supported"}})
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            print(f"upstream HTTP {error.code}: {body[:2000]}", flush=True)
            self.send_json(error.code, {"error": {"type": "api_error", "message": body}})
        except UpstreamHTTPError as error:
            print(f"upstream HTTP {error.code}: {error.body[:2000]}", flush=True)
            self.send_json(error.code, {"error": {"type": "api_error", "message": error.body}})
        except Exception as error:
            print(f"proxy error: {error}", flush=True)
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": {"type": "api_error", "message": str(error)}})

    def upstream_json(self, path, payload=None):
        data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"content-type": "application/json", "authorization": self.headers.get("authorization", "Bearer sk-local-dummy")}
        request = urllib.request.Request(self.upstream_base + path, data=data, headers=headers, method="GET" if payload is None else "POST")
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            raise UpstreamHTTPError(error.code, body) from error

    def models_response(self):
        try:
            upstream = self.upstream_json("/models")
            ids = [item.get("id") for item in upstream.get("data", []) if isinstance(item, dict) and item.get("id")]
        except Exception:
            ids = [DEFAULT_MODEL]
        models = []
        for model_id in ids:
            exposed = prefixed_model(model_id)
            models.append({
                "id": exposed,
                "type": "model",
                "display_name": f"ILaaS {model_id}",
                "created_at": int(time.time()),
                "owned_by": "ilaas",
            })
        return {"data": models, "has_more": False, "first_id": models[0]["id"] if models else None, "last_id": models[-1]["id"] if models else None}

    def build_chat_payload(self, payload, stream=False):
        chat_payload = {
            "model": strip_model_prefix(payload.get("model", DEFAULT_MODEL)),
            "messages": chat_messages_from_anthropic(payload),
            "stream": stream,
        }
        if payload.get("max_tokens") is not None:
            requested = int(payload["max_tokens"])
            if requested > MAX_OUTPUT_TOKENS:
                print(f"claude proxy: max_tokens {requested} clamped to {MAX_OUTPUT_TOKENS}", flush=True)
            chat_payload["max_tokens"] = min(requested, MAX_OUTPUT_TOKENS)
        if payload.get("temperature") is not None:
            chat_payload["temperature"] = float(payload["temperature"])
        if payload.get("top_p") is not None:
            chat_payload["top_p"] = float(payload["top_p"])
        if payload.get("stop_sequences"):
            chat_payload["stop"] = payload["stop_sequences"]
        tools = chat_tools_from_anthropic(payload)
        if tools:
            chat_payload["tools"] = tools
            chat_payload["tool_choice"] = chat_tool_choice_from_anthropic(payload)
        debug_payload_path = os.environ.get("ILAAS_CLAUDE_DEBUG_PAYLOAD")
        if debug_payload_path:
            try:
                with open(debug_payload_path, "w") as fh:
                    json.dump(chat_payload, fh, ensure_ascii=False, indent=2)
            except Exception:
                pass
        return chat_payload

    def call_chat_completions(self, payload):
        chat_payload = self.build_chat_payload(payload, stream=False)
        try:
            return self.upstream_json("/chat/completions", chat_payload)
        except UpstreamHTTPError as error:
            rule = retry_policy.match(chat_payload, error.body)
            if rule:
                print(f"claude proxy: retrying {chat_payload.get('model')} (trigger: {rule.get('error_substring')})", flush=True)
                return self.upstream_json("/chat/completions", retry_policy.retry_payload(chat_payload, rule))
            raise

    def write_anthropic_result(self, request_payload, chat_response):
        response_id = "msg_" + uuid.uuid4().hex
        model = request_payload.get("model", prefixed_model(DEFAULT_MODEL))
        choice = (chat_response.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        finish_reason = choice.get("finish_reason")
        text = message.get("content") or ""
        content = []
        if text or not message.get("tool_calls"):
            content.append({"type": "text", "text": text})
        for tool_call in message.get("tool_calls") or []:
            function = tool_call.get("function") or {}
            try:
                tool_input = json.loads(function.get("arguments") or "{}")
            except json.JSONDecodeError:
                tool_input = {"arguments": function.get("arguments") or ""}
            content.append({
                "type": "tool_use",
                "id": tool_call.get("id") or "toolu_" + uuid.uuid4().hex,
                "name": function.get("name", ""),
                "input": tool_input,
            })
        stop_reason, stop_sequence = resolve_stop(
            finish_reason, text, request_payload.get("stop_sequences") or [], bool(message.get("tool_calls"))
        )
        usage = anthropic_usage(chat_response.get("usage"))
        result = anthropic_message(response_id, model, content, stop_reason, usage)
        result["stop_sequence"] = stop_sequence
        self.send_json(HTTPStatus.OK, result)

    def upstream_stream(self, path, chat_payload):
        """Open a streaming POST to upstream; return (conn, response) on HTTP 200.

        Raises UpstreamHTTPError on a non-200 status or a connect/read failure.
        The socket is switched to IDLE_TIMEOUT for chunk reads after connect.
        """
        body = json.dumps(chat_payload, ensure_ascii=False).encode("utf-8")
        parsed = urllib.parse.urlparse(self.upstream_base + path)
        conn = http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=CONNECT_TIMEOUT)
        headers = {"content-type": "application/json", "authorization": self.headers.get("authorization", "Bearer sk-local-dummy")}
        try:
            conn.request("POST", parsed.path or "/", body=body, headers=headers)
            response = conn.getresponse()
            if response.status != 200:
                error_body = response.read().decode("utf-8", errors="replace")
                conn.close()
                raise UpstreamHTTPError(response.status, error_body)
            if conn.sock is not None:
                conn.sock.settimeout(IDLE_TIMEOUT)
            return conn, response
        except UpstreamHTTPError:
            raise
        except (http.client.HTTPException, OSError) as error:
            try:
                conn.close()
            except Exception:
                pass
            raise UpstreamHTTPError(502, f"upstream stream connect/read failure: {error}") from error

    def handle_streaming_messages(self, request_payload):
        chat_payload = self.build_chat_payload(request_payload, stream=True)
        try:
            conn, response = self.upstream_stream("/chat/completions", chat_payload)
        except UpstreamHTTPError as error:
            rule = retry_policy.match(chat_payload, error.body)
            if rule:
                print(f"claude proxy: retrying {chat_payload.get('model')} (trigger: {rule.get('error_substring')})", flush=True)
                try:
                    conn, response = self.upstream_stream("/chat/completions", retry_policy.retry_payload(chat_payload, rule))
                except UpstreamHTTPError as err2:
                    print(f"upstream HTTP {err2.code}: {err2.body[:2000]}", flush=True)
                    self.send_json(err2.code, {"error": {"type": "api_error", "message": err2.body}})
                    return
            else:
                print(f"upstream HTTP {error.code}: {error.body[:2000]}", flush=True)
                self.send_json(error.code, {"error": {"type": "api_error", "message": error.body}})
                return
        self.write_anthropic_stream(request_payload, conn, response)

    def begin_sse(self):
        self.send_response(HTTPStatus.OK)
        self.send_header("content-type", "text/event-stream; charset=utf-8")
        self.send_header("cache-control", "no-cache")
        self.send_header("transfer-encoding", "chunked")
        self.end_headers()

    def end_sse(self):
        self.wfile.write(b"0\r\n\r\n")
        self.wfile.flush()

    def write_anthropic_stream(self, request_payload, conn, response):
        """Translate an upstream Chat Completions SSE stream to Anthropic
        events incrementally: text deltas live, tool-call argument fragments
        forwarded as input_json_delta as they arrive (true streaming)."""
        response_id = "msg_" + uuid.uuid4().hex
        model = request_payload.get("model", prefixed_model(DEFAULT_MODEL))
        input_tokens = estimate_tokens(request_payload)
        self.begin_sse()
        self.write_chunk(sse({"type": "message_start", "message": {
            "id": response_id, "type": "message", "role": "assistant", "model": model,
            "content": [], "stop_reason": None, "stop_sequence": None,
            "usage": {"input_tokens": input_tokens, "output_tokens": 0},
        }}))

        next_index = 0
        text_index = None
        full_text = ""
        tool_blocks = {}  # upstream tool index -> dict(block, id, name, started, pending_args)
        finish_reason = None
        usage_out = 0

        def close_text():
            nonlocal text_index
            if text_index is not None:
                self.write_chunk(sse({"type": "content_block_stop", "index": text_index}))
                text_index = None

        def emit_stream_error(message):
            self.write_chunk(sse({"type": "error", "error": {"type": "api_error", "message": message}}))
            self.write_chunk(sse({"type": "message_stop"}))
            self.end_sse()

        try:
            while True:
                raw = response.readline()
                if not raw:
                    break
                line = raw.decode("utf-8", errors="replace").strip()
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                choice = (chunk.get("choices") or [{}])[0]
                delta = choice.get("delta") or {}
                content = delta.get("content")
                if isinstance(content, str) and content:
                    if text_index is None:
                        text_index = next_index
                        next_index += 1
                        self.write_chunk(sse({"type": "content_block_start", "index": text_index, "content_block": {"type": "text", "text": ""}}))
                    full_text += content
                    self.write_chunk(sse({"type": "content_block_delta", "index": text_index, "delta": {"type": "text_delta", "text": content}}))
                for tc in delta.get("tool_calls") or []:
                    if not isinstance(tc, dict):
                        continue
                    ti = tc.get("index", 0)
                    if ti not in tool_blocks:
                        close_text()
                        tool_blocks[ti] = {"block": next_index, "id": None, "name": None, "started": False, "pending_args": ""}
                        next_index += 1
                    entry = tool_blocks[ti]
                    fn = tc.get("function") or {}
                    if entry["id"] is None and tc.get("id"):
                        entry["id"] = tc["id"]
                    if not entry["name"] and fn.get("name"):
                        entry["name"] = fn["name"]
                    args_frag = fn.get("arguments")
                    if not entry["started"] and entry["name"]:
                        entry["started"] = True
                        self.write_chunk(sse({"type": "content_block_start", "index": entry["block"], "content_block": {
                            "type": "tool_use",
                            "id": entry["id"] or ("toolu_" + uuid.uuid4().hex),
                            "name": entry["name"], "input": {},
                        }}))
                        if entry["pending_args"]:
                            self.write_chunk(sse({"type": "content_block_delta", "index": entry["block"], "delta": {"type": "input_json_delta", "partial_json": entry["pending_args"]}}))
                            entry["pending_args"] = ""
                    if args_frag:
                        if entry["started"]:
                            self.write_chunk(sse({"type": "content_block_delta", "index": entry["block"], "delta": {"type": "input_json_delta", "partial_json": args_frag}}))
                        else:
                            entry["pending_args"] += args_frag
                if choice.get("finish_reason"):
                    finish_reason = choice["finish_reason"]
                usage = chunk.get("usage")
                if isinstance(usage, dict):
                    if usage.get("completion_tokens") is not None:
                        usage_out = int(usage["completion_tokens"])
                    if usage.get("prompt_tokens") is not None:
                        input_tokens = int(usage["prompt_tokens"])
        except (socket.timeout, OSError) as error:
            emit_stream_error(f"upstream stream idle timeout: {error}")
            try:
                conn.close()
            except Exception:
                pass
            return
        except Exception as error:
            print(f"stream translation error: {error}", flush=True)
            emit_stream_error(f"stream translation error: {error}")
            try:
                conn.close()
            except Exception:
                pass
            return
        finally:
            try:
                conn.close()
            except Exception:
                pass

        close_text()
        any_tool = False
        for entry in tool_blocks.values():
            if entry["started"]:
                any_tool = True
                self.write_chunk(sse({"type": "content_block_stop", "index": entry["block"]}))
        stop_reason, stop_sequence = resolve_stop(
            finish_reason, full_text, request_payload.get("stop_sequences") or [], any_tool
        )
        self.write_chunk(sse({"type": "message_delta", "delta": {"stop_reason": stop_reason, "stop_sequence": stop_sequence}, "usage": {"output_tokens": usage_out}}))
        self.write_chunk(sse({"type": "message_stop"}))
        self.end_sse()

    def write_chunk(self, chunk):
        self.wfile.write(f"{len(chunk):X}\r\n".encode("ascii"))
        self.wfile.write(chunk)
        self.wfile.write(b"\r\n")
        self.wfile.flush()

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args), flush=True)


def main():
    parser = argparse.ArgumentParser(description="Minimal Anthropic Messages proxy for Claude Code through ILaaS/LiteLLM.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4002)
    parser.add_argument("--upstream", default="http://127.0.0.1:4000/v1")
    args = parser.parse_args()
    ProxyHandler.upstream_base = args.upstream.rstrip("/")
    server = ThreadingHTTPServer((args.host, args.port), ProxyHandler)
    print(f"listening on http://{args.host}:{args.port}/v1/messages -> {ProxyHandler.upstream_base}/chat/completions", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
