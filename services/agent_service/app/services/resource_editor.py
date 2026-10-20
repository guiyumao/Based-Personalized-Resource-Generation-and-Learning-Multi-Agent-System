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

import base64
import json
import logging
import os
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session

from common.ai_errors import AIServiceError
from common.config import get_settings
from common.models.learning import AuditLog, Resource, SystemConfig
from common.models.media import ResourceIllustration, ResourceRevision
from common.resource_version import resource_version
from services.agent_service.app.services.llm_factory import LLMFactory

LOGGER = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_ILLUSTRATION_DIR = _PROJECT_ROOT / "storage" / "illustrations"

_IMAGE_PROVIDER_NAME_KEY = "image_provider.name"
_IMAGE_PROVIDER_MODEL_KEY = "image_provider.model"
_IMAGE_PROVIDER_ENABLED_KEY = "image_provider.enabled"

#: Styles accepted for an admin rewrite. Kept small so the LLM is steered by a
#: controlled vocabulary rather than an unbounded free-text prompt.
REWRITE_STYLES = ("concise", "detailed", "plain", "case", "interactive")


def _live_llm_authorized() -> bool:
    """Whether a real paid text-model call is explicitly authorized (INC-01 gate).

    The two environment switches mirror the existing live-test gate: neither
    ``RUN_LIVE_LLM=1`` alone nor a configured provider credential is enough to
    spend money. Both must be set explicitly by an operator who has approved the
    budget for this run.
    """

    return (
        os.getenv("RUN_LIVE_LLM", "").strip().lower() in {"1", "true", "yes", "on"}
        and os.getenv("DEEPSEEK_LIVE_PAID_ACK", "").strip().lower() in {"1", "true", "yes", "on"}
    )


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
    The status is derived from local configuration only — no outbound probe is
    made — so a healthy-looking backend and a genuinely down backend are both
    reported as ``health="unknown"`` rather than being confused with the
    configuration states below.
    """

    settings = get_settings()
    provider = _config_value(db, _IMAGE_PROVIDER_NAME_KEY)
    model = _config_value(db, _IMAGE_PROVIDER_MODEL_KEY) or settings.image_provider_model
    base_url = settings.image_provider_base_url
    has_key = bool(settings.image_provider_api_key)
    enabled = _config_value(db, _IMAGE_PROVIDER_ENABLED_KEY).strip().lower() not in {"0", "false", "no"}

    if not has_key:
        status = "blocked"
        reason = "未配置图片 Provider 凭据，图文生成不可用。"
    elif not base_url or not model:
        status = "invalid"
        reason = "图片 Provider 配置不完整（缺少 base_url 或模型名），无法使用。"
    elif not enabled:
        status = "disabled"
        reason = "图片 Provider 已配置但被管理员停用。"
    else:
        status = "configured"
        reason = "图片 Provider 配置就绪；真实图片生成后端接入仍待完成。"

    return {
        "configured": has_key and bool(base_url) and bool(model) and enabled,
        "enabled": enabled,
        "provider": provider,
        "model": model,
        "status": status,
        "health": "unknown",
        "reason": reason,
    }


def set_image_provider(
    db: Session,
    admin_id: int,
    provider: str,
    model: str,
    enabled: bool | None = None,
) -> dict[str, object]:
    """Persist the non-sensitive image-provider metadata (name, model, enabled)."""

    provider = (provider or "").strip()
    model = (model or "").strip()
    _set_config_value(db, _IMAGE_PROVIDER_NAME_KEY, provider)
    _set_config_value(db, _IMAGE_PROVIDER_MODEL_KEY, model)
    if enabled is not None:
        _set_config_value(db, _IMAGE_PROVIDER_ENABLED_KEY, "true" if enabled else "false")
    db.add(
        AuditLog(
            level="INFO",
            event="image_provider.updated",
            actor_user_id=admin_id,
            message=f"provider={provider or '-'} model={model or '-'} enabled={enabled}",
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
    if not _live_llm_authorized():
        return {
            "resource_id": resource_id,
            "title": resource.title,
            "status": "blocked",
            "reason": "AI 改写需要授权真实模型调用（RUN_LIVE_LLM=1 且 DEEPSEEK_LIVE_PAID_ACK=1）。",
            "provider": provider,
            "model": model,
            "rewritten_content": "",
        }
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
    admin_id: int,
) -> dict[str, object]:
    """Generate a real illustration for one resource section.

    With no image provider configured this returns ``status=blocked`` (honest, no
    placeholder). With a configured provider it makes a real image-generation
    call, persists the PNG, and records a ``pending`` illustration for review —
    it never touches the live resource until an administrator approves and
    inserts it.
    """

    resource = db.get(Resource, resource_id)
    if resource is None:
        raise LookupError("Resource not found")
    status = image_provider_status(db)
    if not status["configured"]:
        return {
            "resource_id": resource_id,
            "section_title": section_title,
            "status": "blocked",
            "reason": status["reason"],
        }

    settings = get_settings()
    effective_prompt = (prompt or "").strip() or _default_illustration_prompt(section_title)
    try:
        image_bytes = _generate_image(settings, effective_prompt)
    except Exception as exc:  # noqa: BLE001 - surface a stable reason to the admin
        LOGGER.exception("illustration_generation_failed resource_id=%s section=%s", resource_id, section_title)
        return {
            "resource_id": resource_id,
            "section_title": section_title,
            "status": "failed",
            "reason": f"图片生成失败：{str(exc)[:200]}",
        }

    _ILLUSTRATION_DIR.mkdir(parents=True, exist_ok=True)
    illustration_id = str(uuid4())
    filename = f"{illustration_id}.png"
    (_ILLUSTRATION_DIR / filename).write_bytes(image_bytes)
    db.add(
        ResourceIllustration(
            id=illustration_id,
            resource_id=resource_id,
            section_title=section_title,
            model=str(status["model"]),
            prompt=effective_prompt,
            status="pending",
            storage_path=f"illustrations/{filename}",
            version=resource_version(resource),
            created_by=admin_id,
        )
    )
    db.commit()
    return {
        "resource_id": resource_id,
        "section_title": section_title,
        "status": "generated",
        "illustration_id": illustration_id,
        "storage_path": f"illustrations/{filename}",
        "model": str(status["model"]),
    }


def _default_illustration_prompt(section_title: str) -> str:
    return (
        f"为教学章节「{section_title}」生成一幅清晰的示意图：简洁、面向学生、"
        "无文字水印，风格统一，适合插入课件正文。"
    )


def _generate_image(settings, prompt: str) -> bytes:
    """Dispatch to the right image provider based on the configured base URL.

    DashScope 通义万相 uses its own async task API; everything else falls back to
    the OpenAI-compatible ``/images/generations`` shape. Raises when the provider
    is unreachable or returns no image; the caller maps that to a safe
    ``status=failed`` response.
    """

    base = (settings.image_provider_base_url or "").rstrip("/")
    if not base:
        raise ValueError("缺少图片 Provider base_url")
    if "dashscope" in base or "aliyuncs" in base:
        return _generate_image_dashscope(settings, prompt)
    return _generate_image_openai(settings, prompt)


def _generate_image_openai(settings, prompt: str) -> bytes:
    base = (settings.image_provider_base_url or "").rstrip("/")
    url = f"{base}/images/generations"
    payload = json.dumps(
        {
            "model": settings.image_provider_model or "dall-e-3",
            "prompt": prompt,
            "n": 1,
            "size": "1024x1024",
            "response_format": "b64_json",
        }
    ).encode("utf-8")
    request = urllib.request.Request(url, data=payload, method="POST")
    request.add_header("Authorization", f"Bearer {settings.image_provider_api_key}")
    request.add_header("Content-Type", "application/json")
    timeout = max(3, settings.llm_request_timeout_seconds)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = json.loads(response.read().decode("utf-8"))
    data = body.get("data") or []
    if not data or "b64_json" not in data[0]:
        raise RuntimeError("图片生成返回为空")
    return base64.b64decode(data[0]["b64_json"])


def _generate_image_dashscope(settings, prompt: str) -> bytes:
    """Generate one image via Alibaba DashScope 通义万相 (async task API).

    Submits a text2image task, polls ``/tasks/{id}`` until SUCCEEDED, then
    downloads the returned image. Kept to the raw HTTP API so no DashScope SDK
    dependency is required.
    """

    import time

    base = (settings.image_provider_base_url or "").rstrip("/")
    model = settings.image_provider_model or "wanx2.1-t2i-turbo"
    submit_url = f"{base}/services/aigc/text2image/image-synthesis"
    payload = json.dumps(
        {
            "model": model,
            "input": {"prompt": prompt},
            "parameters": {"size": "1024*1024", "n": 1},
        }
    ).encode("utf-8")
    request = urllib.request.Request(submit_url, data=payload, method="POST")
    request.add_header("Authorization", f"Bearer {settings.image_provider_api_key}")
    request.add_header("Content-Type", "application/json")
    request.add_header("X-DashScope-Async", "enable")
    timeout = max(3, settings.llm_request_timeout_seconds)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        submitted = json.loads(response.read().decode("utf-8"))
    task_id = (submitted.get("output") or {}).get("task_id")
    if not task_id:
        raise RuntimeError(
            f"通义万相提交失败：{submitted.get('message') or submitted.get('code') or '无 task_id'}"
        )

    poll_url = f"{base}/tasks/{task_id}"
    deadline = time.time() + 120
    while time.time() < deadline:
        poll_req = urllib.request.Request(
            poll_url, headers={"Authorization": f"Bearer {settings.image_provider_api_key}"}
        )
        with urllib.request.urlopen(poll_req, timeout=timeout) as response:
            status = json.loads(response.read().decode("utf-8"))
        output = status.get("output") or {}
        state = output.get("task_status")
        if state == "SUCCEEDED":
            results = output.get("results") or []
            if not results or not results[0].get("url"):
                raise RuntimeError("通义万相返回无图片")
            with urllib.request.urlopen(urllib.request.Request(results[0]["url"]), timeout=timeout) as image_response:
                return image_response.read()
        if state in {"FAILED", "CANCELED", "UNKNOWN"}:
            raise RuntimeError(f"通义万相生成失败：{output.get('message') or state}")
        time.sleep(2)
    raise RuntimeError("通义万相生成超时")


def list_illustrations(db: Session, resource_id: int) -> list[dict[str, object]]:
    """List illustration drafts for a resource, newest first."""

    rows = (
        db.query(ResourceIllustration)
        .filter_by(resource_id=resource_id)
        .order_by(ResourceIllustration.created_at.desc())
        .all()
    )
    return [
        {
            "id": row.id,
            "section_title": row.section_title,
            "model": row.model,
            "prompt": row.prompt,
            "status": row.status,
            "storage_path": row.storage_path,
            "version": row.version,
        }
        for row in rows
    ]


def review_illustration(
    db: Session,
    illustration_id: str,
    approve: bool,
    admin_id: int,
) -> dict[str, object]:
    """Approve or reject a generated illustration draft."""

    row = db.get(ResourceIllustration, illustration_id)
    if row is None:
        raise LookupError("Illustration not found")
    row.status = "approved" if approve else "rejected"
    row.reviewed_at = datetime.now(UTC)
    row.reviewed_by = admin_id
    db.commit()
    return {"illustration_id": illustration_id, "status": row.status}


def insert_illustration(
    db: Session,
    illustration_id: str,
    admin_id: int,
) -> dict[str, object]:
    """Insert an approved illustration into its resource body and persist a version.

    Only an ``approved`` draft may be inserted; the previous body is snapshotted
    through :func:`apply_resource_content` so the change is reversible.
    """

    row = db.get(ResourceIllustration, illustration_id)
    if row is None:
        raise LookupError("Illustration not found")
    if row.status != "approved":
        raise ValueError("Illustration must be approved before inserting")
    resource = db.get(Resource, row.resource_id)
    if resource is None:
        raise LookupError("Resource not found")
    image_md = f"![{row.section_title}](/storage/{row.storage_path})"
    new_content = _insert_image_markdown(resource.content or "", row.section_title, image_md)
    result = apply_resource_content(db, admin_id, resource.id, new_content, "")
    return {
        "resource_id": resource.id,
        "resource_version": result["resource_version"],
        "illustration_id": illustration_id,
    }


def _insert_image_markdown(content: str, section_title: str, image_md: str) -> str:
    """Insert an image reference right after the matching ``##`` section heading."""

    heading = f"## {section_title}".strip()
    lines = (content or "").splitlines()
    out: list[str] = []
    inserted = False
    for line in lines:
        out.append(line)
        if not inserted and line.strip() == heading:
            out.append("")
            out.append(image_md)
            inserted = True
    if not inserted:
        out.append("")
        out.append(heading)
        out.append(image_md)
    return "\n".join(out)
