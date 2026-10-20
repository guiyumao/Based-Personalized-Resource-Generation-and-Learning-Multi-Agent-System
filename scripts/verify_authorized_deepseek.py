"""Explicitly authorized live run, secret via getpass, fixed upstream and hard caps.

Separate from normal pytest/no-cost execution. Child APIs only receive a local
gateway token; the real key stays in this parent process's memory.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import secrets
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class AuthorizedGateway:
    def __init__(self, key: str, output: Path):
        self.key = key
        self.output = output
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.Lock()
        self.chat = self.tools = self.reserved_output = self.used_output = 0
        self.requests = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_POST(self):
                if self.headers.get("Authorization") != "Bearer " + owner.token:
                    self.reply(401, b'{"error":{"message":"invalid local gateway token"}}')
                    return
                if self.path not in {"/v1/chat/completions", "/v1/tools/search", "/v1/tools/fetch"}:
                    self.reply(403, b'{"error":{"message":"path outside authorization"}}')
                    return
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
                chat = self.path.endswith("chat/completions")
                with owner.lock:
                    requested = min(int(body.get("max_tokens") or 2500), 4000) if chat else 0
                    allowed = owner.chat < 30 if chat else owner.tools < 6
                    if not allowed or owner.reserved_output + owner.used_output + requested > 60000:
                        self.reply(429, b'{"error":{"message":"authorized budget exhausted"}}')
                        return
                    if chat:
                        owner.chat += 1
                        owner.reserved_output += requested
                        body["max_tokens"] = requested
                        # One fixed model scope, no silent provider/model fallback.
                        body["model"] = "deepseek-chat"
                    else:
                        owner.tools += 1
                    attempt = owner.chat + owner.tools
                row = {
                    "attempt": attempt,
                    "started": datetime.now(UTC).isoformat(),
                    "path": self.path,
                    "request_model": body.get("model"),
                    "max_output_reserved": requested,
                    "upstream": "https://api.deepseek.com",
                    "source": "LIVE_AUTHORIZED_VIA_LOCAL_GATEWAY",
                }
                start = time.monotonic()
                request = urllib.request.Request(
                    "https://api.deepseek.com" + self.path,
                    data=json.dumps(body).encode(),
                    headers={
                        "Authorization": "Bearer " + owner.key,
                        "Content-Type": "application/json",
                    },
                    method="POST",
                )
                payload = b""
                status = 0
                usage = None
                try:
                    with urllib.request.urlopen(request, timeout=60) as response:
                        status = response.status
                        payload = response.read(2 * 1024 * 1024)
                    parsed = json.loads(payload) if not body.get("stream") else {}
                    usage = parsed.get("usage")
                    row.update(response_model=parsed.get("model"), response_id=parsed.get("id"))
                except urllib.error.HTTPError as exc:
                    status = exc.code
                    payload = exc.read(20000)
                except Exception as exc:
                    row["error_type"] = type(exc).__name__
                    payload = b'{"error":{"message":"upstream failed; see redacted ledger"}}'
                finally:
                    with owner.lock:
                        owner.reserved_output -= requested
                        # Ambiguous/streaming usage keeps its full reservation.
                        owner.used_output += (
                            int(usage.get("completion_tokens", requested)) if usage else requested
                        )
                        row.update(
                            status=status,
                            elapsed_seconds=round(time.monotonic() - start, 3),
                            usage=usage,
                            output_budget_charged=owner.used_output,
                            amount=None,
                        )
                        owner.requests.append(row)
                        with (output / "request-ledger.jsonl").open(
                            "a", encoding="utf-8"
                        ) as stream:
                            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                    self.reply(status or 502, payload)

            def reply(self, status, payload):
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def base(self):
        return f"http://127.0.0.1:{self.server.server_port}"

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.key = ""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument("--authorized", action="store_true")
    args = parser.parse_args()
    if not args.authorized or os.getenv("NO_COST_TEST") == "1":
        parser.error("requires separate explicit live authorization, outside no-cost runtime")
    output = args.run_root.resolve()
    output.mkdir(parents=True, exist_ok=False)
    # No command-line argument, environment value, file, or output contains key.
    key = getpass.getpass("DeepSeek test key (hidden): ")
    gateway = AuthorizedGateway(key, output)
    key = ""
    result = {
        "authorization": {"chat_attempts": 30, "search_fetch_attempts": 6, "output_tokens": 60000},
        "source": "LIVE_AUTHORIZED_VIA_LOCAL_GATEWAY",
    }
    try:
        import httpx

        with httpx.Client(timeout=70, trust_env=False) as client:
            response = client.post(
                gateway.base + "/v1/chat/completions",
                headers={"Authorization": "Bearer " + gateway.token},
                json={
                    "model": "deepseek-chat",
                    "messages": [
                        {"role": "user", "content": "请只用一句中文说明TCP确认机制，不超过30字。"}
                    ],
                    "max_tokens": 128,
                },
            )
            result["smoke"] = {"http": response.status_code}
            if response.status_code != 200:
                result["smoke"]["error"] = response.text[:1000]
                raise RuntimeError("Live connectivity failed; no business calls started")
            data = response.json()
            result["smoke"].update(
                model=data.get("model"),
                id=data.get("id"),
                usage=data.get("usage"),
                answer=data["choices"][0]["message"]["content"],
            )
        print(
            "Live connectivity confirmed; starting isolated real-provider business checks",
            flush=True,
        )
        # This child retains the no-cost boundary. Only this explicitly
        # authorized parent can access the real upstream; child key is sentinel.
        from run_no_cost_tests import isolated_environment

        env = isolated_environment(output / "business", [gateway.server.server_port])
        env.update(
            DEEPSEEK_API_BASE=gateway.base + "/v1",
            DEEPSEEK_SEARCH_BASE=gateway.base,
            DEEPSEEK_MODEL="deepseek-chat",
            LIVE_GATEWAY_TOKEN=gateway.token,
            NO_COST_LOCAL_API_TOKEN=gateway.token,
            LIVE_GATEWAY_BASE=gateway.base,
            LIVE_OUTPUT=str(output),
        )
        with (output / "business.log").open("w", encoding="utf-8") as log:
            child = subprocess.run(
                [sys.executable, str(ROOT / "scripts/verify_live_business.py")],
                cwd=ROOT,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=420,
            )
        result["business_exit_code"] = child.returncode
    except Exception as exc:
        result["error"] = str(exc)
    finally:
        gateway.close()
        result.update(
            chat_attempts=gateway.chat,
            search_fetch_attempts=gateway.tools,
            conservative_output_charged=gateway.used_output,
            amount=None,
            passed="error" not in result and result.get("business_exit_code") == 0,
        )
        (output / "LIVE_SUMMARY.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
