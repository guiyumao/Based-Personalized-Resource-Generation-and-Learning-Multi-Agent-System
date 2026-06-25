"""Content audit agent — validates AI-generated output against user-requested topics."""

from __future__ import annotations

import json
from typing import Any

from common.config import Settings, get_settings
from services.agent_service.app.services.llm_factory import LLMFactory

AUDIT_SYSTEM_PROMPT = """你是教育内容审核员。检查 AI 生成的内容是否与用户指定的主题匹配。

审核标准（只在以下严重情况下 REJECT）：
1. **学科跑偏**：输出内容与用户需求完全不相符，例如用户要"算法"，结果给了"微积分"或完全不相关的内容。
2. **明显学术错误**：关键概念定义完全错误、因果关系颠倒。
3. **空内容/乱码**：输出为空、全是乱码、或无可读内容。

注意：以下情况应该 PASS：
- 中文编号格式（如"第1题"、"第X题"）是正常的题目格式，不是模板错误。
- 只要核心概念围绕用户指定的知识点，细微偏差不影响通过。
- 题目形式（选择题/填空题/判断题）只要可作答即可。

只回复一个 JSON：{"verdict": "PASS"|"REJECT", "reason": "一句话原因"}"""

AUDIT_TIMEOUT = 15  # seconds — keep it fast


class AuditService:
    """Validate generated content relevance and quality before returning to user."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def audit_exercises(
        self,
        knowledge_point: str,
        exercises: list[dict[str, Any]],
    ) -> tuple[bool, str]:
        """Check if generated exercises match the requested knowledge point.

        Returns (passed, reason).
        """
        if not exercises:
            return False, "exercises list is empty"

        # Build a concise summary for audit
        prompts = [str(e.get("prompt", ""))[:120] for e in exercises[:3]]
        answers = [str(e.get("answer", ""))[:80] for e in exercises[:3]]
        summary = (
            f"知识点：{knowledge_point}\n"
            f"题目：{' | '.join(prompts)}\n"
            f"答案：{' | '.join(answers)}"
        )
        return self._call_auditor(knowledge_point, summary)

    def audit_courseware(
        self,
        knowledge_point: str,
        content: str,
        title: str = "",
    ) -> tuple[bool, str]:
        """Check if generated courseware matches the requested knowledge point."""
        if not content or len(content) < 50:
            return False, "courseware content is too short"
        summary = f"标题：{title}\n内容摘要：{content[:800]}"
        return self._call_auditor(knowledge_point, summary)

    def _call_auditor(self, knowledge_point: str, content_summary: str) -> tuple[bool, str]:
        """Call the audit LLM and return (passed, reason)."""
        try:
            llm = LLMFactory(self.settings).build_chat_model(temperature=0.0)
            result = llm.invoke(
                [
                    {"role": "system", "content": AUDIT_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"用户请求的主题：{knowledge_point}\n\n"
                            f"AI 生成的内容：\n{content_summary[:1200]}"
                        ),
                    },
                ],
                timeout=AUDIT_TIMEOUT,
            )
            parsed = self._parse_audit_response(self._coerce_text(result.content))
            return parsed["verdict"] == "PASS", parsed.get("reason", "unknown")
        except Exception as exc:
            # Audit failed → let it through with a warning flag
            return True, f"audit_unavailable: {str(exc)[:60]}"

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
            return json.loads(cleaned)
        except json.JSONDecodeError:
            # Fallback: scan for verdict keywords
            if "PASS" in cleaned.upper():
                return {"verdict": "PASS", "reason": "keyword_match"}
            if "REJECT" in cleaned.upper():
                return {"verdict": "REJECT", "reason": f"keyword_match: {cleaned[:100]}"}
            return {"verdict": "PASS", "reason": "parse_fallback"}
