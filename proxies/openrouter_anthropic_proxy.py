from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


SERVICE_NAME = "openrouter-anthropic-discovery-proxy"
DISCOVERY_PREFIX = "claude-openrouter-"


def exposed_model_id(model_id: str) -> str:
    return f"{DISCOVERY_PREFIX}{model_id}"


def upstream_model_id(model_id: str) -> str:
    return model_id.removeprefix(DISCOVERY_PREFIX)


def eligible_model(item: dict) -> bool:
    supported = set(item.get("supported_parameters") or [])
    output_modalities = set((item.get("architecture") or {}).get("output_modalities") or ["text"])
    return isinstance(item.get("id"), str) and "tools" in supported and "text" in output_modalities


def anthropic_models(payload: dict) -> dict:
    models = []
    for item in payload.get("data", []):
        if not isinstance(item, dict) or not eligible_model(item):
            continue
        model_id = item["id"]
        created = datetime.fromtimestamp(int(item.get("created") or 0), tz=timezone.utc).isoformat().replace("+00:00", "Z")
        context_window = int(item.get("context_length") or 0)
        max_tokens = int((item.get("top_provider") or {}).get("max_completion_tokens") or 0)
        models.append(
            {
                "id": exposed_model_id(model_id),
                "type": "model",
                "display_name": f"OpenRouter · {item.get('name') or model_id}",
                "created_at": created,
                "max_input_tokens": context_window,
                "max_tokens": max_tokens,
            }
        )
    models.sort(key=lambda item: item["id"])
    return {
        "data": models,
        "has_more": False,
        "first_id": models[0]["id"] if models else None,
        "last_id": models[-1]["id"] if models else None,
    }


def inject_model_identity(payload: dict) -> dict:
    model = payload.get("model")
    if not isinstance(model, str) or not model:
        return payload
    actual_model = upstream_model_id(model)
    instruction = (
        f"The active API model is OpenRouter model '{actual_model}'. If asked which model is active, "
        f"answer exactly '{actual_model}' and do not infer another identity."
    )
    updated = dict(payload)
    updated["model"] = actual_model
    system = updated.get("system")
    if isinstance(system, str):
        updated["system"] = f"{system}\n\n{instruction}"
    elif isinstance(system, list):
        updated["system"] = [*system, {"type": "text", "text": instruction}]
    else:
        updated["system"] = instruction
    return updated


class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    upstream_base = "https://openrouter.ai/api"

    def send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def upstream_headers(self) -> dict[str, str]:
        skipped = {"host", "content-length", "connection", "accept-encoding"}
        return {key: value for key, value in self.headers.items() if key.lower() not in skipped}

    def upstream_request(self, *, body: bytes | None = None):
        request = urllib.request.Request(
            f"{self.upstream_base}{self.path}",
            data=body,
            headers=self.upstream_headers(),
            method=self.command,
        )
        try:
            return urllib.request.urlopen(request, timeout=3600)
        except urllib.error.HTTPError as error:
            return error

    def do_HEAD(self) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("content-length", "0")
        self.end_headers()

    def relay(self, response) -> None:
        self.send_response(response.status)
        skipped = {"content-length", "connection", "transfer-encoding", "content-encoding"}
        for key, value in response.headers.items():
            if key.lower() not in skipped:
                self.send_header(key, value)
        self.send_header("connection", "close")
        self.end_headers()
        while True:
            chunk = response.read(65536)
            if not chunk:
                break
            self.wfile.write(chunk)
            self.wfile.flush()
        self.close_connection = True

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/health":
            self.send_json(HTTPStatus.OK, {"ok": True, "service": SERVICE_NAME})
            return
        if path == "/v1/models":
            response = self.upstream_request()
            if response.status >= 400:
                self.relay(response)
                return
            self.send_json(HTTPStatus.OK, anthropic_models(json.load(response)))
            return
        self.relay(self.upstream_request())

    def do_POST(self) -> None:
        length = int(self.headers.get("content-length", "0"))
        body = self.rfile.read(length) if length else b""
        if urlsplit(self.path).path in {"/v1/messages", "/v1/messages/count_tokens"} and body:
            try:
                body = json.dumps(inject_model_identity(json.loads(body))).encode("utf-8")
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass
        self.relay(self.upstream_request(body=body))

def main() -> None:
    parser = argparse.ArgumentParser(description="OpenRouter Anthropic passthrough with Claude model discovery.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4012)
    parser.add_argument("--upstream", default="https://openrouter.ai/api")
    args = parser.parse_args()
    ProxyHandler.upstream_base = args.upstream.rstrip("/")
    server = ThreadingHTTPServer((args.host, args.port), ProxyHandler)
    print(f"listening on http://{args.host}:{args.port} -> {ProxyHandler.upstream_base}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
