"""Deterministic structural and source validation for generated content.

This module implements the two verifiable layers of content checking:

1. **Structural checks** — pure code, no model.  Required fields, type rules,
   placeholders, duplicated items, and truncation are decided by rules, so a
   result is reproducible and can be asserted in tests.
2. **Source checks** — verify that a generated artefact is actually anchored in
   the knowledge chunks that were retrieved for this request.  A citation that
   names a chunk id which was never retrieved is a fabricated source, not a
   citation.

Semantic LLM review is deliberately *not* implemented here; it lives in
:mod:`services.agent_service.app.services.audit_service` behind an explicit
``unavailable`` status.  Keeping the deterministic layers separate means a
missing model can never be reported as "validated".

Nothing in this module raises for bad content: a validation report is always
returned so callers can persist it, show it, and decide the next action.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal

CheckStatus = Literal["passed", "failed", "skipped"]
ValidationStage = Literal["structure", "source"]
OverallVerdict = Literal["valid", "needs_revision", "insufficient_evidence", "unsupported"]

# Placeholder markers that indicate the model emitted an unfinished draft.
# Deliberately narrow: ordinary Chinese prose legitimately contains "等" and "略",
# so only unambiguous instruction-like or empty-slot markers are listed.
PLACEHOLDER_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\{\{[^}]{0,60}\}\}"),
    re.compile(r"\[(?:待补充|待填写|待定|TODO|TBD|待生成)\]", re.IGNORECASE),
    re.compile(r"(?:此处|这里)(?:省略|略去|待补充|留空)"),
    re.compile(r"<[^>\n]{0,40}(?:待补充|placeholder|TODO)[^>\n]{0,40}>", re.IGNORECASE),
    re.compile(r"\bTODO\b|\bTBD\b|\bFIXME\b|\bXXX\b"),
    re.compile(r"作为(?:一个)?AI(?:语言)?模型"),
    re.compile(r"我(?:是|作为)(?:一个)?AI(?:语言)?模型"),
    re.compile(r"我(?:无法|不能)(?:直接)?(?:生成|提供|输出)"),
)

# Explicit citation markers the generator is asked to emit.  Both the bracketed
# form ("[来源:c1]") and the bare form ("来源:c1") are accepted, because models
# emit both; a bare "参考" without an identifier is intentionally not matched.
CITATION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\[(?:来源|参考|ref|source)\s*[:：]\s*([^\]\n]{1,120})\]", re.IGNORECASE),
    re.compile(r"(?<!\[)(?:来源|参考资料)\s*[:：]\s*([A-Za-z0-9._:\-]{2,80})"),
    re.compile(r"\[(?:chunk|doc|src)[-_:/]?([A-Za-z0-9._:\-]{1,80})\]", re.IGNORECASE),
    re.compile(r"\[(\d{1,2})\](?!\()"),
)

REQUIRED_COURSEWARE_SECTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("学习目标", ("学习目标", "教学目标", "本节目标")),
    ("知识讲解", ("知识讲解", "核心概念", "核心定义", "概念讲解")),
    ("示例", ("示例", "例题", "案例", "举例")),
    ("小结", ("小结", "总结", "回顾")),
    ("自测", ("自测", "练习", "检验")),
)


@dataclass(frozen=True)
class ValidationCheck:
    """One named deterministic check and its outcome."""

    check_id: str
    stage: ValidationStage
    passed: bool
    detail: str
    status: CheckStatus = "passed"

    def as_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "stage": self.stage,
            "status": self.status,
            "passed": self.passed,
            "detail": self.detail,
        }


@dataclass
class ValidationReport:
    """Aggregated deterministic validation result for one generated artefact."""

    resource_type: str
    checks: list[ValidationCheck] = field(default_factory=list)
    citations: list[dict[str, Any]] = field(default_factory=list)
    source_coverage: float = 0.0
    notes: list[str] = field(default_factory=list)

    @property
    def structure_passed(self) -> bool:
        return all(check.passed for check in self.checks if check.stage == "structure")

    @property
    def source_passed(self) -> bool:
        source_checks = [check for check in self.checks if check.stage == "source"]
        if not source_checks:
            return False
        return all(check.passed for check in source_checks)

    @property
    def verdict(self) -> OverallVerdict:
        if not self.structure_passed:
            return "needs_revision"
        source_checks = [check for check in self.checks if check.stage == "source"]
        if not source_checks:
            return "insufficient_evidence"
        statuses = {check.status for check in source_checks}
        if statuses == {"skipped"}:
            return "insufficient_evidence"
        if not self.source_passed:
            return "unsupported"
        return "valid"

    def as_dict(self) -> dict[str, Any]:
        return {
            "resource_type": self.resource_type,
            "verdict": self.verdict,
            "structure_passed": self.structure_passed,
            "source_passed": self.source_passed,
            "source_coverage": round(self.source_coverage, 4),
            "citations": self.citations,
            "checks": [check.as_dict() for check in self.checks],
            "notes": self.notes,
        }

    def failed_checks(self) -> list[ValidationCheck]:
        return [check for check in self.checks if not check.passed and check.status == "failed"]


def _check(
    check_id: str,
    stage: ValidationStage,
    passed: bool,
    detail: str,
    *,
    skipped: bool = False,
) -> ValidationCheck:
    if skipped:
        return ValidationCheck(check_id, stage, False, detail, "skipped")
    return ValidationCheck(check_id, stage, passed, detail, "passed" if passed else "failed")


def find_placeholders(text: str) -> list[str]:
    """Return the distinct placeholder markers found in ``text``."""

    found: list[str] = []
    for pattern in PLACEHOLDER_PATTERNS:
        for match in pattern.finditer(text or ""):
            marker = match.group(0).strip()
            if marker and marker not in found:
                found.append(marker)
    return found


def detect_truncation(text: str) -> str | None:
    """Return a human-readable reason when ``text`` looks cut off, else ``None``."""

    stripped = (text or "").strip()
    if not stripped:
        return "content is empty"
    if stripped.endswith(("...", "…", "，", ",", "、", "：", ":", "（", "(", "【", "[")):
        return "content ends with a dangling separator or ellipsis"
    if stripped.count("```") % 2 == 1:
        return "content has an unterminated fenced code block"
    if stripped.count("**") % 2 == 1:
        return "content has an unbalanced bold marker"
    return None


def _iter_exercise_items(exercises: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in exercises if isinstance(item, dict)]


def validate_exercises(
    knowledge_point: str,
    exercises: list[dict[str, Any]],
) -> ValidationReport:
    """Structurally validate a generated exercise set.

    Checks answer/option consistency and duplicate prompts without needing any
    model: an item whose stored ``answer`` is not among its own options cannot be
    answered correctly by a learner.
    """

    report = ValidationReport(resource_type="exercise")
    items = _iter_exercise_items(exercises)

    report.checks.append(
        _check("exercises_present", "structure", bool(items), f"{len(items)} exercise(s) received")
    )
    if not items:
        return report

    required = ("prompt", "answer", "analysis", "question_type", "difficulty")
    missing_rows: list[str] = []
    for index, item in enumerate(items, 1):
        missing = [name for name in required if not str(item.get(name) or "").strip()]
        if missing:
            missing_rows.append(f"#{index} missing {', '.join(missing)}")
    report.checks.append(
        _check(
            "exercises_required_fields",
            "structure",
            not missing_rows,
            "; ".join(missing_rows) or "all exercises carry prompt/answer/analysis/type/difficulty",
        )
    )

    option_problems: list[str] = []
    for index, item in enumerate(items, 1):
        if str(item.get("question_type")) != "choice":
            continue
        options = [str(option).strip() for option in (item.get("options") or []) if str(option).strip()]
        if len(options) < 2:
            option_problems.append(f"#{index} has {len(options)} usable option(s)")
            continue
        if len({option for option in options}) != len(options):
            option_problems.append(f"#{index} repeats an option")
        answer = str(item.get("answer") or "").strip()
        if answer and not _answer_matches_option(answer, options):
            option_problems.append(f"#{index} answer is not among its options")
    report.checks.append(
        _check(
            "exercises_option_consistency",
            "structure",
            not option_problems,
            "; ".join(option_problems) or "every choice answer resolves to one of its own options",
        )
    )

    prompts = [re.sub(r"\s+", "", str(item.get("prompt") or "")) for item in items]
    duplicates = {prompt for prompt in prompts if prompt and prompts.count(prompt) > 1}
    report.checks.append(
        _check(
            "exercises_unique_prompts",
            "structure",
            not duplicates,
            f"{len(duplicates)} duplicated prompt(s)" if duplicates else "no duplicated prompts",
        )
    )

    placeholder_hits = [
        f"#{index} -> {marker}"
        for index, item in enumerate(items, 1)
        for marker in find_placeholders(str(item.get("prompt") or ""))
    ]
    report.checks.append(
        _check(
            "exercises_no_placeholders",
            "structure",
            not placeholder_hits,
            "; ".join(placeholder_hits) or "no placeholder markers",
        )
    )

    empty_answers = [
        f"#{index}" for index, item in enumerate(items, 1) if not str(item.get("answer") or "").strip()
    ]
    report.checks.append(
        _check(
            "exercises_answers_non_empty",
            "structure",
            not empty_answers,
            f"empty answer for {', '.join(empty_answers)}" if empty_answers else "every exercise has an answer",
        )
    )

    analysis_missing = [
        f"#{index}"
        for index, item in enumerate(items, 1)
        if not str(item.get("analysis") or "").strip()
    ]
    report.checks.append(
        _check(
            "exercises_analysis_present",
            "structure",
            not analysis_missing,
            f"missing analysis for {', '.join(analysis_missing)}"
            if analysis_missing
            else "every exercise carries an analysis",
        )
    )
    report.notes.append(f"knowledge_point={knowledge_point}")
    return report


def _answer_matches_option(answer: str, options: list[str]) -> bool:
    """Return True when a stored answer identifies one of the given options.

    Handles the three shapes generators actually emit: the literal option text,
    a letter key (``A``/``A.``/``A、``), and a 1-based index.
    """

    normalized_answer = re.sub(r"\s+", "", answer).casefold()
    normalized_options = [re.sub(r"\s+", "", option).casefold() for option in options]
    if normalized_answer in normalized_options:
        return True
    # Strip a leading "A." / "A、" / "A)" style key and compare the remainder.
    body = re.sub(r"^[A-Za-z][.、)．:：]\s*", "", answer).strip()
    if body and re.sub(r"\s+", "", body).casefold() in normalized_options:
        return True
    key = re.match(r"^([A-Za-z])[.、)．:：]?$", answer.strip())
    if key:
        index = ord(key.group(1).upper()) - ord("A")
        return 0 <= index < len(options)
    if answer.strip().isdigit():
        index = int(answer.strip()) - 1
        return 0 <= index < len(options)
    return False


def validate_courseware(knowledge_point: str, content: str, title: str = "") -> ValidationReport:
    """Structurally validate generated courseware markdown."""

    report = ValidationReport(resource_type="courseware")
    stripped = (content or "").strip()

    report.checks.append(
        _check("courseware_min_length", "structure", len(stripped) >= 80, f"{len(stripped)} characters")
    )

    covered = [
        name
        for name, aliases in REQUIRED_COURSEWARE_SECTIONS
        if any(alias in stripped for alias in aliases)
    ]
    missing_sections = [
        name
        for name, aliases in REQUIRED_COURSEWARE_SECTIONS
        if not any(alias in stripped for alias in aliases)
    ]
    report.checks.append(
        _check(
            "courseware_required_sections",
            "structure",
            len(covered) >= 3,
            f"covered {len(covered)}/{len(REQUIRED_COURSEWARE_SECTIONS)}; missing: {', '.join(missing_sections) or 'none'}",
        )
    )

    error_markers = [
        marker
        for marker in ("error:", "traceback", "无法生成", "生成失败")
        if marker in stripped[:400].lower()
    ]
    report.checks.append(
        _check(
            "courseware_no_generation_failure_text",
            "structure",
            not error_markers,
            f"failure markers: {', '.join(error_markers)}" if error_markers else "no failure markers",
        )
    )

    placeholders = find_placeholders(stripped)
    report.checks.append(
        _check(
            "courseware_no_placeholders",
            "structure",
            not placeholders,
            f"placeholders: {', '.join(placeholders)}" if placeholders else "no placeholder markers",
        )
    )

    truncation = detect_truncation(stripped)
    report.checks.append(
        _check(
            "courseware_not_truncated",
            "structure",
            truncation is None,
            truncation or "content is not truncated",
        )
    )
    report.notes.append(f"knowledge_point={knowledge_point} title={title or '(untitled)'}")
    return report


def validate_mind_map(payload: str | dict[str, Any]) -> ValidationReport:
    """Validate a mind map expressed either as JSON nodes/edges or Mermaid text.

    Mermaid output is checked for the syntax properties that actually break
    rendering: a declared diagram type, a non-empty node set, and balanced
    brackets.  A JSON map is checked for unique node ids and for edges whose
    endpoints exist.
    """

    report = ValidationReport(resource_type="mind_map")
    parsed: dict[str, Any] | None = None
    mermaid_text = ""

    if isinstance(payload, dict):
        parsed = payload
    else:
        raw = (payload or "").strip()
        fenced = re.search(r"```(?:mermaid)?\s*\n(.*?)```", raw, re.DOTALL)
        candidate = fenced.group(1).strip() if fenced else raw
        if candidate.startswith("mindmap") or candidate.startswith(("graph ", "flowchart ")):
            mermaid_text = candidate
        else:
            try:
                loaded = json.loads(candidate)
                parsed = loaded if isinstance(loaded, dict) else None
            except (json.JSONDecodeError, TypeError):
                mermaid_text = candidate

    if parsed is not None:
        nodes = parsed.get("nodes")
        edges = parsed.get("edges") or []
        if not isinstance(nodes, list):
            nodes = []
        report.checks.append(
            _check("mindmap_has_nodes", "structure", bool(nodes), f"{len(nodes)} node(s)")
        )
        node_ids = [
            str(node.get("id")) for node in nodes if isinstance(node, dict) and node.get("id")
        ]
        report.checks.append(
            _check(
                "mindmap_unique_node_ids",
                "structure",
                len(node_ids) == len(set(node_ids)),
                "duplicate node ids present"
                if len(node_ids) != len(set(node_ids))
                else "node ids are unique",
            )
        )
        dangling = [
            str(edge.get("source"))
            + "->"
            + str(edge.get("target"))
            for edge in edges
            if isinstance(edge, dict)
            and (
                str(edge.get("source")) not in set(node_ids)
                or str(edge.get("target")) not in set(node_ids)
            )
        ]
        report.checks.append(
            _check(
                "mindmap_edges_resolve",
                "structure",
                not dangling,
                f"unresolved edges: {', '.join(dangling[:5])}" if dangling else "all edges resolve",
            )
        )
        labels = [
            str(node.get("label") or node.get("id") or "") for node in nodes if isinstance(node, dict)
        ]
        placeholders = [marker for label in labels for marker in find_placeholders(label)]
        report.checks.append(
            _check(
                "mindmap_no_placeholders",
                "structure",
                not placeholders,
                f"placeholders: {', '.join(placeholders)}" if placeholders else "no placeholder markers",
            )
        )
        return report

    text = mermaid_text
    report.checks.append(
        _check(
            "mindmap_declares_diagram_type",
            "structure",
            bool(re.match(r"^\s*(mindmap|graph|flowchart)\b", text)),
            "Mermaid diagram type declaration present"
            if re.match(r"^\s*(mindmap|graph|flowchart)\b", text)
            else "missing Mermaid diagram type declaration",
        )
    )
    report.checks.append(
        _check("mindmap_has_nodes", "structure", bool(text.strip()), f"{len(text)} characters")
    )
    report.checks.append(
        _check(
            "mindmap_balanced_brackets",
            "structure",
            text.count("[") == text.count("]")
            and text.count("(") == text.count(")")
            and text.count("{") == text.count("}"),
            "unbalanced brackets in Mermaid source"
            if text.count("[") != text.count("]")
            or text.count("(") != text.count(")")
            or text.count("{") != text.count("}")
            else "brackets are balanced",
        )
    )
    placeholders = find_placeholders(text)
    report.checks.append(
        _check(
            "mindmap_no_placeholders",
            "structure",
            not placeholders,
            f"placeholders: {', '.join(placeholders)}" if placeholders else "no placeholder markers",
        )
    )
    return report


def validate_code_case(payload: dict[str, Any]) -> ValidationReport:
    """Validate a static code-practice case.

    This project has no sandbox, so a code case is deliberately a *static*
    artefact: language, objective, prerequisites, example code, expected output,
    run steps, and common errors.  The validator therefore checks that the
    declared structure is present and that the example is not presented as
    already-executed output.
    """

    report = ValidationReport(resource_type="code_case")
    if not isinstance(payload, dict):
        report.checks.append(_check("code_case_is_object", "structure", False, "payload is not an object"))
        return report

    report.checks.append(_check("code_case_is_object", "structure", True, "payload is an object"))

    required = ("language", "objective", "example_code", "run_steps")
    missing = [name for name in required if not payload.get(name)]
    report.checks.append(
        _check(
            "code_case_required_fields",
            "structure",
            not missing,
            f"missing: {', '.join(missing)}" if missing else "language/objective/example_code/run_steps present",
        )
    )

    code = str(payload.get("example_code") or "")
    report.checks.append(
        _check("code_case_example_non_empty", "structure", bool(code.strip()), f"{len(code)} characters")
    )

    run_steps = payload.get("run_steps")
    steps_ok = isinstance(run_steps, list) and any(str(step).strip() for step in run_steps)
    report.checks.append(
        _check(
            "code_case_run_steps_actionable",
            "structure",
            steps_ok,
            f"{len(run_steps)} run step(s)" if isinstance(run_steps, list) else "run_steps is not a list",
        )
    )

    execution_claim = bool(payload.get("executed")) or bool(payload.get("sandbox_output"))
    report.checks.append(
        _check(
            "code_case_no_execution_claim",
            "structure",
            not execution_claim,
            "payload claims the code was executed; this system has no sandbox"
            if execution_claim
            else "no execution claim; example is static",
        )
    )

    placeholders = find_placeholders(code)
    report.checks.append(
        _check(
            "code_case_no_placeholders",
            "structure",
            not placeholders,
            f"placeholders in example: {', '.join(placeholders)}"
            if placeholders
            else "no placeholder markers",
        )
    )
    return report


def validate_video_script(payload: dict[str, Any]) -> ValidationReport:
    """Validate a teaching video *script* (never a video file)."""

    report = ValidationReport(resource_type="video_script")
    if not isinstance(payload, dict):
        report.checks.append(
            _check("video_script_is_object", "structure", False, "payload is not an object")
        )
        return report

    report.checks.append(_check("video_script_is_object", "structure", True, "payload is an object"))

    chapters = payload.get("chapters")
    if not isinstance(chapters, list):
        chapters = []
    report.checks.append(
        _check("video_script_has_chapters", "structure", bool(chapters), f"{len(chapters)} chapter(s)")
    )

    narration_missing = [
        f"#{index}"
        for index, chapter in enumerate(chapters, 1)
        if not isinstance(chapter, dict) or not str(chapter.get("narration") or "").strip()
    ]
    if chapters:
        report.checks.append(
            _check(
                "video_script_chapters_have_narration",
                "structure",
                not narration_missing,
                f"missing narration in {', '.join(narration_missing)}"
                if narration_missing
                else "every chapter carries narration",
            )
        )

    durations: list[float] = []
    bad_durations: list[str] = []
    for index, chapter in enumerate(chapters, 1):
        if not isinstance(chapter, dict):
            continue
        seconds = chapter.get("duration_seconds")
        try:
            value = float(seconds)
        except (TypeError, ValueError):
            bad_durations.append(f"#{index}")
            continue
        if value <= 0:
            bad_durations.append(f"#{index}")
        else:
            durations.append(value)
    if chapters:
        report.checks.append(
            _check(
                "video_script_durations_valid",
                "structure",
                not bad_durations,
                f"invalid duration in {', '.join(bad_durations)}"
                if bad_durations
                else f"total {round(sum(durations), 1)}s across {len(durations)} chapter(s)",
            )
        )

    total = payload.get("total_duration_seconds")
    if total is not None and durations:
        try:
            declared = float(total)
        except (TypeError, ValueError):
            declared = -1.0
        drift = abs(declared - sum(durations))
        report.checks.append(
            _check(
                "video_script_total_matches_chapters",
                "structure",
                drift <= max(1.0, 0.05 * sum(durations)),
                f"declared {declared}s vs summed {round(sum(durations), 1)}s",
            )
        )

    # A script must not claim a rendered media artefact exists.
    claimed_file = any(
        payload.get(key) for key in ("video_path", "video_url", "rendered_file", "media_url")
    )
    report.checks.append(
        _check(
            "video_script_is_script_only",
            "structure",
            not claimed_file,
            "payload references a rendered video file; this system only produces scripts"
            if claimed_file
            else "script-only artefact, no fabricated media file",
        )
    )

    all_narration = " ".join(
        str(chapter.get("narration") or "") for chapter in chapters if isinstance(chapter, dict)
    )
    placeholders = find_placeholders(all_narration)
    report.checks.append(
        _check(
            "video_script_no_placeholders",
            "structure",
            not placeholders,
            f"placeholders: {', '.join(placeholders)}" if placeholders else "no placeholder markers",
        )
    )
    return report


def extract_citations(content: str, source_chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map in-text citation markers onto the chunks that were actually retrieved.

    A marker that does not resolve to a supplied chunk is reported with
    ``resolved=False`` so callers can surface fabricated sources instead of
    silently dropping them.
    """

    if not content:
        return []

    id_to_chunk: dict[str, dict[str, Any]] = {}
    ordinal_to_chunk: dict[int, dict[str, Any]] = {}
    for index, chunk in enumerate(source_chunks, 1):
        if not isinstance(chunk, dict):
            continue
        chunk_id = str(chunk.get("id") or "").strip()
        if chunk_id:
            id_to_chunk[chunk_id.casefold()] = chunk
        ordinal_to_chunk[index] = chunk

    citations: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for pattern in CITATION_PATTERNS:
        for match in pattern.finditer(content):
            marker = match.group(0).strip()
            token = (match.group(1) or "").strip()
            key = (marker, token)
            if key in seen:
                continue
            seen.add(key)

            resolved_chunk: dict[str, Any] | None = None
            if token.casefold() in id_to_chunk:
                resolved_chunk = id_to_chunk[token.casefold()]
            elif token.isdigit() and int(token) in ordinal_to_chunk:
                resolved_chunk = ordinal_to_chunk[int(token)]
            else:
                for chunk_id, chunk in id_to_chunk.items():
                    if token and (token.casefold() in chunk_id or chunk_id in token.casefold()):
                        resolved_chunk = chunk
                        break

            entry: dict[str, Any] = {
                "marker": marker,
                "reference": token,
                "resolved": resolved_chunk is not None,
            }
            if resolved_chunk is not None:
                metadata = resolved_chunk.get("metadata")
                entry["chunk_id"] = str(resolved_chunk.get("id") or "")
                if isinstance(metadata, dict):
                    entry["source"] = str(
                        metadata.get("source") or metadata.get("source_site") or metadata.get("title") or ""
                    )
                    entry["knowledge_point"] = str(metadata.get("knowledge_point") or "")
            citations.append(entry)
    return citations


