"""Budget-gateway unit integration; upstream is in-memory, never a paid call."""

import json
import urllib.request

import httpx
import pytest

from scripts.verify_authorized_deepseek import AuthorizedGateway


@pytest.fixture
def gateway(tmp_path, monkeypatch):
    calls = []

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, *args):
            return json.dumps(
                {
                    "id": "fake-response",
                    "model": "test",
                    "choices": [],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 2},
                }
            ).encode()

    def fake(request, **kwargs):
        calls.append(json.loads(request.data))
        return Response()

    monkeypatch.setattr(urllib.request, "urlopen", fake)
    instance = AuthorizedGateway("not-a-real-provider-key", tmp_path)
    yield instance, calls, tmp_path
    instance.close()


def request(gateway, path="/v1/chat/completions", **body):
    return httpx.post(
        gateway.base + path,
        headers={"Authorization": "Bearer " + gateway.token},
        json=body,
        trust_env=False,
    )


def test_chat_attempt_cap_and_no_key_in_ledger(gateway):
    server, calls, tmp_path = gateway
    for _ in range(30):
        assert request(server, max_tokens=16).status_code == 200
    assert request(server, max_tokens=16).status_code == 429
    assert len(calls) == 30 and server.chat == 30
    assert all(row["model"] == "deepseek-chat" for row in calls)
    assert "not-a-real-provider-key" not in (tmp_path / "request-ledger.jsonl").read_text()


def test_tools_have_separate_six_attempt_budget(gateway):
    server, calls, _ = gateway
    for _ in range(6):
        assert request(server, path="/v1/tools/search", query="test").status_code == 200
    assert request(server, path="/v1/tools/fetch", url="https://example.edu").status_code == 429
    assert server.chat == 0 and server.tools == 6 and len(calls) == 6


def test_output_reservation_blocks_before_upstream(gateway):
    server, calls, _ = gateway
    server.used_output = 59950
    assert request(server, max_tokens=128).status_code == 429
    assert not calls
