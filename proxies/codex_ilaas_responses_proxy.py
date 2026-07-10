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


SERVICE_NAME = "ilaas-codex-responses-proxy"
# Connect to upstream once; then allow up to IDLE_TIMEOUT seconds between
# SSE chunks. No total-duration cap while chunks keep flowing (B1).
CONNECT_TIMEOUT = 10
IDLE_TIMEOUT = int(os.environ.get("ILAAS_PROXY_IDLE_TIMEOUT", "120"))


class UpstreamHTTPError(Exception):
    def __init__(self, code, body):
        super().__init__(body)
        self.code = code
        self.body = body


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
            self.send_json(HTTPStatus.OK, {"ok": True, "service": SERVICE_NAME})
            return
        self.send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_POST(self):
        if self.path != "/v1/responses":
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "only /v1/responses is supported"})
            return

        try:
            content_length = int(self.headers.get("content-length", "0"))
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
            if payload.get("stream"):
                self.handle_streaming_responses(payload)
            else:
                chat_response = self.call_chat_completions(payload)
                self.write_responses_result(payload, chat_response)
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            self.send_json(error.code, {"error": body})
        except UpstreamHTTPError as error:
            self.send_json(error.code, {"error": error.body})
        except Exception as error:
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(error)})

    def build_chat_payload(self, payload, stream=False):
        chat_payload = {
            "model": payload.get("model", "ilaas-default"),
            "messages": chat_messages_from_responses(payload),
            "stream": stream,
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
        return chat_payload

    def call_chat_completions(self, payload):
        chat_payload = self.build_chat_payload(payload, stream=False)
        headers = {
            "content-type": "application/json",
            "authorization": self.headers.get("authorization", "Bearer sk-local-dummy"),
        }
        try:
            return self.post_chat_completion(chat_payload, headers)
        except UpstreamHTTPError as error:
            rule = retry_policy.match(chat_payload, error.body)
            if rule:
                print(f"codex proxy: retrying {chat_payload.get('model')} (trigger: {rule.get('error_substring')})", flush=True)
                return self.post_chat_completion(retry_policy.retry_payload(chat_payload, rule), headers)
            raise

    def post_chat_completion(self, chat_payload, headers):
        request = urllib.request.Request(
            self.upstream_base + "/chat/completions",
            data=json.dumps(chat_payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            raise UpstreamHTTPError(error.code, body) from error

    def write_chunked(self, chunk):
        self.wfile.write(f"{len(chunk):X}\r\n".encode("ascii"))
        self.wfile.write(chunk)
        self.wfile.write(b"\r\n")
        self.wfile.flush()

    def upstream_stream(self, path, chat_payload):
        """Open a streaming POST to upstream; return (conn, response) on 200.

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

    def handle_streaming_responses(self, request_payload):
        chat_payload = self.build_chat_payload(request_payload, stream=True)
        try:
            conn, response = self.upstream_stream("/chat/completions", chat_payload)
        except UpstreamHTTPError as error:
            rule = retry_policy.match(chat_payload, error.body)
            if rule:
                print(f"codex proxy: retrying {chat_payload.get('model')} (trigger: {rule.get('error_substring')})", flush=True)
                try:
                    conn, response = self.upstream_stream("/chat/completions", retry_policy.retry_payload(chat_payload, rule))
                except UpstreamHTTPError as err2:
                    print(f"upstream HTTP {err2.code}: {err2.body[:2000]}", flush=True)
                    self.send_json(err2.code, {"error": err2.body})
                    return
            else:
                print(f"upstream HTTP {error.code}: {error.body[:2000]}", flush=True)
                self.send_json(error.code, {"error": error.body})
                return
        self.write_responses_stream(request_payload, conn, response)

    def begin_sse(self):
        self.send_response(HTTPStatus.OK)
        self.send_header("content-type", "text/event-stream; charset=utf-8")
        self.send_header("cache-control", "no-cache")
        self.send_header("x-accel-buffering", "no")
        self.send_header("transfer-encoding", "chunked")
        self.end_headers()

    def end_sse(self):
        self.wfile.write(b"0\r\n\r\n")
        self.wfile.flush()

    def write_responses_result(self, request_payload, chat_response):
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
        self.send_json(HTTPStatus.OK, response_object(response_id, model, "completed", output, usage))

    def write_responses_stream(self, request_payload, conn, response):
        """Translate an upstream Chat Completions SSE stream to Responses-API
        events incrementally: text deltas as response.output_text.delta and
        tool-call argument fragments as response.function_call_arguments.delta
        as they arrive (true streaming)."""
        response_id = "resp_" + uuid.uuid4().hex
        model = request_payload.get("model", "ilaas-default")
        in_progress = response_object(response_id, model, "in_progress", [])
        self.begin_sse()
        self.write_chunked(sse_line({"type": "response.created", "response": in_progress}))
        self.write_chunked(sse_line({"type": "response.in_progress", "response": in_progress}))

        output = []
        next_index = 0
        text_state = None  # {"index","id","text","started","closed"}
        tool_states = {}  # upstream tool index -> dict
        finish_reason = None
        usage_raw = None

        def ensure_text_started():
            nonlocal text_state, next_index
            if text_state is None:
                text_state = {"index": next_index, "id": "msg_" + uuid.uuid4().hex, "text": "", "started": False, "closed": False}
                next_index += 1
            if not text_state["started"]:
                text_state["started"] = True
                self.write_chunked(sse_line({
                    "type": "response.output_item.added", "output_index": text_state["index"],
                    "item": {"id": text_state["id"], "type": "message", "role": "assistant", "status": "in_progress", "content": []},
                }))
                self.write_chunked(sse_line({
                    "type": "response.content_part.added", "item_id": text_state["id"],
                    "output_index": text_state["index"], "content_index": 0,
                    "part": {"type": "output_text", "text": "", "annotations": []},
                }))

        def close_text():
            nonlocal text_state
            if text_state and text_state["started"] and not text_state["closed"]:
                text_state["closed"] = True
                text = text_state["text"]
                self.write_chunked(sse_line({"type": "response.output_text.done", "item_id": text_state["id"], "output_index": text_state["index"], "content_index": 0, "text": text}))
                self.write_chunked(sse_line({"type": "response.content_part.done", "item_id": text_state["id"], "output_index": text_state["index"], "content_index": 0, "part": {"type": "output_text", "text": text, "annotations": []}}))
                item = {"type": "message", "id": text_state["id"], "status": "completed", "role": "assistant", "content": [{"type": "output_text", "text": text, "annotations": []}]}
                self.write_chunked(sse_line({"type": "response.output_item.done", "output_index": text_state["index"], "sequence_number": text_state["index"] + 1, "item": item}))
                output.append(item)
                text_state = None

        def emit_stream_error(message):
            failed = response_object(response_id, model, "failed", [], None)
            failed["error"] = {"message": message}
            self.write_chunked(sse_line({"type": "response.failed", "response": failed}))
            self.write_chunked(b"data: [DONE]\n\n")
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
                    ensure_text_started()
                    text_state["text"] += content
                    self.write_chunked(sse_line({"type": "response.output_text.delta", "item_id": text_state["id"], "output_index": text_state["index"], "content_index": 0, "delta": content}))
                for tc in delta.get("tool_calls") or []:
                    if not isinstance(tc, dict):
                        continue
                    ti = tc.get("index", 0)
                    if ti not in tool_states:
                        close_text()
                        tool_states[ti] = {"index": next_index, "id": "fc_" + uuid.uuid4().hex, "call_id": None, "name": None, "arguments": "", "emitted": 0, "started": False, "closed": False}
                        next_index += 1
                    st = tool_states[ti]
                    fn = tc.get("function") or {}
                    if st["call_id"] is None and tc.get("id"):
                        st["call_id"] = tc["id"]
                    if not st["name"] and fn.get("name"):
                        st["name"] = fn["name"]
                    args_frag = fn.get("arguments") or ""
                    if args_frag:
                        st["arguments"] += args_frag
                    if not st["started"] and st["name"]:
                        st["started"] = True
                        self.write_chunked(sse_line({
                            "type": "response.output_item.added", "output_index": st["index"],
                            "item": {"type": "function_call", "id": st["id"], "call_id": st["call_id"] or ("call_" + uuid.uuid4().hex), "status": "in_progress", "name": st["name"], "arguments": ""},
                        }))
                    if st["started"] and len(st["arguments"]) > st["emitted"]:
                        new = st["arguments"][st["emitted"]:]
                        self.write_chunked(sse_line({"type": "response.function_call_arguments.delta", "item_id": st["id"], "output_index": st["index"], "delta": new}))
                        st["emitted"] = len(st["arguments"])
                if choice.get("finish_reason"):
                    finish_reason = choice["finish_reason"]
                usage = chunk.get("usage")
                if isinstance(usage, dict):
                    usage_raw = usage
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
        for st in tool_states.values():
            if st["started"] and not st["closed"]:
                st["closed"] = True
                self.write_chunked(sse_line({"type": "response.function_call_arguments.done", "item_id": st["id"], "output_index": st["index"], "arguments": st["arguments"]}))
                item = {"type": "function_call", "id": st["id"], "call_id": st["call_id"] or ("call_" + uuid.uuid4().hex), "status": "completed", "name": st["name"], "arguments": st["arguments"]}
                self.write_chunked(sse_line({"type": "response.output_item.done", "output_index": st["index"], "sequence_number": st["index"] + 1, "item": item}))
                output.append(item)

        usage = responses_usage(usage_raw) if usage_raw else None
        self.write_chunked(sse_line({"type": "response.completed", "response": response_object(response_id, model, "completed", output, usage)}))
        self.write_chunked(b"data: [DONE]\n\n")
        self.end_sse()

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