def validate_sources(
    content: str,
    source_chunks: list[dict[str, Any]],
    *,
    knowledge_point: str = "",
) -> tuple[list[dict[str, Any]], list[ValidationCheck], float]:
    """Check whether generated content is anchored in the retrieved evidence.

    Returns the resolved citations, the source-stage checks, and the fraction of
    usable retrieved chunks that the content actually cited.

    Three distinct outcomes are reported deliberately:

    * no retrieved chunks -> ``skipped`` / *insufficient_evidence*: the system
      must not claim a source it never had.
    * chunks retrieved but content cites a non-existent id -> *unsupported*:
      a fabricated citation is worse than no citation.
    * chunks retrieved and cited -> coverage is measured against real chunks.
    """

    chunks = [chunk for chunk in (source_chunks or []) if isinstance(chunk, dict)]
    checks: list[ValidationCheck] = []

    if not chunks:
        checks.append(
            _check(
                "sources_available",
                "source",
                False,
                "no knowledge chunk was retrieved for this request",
                skipped=True,
            )
        )
        return [], checks, 0.0

    checks.append(
        _check("sources_available", "source", True, f"{len(chunks)} retrieved chunk(s) available")
    )

    citations = extract_citations(content, chunks)
    unresolvable = [citation for citation in citations if not citation.get("resolved")]
    if citations:
        checks.append(
            _check(
                "sources_citations_resolve",
                "source",
                not unresolvable,
                "unresolvable citation markers: "
                + ", ".join(str(item["marker"]) for item in unresolvable[:5])
                if unresolvable
                else f"all {len(citations)} citation marker(s) resolve to retrieved chunks",
            )
        )
    else:
        checks.append(
            _check(
                "sources_citations_resolve",
                "source",
                False,
                "content carries no explicit citation marker",
                skipped=True,
            )
        )

    resolved_ids = {
        str(citation.get("chunk_id"))
        for citation in citations
        if citation.get("resolved") and citation.get("chunk_id")
    }
    available_ids = {str(chunk.get("id") or "") for chunk in chunks if chunk.get("id")}
    coverage = (len(resolved_ids) / len(available_ids)) if available_ids else 0.0

    topic_hits = 0
    if knowledge_point:
        normalized_point = re.sub(r"\s+", "", knowledge_point).casefold()
        for chunk in chunks:
            metadata = chunk.get("metadata") if isinstance(chunk.get("metadata"), dict) else {}
            haystack = re.sub(
                r"\s+",
                "",
                f"{chunk.get('content') or ''} {metadata.get('knowledge_point') or ''}",
            ).casefold()
            if normalized_point and normalized_point in haystack:
                topic_hits += 1
    if knowledge_point:
        checks.append(
            _check(
                "sources_cover_knowledge_point",
                "source",
                topic_hits > 0,
                f"{topic_hits}/{len(chunks)} chunk(s) mention the requested knowledge point"
                if topic_hits
                else "no retrieved chunk mentions the requested knowledge point",
            )
        )

    return citations, checks, coverage


