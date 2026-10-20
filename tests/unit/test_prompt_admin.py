"""Prompt-template registry and its administrator routes (P1-07)."""
from __future__ import annotations

import pytest

from services.agent_service.app.services import prompt_registry
from services.agent_service.app.services.prompt_registry import (
    ALLOWED_PROMPTS,
    _path_for,
    _placeholders,
    list_prompt_versions,
    list_prompts,
    load_prompt_template,
    read_prompt,
    read_prompt_version,
    restore_prompt,
    update_prompt,
)


@pytest.fixture
def isolated_prompt_dir(tmp_path, monkeypatch):
    """Point the registry at a temp directory so tests never touch real prompts."""

    monkeypatch.setattr(prompt_registry, "PROMPT_DIR", tmp_path)
    (tmp_path / "resource_gen.md").write_text(
        "# Resource\nRoute to {agent_name} with {knowledge_point}.", encoding="utf-8"
    )
    return tmp_path


def test_path_for_rejects_unknown_and_traversal():
    for bad in ("../secret.md", "resource_gen.md/../../etc", "coordinator.py", "", "Resource_gen.md"):
        with pytest.raises(LookupError):
            _path_for(bad)


def test_path_for_resolves_whitelisted():
    assert _path_for("resource_gen.md").name == "resource_gen.md"


def test_placeholders_extraction():
    assert _placeholders("use {subject} and {knowledge_point} and {subject}") == [
        "knowledge_point",
        "subject",
    ]
    assert _placeholders("no variables here") == []


def test_update_prompt_preserves_placeholders(isolated_prompt_dir):
    # Dropping a declared placeholder must fail before any write happens.
    with pytest.raises(ValueError) as exc:
        update_prompt("resource_gen.md", "no placeholders at all")
    assert "agent_name" in str(exc.value)

    # The real file is untouched because validation ran before the write.
    assert "agent_name" in (isolated_prompt_dir / "resource_gen.md").read_text(encoding="utf-8")


def test_update_prompt_succeeds_keeping_placeholders(isolated_prompt_dir):
    updated = update_prompt("resource_gen.md", "Route to {agent_name} and {knowledge_point}.")
    assert updated["name"] == "resource_gen.md"
    assert "agent_name" in (isolated_prompt_dir / "resource_gen.md").read_text(encoding="utf-8")


def test_list_and_read_prompts(isolated_prompt_dir):
    items = list_prompts()
    assert len(items) == 1
    assert items[0]["name"] == "resource_gen.md"
    assert items[0]["placeholders"] == ["agent_name", "knowledge_point"]

    detail = read_prompt("resource_gen.md")
    assert detail["content"].startswith("# Resource")
    assert detail["placeholders"] == ["agent_name", "knowledge_point"]


def test_allowed_prompts_are_stable():
    # The whitelist must stay a plain tuple of known .md files so the route can
    # never resolve an arbitrary path.
    assert isinstance(ALLOWED_PROMPTS, tuple)
    assert all(name.endswith(".md") and "/" not in name and "\\" not in name for name in ALLOWED_PROMPTS)


def test_orphan_templates_are_not_exposed():
    # Templates with no loader must not be editable: editing them would change
    # nothing because the coordinator/QA services still embed prompts inline.
    orphans = {"coordinator.md", "knowledge_graph.md", "learner_profile.md", "path_planning.md", "qa.md"}
    assert orphans.isdisjoint(ALLOWED_PROMPTS)
    # The six templates the generation chain actually loads must stay present.
    assert {"resource_gen.md", "exercise_gen.md", "evaluation_feedback.md", "mind_map_gen.md", "code_case_gen.md", "video_script_gen.md"} <= set(ALLOWED_PROMPTS)


def test_update_prompt_snapshots_previous_version(isolated_prompt_dir):
    update_prompt("resource_gen.md", "Route to {agent_name} and {knowledge_point}. (v2)")
    versions = list_prompt_versions("resource_gen.md")
    assert len(versions) == 1
    # The snapshot preserves the pre-update body.
    snapshot = read_prompt_version("resource_gen.md", versions[0]["version"])
    assert "Route to" in snapshot["content"]
    assert "v2" not in snapshot["content"]


def test_restore_prompt_restores_and_snapshots_again(isolated_prompt_dir):
    first = update_prompt("resource_gen.md", "v2 keeps {agent_name} and {knowledge_point}.")
    versions = list_prompt_versions("resource_gen.md")
    assert len(versions) == 1

    restore_prompt("resource_gen.md", versions[0]["version"])
    restored = read_prompt("resource_gen.md")
    assert "v2 keeps" not in restored["content"]
    # Restoring snapshots the v2 body, so no state is ever lost.
    assert len(list_prompt_versions("resource_gen.md")) == 2
    assert first["placeholders"] == ["agent_name", "knowledge_point"]


def test_restore_prompt_rejects_unknown_version(isolated_prompt_dir):
    with pytest.raises(LookupError):
        restore_prompt("resource_gen.md", "19990101T000000000000Z")
    # Traversal-style version ids are rejected before touching the filesystem.
    with pytest.raises(LookupError):
        read_prompt_version("resource_gen.md", "../secret")


def test_load_prompt_template_reloads_when_file_changes(tmp_path, monkeypatch):
    monkeypatch.setattr(prompt_registry, "PROMPT_DIR", tmp_path)
    (tmp_path / "cache_probe.md").write_text("first body {subject}", encoding="utf-8")

    assert load_prompt_template("cache_probe.md") == "first body {subject}"

    (tmp_path / "cache_probe.md").write_text("second body {subject}", encoding="utf-8")
    # Bump mtime deterministically so the cache key actually differs.
    import os

    os.utime(tmp_path / "cache_probe.md", (1_000_000_000, 1_000_000_001))

    assert load_prompt_template("cache_probe.md") == "second body {subject}"
