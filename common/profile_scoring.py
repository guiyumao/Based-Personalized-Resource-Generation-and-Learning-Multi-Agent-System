"""Evidence-based scoring for the seven-dimension ZhiShu profile.

The scores in this module are learning-behaviour proxies, not psychometric
measurements.  Every numeric result carries its evidence count, source,
confidence and algorithm version.  A dimension is left unscored when the
available evidence cannot support a defensible estimate.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime
from statistics import mean, pstdev
from typing import Any

ZHISHU_PROFILE_DIMENSIONS = (
    "comprehension",
    "memory",
    "application",
    "imagination",
    "attention",
    "knowledge_base",
    "learning_goal",
)

PROFILE_SCORING_ALGORITHM_VERSION = "zhishu-scoring-v3"
MIN_EVIDENCE_COUNT = 3
SUFFICIENT_EVIDENCE_COUNT = 6
RECENCY_HALF_LIFE_DAYS = 45
RECENCY_MAX_AGE_DAYS = 365
SOURCE_QUALITY_WEIGHTS = {
    "objective_or_rule": 1.0,
    "llm_scored": 0.85,
    "user_reported": 0.65,
    "unknown": 0.75,
}


def normalize_answer_row(answer_record: Any, exercise: Any) -> dict[str, Any]:
    """Convert ORM answer/exercise objects into the scorer's stable shape."""

    payload = _parse_json(getattr(exercise, "content", ""))
    evaluation = getattr(answer_record, "evaluation_json", {})
    if not isinstance(evaluation, dict):
        evaluation = {}
    created_at = getattr(answer_record, "created_at", None)
    return {
        "answer_record_id": getattr(answer_record, "id", None),
        "exercise_id": getattr(answer_record, "exercise_id", getattr(exercise, "id", None)),
        "knowledge_point": str(payload.get("knowledge_point") or getattr(exercise, "knowledge_point_id", "")),
        "question_type": str(payload.get("question_type") or getattr(exercise, "type", "")),
        "difficulty": getattr(exercise, "difficulty", 1),
        "prompt": str(payload.get("prompt") or ""),
        "user_answer": getattr(answer_record, "user_answer", ""),
        "is_correct": getattr(answer_record, "is_correct", None),
        "time_spent": getattr(answer_record, "time_spent", 0) or 0,
        "evaluation": evaluation,
        "evidence_source": _evidence_source(evaluation),
        "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else created_at,
    }


def score_zhishu_profile(
    *,
    learner_profile: dict[str, Any],
    records: Iterable[dict[str, Any]],
    explicit_mastery: int | float | None = None,
) -> dict[str, Any]:
    """Build an auditable seven-dimension profile from normalized evidence."""

    normalized_records = [record for record in records if isinstance(record, dict)]
    dimensions: dict[str, dict[str, Any]] = {
        dimension: _insufficient_dimension(normalized_records)
        for dimension in ZHISHU_PROFILE_DIMENSIONS
    }

    dimensions["knowledge_base"] = _score_outcome_dimension(
        normalized_records,
        label="知识掌握行为代理",
        interpretation="基于答题正确性、题目难度和近期记录的掌握代理，不代表稳定的能力测验分数。",
        fallback_score=explicit_mastery,
    )
    dimensions["comprehension"] = _score_outcome_dimension(
        _select(normalized_records, {"choice", "single_choice", "multiple_choice", "judge", "true_false", "fill", "blank", "short_answer"}),
        label="理解表现行为代理",
        interpretation="基于概念题、填空题和简答题表现的理解代理。",
    )
    dimensions["application"] = _score_outcome_dimension(
        [
            record
            for record in normalized_records
            if _question_type(record) in {"code", "programming", "project", "short_answer"}
            and _difficulty_number(record) >= 2
        ],
        label="应用表现行为代理",
        interpretation="基于中高难度代码、项目和简答任务表现的应用代理。",
    )
    dimensions["memory"] = _score_memory(normalized_records)
    dimensions["attention"] = _score_attention(normalized_records)
    dimensions["imagination"] = _score_imagination(normalized_records)
    dimensions["learning_goal"] = _score_goal(learner_profile)

    evidence_ids = [record.get("answer_record_id") for record in normalized_records if record.get("answer_record_id") is not None]
    return {
        "schema": "zhishu-seven-dimension-profile",
        "algorithm_version": PROFILE_SCORING_ALGORITHM_VERSION,
        "source_of_truth": "current_project.user_profiles_and_answer_records",
        "dimensions": dimensions,
        "evidence": {
            "answer_record_count": len(normalized_records),
            "answer_record_ids": evidence_ids[-100:],
        },
        "calculation": {
            "recency_half_life_days": RECENCY_HALF_LIFE_DAYS,
            "recency_max_age_days": RECENCY_MAX_AGE_DAYS,
            "minimum_evidence_count": MIN_EVIDENCE_COUNT,
            "sufficient_evidence_count": SUFFICIENT_EVIDENCE_COUNT,
            "confidence_semantics": "evidence_coverage_heuristic_not_calibrated_probability",
        },
        "next_evidence": {
            dimension: item.get("next_evidence", [])
            for dimension, item in dimensions.items()
            if item.get("status") == "insufficient"
        },
        "unmapped_current_fields": ["learning_style", "cognitive_abilities", "profile_analysis"],
        "notes": [
            "数值是学习行为代理，不是记忆力、想象力或注意力等心理测量结论。",
            "样本量不足或缺少相应证据时返回 insufficient_evidence，不生成猜测分数。",
        ],
    }


