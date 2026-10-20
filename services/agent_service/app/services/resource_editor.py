"""Administrator resource editing (P1-07): LLM rewrite, image-provider config and
an explicit BLOCKED entry for image-text composition.

Everything here is administrator-only at the route layer. The two capabilities are
kept honest:

- ``rewrite`` calls the configured text model. When no model is configured the
  call returns ``status=blocked`` with a clear reason instead of fabricating a
  rewrite, and when it runs the real per-call usage ledger (P1-06) still records
  the tokens.
- image-text composition reports the image-provider configuration and returns
  ``status=blocked`` until a real image backend is provisioned. There is no
  fake "image generated" path.
"""

from __future__ import annotations

import logging
from uuid import uuid4

from sqlalchemy.orm import Session

from common.ai_errors import AIServiceError
from common.config import get_settings
from common.models.learning import AuditLog, Resource, SystemConfig
from common.models.media import ResourceRevision
from common.resource_version import resource_version
from services.agent_service.app.services.llm_factory import LLMFactory

LOGGER = logging.getLogger(__name__)

_IMAGE_PROVIDER_NAME_KEY = "image_provider.name"
_IMAGE_PROVIDER_MODEL_KEY = "image_provider.model"

#: Styles accepted for an admin rewrite. Kept small so the LLM is steered by a
#: controlled vocabulary rather than an unbounded free-text prompt.
REWRITE_STYLES = ("concise", "detailed", "plain", "case", "interactive")


def _config_value(db: Session, key: str) -> str:
    row = db.get(SystemConfig, key)
    return str(row.value).strip() if row is not None else ""


def _set_config_value(db: Session, key: str, value: str) -> None:
    row = db.get(SystemConfig, key)
    if row is None:
        db.add(SystemConfig(key=key, value=value))
    else:
        row.value = value


def image_provider_status(db: Session) -> dict[str, object]:
    """Report whether an image-generation provider is usable.

    The credential lives in deployment configuration (``IMAGE_PROVIDER_API_KEY``);
    the administrator UI records only the non-sensitive provider name and model.
    """

    settings = get_settings()
    provider = _config_value(db, _IMAGE_PROVIDER_NAME_KEY)
    model = _config_value(db, _IMAGE_PROVIDER_MODEL_KEY) or settings.image_provider_model
    configured = bool(settings.image_provider_api_key)
    if configured:
        status = "configured"
        reason = "图片 Provider 凭据已配置；图片生成后端接入仍待完成。"
    else:
        status = "blocked"
        reason = "未配置图片 Provider 凭据，图文生成不可用。"
    return {
        "configured": configured,
        "provider": provider,
        "model": model,
        "status": status,
        "reason": reason,
    }


def set_image_provider(db: Session, admin_id: int, provider: str, model: str) -> dict[str, object]:
    """Persist the non-sensitive image-provider metadata (name and model)."""

    provider = (provider or "").strip()
    model = (model or "").strip()
    _set_config_value(db, _IMAGE_PROVIDER_NAME_KEY, provider)
    _set_config_value(db, _IMAGE_PROVIDER_MODEL_KEY, model)
    db.add(
        AuditLog(
            level="INFO",
            event="image_provider.updated",
            actor_user_id=admin_id,
            message=f"provider={provider or '-'} model={model or '-'}",
        )
    )
    db.commit()
    return image_provider_status(db)


def _active_llm(settings) -> tuple[str | None, str | None]:
    """Best-effort provider/model for a transparent response; the usage ledger is
    authoritative for the real call attribution."""

    light = settings.llm_light_model
    if settings.qwen_api_base and settings.qwen_api_key:
        return "qwen", light or settings.qwen_model
    if settings.deepseek_api_base and settings.deepseek_api_key:
        return "deepseek", light or settings.deepseek_model
    if settings.openai_api_key:
        return "openai", light or settings.openai_model
    return None, None


