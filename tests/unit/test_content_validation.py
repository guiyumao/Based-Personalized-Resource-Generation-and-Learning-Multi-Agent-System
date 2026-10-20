"""Tests for deterministic structural and source validation of generated content.

These tests exercise pure functions only: no model, no database, no network.  A
deterministic validator is only worth having if its verdicts are reproducible,
so every assertion here pins an exact outcome.
"""

from __future__ import annotations

from services.agent_service.app.services.content_validation import (
    detect_truncation,
    extract_citations,
    find_placeholders,
    validate_code_case,
    validate_courseware,
    validate_exercises,
    validate_generated_resource,
    validate_mind_map,
    validate_sources,
    validate_video_script,
)

GOOD_COURSEWARE = (
    "# 循环结构\n\n"
    "## 学习目标\n学完本节能够写出带终止条件的循环。\n\n"
    "## 知识讲解\n循环由初始化、条件判断和迭代三部分组成，缺少终止条件会死循环。\n\n"
    "## 示例\n下面的例子演示累加求和：\n\n```python\ntotal = 0\nfor i in range(5):\n"
    "    total += i\n```\n\n"
    "## 课堂小结\n记住先写终止条件，再写循环体。\n\n"
    "## 学完后自测\n1. 什么情况下会出现死循环？\n2. 如何提前结束循环？\n"
)


def _chunk(chunk_id: str, content: str, knowledge_point: str = "循环") -> dict:
    return {
        "id": chunk_id,
        "content": content,
        "metadata": {"knowledge_point": knowledge_point, "source": "kb/course.md"},
    }


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def test_find_placeholders_detects_unfinished_draft_markers():
    text = "这里是标题\n[待补充]\nTODO: 补充例子\n{{outline}}\n我是一个AI模型，无法生成该内容"
    found = find_placeholders(text)
    assert "[待补充]" in found
    assert "{{outline}}" in found
    assert any("TODO" in marker for marker in found)
    assert any("AI" in marker for marker in found)


def test_find_placeholders_ignores_legitimate_chinese_prose():
    # "等" and "略" are ordinary words; flagging them would reject good content.
    found = find_placeholders("常见的排序算法有冒泡排序、快速排序等；策略略作调整即可。")
    assert found == []


def test_detect_truncation_flags_dangling_separator_and_open_code_block():
    assert detect_truncation("这是一个没有写完的句子，") is not None
    assert detect_truncation("```python\nprint(1)") is not None
    assert detect_truncation("") is not None
    assert detect_truncation("这是一个完整的句子。") is None


# --------------------------------------------------------------------------
# courseware
# --------------------------------------------------------------------------


def test_validate_courseware_passes_complete_document():
    report = validate_courseware("循环结构", GOOD_COURSEWARE, "循环结构")
    assert report.structure_passed is True
    assert report.verdict in {"insufficient_evidence", "unsupported", "valid"}


def test_validate_courseware_rejects_missing_sections():
    report = validate_courseware("循环结构", "太短了")
    assert report.structure_passed is False
    assert report.verdict == "needs_revision"
    failed = {check.check_id for check in report.failed_checks()}
    assert "courseware_min_length" in failed
    assert "courseware_required_sections" in failed


def test_validate_courseware_rejects_placeholder_content():
    content = GOOD_COURSEWARE.replace("学完本节能够写出带终止条件的循环。", "[待补充]")
    report = validate_courseware("循环结构", content)
    failed = {check.check_id for check in report.failed_checks()}
    assert "courseware_no_placeholders" in failed


def test_validate_courseware_rejects_generation_failure_text():
    content = GOOD_COURSEWARE.replace("# 循环结构", "# 循环结构\n\nTraceback (most recent call last):")
    report = validate_courseware("循环结构", content)
    failed = {check.check_id for check in report.failed_checks()}
    assert "courseware_no_generation_failure_text" in failed


# --------------------------------------------------------------------------
# exercise answer consistency
# --------------------------------------------------------------------------


def _exercise(**overrides) -> dict:
    base = {
        "prompt": "以下哪个是循环的终止条件？",
        "question_type": "choice",
        "difficulty": "foundation",
        "options": ["i < 10", "i = 10", "i > 10"],
        "answer": "i < 10",
        "analysis": "条件为真时继续循环。",
    }
    base.update(overrides)
    return base


def test_validate_exercises_accepts_consistent_choice_answer():
    report = validate_exercises("循环", [_exercise()])
    assert report.structure_passed is True


def test_validate_exercises_rejects_answer_not_in_own_options():
    report = validate_exercises("循环", [_exercise(answer="i != 10")])
    assert report.structure_passed is False
    failed = {check.check_id for check in report.failed_checks()}
    assert "exercises_option_consistency" in failed


def test_validate_exercises_accepts_letter_and_index_answer_keys():
    by_letter = validate_exercises("循环", [_exercise(answer="A")])
    by_index = validate_exercises("循环", [_exercise(answer="1")])
    assert by_letter.structure_passed is True
    assert by_index.structure_passed is True


def test_validate_exercises_rejects_out_of_range_letter_key():
    report = validate_exercises("循环", [_exercise(answer="Z")])
    assert report.structure_passed is False