def _score_outcome_dimension(
    records: list[dict[str, Any]],
    *,
    label: str,
    interpretation: str,
    fallback_score: int | float | None = None,
) -> dict[str, Any]:
    evidence = [record for record in records if _outcome_score(record) is not None]
    if len(evidence) < MIN_EVIDENCE_COUNT:
        if fallback_score is not None and not evidence:
            score = _bounded_score(fallback_score)
            return _dimension(
                score=score,
                confidence=0.45,
                source="profile_explicit",
                status="limited",
                records=[],
                label=label,
                interpretation="沿用已保存的显式掌握度；没有足够的答题记录用于独立校验。",
            )
        return _insufficient_dimension(records, label=label, interpretation=interpretation)

    weighted_scores: list[tuple[float, float]] = []
    for record in evidence:
        outcome = _outcome_score(record)
        assert outcome is not None
        weight = _record_weight(record)
        weighted_scores.append((outcome, weight))
    score = round(sum(value * weight for value, weight in weighted_scores) / sum(weight for _, weight in weighted_scores))
    return _dimension(
        score=score,
        confidence=_confidence(len(evidence), evidence),
        source="behavior_inference",
        status=_status(len(evidence)),
        records=evidence,
        label=label,
        interpretation=interpretation,
    )


def _score_memory(records: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if record.get("exercise_id") is not None and _outcome_score(record) is not None:
            grouped[str(record["exercise_id"])].append(record)
    repeated = [item for items in grouped.values() if len(items) >= 2 for item in sorted(items, key=_record_order)[1:]]
    if len(repeated) < MIN_EVIDENCE_COUNT:
        return _insufficient_dimension(
            repeated,
            label="记忆保持行为代理",
            interpretation="只有同一题目的重复作答且有后续表现时，才估计保持代理；单次答题不能证明记忆力。",
        )
    return _dimension(
        score=round(_weighted_mean(repeated)),
        confidence=_confidence(len(repeated), repeated),
        source="behavior_inference",
        status=_status(len(repeated)),
        records=repeated,
        label="记忆保持行为代理",
        interpretation="基于重复作答后的后续正确表现，不等同于记忆力测验。",
    )


def _score_attention(records: list[dict[str, Any]]) -> dict[str, Any]:
    timed = [record for record in records if _positive_number(record.get("time_spent"))]
    if len(timed) < MIN_EVIDENCE_COUNT:
        return _insufficient_dimension(
            timed,
            label="持续作答行为代理",
            interpretation="需要至少三条带有效耗时的作答记录；该指标只能反映作答过程稳定性。",
        )
    times = [float(record["time_spent"]) for record in timed]
    stability = 1.0 if len(times) == 1 or mean(times) == 0 else max(0.0, min(1.0, 1.0 - (pstdev(times) / mean(times))))
    no_timeout = [record for record in timed if not _timed_out(record)]
    score = round((0.7 * (len(no_timeout) / len(timed)) + 0.3 * stability) * 100)
    return _dimension(
        score=score,
        confidence=_confidence(len(timed), timed),
        source="behavior_inference",
        status=_status(len(timed)),
        records=timed,
        label="持续作答行为代理",
        interpretation="基于有效耗时、超时标记和作答时长稳定性，不是临床或心理学注意力结论。",
    )


def _score_imagination(records: list[dict[str, Any]]) -> dict[str, Any]:
    evidence: list[dict[str, Any]] = []
    values: list[float] = []
    for record in records:
        if _question_type(record) not in {"short_answer", "code", "programming", "project"}:
            continue
        value = _creative_score(record.get("evaluation"))
        if value is not None:
            evidence.append(record)
            values.append(value)
    if len(evidence) < MIN_EVIDENCE_COUNT:
        return _insufficient_dimension(
            evidence,
            label="开放性表达行为代理",
            interpretation="需要可靠的开放题创意/多样性评分字段；答案长度或大模型描述本身不作为想象力分数。",
        )
    return _dimension(
        score=round(mean(values)),
        confidence=_confidence(len(evidence), evidence),
        source="behavior_inference",
        status=_status(len(evidence)),
        records=evidence,
        label="开放性表达行为代理",
        interpretation="基于已持久化的开放题评分字段，不等同于想象力测验。",
    )


def _score_goal(profile: dict[str, Any]) -> dict[str, Any]:
    dimensions = profile.get("profile_dimensions")
    dimensions = dimensions if isinstance(dimensions, dict) else {}
    goal = str(profile.get("goal_orientation") or dimensions.get("goalOrientation") or "").strip()
    if not goal:
        return _insufficient_dimension([], label="学习目标清晰度", interpretation="没有用户明确填写或对话提取的目标描述。")
    sources = profile.get("profile_fact_sources")
    sources = sources if isinstance(sources, dict) else {}
    metadata = sources.get("goalOrientation")
    source = metadata.get("source") if isinstance(metadata, dict) else "profile_fact_unclassified"
    confidence = {"user_declared": 0.9, "conversation_extracted": 0.7}.get(source, 0.5)
    score = min(100, 35 + len("".join(goal.split())) * 3)
    return {
        "value": goal,
        "score": score,
        "confidence": confidence,
        "status": "explicit" if source in {"user_declared", "conversation_extracted"} else "limited",
        "source": source,
        "evidence_window": "profile field",
        "sample_size": 1,
        "evidence_ids": [],
        "evidence_summary": "该分数只表示目标描述的完整度，不表示目标合理性、达成概率或学习能力。",
        "interpretation": "学习目标清晰度",
        "updated_at": metadata.get("updated_at") if isinstance(metadata, dict) else None,
    }


def _dimension(*, score: int, confidence: float, source: str, status: str, records: list[dict[str, Any]], label: str, interpretation: str) -> dict[str, Any]:
    return {
        "value": score,
        "score": score,
        "confidence": round(max(0.0, min(0.95, confidence)), 3),
        "status": status,
        "source": source,
        "evidence_window": _evidence_window(records),
        "sample_size": len(records),
        "evidence_ids": [record.get("answer_record_id") for record in records if record.get("answer_record_id") is not None][-20:],
        "evidence_summary": f"{len(records)} 条记录支持“{label}”；{interpretation}",
        "evidence_source_mix": _source_mix(records),
        "interpretation": interpretation,
        "next_evidence": [],
        "updated_at": _latest_timestamp(records),
    }


def _insufficient_dimension(records: list[dict[str, Any]], *, label: str = "该维度", interpretation: str = "当前数据不足以支持可靠推断。") -> dict[str, Any]:
    return {
        "value": None,
        "score": None,
        "confidence": 0.0,
        "status": "insufficient",
        "source": "insufficient_evidence",
        "evidence_window": _evidence_window(records),
        "sample_size": len(records),
        "evidence_ids": [record.get("answer_record_id") for record in records if record.get("answer_record_id") is not None][-20:],
        "evidence_summary": interpretation,
        "evidence_source_mix": _source_mix(records),
        "interpretation": interpretation,
        "next_evidence": _next_evidence_for(label),
        "updated_at": _latest_timestamp(records),
    }


def _select(records: list[dict[str, Any]], question_types: set[str]) -> list[dict[str, Any]]:
    return [record for record in records if _question_type(record) in question_types]


def _outcome_score(record: dict[str, Any]) -> float | None:
    evaluation = record.get("evaluation")
    if isinstance(evaluation, dict):
        ratio = evaluation.get("ratio")
        if isinstance(ratio, (int, float)) and math.isfinite(float(ratio)):
            return _bounded_score(float(ratio) * 100)
        score = evaluation.get("score")
        max_score = evaluation.get("max_score")
        if isinstance(score, (int, float)) and isinstance(max_score, (int, float)) and float(max_score) > 0:
            return _bounded_score(float(score) / float(max_score) * 100)
    result = record.get("is_correct")
    if isinstance(result, bool):
        return 100.0 if result else 0.0
    return None


def _creative_score(evaluation: Any) -> float | None:
    if not isinstance(evaluation, dict):
        return None
    keys = ("imagination_score", "creativity_score", "open_ended_score", "diversity_score")
    for key in keys:
        value = evaluation.get(key)
        if isinstance(value, (int, float)) and 0 <= float(value) <= 100:
            return float(value)
    rubric = evaluation.get("rubric")
    if isinstance(rubric, dict):
        for key in keys:
            value = rubric.get(key)
            if isinstance(value, (int, float)) and 0 <= float(value) <= 100:
                return float(value)
    return None


def _question_type(record: dict[str, Any]) -> str:
    return str(record.get("question_type") or "").strip().lower()


def _difficulty_number(record: dict[str, Any]) -> int:
    value = record.get("difficulty")
    if isinstance(value, (int, float)):
        return max(1, min(3, int(value)))
    return {"foundation": 1, "basic": 1, "intermediate": 2, "advanced": 3, "hard": 3}.get(str(value).lower(), 1)


def _confidence(count: int, records: list[dict[str, Any]] | None = None) -> float:
    """Estimate evidence coverage, explicitly not a calibrated probability."""

    confidence = 0.2 + 0.75 * min(1.0, count / 10.0)
    if records:
        confidence *= _recency_coverage(records)
        confidence *= _source_quality_coverage(records)
    return min(0.95, confidence)


def _status(count: int) -> str:
    return "sufficient" if count >= SUFFICIENT_EVIDENCE_COUNT else "limited"


def _bounded_score(value: int | float) -> int:
    return max(0, min(100, round(float(value))))


def _positive_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(float(value)) and float(value) > 0


def _record_weight(record: dict[str, Any]) -> float:
    difficulty_weight = 1.0 + (0.15 * max(0, _difficulty_number(record) - 1))
    source_weight = SOURCE_QUALITY_WEIGHTS.get(str(record.get("evidence_source") or "unknown"), 0.75)
    return _recency_weight(record) * source_weight * difficulty_weight


def _weighted_mean(records: list[dict[str, Any]]) -> float:
    pairs = [(_outcome_score(record), _record_weight(record)) for record in records]
    pairs = [(score, weight) for score, weight in pairs if score is not None]
    if not pairs:
        return 0.0
    return sum(score * weight for score, weight in pairs) / sum(weight for _, weight in pairs)


def _recency_weight(record: dict[str, Any]) -> float:
    timestamp = _parse_timestamp(record.get("created_at"))
    if timestamp is None:
        return 0.75
    age_days = max(0.0, (datetime.now(UTC) - timestamp).total_seconds() / 86_400)
    if age_days >= RECENCY_MAX_AGE_DAYS:
        return 0.05
    return max(0.05, 0.5 ** (age_days / RECENCY_HALF_LIFE_DAYS))


def _recency_coverage(records: list[dict[str, Any]]) -> float:
    if not records:
        return 0.0
    return sum(_recency_weight(record) for record in records) / len(records)


def _source_quality_coverage(records: list[dict[str, Any]]) -> float:
    if not records:
        return 0.0
    return sum(
        SOURCE_QUALITY_WEIGHTS.get(str(record.get("evidence_source") or "unknown"), 0.75)
        for record in records
    ) / len(records)


def _source_mix(records: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        source = str(record.get("evidence_source") or "unknown")
        counts[source] = counts.get(source, 0) + 1
    return counts


def _evidence_source(evaluation: dict[str, Any]) -> str:
    if evaluation.get("llm_used"):
        return "llm_scored"
    if any(isinstance(evaluation.get(key), (int, float)) for key in ("ratio", "score", "max_score")):
        return "objective_or_rule"
    return "unknown"


def _parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        timestamp = value
    elif isinstance(value, str):
        try:
            timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=UTC)
    return timestamp.astimezone(UTC)


def _next_evidence_for(label: str) -> list[str]:
    if "记忆" in label:
        return ["对同一知识点安排至少 3 次间隔重复作答，并保留每次答题时间。"]
    if "开放" in label or "想象" in label:
        return ["增加开放题，并持久化创意性、方案多样性等 rubric 分项评分。"]
    if "持续" in label or "作答" in label:
        return ["积累至少 3 条带有效耗时的连续作答记录，并记录超时状态。"]
    if "目标" in label:
        return ["由用户明确填写学习目标，或在对话中确认提取结果。"]
    if "应用" in label:
        return ["积累至少 3 条中高难度代码、项目或综合题记录。"]
    if "理解" in label:
        return ["积累至少 3 条概念题、填空题或简答题评分记录。"]
    return ["继续积累至少 3 条可判分的真实答题记录。"]


def _timed_out(record: dict[str, Any]) -> bool:
    evaluation = record.get("evaluation")
    return isinstance(evaluation, dict) and bool(evaluation.get("timed_out") or evaluation.get("is_timeout"))


def _record_order(record: dict[str, Any]) -> tuple[str, str]:
    return (str(record.get("created_at") or ""), str(record.get("answer_record_id") or ""))


def _evidence_window(records: list[dict[str, Any]]) -> str:
    timestamps = sorted(str(record.get("created_at")) for record in records if record.get("created_at"))
    if not timestamps:
        return "answer records"
    return timestamps[0] if timestamps[0] == timestamps[-1] else f"{timestamps[0]} to {timestamps[-1]}"


def _latest_timestamp(records: list[dict[str, Any]]) -> str | None:
    timestamps = [str(record.get("created_at")) for record in records if record.get("created_at")]
    return max(timestamps) if timestamps else None


def _parse_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (TypeError, ValueError):
            return {}
    return {}