def rewrite_resource(
    db: Session,
    resource_id: int,
    instruction: str,
    style: str,
) -> dict[str, object]:
    """Rewrite a resource's Markdown body with the configured text model.

    The rewrite is generated and returned but **not** persisted: the
    administrator reviews the result and applies it through a separate content
    update so an accidental paid call can never silently overwrite a resource.
    """

    resource = db.get(Resource, resource_id)
    if resource is None:
        raise LookupError("Resource not found")

    instruction = (instruction or "").strip()
    if not instruction:
        raise ValueError("Rewrite instruction is required")

    settings = get_settings()
    provider, model = _active_llm(settings)
    try:
        llm = LLMFactory(settings).build_for_task("rewrite", temperature=0.3)
    except (ValueError, ImportError, AIServiceError):
        return {
            "resource_id": resource_id,
            "title": resource.title,
            "status": "blocked",
            "reason": "未配置可用的文本生成模型，无法执行改写。",
            "provider": provider,
            "model": model,
            "rewritten_content": "",
        }

    try:
        from langchain_core.output_parsers import StrOutputParser
        from langchain_core.prompts import ChatPromptTemplate

        style_hint = {
            "concise": "压缩冗余，突出规则、最小示例和快速自测。",
            "detailed": "补充解释、步骤和背景，使内容更完整。",
            "plain": "用平实、通俗的语言，降低阅读门槛。",
            "case": "用案例驱动，强调从题意到解法的迁移。",
            "interactive": "增加提问、自检提示和互动感。",
        }.get(style, "保持原意，提升清晰度和教学效果。")
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", "你是教学内容的专业编辑。只输出改写后的 Markdown 正文，不添加任何解释、前言或代码围栏。"),
                (
                    "human",
                    "原始内容：\n{content}\n\n改写要求：{instruction}\n\n风格要求：{style_hint}",
                ),
            ]
        )
        chain = prompt | llm | StrOutputParser()
        rewritten = str(
            chain.invoke(
                {
                    "content": resource.content,
                    "instruction": instruction,
                    "style_hint": style_hint,
                }
            )
        ).strip()
    except Exception:  # noqa: BLE001 - surface a stable, safe reason to the admin
        LOGGER.exception("resource rewrite failed resource_id=%s", resource_id)
        return {
            "resource_id": resource_id,
            "title": resource.title,
            "status": "failed",
            "reason": "改写失败，请检查模型配置或稍后重试。",
            "provider": provider,
            "model": model,
            "rewritten_content": "",
        }

    return {
        "resource_id": resource_id,
        "title": resource.title,
        "status": "generated",
        "provider": provider,
        "model": model,
        "rewritten_content": rewritten,
    }


def apply_resource_content(
    db: Session,
    admin_id: int,
    resource_id: int,
    content: str,
    expected_version: str,
) -> dict[str, object]:
    """Persist a reviewed rewrite, snapshotting the previous body first."""

    resource = db.get(Resource, resource_id)
    if resource is None:
        raise LookupError("Resource not found")
    if expected_version and resource_version(resource) != expected_version:
        raise ValueError("Resource changed; refresh before applying")
    if not content.strip():
        raise ValueError("Content must not be empty")

    version = resource_version(resource)
    if (
        db.query(ResourceRevision)
        .filter_by(resource_id=resource.id, version=version)
        .first()
        is None
    ):
        db.add(
            ResourceRevision(
                id=str(uuid4()),
                resource_id=resource.id,
                user_id=admin_id,
                version=version,
                title=resource.title,
                content=resource.content,
                structured_json=resource.structured_json,
            )
        )
    resource.content = content
    db.add(
        AuditLog(
            level="INFO",
            event="resource.content.rewritten",
            actor_user_id=admin_id,
            message=f"resource={resource.id}",
        )
    )
    db.commit()
    db.refresh(resource)
    return {"resource_id": resource.id, "resource_version": resource_version(resource)}


def resource_sections(content: str) -> list[dict[str, object]]:
    """List the ``##`` sections of a Markdown body for image-text composition.

    The document-level ``# title`` is already carried by ``Resource.title``, so it
    is not a candidate section for an illustration.
    """

    sections: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    for line in (content or "").splitlines():
        if line.startswith("## "):
            if current is not None:
                sections.append(current)
            current = {"title": line[3:].strip(), "chars": 0}
        elif current is not None:
            current["chars"] = int(current["chars"]) + len(line) + 1
    if current is not None:
        sections.append(current)
    return sections


def illustrate_resource(
    db: Session,
    resource_id: int,
    section_title: str,
    prompt: str,
) -> dict[str, object]:
    """Request an illustration for one resource section.

    Honest by design: with no image backend provisioned this always returns
    ``status=blocked``, and the reason distinguishes "not configured" from
    "configured but not yet wired". No placeholder image is ever produced.
    """

    resource = db.get(Resource, resource_id)
    if resource is None:
        raise LookupError("Resource not found")
    status = image_provider_status(db)
    if not status["configured"]:
        return {
            "resource_id": resource_id,
            "section_title": section_title,
            "prompt": prompt,
            "status": "blocked",
            "reason": status["reason"],
        }
    return {
        "resource_id": resource_id,
        "section_title": section_title,
        "prompt": prompt,
        "status": "blocked",
        "reason": "图片 Provider 已配置，但图片生成后端尚未接入，无法生成配图。",
    }