def test_validate_exercises_rejects_duplicate_prompts():
    report = validate_exercises("循环", [_exercise(), _exercise()])
    failed = {check.check_id for check in report.failed_checks()}
    assert "exercises_unique_prompts" in failed


def test_validate_exercises_rejects_missing_required_field():
    report = validate_exercises("循环", [_exercise(analysis="")])
    failed = {check.check_id for check in report.failed_checks()}
    assert "exercises_required_fields" in failed
    assert "exercises_analysis_present" in failed


def test_validate_exercises_rejects_empty_set():
    report = validate_exercises("循环", [])
    assert report.structure_passed is False


# --------------------------------------------------------------------------
# mind map
# --------------------------------------------------------------------------


def test_validate_mind_map_accepts_structured_nodes_and_edges():
    payload = {
        "nodes": [{"id": "root", "label": "循环"}, {"id": "child", "label": "for"}],
        "edges": [{"source": "root", "target": "child"}],
    }
    report = validate_mind_map(payload)
    assert report.structure_passed is True


def test_validate_mind_map_rejects_dangling_edges():
    payload = {
        "nodes": [{"id": "root", "label": "循环"}],
        "edges": [{"source": "root", "target": "missing"}],
    }
    report = validate_mind_map(payload)
    assert report.structure_passed is False
    failed = {check.check_id for check in report.failed_checks()}
    assert "mindmap_edges_resolve" in failed


def test_validate_mind_map_accepts_mermaid_text():
    mermaid = "mindmap\n  root((循环))\n    for\n    while\n"
    report = validate_mind_map(mermaid)
    assert report.structure_passed is True


def test_validate_mind_map_rejects_mermaid_without_diagram_type():
    report = validate_mind_map("root((循环))\n  for\n")
    failed = {check.check_id for check in report.failed_checks()}
    assert "mindmap_declares_diagram_type" in failed


def test_validate_mind_map_rejects_unbalanced_mermaid_brackets():
    report = validate_mind_map("mindmap\n  root((循环)\n    for\n")
    failed = {check.check_id for check in report.failed_checks()}
    assert "mindmap_balanced_brackets" in failed


# --------------------------------------------------------------------------
# code case (static only - this project has no sandbox)
# --------------------------------------------------------------------------


def test_validate_code_case_accepts_static_example():
    report = validate_code_case(
        {
            "language": "python",
            "objective": "掌握累加求和",
            "prerequisites": ["变量", "for 循环"],
            "example_code": "total = 0\nfor i in range(5):\n    total += i\nprint(total)",
            "expected_output": "10",
            "run_steps": ["保存为 sum.py", "运行 python sum.py"],
            "common_errors": ["缩进错误"],
        }
    )
    assert report.structure_passed is True


def test_validate_code_case_rejects_execution_claim():
    report = validate_code_case(
        {
            "language": "python",
            "objective": "x",
            "example_code": "print(1)",
            "run_steps": ["run it"],
            "executed": True,
            "sandbox_output": "1",
        }
    )
    assert report.structure_passed is False
    failed = {check.check_id for check in report.failed_checks()}
    assert "code_case_no_execution_claim" in failed


def test_validate_code_case_rejects_missing_run_steps():
    report = validate_code_case({"language": "python", "objective": "x", "example_code": "print(1)"})
    failed = {check.check_id for check in report.failed_checks()}
    assert "code_case_required_fields" in failed
    assert "code_case_run_steps_actionable" in failed


# --------------------------------------------------------------------------
# video script (script only - no video file is ever produced)
# --------------------------------------------------------------------------


def test_validate_video_script_accepts_well_formed_script():
    report = validate_video_script(
        {
            "title": "循环入门",
            "total_duration_seconds": 120,
            "chapters": [
                {
                    "chapter_id": "c1",
                    "title": "导入",
                    "narration": "同学们好，今天讲循环。",
                    "visual": "黑板演示",
                    "duration_seconds": 60,
                },
                {
                    "chapter_id": "c2",
                    "title": "练习",
                    "narration": "请写出累加求和。",
                    "visual": "屏幕题目",
                    "duration_seconds": 60,
                },
            ],
        }
    )
    assert report.structure_passed is True


def test_validate_video_script_rejects_claimed_video_file():
    report = validate_video_script(
        {
            "chapters": [{"narration": "x", "duration_seconds": 10}],
            "video_path": "/tmp/out.mp4",
        }
    )
    assert report.structure_passed is False
    failed = {check.check_id for check in report.failed_checks()}
    assert "video_script_is_script_only" in failed


def test_validate_video_script_rejects_chapter_without_narration():
    report = validate_video_script({"chapters": [{"visual": "x", "duration_seconds": 10}]})
    failed = {check.check_id for check in report.failed_checks()}
    assert "video_script_chapters_have_narration" in failed


def test_validate_video_script_rejects_invalid_duration_and_total_drift():
    report = validate_video_script(
        {
            "total_duration_seconds": 500,
            "chapters": [
                {"narration": "a", "duration_seconds": 10},
                {"narration": "b", "duration_seconds": 0},
            ],
        }
    )
    failed = {check.check_id for check in report.failed_checks()}
    assert "video_script_durations_valid" in failed
    assert "video_script_total_matches_chapters" in failed