def validate_generated_resource(
    *,
    resource_type: str,
    content: str = "",
    exercises: list[dict[str, Any]] | None = None,
    payload: dict[str, Any] | None = None,
    knowledge_point: str = "",
    source_chunks: list[dict[str, Any]] | None = None,
    title: str = "",
) -> dict[str, Any]:
    """Run structural then source validation and return a serializable report.

    ``resource_type`` selects the structural contract.  Unknown types are
    reported with a failing structural check rather than being silently treated
    as valid.
    """

    if resource_type == "exercise":
        report = validate_exercises(knowledge_point, exercises or [])
    elif resource_type == "mind_map":
        report = validate_mind_map(payload if payload is not None else content)
    elif resource_type == "code_case":
        report = validate_code_case(payload or {})
    elif resource_type == "video_script":
        report = validate_video_script(payload or {})
    elif resource_type in {"courseware", "notes", "exam"}:
        report = validate_courseware(knowledge_point, content, title)
    else:
        report = ValidationReport(resource_type=resource_type)
        report.checks.append(
            _check(
                "resource_type_known",
                "structure",
                False,
                f"no structural contract is registered for resource_type={resource_type!r}",
            )
        )
        report.notes.append(f"knowledge_point={knowledge_point}")
        return report.as_dict()

    citations, source_checks, coverage = validate_sources(
        content if resource_type != "exercise" else _flatten_exercises(exercises or []),
        source_chunks or [],
        knowledge_point=knowledge_point,
    )
    report.citations = citations
    report.checks.extend(source_checks)
    report.source_coverage = coverage
    return report.as_dict()


def _flatten_exercises(exercises: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for item in exercises:
        if not isinstance(item, dict):
            continue
        parts.append(str(item.get("prompt") or ""))
        parts.append(str(item.get("analysis") or ""))
    return "\n".join(parts)
