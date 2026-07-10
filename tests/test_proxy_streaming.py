import json
import socket
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from proxies import claude_ilaas_messages_proxy as claude_proxy


def sse_line(payload):
    """A Chat Completions SSE data line, as upstream would emit."""
    if payload == "[DONE]":
        return b"data: [DONE]\n\n"
    return b"data: " + json.dumps(payload).encode("utf-8") + b"\n\n"


def parse_events(events):
    """Decode the list of chunk bytes written by the proxy into (type, data)."""
    out = []
    for chunk in events:
        for block in chunk.decode("utf-8").split("\n\n"):
            block = block.strip()
            if not block:
                continue
            ev_type = None
            data = None
            for line in block.split("\n"):
                if line.startswith("event: "):
                    ev_type = line[7:].strip()
                elif line.startswith("data: "):
                    data = line[6:]
            if ev_type and data:
                out.append((ev_type, json.loads(data)))
    return out


class CapturingHandler(claude_proxy.ProxyHandler):
    """A handler that records SSE chunks instead of writing to a socket."""

    def __init__(self):
        self.events = []

    def begin_sse(self):
        pass

    def end_sse(self):
        pass

    def write_chunk(self, chunk):
        self.events.append(chunk)


class FakeResponse:
    def __init__(self, lines):
        self._lines = iter(lines)

    def readline(self):
        try:
            return next(self._lines)
        except StopIteration:
            return b""


class _NoConn:
    def close(self):
        pass


class StreamingTranslatorTest(unittest.TestCase):
    def _run(self, lines, request_payload=None):
        handler = CapturingHandler()
        handler.write_anthropic_stream(
            request_payload or {"model": "claude-ilaas-test", "messages": []},
            _NoConn(),
            FakeResponse(lines),
        )
        return parse_events(handler.events)

    def test_text_deltas_streamed(self):
        lines = [
            sse_line({"choices": [{"delta": {"content": "Hello"}}]}),
            sse_line({"choices": [{"delta": {"content": " world"}}]}),
            sse_line({"choices": [{"delta": {}, "finish_reason": "stop"}]}),
            sse_line("[DONE]"),
        ]
        events = self._run(lines)
        types = [t for t, _ in events]
        self.assertEqual(types[0], "message_start")
        self.assertEqual(types[-1], "message_stop")
        deltas = [d for t, d in events if t == "content_block_delta"]
        self.assertEqual([d["delta"]["text"] for d in deltas], ["Hello", " world"])
        msg_delta = [d for t, d in events if t == "message_delta"][0]
        self.assertEqual(msg_delta["delta"]["stop_reason"], "end_turn")

    def test_tool_call_arguments_split_across_chunks(self):
        lines = [
            sse_line({"choices": [{"delta": {"tool_calls": [
                {"index": 0, "id": "call_1", "type": "function",
                 "function": {"name": "read_file", "arguments": ""}}]}}]}),
            sse_line({"choices": [{"delta": {"tool_calls": [
                {"index": 0, "function": {"arguments": "{\"path\":"}}]}}]}),
            sse_line({"choices": [{"delta": {"tool_calls": [
                {"index": 0, "function": {"arguments": "\"README.md\"}"}}]}}]}),
            sse_line({"choices": [{"delta": {}, "finish_reason": "tool_calls"}]}),
            sse_line("[DONE]"),
        ]
        events = self._run(lines)
        starts = [d for t, d in events if t == "content_block_start"]
        self.assertEqual(starts[0]["content_block"]["type"], "tool_use")
        self.assertEqual(starts[0]["content_block"]["name"], "read_file")
        self.assertEqual(starts[0]["content_block"]["id"], "call_1")
        deltas = [d for t, d in events if t == "content_block_delta"]
        self.assertTrue(all(d["delta"]["type"] == "input_json_delta" for d in deltas))
        combined = "".join(d["delta"]["partial_json"] for d in deltas)
        self.assertEqual(json.loads(combined), {"path": "README.md"})
        msg_delta = [d for t, d in events if t == "message_delta"][0]
        self.assertEqual(msg_delta["delta"]["stop_reason"], "tool_use")
        self.assertIn("content_block_stop", [t for t, _ in events])

    def test_premature_eof_ends_gracefully(self):
        lines = [sse_line({"choices": [{"delta": {"content": "Hi"}}]})]
        events = self._run(lines)
        types = [t for t, _ in events]
        self.assertEqual(types[0], "message_start")
        self.assertEqual(types[-1], "message_stop")
        self.assertNotIn("error", types)

    def test_mid_stream_oserror_emits_terminal_error(self):
        class RaisingResponse:
            def readline(self):
                raise ConnectionResetError("upstream reset")

        handler = CapturingHandler()
        handler.write_anthropic_stream(
            {"model": "claude-ilaas-test", "messages": []}, _NoConn(), RaisingResponse()
        )
        events = parse_events(handler.events)
        types = [t for t, _ in events]
        self.assertEqual(types[0], "message_start")
        self.assertIn("error", types)
        self.assertEqual(types[-1], "message_stop")

    def test_idle_timeout_emits_error(self):
        class IdleResponse:
            def readline(self):
                raise socket.timeout("idle")

        handler = CapturingHandler()
        handler.write_anthropic_stream(
            {"model": "claude-ilaas-test", "messages": []}, _NoConn(), IdleResponse()
        )
        events = parse_events(handler.events)
        err = [d for t, d in events if t == "error"][0]
        self.assertIn("idle timeout", err["error"]["message"])


class _FakeUpstreamHandler(BaseHTTPRequestHandler):
    script = []

    def do_POST(self):
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.end_headers()
        for line in type(self).script:
            self.wfile.write(line)
            self.wfile.flush()

    def log_message(self, *args):
        pass


class StreamingEndToEndTest(unittest.TestCase):
    def _start(self, handler_class):
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler_class)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return server

    def _stop(self, server):
        server.shutdown()
        server.server_close()

    def _post_stream(self, port, payload):
        import http.client

        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        body = json.dumps(payload).encode("utf-8")
        conn.request("POST", "/v1/messages", body=body, headers={"content-type": "application/json"})
        response = conn.getresponse()
        data = response.read().decode("utf-8")
        conn.close()
        return data

    def test_end_to_end_text_streaming(self):
        _FakeUpstreamHandler.script = [
            sse_line({"choices": [{"delta": {"content": "Hi "}}]}),
            sse_line({"choices": [{"delta": {"content": "there"}}]}),
            sse_line({"choices": [{"delta": {}, "finish_reason": "stop"}]}),
            sse_line("[DONE]"),
        ]
        upstream = self._start(_FakeUpstreamHandler)
        try:
            claude_proxy.ProxyHandler.upstream_base = f"http://127.0.0.1:{upstream.server_address[1]}/v1"
            proxy = self._start(claude_proxy.ProxyHandler)
            try:
                raw = self._post_stream(proxy.server_address[1], {"model": "claude-ilaas-test", "messages": [], "stream": True, "max_tokens": 16})
            finally:
                self._stop(proxy)
        finally:
            self._stop(upstream)
        # The response is an SSE stream of Anthropic events.
        self.assertIn("event: message_start", raw)
        self.assertIn("text_delta", raw)
        self.assertIn("event: message_stop", raw)


if __name__ == "__main__":
    unittest.main()
