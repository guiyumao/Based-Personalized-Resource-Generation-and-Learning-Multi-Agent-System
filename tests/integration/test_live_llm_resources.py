"""Real-LLM end-to-end verification for the structured resource types.

Opt-in only::

    RUN_LIVE_LLM=1 python -m pytest -m live_llm tests/integration/test_live_llm_resources.py -q

Without ``RUN_LIVE_LLM`` (and without provider credentials) this module skips at
collection time and prints ``LIVE_LLM_NOT_CONFIGURED``, so the ordinary pytest
run never depends on a model provider, a network path, or a paid key.

What "verified" means here
--------------------------
Every test below walks the *whole* chain with the project's own
``LLMFactory``/``Settings`` and no second client:

    request -> real LLM call -> JSON parse -> Pydantic model
    -> content_validation -> audit status -> persistence -> read back

Nothing is stubbed on the happy path. The failure-semantics tests deliberately
break one stage at a time (dead endpoint, non-JSON answer, empty retrieval) and
assert that the pipeline reports a real error instead of a fabricated success.
"""

from __future__ import annotations

import json
import logging
import os
import time
import warnings
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest

from common.config import get_settings
from common.db.session import SessionLocal
from common.models.learning import Resource
from common.schemas.agent import ResourceGenerationRequest

pytestmark = pytest.mark.live_llm

LIVE_LLM_MARKER = "LIVE_LLM_NOT_CONFIGURED"
_TRUTHY = {"1", "true", "yes", "on"}


def _live_llm_enabled() -> bool:
    return os.getenv("RUN_LIVE_LLM", "").strip().lower() in _TRUTHY


def _paid_calls_acknowledged() -> bool:
    """A second, explicit gate for paid calls.

    ``RUN_LIVE_LLM=1`` alone is a developer convenience. It is not a budget
    authorization: an accidental PowerShell empty assignment removed the
    guard variables once and this suite spent real tokens. Requiring a
    separate acknowledgement makes that class of accident much harder.
    """

    return os.getenv("DEEPSEEK_LIVE_PAID_ACK", "").strip().lower() in _TRUTHY


def _credentials_configured() -> bool:
    """Only DeepSeek counts for this suite.

    The previous check accepted Qwen/OpenAI too, so a ``live_llm`` run could
    silently validate a different provider while the report claimed DeepSeek.
    """

    settings = get_settings()
    return bool(settings.deepseek_api_base) and bool(
        settings.deepseek_api_key or settings.openai_api_key
    )


if not _live_llm_enabled():
    pytest.skip(
        f"{LIVE_LLM_MARKER}: RUN_LIVE_LLM is not set. "
        "Run 'RUN_LIVE_LLM=1 pytest -m live_llm' to execute these tests.",
        allow_module_level=True,
    )

if not _credentials_configured():
    pytest.skip(
        f"{LIVE_LLM_MARKER}: DeepSeek credentials are not configured "
        "(DEEPSEEK_API_BASE plus DEEPSEEK_API_KEY or OPENAI_API_KEY is required; "
        "this suite does not accept Qwen-only or OpenAI-only routing).",
        allow_module_level=True,
    )

if not _paid_calls_acknowledged():
    pytest.skip(
        f"{LIVE_LLM_MARKER}: paid calls are not acknowledged. Set "
        "DEEPSEEK_LIVE_PAID_ACK=1 only after the user has granted a budget; "
        "RUN_LIVE_LLM alone must not spend money.",
        allow_module_level=True,
    )


from services.agent_service.app.services.content_validation import (  # noqa: E402
    validate_generated_resource,
)
from services.agent_service.app.services.llm_factory import LLMFactory  # noqa: E402
from services.agent_service.app.services.resource_generation import (  # noqa: E402
    ResourceGenerationError,
    ResourceGenerationService,
)
from services.resource_service.app.services.resource_manager import ResourceManager  # noqa: E402

#: One representative knowledge point per resource type. They are ordinary
#: curriculum topics, not personal data.
CASES = {
    "mind_map": "二分查找",
    "code_case": "Python 循环结构",
    "video_script": "HTTP 请求与响应",
}

GENERATORS = {
    "mind_map": "generate_mind_map",
    "code_case": "generate_code_case",
    "video_script": "generate_video_script",
}

STRUCTURED_KEY = {
    "mind_map": "mind_map",
    "code_case": "code_case",
    "video_script": "video_script",
}

