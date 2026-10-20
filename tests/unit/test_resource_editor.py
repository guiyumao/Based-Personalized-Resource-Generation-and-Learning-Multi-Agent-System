"""Administrator resource editing capabilities (P1-07): rewrite, image provider,
section composition and the explicit BLOCKED entry."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from common.db.base import Base
from common.models.learning import AuditLog, Resource, SystemConfig
from common.models.media import ResourceIllustration, ResourceRevision
from services.agent_service.app.services import resource_editor
from services.agent_service.app.services.resource_editor import (
    _insert_image_markdown,
    apply_resource_content,
    illustrate_resource,
    image_provider_status,
    insert_illustration,
    list_illustrations,
    resource_sections,
    review_illustration,
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


def test_image_provider_invalid_when_key_without_url_or_model(editor_db, monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(
        resource_editor,
        "get_settings",
        lambda: SimpleNamespace(
            image_provider_api_key="secret", image_provider_base_url="", image_provider_model=""
        ),
    )
    factory, _ = editor_db
    with factory() as db:
        status = image_provider_status(db)
        assert status["status"] == "invalid"
        assert status["configured"] is False
        assert status["enabled"] is True


def test_image_provider_disabled_flag(editor_db, monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(
        resource_editor,
        "get_settings",
        lambda: SimpleNamespace(
            image_provider_api_key="secret",
            image_provider_base_url="https://img.example",
            image_provider_model="dall-e-3",
        ),
    )
    factory, _ = editor_db
    with factory() as db:
        db.add(SystemConfig(key="image_provider.enabled", value="false"))
        db.commit()
        status = image_provider_status(db)
        assert status["status"] == "disabled"
        assert status["configured"] is False


def test_image_provider_configured_when_complete(editor_db, monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(
        resource_editor,
        "get_settings",
        lambda: SimpleNamespace(
            image_provider_api_key="secret",
            image_provider_base_url="https://img.example",
            image_provider_model="dall-e-3",
        ),
    )
    factory, _ = editor_db
    with factory() as db:
        status = image_provider_status(db)
        assert status["status"] == "configured"
        assert status["configured"] is True
        assert status["health"] == "unknown"


def test_rewrite_resource_blocked_without_model(editor_db, monkeypatch):
    monkeypatch.setattr(resource_editor, "LLMFactory", _NoCredentialLLMFactory)
    # Authorize paid calls so this test reaches the "no model" branch, not the gate.
    monkeypatch.setenv("RUN_LIVE_LLM", "1")
    monkeypatch.setenv("DEEPSEEK_LIVE_PAID_ACK", "1")
    factory, make_resource = editor_db
    resource_id = make_resource()
    with factory() as db:
        result = rewrite_resource(db, resource_id, instruction="简化语言", style="plain")
        assert result["resource_id"] == resource_id
        assert result["status"] == "blocked"
        assert result["rewritten_content"] == ""


def test_rewrite_blocked_without_paid_authorization(editor_db, monkeypatch):
    monkeypatch.delenv("RUN_LIVE_LLM", raising=False)
    monkeypatch.delenv("DEEPSEEK_LIVE_PAID_ACK", raising=False)
    factory, make_resource = editor_db
    resource_id = make_resource()
    with factory() as db:
        result = rewrite_resource(db, resource_id, instruction="简化语言", style="plain")
        assert result["status"] == "blocked"
        assert "授权" in result["reason"]
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
        result = illustrate_resource(db, resource_id, section_title="概念", prompt="", admin_id=1)
        assert result["status"] == "blocked"
        assert result["reason"]


def test_insert_image_markdown_after_heading():
    content = "# 标题\n\n## 概念\n正文 A\n\n## 示例\n正文 B"
    out = _insert_image_markdown(content, "概念", "![概念](/storage/illustrations/x.png)")
    assert "![概念](/storage/illustrations/x.png)" in out
    # The image lands right after the "## 概念" heading, before the body.
    assert out.index("## 概念") < out.index("![概念]") < out.index("正文 A")


def test_insert_image_markdown_appends_when_section_missing():
    content = "# 标题\n\n## 其他\n正文"
    out = _insert_image_markdown(content, "概念", "![概念](/storage/illustrations/x.png)")
    assert "## 概念" in out
    assert "![概念](/storage/illustrations/x.png)" in out


def test_illustration_review_and_insert(editor_db):
    factory, make_resource = editor_db
    resource_id = make_resource()
    with factory() as db:
        db.add(
            ResourceIllustration(
                id="ill-1",
                resource_id=resource_id,
                section_title="概念",
                model="dall-e-3",
                prompt="教学配图",
                status="pending",
                storage_path="illustrations/ill-1.png",
                version="",
                created_by=1,
            )
        )
        db.commit()

        assert list_illustrations(db, resource_id)[0]["status"] == "pending"

        # Not approved -> insert rejected.
        with pytest.raises(ValueError):
            insert_illustration(db, "ill-1", admin_id=1)

        review_illustration(db, "ill-1", approve=True, admin_id=1)
        assert list_illustrations(db, resource_id)[0]["status"] == "approved"

        result = insert_illustration(db, "ill-1", admin_id=1)
        assert result["resource_id"] == resource_id
        assert "![概念](/storage/illustrations/ill-1.png)" in db.get(Resource, resource_id).content
        # Insertion snapshots the previous body as a revision.
        assert db.query(ResourceRevision).filter_by(resource_id=resource_id).count() == 1
