"""Prompt-template registry and its administrator routes (P1-07)."""
from __future__ import annotations

import pytest

from services.agent_service.app.services import prompt_registry
from services.agent_service.app.services.prompt_registry import (
    ALLOWED_PROMPTS,
    _path_for,
    _placeholders,
    list_prompts,
    read_prompt,
    update_prompt,
)


@pytest.fixture
def isolated_prompt_dir(tmp_path, monkeypatch):
    """Point the registry at a temp directory so tests never touch real prompts."""

    monkeypatch.setattr(prompt_registry, "PROMPT_DIR", tmp_path)
    (tmp_path / "coordinator.md").write_text(
        "# Coordinator\nRoute to {agent_name} with {knowledge_point}.", encoding="utf-8"
    )
    return tmp_path


def test_path_for_rejects_unknown_and_traversal():
    for bad in ("../secret.md", "coordinator.md/../../etc", "resource_gen.py", "", "Coordinator.md"):
        with pytest.raises(LookupError):
            _path_for(bad)


def test_path_for_resolves_whitelisted():
    assert _path_for("coordinator.md").name == "coordinator.md"


def test_placeholders_extraction():
    assert _placeholders("use {subject} and {knowledge_point} and {subject}") == [
        "knowledge_point",
        "subject",
    ]
    assert _placeholders("no variables here") == []


def test_update_prompt_preserves_placeholders(isolated_prompt_dir):
    # Dropping a declared placeholder must fail before any write happens.
    with pytest.raises(ValueError) as exc:
        update_prompt("coordinator.md", "no placeholders at all")
    assert "agent_name" in str(exc.value)

    # The real file is untouched because validation ran before the write.
    assert "agent_name" in (isolated_prompt_dir / "coordinator.md").read_text(encoding="utf-8")


def test_update_prompt_succeeds_keeping_placeholders(isolated_prompt_dir):
    updated = update_prompt("coordinator.md", "Route to {agent_name} and {knowledge_point}.")
    assert updated["name"] == "coordinator.md"
    assert "agent_name" in (isolated_prompt_dir / "coordinator.md").read_text(encoding="utf-8")


def test_list_and_read_prompts(isolated_prompt_dir):
    items = list_prompts()
    assert len(items) == 1
    assert items[0]["name"] == "coordinator.md"
    assert items[0]["placeholders"] == ["agent_name", "knowledge_point"]

    detail = read_prompt("coordinator.md")
    assert detail["content"].startswith("# Coordinator")
    assert detail["placeholders"] == ["agent_name", "knowledge_point"]


def test_allowed_prompts_are_stable():
    # The whitelist must stay a plain tuple of known .md files so the route can
    # never resolve an arbitrary path.
    assert isinstance(ALLOWED_PROMPTS, tuple)
    assert all(name.endswith(".md") and "/" not in name and "\\" not in name for name in ALLOWED_PROMPTS)