#: Text that must never appear in a log line, whatever the provider returns.
SECRET_MARKERS = ("Authorization", "Bearer ", "sk-", "api_key", "api-key", "DEEPSEEK_API_KEY")


@pytest.fixture(scope="module")
def service() -> ResourceGenerationService:
    service = ResourceGenerationService()
    model = service.llm_factory.build_chat_model()
    base_url = str(getattr(model, "openai_api_base", "") or "")
    host = (urlsplit(base_url).hostname or "").lower()
    allow_gateway = os.getenv("DEEPSEEK_ALLOW_GATEWAY", "").strip().lower() in _TRUTHY
    if host != "api.deepseek.com":
        if not allow_gateway:
            pytest.fail(
                f"live_llm is configured for {host or '<empty>'!r}, not api.deepseek.com. "
                "A DeepSeek conclusion must not be produced from another route; "
                "set DEEPSEEK_ALLOW_GATEWAY=1 only when the run is reported as gateway."
            )
        warnings.warn(
            f"DeepSeek acceptance is running via gateway host {host!r}; "
            "the report must say 'via gateway', not 'official direct'.",
            stacklevel=1,
        )
    return service


@pytest.fixture
def created_resource_ids() -> list[int]:
    """Track persisted rows so the live run leaves the database as it found it."""

    ids: list[int] = []
    yield ids

    if not ids:
        return
    with SessionLocal() as db:
        db.query(Resource).filter(Resource.id.in_(ids)).delete(synchronize_session=False)
        db.commit()


def _request(user_id: int, resource_type: str, knowledge_point: str, **overrides) -> ResourceGenerationRequest:
    payload = {
        "user_id": user_id,
        "knowledge_point": knowledge_point,
        "resource_type": resource_type,
        "subject": "计算机基础",
        "learner_profile": {"style": "visual"},
    }
    payload.update(overrides)
    return ResourceGenerationRequest(**payload)


def _generate(service: ResourceGenerationService, resource_type: str, request) -> dict:
    return getattr(service, GENERATORS[resource_type])(request)


# --------------------------------------------------------------------------- #
# happy path: full chain, one real call per resource type
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("resource_type", sorted(CASES))
def test_live_generation_full_chain(
    service: ResourceGenerationService,
    test_user,
    created_resource_ids: list[int],
    resource_type: str,
) -> None:
    request = _request(test_user.id, resource_type, CASES[resource_type])

    started = time.perf_counter()
    response = _generate(service, resource_type, request)
    elapsed = time.perf_counter() - started

    # 1. the request produced a resource with the requested type
    assert response["resource_type"] == resource_type
    assert response["generation_status"] == "generated"

    # 2. JSON parse + Pydantic validation produced the typed payload
    structured = response[STRUCTURED_KEY[resource_type]]
    assert isinstance(structured, dict) and structured, "the structured payload must not be empty"
    if resource_type == "mind_map":
        assert structured["nodes"], "a mind map must carry nodes"
        assert all("id" in node and "label" in node for node in structured["nodes"])
    elif resource_type == "code_case":
        assert structured["run_steps"], "a code case must carry human run steps"
        assert "executed" not in structured, "this system never executes generated code"
    else:
        assert structured["chapters"], "a video script must carry chapters"
        assert "video_path" not in structured, "this system never produces a media file"

    # 3. deterministic structural + source validation ran on the model's own JSON
    validation = response["content_validation"]
    assert validation["resource_type"] == resource_type
    assert validation["structure_passed"] is True, json.dumps(
        [check for check in validation["checks"] if check["status"] == "failed"], ensure_ascii=False
    )
    assert validation["verdict"] in {"valid", "insufficient_evidence"}, validation["verdict"]

    # 4. the audit layer judged the resource against its own contract
    assert response["audit_status"] in {"passed", "unavailable"}, response["audit_status"]
    assert response["audit_status"] != "rejected", response["audit_reason"]
    if response["audit_status"] == "unavailable":
        warnings.warn(
            "audit_status=unavailable means the audit did not run; "
            f"it is not an audit pass (reason: {response['audit_reason']})",
            stacklevel=1,
        )

    # 5. it was persisted and the id is real
    resource_id = response["id"]
    assert isinstance(resource_id, int) and resource_id > 0
    created_resource_ids.append(resource_id)

    # 6. it can be read back, with the payload and the validation report intact
    with SessionLocal() as db:
        item = ResourceManager(db).get_resource(resource_id)
    assert item is not None
    assert item.type == resource_type
    assert item.audit_status in {"passed", "unavailable"}
    assert item.content and item.content.strip(), "the readable rendering must be stored"
    assert item.structured is not None, "the typed payload must be readable back"
    assert item.content_validation is not None, "the validation report must be readable back"
    assert item.content_validation["resource_type"] == resource_type

    print(
        f"[live] {resource_type}: id={resource_id} audit={response['audit_status']} "
        f"verdict={validation['verdict']} elapsed={elapsed:.1f}s"
    )


