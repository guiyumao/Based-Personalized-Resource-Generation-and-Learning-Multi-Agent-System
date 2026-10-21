"""Controlled-provider tests: persistence, selective retries and no double work."""
import json

import pytest

from common.models.learning import Exercise, Resource
from common.schemas.agent import ResourceGenerationRequest, ResourceGenerationResponse
from services.agent_service.app.services.courseware_quality import check_module
from services.agent_service.app.services.resource_generation import (
    ResourceGenerationError,
    ResourceGenerationService,
)


def module_fixture():
    """Structural fixture, not evidence of model or academic content quality."""
    text = "本地受控模型测试正文，用于验证章节不会丢失、持久化完整、重试只发生在失败章节。" * 15
    return text + "\n\n步骤1：给出输入。\n步骤2：展示中间结果。\n步骤3：检查结果。\n\n|阶段|状态|\n|---|---|\n|1|输入|\n|2|过程|\n|3|结果|\n\n" + "\n\n".join(
        f"### 题目{i}\n说明第{i}个条件。\n\n### 答案与解析{i}\n标准答案：第{i}个条件成立；逐步检查边界再得出结果。" for i in range(1, 4))


@pytest.fixture
def generator(monkeypatch, test_user):
    service = ResourceGenerationService()
    context = {"knowledge_base_version": service.settings.knowledge_base_version, "knowledge_point_id": "",
               "retrieved_chunks": [], "source_ids": []}
    monkeypatch.setattr(service, "_load_retrieval_context", lambda *args, **kwargs: ([], context))
    # The real video encoder is covered in test_resource_artifacts; chapter tests
    # exercise controlled text generation without encoding a new movie per case.
    monkeypatch.setattr(service, "_ensure_courseware_video", lambda resource: {"video": {"status": "not_tested"}})
    return service, ResourceGenerationRequest(user_id=test_user.id, knowledge_point=f"测试排序{test_user.id}",
        request_text="生成完整初学课件", assistant_operation_key=f"teaching-test:{test_user.id}")


def test_nine_modules_roundtrip_exercises_and_zero_call_replay(generator, monkeypatch, db_session):
    service, request = generator
    calls = []
    monkeypatch.setattr(service, "_invoke_llm", lambda variables, **kwargs: calls.append(json.loads(variables["chapter_instruction"])["当前章节"]) or module_fixture())
    result = service.generate_courseware_with_plan(request)
    assert len(calls) == 9
    saved = db_session.get(Resource, result["id"])
    assert saved.content == result["content"]
    metadata = json.loads(saved.structured_json)
    assert metadata["quality"]["status"] == "passed" and len(metadata["chapters"]) == 9
    assert metadata["quality"]["semantic_accuracy"] == "requires_subject_review"
    assert len(metadata["exercises"]) == 3
    for exercise in metadata["exercises"]:
        assert db_session.get(Exercise, exercise["exercise_id"]).knowledge_point_id == saved.knowledge_point_id
    replay = service.generate_courseware_with_plan(request)
    ResourceGenerationResponse.model_validate(replay)
    assert replay["id"] == result["id"] and len(calls) == 9


def test_cross_request_reuse_and_explicit_regeneration(generator, monkeypatch, db_session):
    service, request = generator
    calls = []
    monkeypatch.setattr(service, '_invoke_llm', lambda variables, **kw: calls.append(variables) or module_fixture())
    first = service.generate_courseware_with_plan(request)
    same = request.model_copy(update={'assistant_operation_key': request.assistant_operation_key + '-another-entry'})
    replay = service.generate_courseware_with_plan(same)
    assert replay['id'] == first['id'] and replay['reused'] is True and len(calls) == 9
    forced = same.model_copy(update={'force_regenerate': True})
    new = service.generate_courseware_with_plan(forced)
    assert new['id'] != first['id'] and len(calls) == 18
    changed = same.model_copy(update={'request_text': '针对边界条件生成新的案例', 'assistant_operation_key': 'different-goal'})
    different = service.generate_courseware_with_plan(changed)
    assert different['id'] != first['id'] and len(calls) == 27


def test_selective_retry_keeps_other_chapters(generator, monkeypatch):
    service, request = generator
    calls = []
    def model(variables, **kwargs):
        heading = json.loads(variables["chapter_instruction"])["当前章节"]
        calls.append(heading)
        return "过短" if heading == "核心原理" and calls.count(heading) == 1 else module_fixture()
    monkeypatch.setattr(service, "_invoke_llm", model)
    assert service.generate_courseware_with_plan(request)["generation_status"] == "generated"
    assert len(calls) == 10 and calls.count("核心原理") == 2 and calls.count("核心概念") == 1


def test_ambiguous_failure_preserves_completed_modules_and_blocks_auto_replay(generator, monkeypatch, db_session):
    service, request = generator
    calls = []
    def model(variables, **kwargs):
        calls.append(variables)
        if len(calls) == 3:
            raise ResourceGenerationError("transport outcome unknown")
        return module_fixture()
    monkeypatch.setattr(service, "_invoke_llm", model)
    with pytest.raises(ResourceGenerationError):
        service.generate_courseware_with_plan(request)
    partial = db_session.query(Resource).filter_by(assistant_operation_key=request.assistant_operation_key).one()
    metadata = json.loads(partial.structured_json)
    assert len(metadata["chapters"]) == 2 and metadata["in_flight"] == "principles"
    with pytest.raises(ResourceGenerationError, match="结果未知"):
        service.generate_courseware_with_plan(request)
    assert len(calls) == 3


def test_quality_rejects_short_missing_answers_and_unclosed_fences():
    assert check_module("concepts", "定义而已")
    assert check_module("practice", "足够长的文字" * 100)
    assert check_module("principles", module_fixture() + "\n```python\nx=1")


def test_chapter_revision_preserves_original_and_only_generates_one_module(generator, monkeypatch, db_session):
    from common.resource_version import resource_version
    service, request = generator
    calls = []
    monkeypatch.setattr(service, "_invoke_llm", lambda variables, **kwargs: calls.append(variables) or module_fixture())
    response = service.generate_courseware_with_plan(request)
    original = db_session.get(Resource, response["id"])
    old_body = original.content
    before = json.loads(original.structured_json)
    new = service.regenerate_chapter(request.user_id, 98765, original.id, resource_version(original), "case")
    assert len(calls) == 10 and new["id"] != original.id
    db_session.expire_all()
    assert db_session.get(Resource, original.id).content == old_body
    after = json.loads(db_session.get(Resource, new["id"]).structured_json)
    assert len(after["exercises"]) == 3
    for chapter in before["chapters"]:
        if chapter["key"] != "case":
            assert chapter["body"] == next(item["body"] for item in after["chapters"] if item["key"] == chapter["key"])
