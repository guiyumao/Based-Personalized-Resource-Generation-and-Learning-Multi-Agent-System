"""Supply-chain containment tests for the Chroma vector store (round 3).

Context
-------
``pip-audit`` reports 5 known vulnerabilities against ``chromadb`` with no
upstream fix available. Chroma 0.5.x also serves its whole HTTP API — including
collection administration — **without authentication**, so the practical risk is
exposure rather than the CVE payloads themselves.

These tests pin the containment controls:

* the published port is bound to host loopback, never to ``0.0.0.0``
* the application refuses to connect to a non-loopback / non-private Chroma host
  unless explicitly overridden
* no code path enables remote code execution (``trust_remote_code``)
"""

from __future__ import annotations

import pathlib
import re

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
COMPOSE = REPO_ROOT / "docker-compose.yml"


def _compose_text() -> str:
    return COMPOSE.read_text(encoding="utf-8")


# --------------------------------------------------------------------- compose
def test_chroma_port_is_not_published_on_all_interfaces() -> None:
    """The Chroma admin API must not be reachable from the network."""

    text = _compose_text()
    # Isolate the chroma service block.
    match = re.search(r"^  chroma:\n(?P<body>(?:.*\n)*?)(?=^  \S|\Z)", text, re.MULTILINE)
    assert match, "chroma service block not found in docker-compose.yml"
    block = match.group("body")

    published = re.findall(r'-\s*"([^"]+)"', block)
    assert published, "chroma service publishes no ports (expected a loopback binding)"

    for mapping in published:
        parts = mapping.split(":")
        # Accept "127.0.0.1:8010:8000" or "8010:8000" forms.
        if len(parts) == 3:
            host_ip = parts[0]
            assert host_ip in {"127.0.0.1", "::1", "localhost"}, (
                f"chroma port published on a non-loopback interface: {mapping}"
            )
        else:
            pytest.fail(
                f"chroma port published without a host address ({mapping}); "
                "that binds to all interfaces and exposes the unauthenticated API"
            )
        assert not re.search(r"\b0\.0\.0\.0\b", mapping), (
            f"chroma port bound to 0.0.0.0: {mapping}"
        )


def test_chroma_image_version_is_pinned() -> None:
    """An unpinned image could silently pull a different (unaudited) version."""

    text = _compose_text()
    match = re.search(r"image:\s*(chromadb/chroma:\S+)", text)
    assert match, "chroma image not found"
    tag = match.group(1).split(":")[-1]
    assert tag != "latest", "chroma image must be pinned to a concrete version"


# ----------------------------------------------------------------- app-side guard
def _guard(host: str, *, allow_remote: bool = False, monkeypatch=None) -> None:
    from common import config as config_module
    from services.agent_service.app.services.rag import _assert_chroma_host_is_trusted

    settings = config_module.get_settings()
    if monkeypatch is not None:
        monkeypatch.setattr(
            type(settings),
            "chroma_allow_remote_host",
            property(lambda self: allow_remote),
            raising=False,
        )
    _assert_chroma_host_is_trusted(host)


@pytest.mark.parametrize(
    "host",
    ["localhost", "127.0.0.1", "::1", "chroma", "10.1.2.3", "172.18.0.5", "192.168.1.10", "100.64.0.7"],
)
def test_trusted_chroma_hosts_are_allowed(host: str, monkeypatch) -> None:
    """Loopback, compose service names and RFC1918 addresses stay usable."""

    _guard(host, monkeypatch=monkeypatch)


@pytest.mark.parametrize(
    "host",
    ["8.8.8.8", "1.1.1.1", "203.0.113.10", "198.51.100.7", "chroma.internal", "chroma.example.com", "evil-host.net"],
)
def test_public_chroma_hosts_are_refused(host: str, monkeypatch) -> None:
    """An unauthenticated Chroma on a public/dotted host must be refused."""

    with pytest.raises(ValueError) as excinfo:
        _guard(host, monkeypatch=monkeypatch)
    assert "CHROMA_ALLOW_REMOTE_HOST" in str(excinfo.value)


def test_remote_chroma_requires_explicit_opt_in(monkeypatch) -> None:
    """The override exists but must be intentional."""

    _guard("203.0.113.10", allow_remote=True, monkeypatch=monkeypatch)


def test_empty_chroma_host_is_rejected(monkeypatch) -> None:
    with pytest.raises(ValueError):
        _guard("", monkeypatch=monkeypatch)


# --------------------------------------------------- no remote code execution
def test_no_code_path_enables_trust_remote_code() -> None:
    """Chroma/SentenceTransformers remote code loading must never be enabled.

    Only executable/searchable *code* is scanned: ``tests/`` names the setting,
    and policy/config metadata (``.github/``) documents it, so neither is a place
    where it could actually be enabled. The check looks for an assignment or
    keyword-argument usage rather than a bare mention.
    """

    # Matches trust_remote_code=<value> (kwarg) or trust_remote_code: <value> (yaml/json key)
    usage_pattern = re.compile(r"trust_remote_code\s*[:=]\s*(?!\s*[\"']?(false|False|no|0)\b)")

    offenders: list[str] = []
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in {".py", ".yml", ".yaml", ".toml"}:
            continue
        if any(
            part in {"node_modules", ".git", "__pycache__", ".venv", "artifacts", "tests", ".github"}
            for part in path.parts
        ):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for line_no, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if usage_pattern.search(line):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{line_no}")

    assert offenders == [], f"trust_remote_code must not be enabled: {offenders}"


def test_documented_default_is_remote_host_disabled() -> None:
    """The shipped default must be the safe one."""

    env_example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    assert "CHROMA_ALLOW_REMOTE_HOST=false" in env_example, (
        ".env.example must document the safe default for CHROMA_ALLOW_REMOTE_HOST"
    )
