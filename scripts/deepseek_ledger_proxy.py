"""Local recording/budget proxy for DeepSeek acceptance runs.

The production knowledge budget only protects knowledge construction and
Search/Fetch. Chat, QA, courseware, exercises and reports are not covered. This
proxy sits in front of the provider so *every* outbound attempt is counted and
can be stopped before it leaves the machine:

    DEEPSEEK_API_BASE=http://127.0.0.1:<port>/v1
    DEEPSEEK_SEARCH_BASE=http://127.0.0.1:<port>
    python scripts/deepseek_ledger_proxy.py --upstream https://api.deepseek.com \
        --ledger artifacts/deepseek-live-<ts>/request-ledger.jsonl --max-attempts 46

It never prints or writes Authorization headers. Responses are buffered, so use
it for counting/budget enforcement, not for SSE latency or streaming-behaviour
tests. It is a test harness, not a production gateway; a real run through it
must be reported as "via gateway".
"""

from __future__ import annotations

import argparse
import json
import os
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit


class AttemptBudgetExceeded(RuntimeError):
    pass


@dataclass
class Ledger:
    path: str
    max_attempts: int = 0
    scenario: str = ""
    _count: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def count(self) -> int:
        with self._lock:
            return self._count

    def reserve(self) -> int:
        with self._lock:
            if self.max_attempts and self._count >= self.max_attempts:
                raise AttemptBudgetExceeded(
                    f"outbound attempt budget exhausted ({self._count}/{self.max_attempts})"
                )
            self._count += 1
            return self._count

    def write(self, payload: dict[str, Any]) -> None:
        directory = os.path.dirname(os.path.abspath(self.path))
        if directory:
            os.makedirs(directory, exist_ok=True)
        line = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        with self._lock, open(self.path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _request_model(body: bytes) -> tuple[str, bool, int]:
    try:
        data = json.loads(body.decode("utf-8")) if body else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "", False, 0
    if not isinstance(data, dict):
        return "", False, 0
    messages = data.get("messages")
    message_count = len(messages) if isinstance(messages, list) else 0
    return str(data.get("model") or ""), bool(data.get("stream")), message_count


def _response_meta(body: bytes) -> dict[str, Any]:
    try:
        data = json.loads(body.decode("utf-8")) if body else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    return {
        "response_model": str(data.get("model") or ""),
        "response_id": str(data.get("id") or ""),
        "usage": usage or None,
    }


class ProxyHandler(BaseHTTPRequestHandler):
    ledger: Ledger
    upstream: str
    timeout: float = 180.0

    def do_POST(self) -> None:  # noqa: N802
        self._proxy()

    def do_GET(self) -> None:  # noqa: N802
        self._proxy()

    def _proxy(self) -> None:
        length = int(self.headers.get("content-length") or 0)
        body = self.rfile.read(length) if length else b""
        request_model, stream, message_count = _request_model(body)
        started = time.perf_counter()
        started_at = _utc_now()

        try:
            attempt = self.ledger.reserve()
        except AttemptBudgetExceeded as exc:
            self.ledger.write(
                {
                    "ts_start": started_at,
                    "ts_end": _utc_now(),
                    "scenario": self.ledger.scenario,
                    "attempt": self.ledger.count,
                    "method": self.command,
                    "path": self.path,
                    "upstream_host": urlsplit(self.upstream).netloc,
                    "request_model": request_model,
                    "stream": stream,
                    "status": 429,
                    "blocked": True,
                    "error": str(exc),
                    "outbound": False,
                }
            )
            self._reply(429, {"error": {"message": str(exc), "type": "proxy_budget_exceeded"}})
            return

        url = self.upstream.rstrip("/") + self.path
        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in {"host", "content-length", "connection", "transfer-encoding"}
        }
        request = urllib.request.Request(url, data=body or None, headers=headers, method=self.command)
        status = 0
        response_body = b""
        error = ""
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                status = int(response.status)
                response_body = response.read()
        except urllib.error.HTTPError as exc:
            status = int(exc.code)
            response_body = exc.read()
            error = f"HTTP {status}"
        except Exception as exc:  # network/timeout: preserve a real failure record
            error = f"{type(exc).__name__}: {exc}"[:300]

        meta = _response_meta(response_body)
        self.ledger.write(
            {
                "ts_start": started_at,
                "ts_end": _utc_now(),
                "scenario": self.ledger.scenario,
                "attempt": attempt,
                "method": self.command,
                "path": self.path,
                "upstream_host": urlsplit(self.upstream).netloc,
                "request_model": request_model,
                "stream": stream,
                "message_count": message_count,
                "status": status,
                "bytes": len(response_body),
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                "error": error,
                "blocked": False,
                "outbound": True,
                **meta,
            }
        )

        if status == 0:
            self._reply(502, {"error": {"message": error or "upstream unavailable", "type": "proxy_upstream_error"}})
            return
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response_body)))
        self.send_header("X-DeepSeek-Proxy-Attempt", str(attempt))
        self.end_headers()
        self.wfile.write(response_body)

    def _reply(self, status: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_args) -> None:
        return


def create_proxy(
    *,
    upstream: str,
    ledger_path: str,
    max_attempts: int = 0,
    scenario: str = "",
    host: str = "127.0.0.1",
    port: int = 0,
) -> ThreadingHTTPServer:
    ledger = Ledger(path=ledger_path, max_attempts=max_attempts, scenario=scenario)
    handler = type("Handler", (ProxyHandler,), {"ledger": ledger, "upstream": upstream})
    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    return server


def main() -> None:
    parser = argparse.ArgumentParser(description="Recording/budget proxy for DeepSeek acceptance")
    parser.add_argument("--upstream", default=os.getenv("DEEPSEEK_UPSTREAM_BASE", "https://api.deepseek.com"))
    parser.add_argument("--ledger", default=os.getenv("DEEPSEEK_LEDGER_PATH", ""))
    parser.add_argument("--max-attempts", type=int, default=int(os.getenv("DEEPSEEK_MAX_ATTEMPTS", "0")))
    parser.add_argument("--scenario", default=os.getenv("DEEPSEEK_SCENARIO", ""))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.getenv("DEEPSEEK_PROXY_PORT", "0")))
    args = parser.parse_args()
    if not args.ledger:
        parser.error("--ledger (or DEEPSEEK_LEDGER_PATH) is required")

    server = create_proxy(
        upstream=args.upstream,
        ledger_path=args.ledger,
        max_attempts=args.max_attempts,
        scenario=args.scenario,
        host=args.host,
        port=args.port,
    )
    host, port = server.server_address
    print(
        json.dumps(
            {
                "event": "deepseek_ledger_proxy_ready",
                "url": f"http://{host}:{port}",
                "upstream_host": urlsplit(args.upstream).netloc,
                "max_attempts": args.max_attempts,
                "ledger": args.ledger,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
