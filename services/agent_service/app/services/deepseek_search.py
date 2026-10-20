"""Official DeepSeek Search/Fetch adapter for reviewed knowledge candidates."""

from __future__ import annotations

import ipaddress
import os
import re
import socket
import time
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

from common.config import get_settings

#: Official endpoint by default. A deployment that must go through a reviewed
#: gateway (or a local recording proxy during acceptance) can override the root
#: explicitly; every such run must be reported as "via gateway", never as a
#: direct official connection.
_ROOT = os.getenv("DEEPSEEK_SEARCH_BASE", "https://api.deepseek.com").rstrip("/")


class DeepSeekSearchUnavailable(RuntimeError):
    def __init__(self, message: str, *, code: str = "DEEPSEEK_SEARCH_UNAVAILABLE") -> None:
        super().__init__(message)
        self.code = code


def _allow_fake_ip() -> bool:
    """Explicit, opt-in relaxation for local fake-IP DNS proxies (e.g. Clash/Surge).

    The machine resolves every public host to a fake 198.18.0.0/15 address, which
    is not "global" and would otherwise fail the SSRF check. This is only enabled
    when the operator sets ``DEEPSEEK_SEARCH_ALLOW_FAKE_IP=1`` after accepting the
    security trade-off (the real fetch still happens on DeepSeek's server side).
    """
    return os.getenv("DEEPSEEK_SEARCH_ALLOW_FAKE_IP", "").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _resolve_public_host(host: str) -> bool:
    try:
        addresses = {row[4][0] for row in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)}
    except OSError:
        return False
    if not addresses:
        return False
    if _allow_fake_ip():
        return True
    return all(ipaddress.ip_address(address).is_global for address in addresses)


def _public_url(url: str) -> bool:
    if len(url) > 8192:
        return False
    try:
        parsed = urlsplit(url)
        _ = parsed.port
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        return False
    host = parsed.hostname.lower().rstrip(".")
    if host in {"localhost", "localhost.localdomain"} or host.endswith((".local", ".internal", ".lan", ".home")):
        return False
    try:
        return ipaddress.ip_address(host).is_global
    except ValueError:
        return not bool(re.fullmatch(r"[0-9.]+|0x[0-9a-f]+", host))


def _post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    key = get_settings().deepseek_api_key
    if not key:
        raise DeepSeekSearchUnavailable("DEEPSEEK_API_KEY is required for Search and Fetch")
    for attempt in range(2):
        call_id = None
        try:
            from services.agent_service.app.services.knowledge_budget import reserve_usage
            reserve_usage("fetch" if path.endswith("/fetch") else "search")
            from common.model_usage import begin_call, finish_call
            call_id = str(uuid4())
            begin_call(call_id, "deepseek-tools", "fetch" if path.endswith("/fetch") else "search")
            with httpx.Client(timeout=45.0 if path.endswith("/fetch") else 20.0) as client:
                response = client.post(
                    f"{_ROOT}{path}",
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
            finish_call(call_id, response=data)
            break
        except httpx.TimeoutException as exc:
            if call_id:
                finish_call(call_id, error=exc)
            if attempt:
                raise
        except httpx.HTTPStatusError as exc:
            if call_id:
                finish_call(call_id, error=exc)
            if attempt or exc.response.status_code not in {408, 429, 500, 502, 503, 504}:
                raise
        except Exception as exc:
            if call_id:
                finish_call(call_id, error=exc)
            raise
        time.sleep(0.75)
    if not isinstance(data, dict):
        raise DeepSeekSearchUnavailable("DeepSeek returned an invalid response")
    return data


def search_sources(query: str, *, count: int = 5, need_content: bool = False) -> list[dict[str, str]]:
    query = query.strip()
    if not 1 <= len(query) <= 128 or not 1 <= count <= 5:
        raise ValueError("Search query or result count is out of bounds")
    data = _post("/v1/tools/search", {"query": query, "count": count, "need_content": need_content})
    rows = data.get("results")
    if not isinstance(rows, list):
        raise DeepSeekSearchUnavailable("DeepSeek Search returned no results array")
    output: list[dict[str, str]] = []
    for row in rows[:count]:
        if not isinstance(row, dict) or not _public_url(str(row.get("url") or "")):
            continue
        item = {
            "title": str(row.get("title") or "")[:300],
            "url": str(row.get("url") or "")[:8192],
            "summary": str(row.get("summary") or row.get("snippet") or "")[:2000],
        }
        if need_content:
            # The public DeepSeek API has no /v1/tools/fetch endpoint (it 404s);
            # search with need_content=True returns the page body inline instead.
            item["content"] = str(row.get("content") or "")[:50000]
        output.append(item)
    return output


def fetch_source(url: str) -> dict[str, Any]:
    if not _public_url(url) or not _resolve_public_host(str(urlsplit(url).hostname)):
        raise ValueError("Invalid source URL")
    data = _post("/v1/tools/fetch", {"url": url})
    content = data.get("content")
    if not isinstance(content, str) or not content.strip():
        raise DeepSeekSearchUnavailable("DeepSeek Fetch returned empty content", code="SOURCE_EMPTY")
    final_url = str(data.get("url") or data.get("final_url") or url)
    if not _public_url(final_url) or not _resolve_public_host(str(urlsplit(final_url).hostname)):
        raise DeepSeekSearchUnavailable("DeepSeek Fetch returned an unsafe final URL")
    content, redactions = re.subn(r"(?i)(?:sk-[a-z0-9_-]{20,}|authorization\s*:\s*bearer\s+\S+)", "[REDACTED_SECRET]", content)
    return {
        "url": url,
        "title": str(data.get("title") or "")[:300],
        "content": content[:50000],
        "truncated": len(content) > 50000,
        "final_url": final_url,
        "redactions": redactions,
    }
