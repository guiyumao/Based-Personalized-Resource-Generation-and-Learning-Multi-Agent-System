"""Administrator resource editing capabilities (P1-07): rewrite, image provider,
section composition and the explicit BLOCKED entry."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from common.db.base import Base
from common.models.learning import AuditLog, Resource, SystemConfig
from common.models.media import ResourceRevision
from services.agent_service.app.services import resource_editor
from services.agent_service.app.services.resource_editor import (
    apply_resource_content,
    illustrate_resource,
    image_provider_status,
    resource_sections,
    rewrite_resource,
    set_image_provider,
)


class _NoCredentialLLMFactory:
    """Simulate a deployment with no text-model credentials configured."""

    def __init__(self, settings):
        self.settings = settings

    def build_for_task(self, task, *, temperature=0.0):
        raise ValueError("No LLM credentials configured.")


@pytest.fixture
def editor_db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'editor.sqlite'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    def resource(**overrides):
        params = {
            "title": "测试课件",
            "type": "courseware",
            "content": "# 标题\n\n## 概念\n正文 A\n\n## 示例\n正文 B",
            "format": "markdown",
            "generation_status": "generated",
            "audit_status": "passed",
            "publish_status": "draft",
        }
        params.update(overrides)
        with factory() as db:
            row = Resource(**params)
            db.add(row)
            db.commit()
            db.refresh(row)
            return row.id

    yield factory, resource
    engine.dispose()


def test_image_provider_is_blocked_without_credential(editor_db):
    factory, _ = editor_db
    with factory() as db:
        status = image_provider_status(db)
        assert status["configured"] is False
        assert status["status"] == "blocked"
        assert status["reason"]


def test_set_image_provider_records_metadata_and_audit(editor_db):
    factory, _ = editor_db
    with factory() as db:
        status = set_image_provider(db, admin_id=1, provider="openai_images", model="dall-e-3")
        assert status["provider"] == "openai_images"
        assert status["model"] == "dall-e-3"
        assert status["status"] == "blocked"  # metadata alone never unlocks generation
        assert db.get(SystemConfig, "image_provider.name").value == "openai_images"
        assert db.query(AuditLog).filter_by(event="image_provider.updated").count() == 1


def test_rewrite_resource_blocked_without_model(editor_db, monkeypatch):
    monkeypatch.setattr(resource_editor, "LLMFactory", _NoCredentialLLMFactory)
    factory, make_resource = editor_db
    resource_id = make_resource()
    with factory() as db:
        result = rewrite_resource(db, resource_id, instruction="简化语言", style="plain")
        assert result["resource_id"] == resource_id
        assert result["status"] == "blocked"
        assert result["rewritten_content"] == ""


def test_rewrite_requires_instruction(editor_db):
    factory, make_resource = editor_db
    resource_id = make_resource()
    with factory() as db:
        with pytest.raises(ValueError):
            rewrite_resource(db, resource_id, instruction="  ", style="plain")


def test_rewrite_missing_resource(editor_db):
    factory, _ = editor_db
    with factory() as db:
        with pytest.raises(LookupError):
            rewrite_resource(db, resource_id=999999, instruction="x", style="plain")


def test_apply_resource_content_snapshots_previous_body(editor_db):
    factory, make_resource = editor_db
    resource_id = make_resource()
    with factory() as db:
        result = apply_resource_content(db, admin_id=7, resource_id=resource_id, content="改写后的正文", expected_version="")
        assert result["resource_id"] == resource_id
        assert db.get(Resource, resource_id).content == "改写后的正文"
        # The pre-edit body is preserved as an immutable revision.
        revisions = db.query(ResourceRevision).filter_by(resource_id=resource_id).all()
        assert len(revisions) == 1
        assert revisions[0].content.startswith("# 标题")
        assert db.query(AuditLog).filter_by(event="resource.content.rewritten").count() == 1


def test_resource_sections_splits_markdown():
    sections = resource_sections("# 标题\n\n## 概念\n正文 A\n\n## 示例\n正文 B")
    assert [section["title"] for section in sections] == ["概念", "示例"]
    assert all(section["chars"] > 0 for section in sections)


def test_illustrate_resource_blocked(editor_db):
    factory, make_resource = editor_db
    resource_id = make_resource()
    with factory() as db:
        result = illustrate_resource(db, resource_id, section_title="概念", prompt="")
        assert result["status"] == "blocked"
        assert result["reason"]
