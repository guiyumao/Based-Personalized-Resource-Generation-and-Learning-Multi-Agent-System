"""ZhiShu seven-dimension profile adapter.

The scoring implementation lives in :mod:`common.profile_scoring` so the
user and agent services expose the same result.  This adapter keeps the
existing personalization call compatible while allowing richer answer
evidence to flow into the scorer.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from common.profile_scoring import (
    PROFILE_SCORING_ALGORITHM_VERSION,
    score_zhishu_profile,
)

MAPPING_ALGORITHM_VERSION = PROFILE_SCORING_ALGORITHM_VERSION


def build_zhishu_profile_view(
    *,
    learner_profile: dict[str, Any],
    mastery_score: int,
    answered_count: int,
    correct_rate: int,
    recent_mistakes: list[dict[str, Any]],
    records: Iterable[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a seven-dimension view from real evidence.

    ``records`` is optional only for compatibility with old callers. New
    callers should pass normalized answer records so every score has an
    evidence chain. The fallback keeps the old knowledge-base aggregate
    available without pretending it can support the other dimensions.
    """

    if records is not None:
        return score_zhishu_profile(
            learner_profile=learner_profile,
            records=records,
            explicit_mastery=mastery_score,
        )

    result = score_zhishu_profile(
        learner_profile=learner_profile,
        records=[],
        explicit_mastery=mastery_score if answered_count else None,
    )
    if answered_count:
        result["dimensions"]["knowledge_base"]["score"] = int(max(0, min(100, round(mastery_score))))
        result["dimensions"]["knowledge_base"]["value"] = result["dimensions"]["knowledge_base"]["score"]
        result["dimensions"]["knowledge_base"]["confidence"] = round(
            min(0.95, answered_count / (answered_count + 5)),
            3,
        )
        result["dimensions"]["knowledge_base"]["source"] = "behavior_inference"
        result["dimensions"]["knowledge_base"]["status"] = "sufficient" if answered_count >= 6 else "limited"
        result["dimensions"]["knowledge_base"]["sample_size"] = answered_count
        result["dimensions"]["knowledge_base"]["evidence_summary"] = (
            f"{answered_count} 次兼容聚合作答，近期正确率 {correct_rate}%，"
            f"近期错题 {len(recent_mistakes)} 条；新调用应传入原始答题记录以获得完整证据链。"
        )
    result["notes"].append("旧调用未提供原始答题记录，仅保留知识掌握聚合值；其余维度不会由聚合值推断。")
    return result
