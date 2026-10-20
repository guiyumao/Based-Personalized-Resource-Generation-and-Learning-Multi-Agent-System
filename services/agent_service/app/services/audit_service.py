"""Rule-first content audit with conditional semantic review."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Literal

from common.config import Settings, get_settings
from common.performance import get_current_trace, traced_invoke
from services.agent_service.app.services.llm_factory import LLMFactory

AUDIT_SYSTEM_PROMPT = """你是教育内容审核员。检查生成内容是否与用户指定主题匹配。
只在以下严重情况 REJECT：学科完全跑偏、明显学术错误、严重逻辑冲突。
中文编号和正常的题目格式不是错误。
只回复 JSON：{"verdict":"PASS"|"REJECT","reason":"一句话原因"}。"""

AUDIT_TIMEOUT = 15
AuditStatus = Literal["passed", "rejected", "unavailable"]

#: Resource kinds whose structure is *not* courseware prose. Their structural
#: contract is enforced deterministically in ``content_validation`` (nodes/edges,
#: static code + run steps, scripted chapters), so the audit layer must not apply
#: the courseware section list to them: a mind map has no "学习目标" section and
#: would otherwise be rejected every single time.
STRUCTURED_RESOURCE_TYPES = frozenset({"mind_map", "code_case", "video_script"})


@dataclass(frozen=True)
class AuditDecision:
    passed: bool
    status: AuditStatus
    reason: str
    method: Literal["rule", "llm"]

    def __iter__(self) -> Iterator[Any]:
        """Keep existing ``passed, reason = decision`` callers compatible."""

        yield self.passed
        yield self.reason


class AuditService:
    """Validate structure in code and reserve LLM review for semantic ambiguity."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def audit_exercises(
        self,
        knowledge_point: str,
        exercises: list[dict[str, Any]],
        *,
        mode: str = "balanced",
    ) -> AuditDecision:
        started = time.perf_counter()
        if not exercises:
            return self._rule_decision(started, False, "exercises list is empty")

        required_fields = ("prompt", "answer", "analysis", "question_type", "difficulty")
        for index, exercise in enumerate(exercises, 1):
            missing = [field for field in required_fields if not str(exercise.get(field) or "").strip()]
            if missing:
                return self._rule_decision(
                    started, False, f"exercise {index} missing fields: {', '.join(missing)}"
                )
            if exercise.get("question_type") == "choice" and len(exercise.get("options") or []) < 2:
                return self._rule_decision(started, False, f"exercise {index} has insufficient options")

        prompts = [str(item.get("prompt", ""))[:160] for item in exercises[:5]]
        answers = [str(item.get("answer", ""))[:100] for item in exercises[:5]]
        summary = f"知识点：{knowledge_point}\n题目：{' | '.join(prompts)}\n答案：{' | '.join(answers)}"
        topic_matched = self._topic_matches(knowledge_point, summary)
        if topic_matched and mode != "quality":
            return self._rule_decision(started, True, "rule_audit_passed")
        self._record_rule_time(started)
        return self._call_auditor(knowledge_point, summary)

    def audit_courseware(
        self,
        knowledge_point: str,
        content: str,
        title: str = "",
        *,
        mode: str = "balanced",
    ) -> AuditDecision:
        started = time.perf_counter()
        stripped = content.strip()
        if len(stripped) < 80:
            return self._rule_decision(started, False, "courseware content is too short")
        lowered = stripped.lower()
        if any(marker in lowered[:300] for marker in ("error:", "traceback", "无法生成", "生成失败")):
            return self._rule_decision(started, False, "courseware contains generation failure text")

        heading_groups = (
            ("学习目标", "教学目标"),
            ("知识讲解", "核心概念", "核心定义"),
            ("示例", "例题", "案例"),
            ("小结", "总结"),
            ("自测", "练习"),
        )
        covered = sum(1 for group in heading_groups if any(item in stripped for item in group))
        if covered < 3:
            return self._rule_decision(started, False, "courseware required sections are incomplete")

        summary = f"标题：{title}\n内容摘要：{stripped[:1200]}"
        topic_matched = self._topic_matches(knowledge_point, f"{title}\n{stripped}")
        if topic_matched and mode != "quality":
            return self._rule_decision(started, True, "rule_audit_passed")
        self._record_rule_time(started)
        return self._call_auditor(knowledge_point, summary)

    def audit_structured_resource(
        self,
        knowledge_point: str,
        resource_type: str,
        content: str,
        title: str = "",
        *,
        mode: str = "balanced",
    ) -> AuditDecision:
        """Audit a structured resource against its *own* contract.

        ``audit_courseware`` demands the courseware section list ("学习目标",
        "知识讲解", "示例", "小结", "自测"). A mind map, a code case and a video
        script legitimately have none of those sections, so reusing that rule set
        rejected every structured resource the moment it was run for real — the
        stub-only tests never noticed. The deterministic structural contract for
        these kinds lives in ``content_validation`` (``mindmap_nodes_present``,
        ``code_case_*``, ``video_script_*``); this audit therefore only enforces
        what is genuinely generic: real content, no failure text, and topical
        relevance.
        """

        started = time.perf_counter()
        stripped = (content or "").strip()
        if resource_type not in STRUCTURED_RESOURCE_TYPES:
            return self._rule_decision(
                started, False, f"resource_type {resource_type!r} is not a structured kind"
            )
        if len(stripped) < 80:
            return self._rule_decision(started, False, "structured content is too short")

        lowered = stripped.lower()
        if any(marker in lowered[:300] for marker in ("error:", "traceback", "无法生成", "生成失败")):
            return self._rule_decision(
                started, False, "structured content contains generation failure text"
            )

        summary = f"标题：{title}\n内容摘要：{stripped[:1200]}"
        topic_matched = self._topic_matches(knowledge_point, f"{title}\n{stripped}")
        if topic_matched and mode != "quality":
            return self._rule_decision(started, True, "rule_audit_passed")
        self._record_rule_time(started)
        return self._call_auditor(knowledge_point, summary)

    def _rule_decision(self, started: float, passed: bool, reason: str) -> AuditDecision:
        self._record_rule_time(started)
        return AuditDecision(passed, "passed" if passed else "rejected", reason, "rule")
    def _record_rule_time(self, started: float) -> None:
        trace = get_current_trace()
        if trace is not None:
            trace.add_stage("audit", (time.perf_counter() - started) * 1000)

    def _topic_matches(self, knowledge_point: str, content: str) -> bool:
        topic = re.sub(r"\s+", "", knowledge_point).casefold()
        normalized_content = re.sub(r"\s+", "", content).casefold()
        if topic and topic in normalized_content:
            return True
        tokens = [
            token.casefold()
            for token in re.split(r"[^0-9A-Za-z_\u4e00-\u9fff]+", knowledge_point)
            if len(token.strip()) >= 2
        ]
        return bool(tokens) and any(token in content.casefold() for token in tokens)

    def _call_auditor(self, knowledge_point: str, content_summary: str) -> AuditDecision:
        try:
            llm = LLMFactory(self.settings).build_chat_model(temperature=0.0)
            result = traced_invoke(
                llm,
                [
                    {"role": "system", "content": AUDIT_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"用户请求的主题：{knowledge_point}\n\nAI 生成的内容：\n{content_summary[:1400]}",
                    },
                ],
                stage="audit",
                timeout=AUDIT_TIMEOUT,
            )
            parsed = self._parse_audit_response(self._coerce_text(result.content))
            passed = parsed["verdict"] == "PASS"
            return AuditDecision(
                passed=passed,
                status="passed" if passed else "rejected",
                reason=parsed.get("reason", "unknown"),
                method="llm",
            )
        except Exception as exc:
            return AuditDecision(True, "unavailable", f"audit_unavailable: {str(exc)[:100]}", "llm")

    def _coerce_text(self, content: Any) -> str:
        if isinstance(content, str):
            return content
        if hasattr(content, "content"):
            return str(content.content)
        return str(content)

    def _parse_audit_response(self, raw: str) -> dict[str, str]:
        cleaned = raw.strip()
        for prefix in ("```json", "```"):
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()
        try:
            payload = json.loads(cleaned)
            if isinstance(payload, dict):
                return {"verdict": str(payload.get("verdict", "PASS")).upper(), "reason": str(payload.get("reason", ""))}
        except json.JSONDecodeError:
            pass
        if "REJECT" in cleaned.upper():
            return {"verdict": "REJECT", "reason": f"keyword_match: {cleaned[:100]}"}
        return {"verdict": "PASS", "reason": "parse_fallback"}
