"""Tests for the structured (non-prose) resource generators.

These cover the three resource types absorbed from the upstream comparison:
``mind_map``, ``code_case`` and ``video_script``.  The LLM, the retriever and
the database are all stubbed, so the tests assert the *contract* this system
promises: a mind map is structured nodes/edges, a code case is static and never
claims execution, and a video script is a script rather than a media file.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from common.schemas.agent import ResourceGenerationRequest
from services.agent_service.app.services import resource_generation as module
from services.agent_service.app.services.resource_generation import (
    ResourceGenerationError,
    ResourceGenerationService,
)


def _snapshot() -> SimpleNamespace:
    return SimpleNamespace(
        mastery_score=62,
        correct_rate=58,
        answered_count=7,
        learner_profile={"weak_question_types": ["choice"], "profile_analysis_summaries": {}},
        recent_mistakes=[],
    )


@pytest.fixture
def service(monkeypatch):
    """A service with retrieval, LLM, audit and persistence stubbed out."""

    svc = ResourceGenerationService()
    monkeypatch.setattr(
        svc,
        "_prepare_structured_request",
        lambda request, resource_type: (
            request.knowledge_point,
            [{"id": "c1", "content": f"{request.knowledge_point} 的基础讲解", "metadata": {}}],
            "知识底稿",
            _snapshot(),
        ),
    )
    monkeypatch.setattr(module, "AuditService", lambda *a, **k: SimpleNamespace(
        audit_structured_resource=lambda *a, **k: SimpleNamespace(status="passed", reason="rule_audit_passed")
    ))
    monkeypatch.setattr(svc, "_persist_generated_resource", lambda *a, **k: 4242)
    return svc


def _request(resource_type: str) -> ResourceGenerationRequest:
    return ResourceGenerationRequest(
        user_id=1,
        knowledge_point="循环结构",
        resource_type=resource_type,  # type: ignore[arg-type]
        subject="Python",
        learner_profile={"style": "visual"},
    )


# --------------------------------------------------------------------------
# mind map
# --------------------------------------------------------------------------


MIND_MAP_PAYLOAD = {
    "title": "循环结构导图",
    "knowledge_point": "循环结构",
    "root_id": "root",
    "nodes": [
        {"id": "root", "label": "循环结构", "parent_id": None, "level": 0, "detail": "重复执行"},
        {"id": "for", "label": "for 循环", "parent_id": "root", "level": 1, "detail": "遍历序列"},
        {"id": "while", "label": "while 循环", "parent_id": "root", "level": 1, "detail": "条件重复"},
    ],
    "edges": [
        {"source": "root", "target": "for", "label": "包含"},
        {"source": "root", "target": "while", "label": "包含"},
    ],
    "mermaid_source": "",
}


def test_generate_mind_map_returns_structured_nodes_and_edges(service, monkeypatch):
    monkeypatch.setattr(service, "_invoke_structured", lambda *a, **k: dict(MIND_MAP_PAYLOAD))
    response = service.generate_mind_map(_request("mind_map"))

    assert response["resource_type"] == "mind_map"
    payload = response["mind_map"]
    assert [node["id"] for node in payload["nodes"]] == ["root", "for", "while"]
    assert payload["edges"][0] == {"source": "root", "target": "for", "label": "包含"}
    # content stays human-readable markdown built from the structure
    assert "# 循环结构导图" in response["content"]
    assert "for 循环" in response["content"]
    assert response["content_validation"]["resource_type"] == "mind_map"


def test_generate_mind_map_survives_dangling_edges_in_validation(service, monkeypatch):
    broken = dict(MIND_MAP_PAYLOAD)
    broken["edges"] = [{"source": "root", "target": "nonexistent", "label": "x"}]
    monkeypatch.setattr(service, "_invoke_structured", lambda *a, **k: broken)

    response = service.generate_mind_map(_request("mind_map"))
    validation = response["content_validation"]
    assert validation["structure_passed"] is False
    assert validation["verdict"] == "needs_revision"
    flagged = {check["check_id"] for check in validation["checks"] if check["status"] == "failed"}
    assert "mindmap_edges_resolve" in flagged


def test_generate_mind_map_renders_mermaid_block_when_supplied(service, monkeypatch):
    payload = dict(MIND_MAP_PAYLOAD)
    payload["mermaid_source"] = "mindmap\n  root((循环结构))\n    for\n    while"
    monkeypatch.setattr(service, "_invoke_structured", lambda *a, **k: payload)

    response = service.generate_mind_map(_request("mind_map"))
    assert "```mermaid" in response["content"]
    assert response["mind_map"]["mermaid_source"].startswith("mindmap")


# --------------------------------------------------------------------------
# code case
# --------------------------------------------------------------------------


CODE_CASE_PAYLOAD = {
    "title": "累加求和案例",
    "language": "python",
    "objective": "掌握用 for 循环累加",
    "prerequisites": ["变量", "for 循环"],
    "example_code": "total = 0\nfor i in range(5):\n    total += i\nprint(total)",
    "code_explanation": ["range(5) 产生 0-4"],
    "expected_output": "10",
    "run_steps": ["保存为 sum.py", "运行 python sum.py"],
    "common_errors": ["缩进不一致"],
    "extension_exercises": ["改成求偶数和"],
}


def test_generate_code_case_is_static_and_carries_run_steps(service, monkeypatch):
    monkeypatch.setattr(service, "_invoke_structured", lambda *a, **k: dict(CODE_CASE_PAYLOAD))
    response = service.generate_code_case(_request("code_case"))

    payload = response["code_case"]
    assert payload["language"] == "python"
    assert payload["run_steps"] == ["保存为 sum.py", "运行 python sum.py"]
    # The response must never claim the code was executed by this system.
    assert "executed" not in payload
    assert "sandbox_output" not in payload
    assert "系统未执行这段代码" in response["content"]


def test_generate_code_case_rejects_missing_run_steps(service, monkeypatch):
    payload = dict(CODE_CASE_PAYLOAD)
    payload["run_steps"] = []
    monkeypatch.setattr(service, "_invoke_structured", lambda *a, **k: payload)

    with pytest.raises(ResourceGenerationError, match="run instructions"):
        service.generate_code_case(_request("code_case"))


def test_generate_code_case_validation_flags_execution_claims(service, monkeypatch):
    payload = dict(CODE_CASE_PAYLOAD)
    payload["executed"] = True
    monkeypatch.setattr(service, "_invoke_structured", lambda *a, **k: payload)

    response = service.generate_code_case(_request("code_case"))
    validation = response["content_validation"]
    flagged = {check["check_id"] for check in validation["checks"] if check["status"] == "failed"}
    assert "code_case_no_execution_claim" in flagged


# --------------------------------------------------------------------------
# video script
# --------------------------------------------------------------------------


VIDEO_SCRIPT_PAYLOAD = {
    "title": "循环结构讲解",
    "target_audience": "初学者",
    "total_duration_seconds": 999,  # deliberately wrong on purpose
    "chapters": [
        {
            "chapter_id": "ch1",
            "title": "导入",
            "narration": "同学们好，今天讲循环。",
            "visual": "板书",
            "on_screen_text": "循环结构",
            "duration_seconds": 60,
        },
        {
            "chapter_id": "ch2",
            "title": "演示",
            "narration": "我们来看一段累加代码。",
            "visual": "代码演示",
            "on_screen_text": "",
            "duration_seconds": 90,
        },
    ],
    "production_notes": ["语速放慢"],
}


def test_generate_video_script_produces_a_script_not_a_video(service, monkeypatch):
    monkeypatch.setattr(service, "_invoke_structured", lambda *a, **k: dict(VIDEO_SCRIPT_PAYLOAD))
    response = service.generate_video_script(_request("video_script"))

    payload = response["video_script"]
    assert [chapter["chapter_id"] for chapter in payload["chapters"]] == ["ch1", "ch2"]
    assert payload["chapters"][0]["narration"] == "同学们好，今天讲循环。"
    assert "video_path" not in payload
    assert "拍摄脚本" in response["content"]
    assert "不是视频文件" in response["content"]


def test_video_script_total_is_the_chapter_sum_not_the_model_claim(service, monkeypatch):
    monkeypatch.setattr(service, "_invoke_structured", lambda *a, **k: dict(VIDEO_SCRIPT_PAYLOAD))
    response = service.generate_video_script(_request("video_script"))
    # 999 was declared; the two real chapters sum to 150 and that must win.
    assert response["video_script"]["total_duration_seconds"] == 150.0
    assert response["content_validation"]["structure_passed"] is True


def test_generate_video_script_rejects_chapters_without_narration(service, monkeypatch):
    payload = dict(VIDEO_SCRIPT_PAYLOAD)
    payload["chapters"] = [{"chapter_id": "ch1", "duration_seconds": 60, "narration": "   "}]
    monkeypatch.setattr(service, "_invoke_structured", lambda *a, **k: payload)

    with pytest.raises(ResourceGenerationError, match="no usable chapters"):
        service.generate_video_script(_request("video_script"))


def test_generate_video_script_rejects_non_positive_duration(service, monkeypatch):
    payload = dict(VIDEO_SCRIPT_PAYLOAD)
    payload["chapters"] = [{"chapter_id": "ch1", "duration_seconds": 0, "narration": "讲解"}]
    monkeypatch.setattr(service, "_invoke_structured", lambda *a, **k: payload)

    with pytest.raises(ResourceGenerationError, match="positive duration"):
        service.generate_video_script(_request("video_script"))


def test_generate_video_script_rejects_claimed_media_file(service, monkeypatch):
    payload = dict(VIDEO_SCRIPT_PAYLOAD)
    payload["video_path"] = "/tmp/lesson.mp4"
    monkeypatch.setattr(service, "_invoke_structured", lambda *a, **k: payload)

    response = service.generate_video_script(_request("video_script"))
    validation = response["content_validation"]
    flagged = {check["check_id"] for check in validation["checks"] if check["status"] == "failed"}
    assert "video_script_is_script_only" in flagged


# --------------------------------------------------------------------------
# JSON parsing contract
# --------------------------------------------------------------------------


def test_parse_json_object_accepts_fenced_json():
    parsed = ResourceGenerationService._parse_json_object('```json\n{"a": 1}\n```', "test")
    assert parsed == {"a": 1}


def test_parse_json_object_rejects_non_json():
    with pytest.raises(ResourceGenerationError, match="did not return a JSON object"):
        ResourceGenerationService._parse_json_object("抱歉，我无法生成。", "test")


# --------------------------------------------------------------------------
# prompt rendering contract
# --------------------------------------------------------------------------


def test_prompt_rendering_leaves_literal_json_braces_untouched():
    """Regression guard: the JSON example in the prompt is not a format field.

    ``str.format`` used to raise ``KeyError: '\\n  "title"'`` on the real prompt
    files, so no structured resource could ever be generated for real.
    """

    template = '结构：\n{\n  "title": "标题",\n  "nodes": [{"id": "a"}]\n}\n知识点：{knowledge_point}\n'
    rendered = module._render_prompt_template(template, {"knowledge_point": "二分查找"}, "test.md")

    assert '"title": "标题"' in rendered
    assert '"nodes": [{"id": "a"}]' in rendered
    assert rendered.endswith("知识点：二分查找\n")


def test_prompt_rendering_reports_a_missing_variable():
    with pytest.raises(ResourceGenerationError, match="missing variable"):
        module._render_prompt_template("知识点：{knowledge_point}", {}, "test.md")


@pytest.mark.parametrize("filename", ["mind_map_gen.md", "code_case_gen.md", "video_script_gen.md"])
def test_real_prompt_files_render_with_the_structured_variables(filename):
    """The shipped prompts must render against the variables the service supplies."""

    variables = {
        "subject": "数据结构",
        "knowledge_point": "二分查找",
        "resource_style": "concise",
        "learner_profile": "画像",
        "context_text": "检索内容",
        "grounding_text": "知识底稿",
    }
    rendered = module._render_prompt_template(
        module._load_prompt_template(filename), variables, filename
    )

    assert "{" + "knowledge_point" + "}" not in rendered
    assert "二分查找" in rendered
    # the literal JSON contract survives intact
    assert '"title"' in rendered