# --------------------------------------------------------------------------- #
# failure semantics
# --------------------------------------------------------------------------- #


def test_live_dead_endpoint_raises_instead_of_fabricating(service, test_user, monkeypatch) -> None:
    """A provider that cannot be reached must surface an error, never a resource."""

    settings = get_settings()
    broken = SimpleNamespace(**{**settings.__dict__})
    broken.deepseek_api_base = "http://127.0.0.1:9/v1"
    broken.deepseek_api_key = "not-a-real-key"
    broken.qwen_api_base = ""
    broken.qwen_api_key = ""
    broken.openai_api_key = ""
    broken.llm_request_timeout_seconds = 5
    monkeypatch.setattr(service, "llm_factory", LLMFactory(broken))

    request = _request(test_user.id, "mind_map", CASES["mind_map"])

    started = time.perf_counter()
    with pytest.raises(ResourceGenerationError):
        service.generate_mind_map(request)
    elapsed = time.perf_counter() - started

    assert elapsed < 60, f"an unreachable provider must fail fast, took {elapsed:.1f}s"
    print(f"[live] dead endpoint raised ResourceGenerationError after {elapsed:.1f}s")


# Non-JSON / 429 / 5xx / slow-response / disconnect semantics live in
# ``tests/integration/test_deepseek_failure_semantics.py``. They use a local
# HTTP stub: asking a real model to answer with prose, or assuming a 1-second
# timeout, is neither deterministic nor free. In particular, LLMFactory clamps
# the request timeout to max(3, configured), so a "1 second budget" test would
# assert the wrong thing.


def test_live_empty_retrieval_reports_insufficient_evidence() -> None:
    """No retrieved chunk may ever be reported as a resolved source.

    The content below is structurally valid, so the *only* failing stage is the
    source stage - which is exactly the case that must not be papered over.
    """

    content = (
        "# 量子退火与课堂纪律\n\n"
        "## 学习目标\n理解一个完全虚构的知识点在本系统中的处理方式。\n\n"
        "## 知识讲解\n该知识点没有任何检索命中，因此没有可回指的来源。\n\n"
        "## 示例\n示例内容同样没有任何来源支撑。\n\n"
        "## 小结\n没有证据就不应给出肯定结论。\n\n"
        "## 自测\n请说明系统在无检索结果时的行为。\n"
    )
    report = validate_generated_resource(
        resource_type="courseware",
        content=content,
        payload=None,
        knowledge_point="",
        source_chunks=[],
        title="无来源探针",
    )

    assert report["structure_passed"] is True
    assert report["verdict"] == "insufficient_evidence"
    assert report["citations"] == [], "no retrieval happened, so no citation may exist"
    print(f"[live] empty retrieval -> verdict={report['verdict']}")


# --------------------------------------------------------------------------- #
# logging hygiene
# --------------------------------------------------------------------------- #


def test_live_logs_do_not_leak_credentials_or_prompts(service, test_user, caplog) -> None:
    """The live path must not log keys, Authorization headers or the full prompt."""

    keyboard = get_settings().deepseek_api_key or get_settings().openai_api_key or ""

    with caplog.at_level(logging.DEBUG):
        response = _generate(service, "mind_map", _request(test_user.id, "mind_map", "栈与队列"))
        created_ids = [response["id"]]

    try:
        blob = "\n".join(record.getMessage() for record in caplog.records)
        for marker in SECRET_MARKERS:
            assert marker.lower() not in blob.lower(), f"log lines leaked {marker!r}"
        if keyboard:
            assert keyboard not in blob, "log lines leaked the provider API key"
        # The rendered generation prompt starts with this instruction; it must not
        # be echoed into the logs.
        assert "你是" not in blob or "严格 JSON" not in blob, "the full prompt was logged"
    finally:
        with SessionLocal() as db:
            db.query(Resource).filter(Resource.id.in_(created_ids)).delete(synchronize_session=False)
            db.commit()
