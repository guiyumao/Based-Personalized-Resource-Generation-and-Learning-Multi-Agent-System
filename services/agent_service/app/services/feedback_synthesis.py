"""Feedback Synthesis Service — LLM-powered cross-agent feedback generation.

This service consumes outputs from all upstream agents (learner profiling,
knowledge graph, knowledge base, learning path, resource generation, exercise
generation, QA, and evaluation) and produces a unified, personalized Chinese
feedback report via LLM synthesis.

It follows the same ChatPromptTemplate + LLMFactory + StrOutputParser pattern
used by ResourceGenerationService and ExerciseGenerationService.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser

from common.config import get_settings
from services.agent_service.app.services.llm_factory import LLMFactory

logger = logging.getLogger(__name__)

_PROMPT_FILENAME = "evaluation_feedback.md"
_MAX_CONTEXT_CHARS = 5000


@lru_cache(maxsize=1)
def _load_prompt_template(filename: str) -> str:
    prompt_path = Path("prompts") / filename
    return prompt_path.read_text(encoding="utf-8")


def _truncate(text: str, max_chars: int = 300) -> str:
    """Truncate text to max_chars, adding ellipsis if cut."""
    if not text:
        return ""
    stripped = text.strip()
    if len(stripped) <= max_chars:
        return stripped
    return stripped[:max_chars] + "…"


def _safe_str(value: Any) -> str:
    """Coerce any value to a non-empty string or return a placeholder."""
    if value is None:
        return ""
    text = str(value).strip()
    return text


class FeedbackSynthesisService:
    """Generate unified LLM feedback by cross-referencing all agent outputs."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.llm_factory = LLMFactory(self.settings)
        self.prompt_template = _load_prompt_template(_PROMPT_FILENAME)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def synthesize_from_agents(
        self,
        *,
        knowledge_point: str,
        learner_profile: dict[str, Any],
        all_agent_outputs: dict[str, Any],
        evaluation_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Main entry point.

        Args:
            knowledge_point: The knowledge point being studied.
            learner_profile: Learner profile dict from PersonalizationService.
            all_agent_outputs: Dict of ``{agent_name: {status, ...}}`` from the
                coordinator's ``_execute_agents``.
            evaluation_data: Dict with keys ``suggestions``, ``profile_snapshot``,
                ``mistake_statistics`` (and optionally ``stage_report``,
                ``comprehensive_report``) from ``ReportService``.

        Returns:
            A dict matching the ``FeedbackSynthesisOutput`` schema, plus a
            ``generated_at`` ISO timestamp.
        """
        synthesis_context = self._build_synthesis_context(
            knowledge_point=knowledge_point,
            learner_profile=learner_profile,
            all_agent_outputs=all_agent_outputs,
            evaluation_data=evaluation_data,
        )

        raw_output = self._invoke_llm({"synthesis_context": synthesis_context})
        parsed = self._parse_synthesis_output(raw_output)
        parsed["generated_at"] = datetime.now(UTC).isoformat()
        return parsed

    def build_fallback(
        self,
        *,
        knowledge_point: str,
        evaluation_data: dict[str, Any],
        error_message: str,
    ) -> dict[str, Any]:
        """Generate data-only fallback feedback when LLM synthesis fails."""
        suggestions = evaluation_data.get("suggestions", {})
        if isinstance(suggestions, dict):
            suggestion_texts = suggestions.get("suggestions", [])
            focus_areas = suggestions.get("focus_areas", [])
            recommended_action = suggestions.get("recommended_action", "")
        else:
            suggestion_texts = []
            focus_areas = []
            recommended_action = ""

        snapshot = evaluation_data.get("profile_snapshot", {})
        if isinstance(snapshot, dict):
            mastery = snapshot.get("mastery_overview", 0)
            habit = snapshot.get("habit_summary", "")
        else:
            mastery = 0
            habit = ""

        mistake_stats = evaluation_data.get("mistake_statistics", {})
        mistake_count = mistake_stats.get("mistake_count", 0) if isinstance(mistake_stats, dict) else 0

        return {
            "overall_assessment": "",
            "core_strengths": [],
            "improvement_areas": [],
            "personalized_feedback": error_message[:300],
            "next_step_plan": {
                "immediate_actions": [],
                "this_week_focus": [knowledge_point] if knowledge_point else [],
                "recommended_resources": [],
            },
            "agent_synthesis_summary": error_message[:200],
            "learning_insight": "",
            "generated_at": datetime.now(UTC).isoformat(),
        }

    # ------------------------------------------------------------------
    # Synthesis context builder
    # ------------------------------------------------------------------

    def _build_synthesis_context(
        self,
        *,
        knowledge_point: str,
        learner_profile: dict[str, Any],
        all_agent_outputs: dict[str, Any],
        evaluation_data: dict[str, Any],
    ) -> str:
        sections: list[str] = []

        sections.append(self._format_profile_section(learner_profile, knowledge_point))
        sections.append(self._format_evaluation_section(evaluation_data))

        agent_formatters: dict[str, Any] = {
            "knowledge_graph_agent": self._format_graph_section,
            "knowledge_base_agent": self._format_kb_section,
            "path_planning_agent": self._format_path_section,
            "resource_generation_agent": self._format_resource_section,
            "exercise_generation_agent": self._format_exercise_section,
            "qa_agent": self._format_qa_section,
        }

        for agent_name, formatter in agent_formatters.items():
            agent_output = all_agent_outputs.get(agent_name, {})
            if isinstance(agent_output, dict) and agent_output.get("status") == "completed":
                sections.append(formatter(agent_output))
            else:
                sections.append(f"## {agent_name}\n状态：未运行或执行失败\n")

        context = "\n\n".join(sections)
        if len(context) > _MAX_CONTEXT_CHARS:
            context = context[:_MAX_CONTEXT_CHARS]
        return context

    # ------------------------------------------------------------------
    # Per-agent section formatters
    # ------------------------------------------------------------------

    def _format_profile_section(self, learner_profile: dict[str, Any], knowledge_point: str) -> str:
        dims = learner_profile.get("profile_dimensions", {})
        summaries = learner_profile.get("profile_analysis_summaries", {})
        lines = [
            "## 学习者画像",
            f"- 当前知识点：{knowledge_point or '未指定'}",
            f"- 学习风格：{_safe_str(learner_profile.get('learning_style', '')) or '未知'}",
            f"- 兴趣方向：{_safe_str(learner_profile.get('interest_direction', '')) or '未知'}",
            f"- 目标导向：{_safe_str(learner_profile.get('goal_orientation', '')) or '未知'}",
            f"- 学习速度：{_safe_str(learner_profile.get('learning_speed', '')) or '未知'}",
            f"- 薄弱题型：{', '.join(learner_profile.get('weak_question_types', [])) or '暂无'}",
            f"- 偏好资源形式：{', '.join(learner_profile.get('preferred_resource_modes', [])) or '暂无'}",
        ]
        if isinstance(dims, dict):
            for key in ("knowledgeBase", "cognitiveStyle", "errorPreference", "learningPace", "interestDirection", "goalOrientation"):
                value = _safe_str(dims.get(key, ""))
                if value:
                    lines.append(f"- 画像维度-{key}：{value}")
        if isinstance(summaries, dict):
            for key, value in summaries.items():
                text = _safe_str(value)
                if text:
                    lines.append(f"- 画像摘要-{key}：{text}")
        return "\n".join(lines)

    def _format_evaluation_section(self, evaluation_data: dict[str, Any]) -> str:
        suggestions = evaluation_data.get("suggestions", {})
        if isinstance(suggestions, dict):
            suggestion_texts = suggestions.get("suggestions", [])
            focus = suggestions.get("focus_areas", [])
            action = suggestions.get("recommended_action", "")
        else:
            suggestion_texts = []
            focus = []
            action = ""

        snapshot = evaluation_data.get("profile_snapshot", {})
        if isinstance(snapshot, dict):
            mastery = snapshot.get("mastery_overview", 0)
            habit = snapshot.get("habit_summary", "")
            heatmap = snapshot.get("heatmap", [])
            radar = snapshot.get("radar_metrics", [])
        else:
            mastery = 0
            habit = ""
            heatmap = []
            radar = []

        mistake_stats = evaluation_data.get("mistake_statistics", {})
        mistake_count = mistake_stats.get("mistake_count", 0) if isinstance(mistake_stats, dict) else 0

        lines = [
            "## 评估数据",
            f"- 综合掌握度：{mastery:.1f}%" if mastery else "" if mastery else "- 综合掌握度：暂无数据",
            f"- 错题总数：{mistake_count}",
            f"- 学习概况：{habit or '暂无'}",
        ]
        if radar:
            radar_text = "，".join(
                f"{item.get('dimension', '')} {item.get('score', 0)}分"
                for item in radar[:5]
                if isinstance(item, dict)
            )
            lines.append(f"- 能力雷达：{radar_text}")
        if heatmap:
            top_hot = heatmap[:5] if isinstance(heatmap, list) else []
            hot_text = "，".join(
                f"{item.get('knowledge_point', '')}: {item.get('mastery', 0):.0f}%"
                for item in top_hot
                if isinstance(item, dict)
            )
            if hot_text:
                lines.append(f"- 知识点掌握热力(Top5)：{hot_text}")
        if focus:
            lines.append(f"- 需重点加强：{'、'.join(focus[:5])}")
        if suggestion_texts:
            lines.append(f"- 数据建议：{'；'.join(suggestion_texts[:3])}")
        if action:
            lines.append(f"- 推荐动作：{action}")
        return "\n".join(lines)

    def _format_graph_section(self, output: dict[str, Any]) -> str:
        deps = output.get("dependencies", [])
        related = output.get("related_resources", [])
        lines = ["## 知识图谱"]
        if deps:
            lines.append(f"- 依赖路径：{_truncate(str(deps), 400)}")
        if related:
            lines.append(f"- 关联资源：{_truncate(str(related), 300)}")
        if not deps and not related:
            lines.append("- 无额外图谱数据")
        return "\n".join(lines)

    def _format_kb_section(self, output: dict[str, Any]) -> str:
        items = output.get("items", [])
        if not items:
            return "## 知识库\n- 未匹配到相关知识点文章"
        lines = ["## 知识库"]
        for item in items[:3]:
            if isinstance(item, dict):
                title = item.get("title", "")
                summary = _truncate(item.get("summary", ""), 120)
                concepts = item.get("concepts", [])
                mistakes = item.get("mistakes", [])
                lines.append(f"- 文章：{title}")
                if summary:
                    lines.append(f"  摘要：{summary}")
                if concepts:
                    lines.append(f"  核心概念：{'、'.join(concepts[:3])}")
                if mistakes:
                    lines.append(f"  易错点：{'、'.join(mistakes[:2])}")
        return "\n".join(lines)

    def _format_path_section(self, output: dict[str, Any]) -> str:
        path = output.get("learning_path", {})
        if not isinstance(path, dict):
            return "## 学习路径\n- 未生成学习路径"
        stages = path.get("stages", [])
        lines = [
            "## 学习路径",
            f"- 预计天数：{path.get('estimated_days', '未知')}",
            f"- 概述：{_safe_str(path.get('overview', '')) or '暂无'}",
        ]
        for stage in (stages if isinstance(stages, list) else [])[:3]:
            if isinstance(stage, dict):
                lines.append(f"- 阶段：{stage.get('title', '')} — {_truncate(stage.get('description', ''), 100)}")
                tasks = stage.get("tasks", [])
                for task in (tasks if isinstance(tasks, list) else [])[:2]:
                    if isinstance(task, dict):
                        lines.append(f"  任务：{task.get('title', '')} ({task.get('task_type', '')}, {task.get('difficulty', '')})")
        return "\n".join(lines)

    def _format_resource_section(self, output: dict[str, Any]) -> str:
        resource = output.get("resource", {})
        if not isinstance(resource, dict):
            return "## 资源生成\n- 未生成课件"
        plan = resource.get("generation_plan", {})
        lines = [
            "## 资源生成",
            f"- 标题：{_safe_str(plan.get('title_suggestion', '')) or resource.get('knowledge_point', '') or '未命名'}",
            f"- 类型：{resource.get('resource_type', '')}",
            f"- 风格：{resource.get('resource_style', '')}",
            f"- 难度：{plan.get('difficulty', '')}",
        ]
        hints = plan.get("personalization_hints", [])
        if hints:
            lines.append(f"- 个性化依据：{'；'.join(hints[:3])}")
        return "\n".join(lines)

    def _format_exercise_section(self, output: dict[str, Any]) -> str:
        ex_set = output.get("exercise_set", {})
        if not isinstance(ex_set, dict):
            return "## 习题生成\n- 未生成习题"
        exercises = ex_set.get("exercises", [])
        lines = [
            "## 习题生成",
            f"- 生成数量：{len(exercises) if isinstance(exercises, list) else 0}",
            f"- 摘要：{_safe_str(ex_set.get('summary', '')) or '暂无'}",
        ]
        if isinstance(exercises, list):
            type_dist: dict[str, int] = {}
            for ex in exercises:
                if isinstance(ex, dict):
                    t = ex.get("question_type", "unknown")
                    type_dist[t] = type_dist.get(t, 0) + 1
            if type_dist:
                dist_text = "，".join(f"{k} {v}道" for k, v in type_dist.items())
                lines.append(f"- 题型分布：{dist_text}")
        return "\n".join(lines)

    def _format_qa_section(self, output: dict[str, Any]) -> str:
        qa = output.get("qa", {})
        if not isinstance(qa, dict):
            return "## 答疑分析\n- 无问答数据"
        analysis = qa.get("structured_analysis", {})
        if not isinstance(analysis, dict):
            analysis = {}
        lines = [
            "## 答疑分析",
            f"- 识别知识缺口：{'、'.join(analysis.get('identified_knowledge_gaps', [])) or '无'}",
            f"- 误解点：{'、'.join(analysis.get('misconceptions', [])) or '无'}",
            f"- 难度评估：{analysis.get('difficulty_level', '')}",
            f"- 推荐下一步知识点：{'、'.join(analysis.get('recommended_next_knowledge_points', [])) or '无'}",
            f"- 学习建议：{'；'.join(analysis.get('study_suggestions', [])) or '无'}",
        ]
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # LLM invocation
    # ------------------------------------------------------------------

    def _invoke_llm(self, variables: dict[str, Any]) -> str:
        try:
            llm = self.llm_factory.build_chat_model(temperature=0.4)
            messages = [
                SystemMessage(content=self.prompt_template),
                HumanMessage(content=variables["synthesis_context"]),
            ]
            chain = llm | StrOutputParser()
            return chain.invoke(messages)
        except Exception:
            logger.exception("LLM synthesis invocation failed")
            raise

    # ------------------------------------------------------------------
    # Output parsing
    # ------------------------------------------------------------------

    def _parse_synthesis_output(self, raw_text: str) -> dict[str, Any]:
        cleaned = raw_text.strip()

        # Level 1: JSON inside ```json / ``` fence
        fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
        if fence_match:
            try:
                return json.loads(fence_match.group(1))
            except json.JSONDecodeError:
                pass

        # Level 2: Any outermost { ... } JSON object
        brace_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass

        # Level 3: Raw text fallback — wrap as personalized_feedback
        return self._raw_text_to_feedback(cleaned)

    def _raw_text_to_feedback(self, text: str) -> dict[str, Any]:
        """Convert unstructured LLM text into a minimal valid feedback dict."""
        return {
            "overall_assessment": _truncate(text, 300),
            "core_strengths": [],
            "improvement_areas": [],
            "personalized_feedback": text[:600],
            "next_step_plan": {
                "immediate_actions": [],
                "this_week_focus": [],
                "recommended_resources": [],
            },
            "agent_synthesis_summary": "LLM 返回了非结构化文本，已作为个性化反馈展示。",
            "learning_insight": _truncate(text.split("。")[0] + "。", 120) if "。" in text else _truncate(text, 120),
        }