# --------------------------------------------------------------------------
# source / groundedness
# --------------------------------------------------------------------------


def test_extract_citations_resolves_known_and_flags_fabricated_ids():
    chunks = [_chunk("c1", "循环内容")]
    content = "循环由三部分组成。[来源:c1] 另外参考来源:does-not-exist"
    citations = extract_citations(content, chunks)
    resolved = {citation["reference"]: citation["resolved"] for citation in citations}
    assert resolved["c1"] is True
    assert resolved["does-not-exist"] is False


def test_extract_citations_maps_ordinal_marker_to_retrieved_chunk():
    chunks = [_chunk("c1", "a"), _chunk("c2", "b")]
    citations = extract_citations("结论如下[2]。", chunks)
    assert citations[0]["resolved"] is True
    assert citations[0]["chunk_id"] == "c2"


def test_validate_sources_returns_insufficient_evidence_when_nothing_retrieved():
    _, checks, coverage = validate_sources(GOOD_COURSEWARE, [], knowledge_point="循环")
    assert coverage == 0.0
    assert len(checks) == 1
    assert checks[0].status == "skipped"
    assert checks[0].check_id == "sources_available"


def test_validate_sources_flags_fabricated_citation_as_unsupported():
    content = GOOD_COURSEWARE + "\n\n[来源:invented-id]"
    citations, checks, _ = validate_sources(
        content, [_chunk("c1", "循环")], knowledge_point="循环"
    )
    unresolved = [check for check in checks if check.check_id == "sources_citations_resolve"]
    assert unresolved and unresolved[0].passed is False
    assert any(citation["resolved"] is False for citation in citations)


def test_validate_sources_measures_coverage_of_real_chunks():
    content = GOOD_COURSEWARE + "\n\n[来源:c1]"
    _, checks, coverage = validate_sources(
        content, [_chunk("c1", "循环"), _chunk("c2", "分支")], knowledge_point="循环"
    )
    assert coverage == 0.5
    assert all(check.passed for check in checks if check.check_id != "sources_cover_knowledge_point")


def test_validate_sources_flags_chunks_that_never_mention_the_knowledge_point():
    _, checks, _ = validate_sources(
        GOOD_COURSEWARE, [_chunk("c1", "无关内容", knowledge_point="排序")], knowledge_point="循环"
    )
    topic = [check for check in checks if check.check_id == "sources_cover_knowledge_point"]
    assert topic and topic[0].passed is False


# --------------------------------------------------------------------------
# dispatcher / verdict semantics
# --------------------------------------------------------------------------


def test_dispatcher_reports_needs_revision_for_bad_structure():
    report = validate_generated_resource(
        resource_type="courseware",
        content="短",
        knowledge_point="循环",
        source_chunks=[_chunk("c1", "循环")],
    )
    assert report["verdict"] == "needs_revision"
    assert report["structure_passed"] is False


def test_dispatcher_reports_insufficient_evidence_when_no_retrieval():
    report = validate_generated_resource(
        resource_type="courseware",
        content=GOOD_COURSEWARE,
        knowledge_point="循环",
        source_chunks=[],
    )
    assert report["verdict"] == "insufficient_evidence"


def test_dispatcher_reports_valid_for_cited_grounded_content():
    report = validate_generated_resource(
        resource_type="courseware",
        content=GOOD_COURSEWARE + "\n\n[来源:c1]",
        knowledge_point="循环",
        source_chunks=[_chunk("c1", "循环由三部分组成")],
    )
    assert report["verdict"] == "valid"
    assert report["structure_passed"] is True
    assert report["source_passed"] is True


def test_dispatcher_reports_unsupported_when_sources_exist_but_unused():
    report = validate_generated_resource(
        resource_type="courseware",
        content=GOOD_COURSEWARE,
        knowledge_point="循环",
        source_chunks=[_chunk("c1", "循环")],
    )
    assert report["verdict"] == "unsupported"


def test_dispatcher_rejects_unknown_resource_type_instead_of_passing_it():
    report = validate_generated_resource(
        resource_type="hologram",
        content="anything",
        source_chunks=[_chunk("c1", "循环")],
    )
    assert report["verdict"] == "needs_revision"
    failed = [check for check in report["checks"] if check["status"] == "failed"]
    assert any(check["check_id"] == "resource_type_known" for check in failed)


def test_dispatcher_routes_exercise_validation_from_items():
    report = validate_generated_resource(
        resource_type="exercise",
        exercises=[_exercise()],
        knowledge_point="循环",
        source_chunks=[_chunk("c1", "循环")],
    )
    assert report["structure_passed"] is True


def test_report_dict_is_json_serializable():
    import json

    report = validate_generated_resource(
        resource_type="mind_map",
        payload={"nodes": [{"id": "a", "label": "循环"}], "edges": []},
        knowledge_point="循环",
        source_chunks=[],
    )
    json.dumps(report)  # must not raise
    assert set(report) >= {"verdict", "checks", "structure_passed", "source_passed", "citations"}
