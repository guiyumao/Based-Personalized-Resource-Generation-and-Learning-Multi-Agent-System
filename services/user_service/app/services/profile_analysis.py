"""AI-powered deep profile analysis — one-shot per cache window.

Architecture:
  Profile data + behaviour → Analysis Agent (single LLM call, ~2000-3000 chars)
  Result cached in DB; regenerated on-demand or when stale (>2h since last gen
  AND profile dimensions changed) or force-refreshed (>24h).
"""

from __future__ import annotations

import json
import re
import threading
import time
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from common.config import get_settings
from common.models.learning import UserProfile
from services.agent_service.app.services.llm_factory import LLMFactory
from services.user_service.app.services.profile_builder import (
    PROFILE_DIMENSION_KEYS,
    PROFILE_DIMENSION_LABELS,
)

# ── In-memory async task tracker ─────────────────────────────────

_analysis_tasks: dict[int, dict[str, Any]] = {}
_TASK_LOCK = threading.Lock()

COOLDOWN_HOURS = 2
FORCE_REFRESH_HOURS = 24

# ── Prompt ───────────────────────────────────────────────────────

ANALYSIS_PROMPT = """你是一个资深的教育心理学家和学习顾问。你的任务是根据学生的
学习画像数据和最近学习行为，撰写一份深度、个性化的学习画像分析报告。

## 输入数据

你会收到：
1. profile_dimensions：六大维度已经填写的值
2. learning_style：学生的学习风格
3. behavior_summary：最近的学习行为摘要（答题数、正确率、学习时长等）
4. habit_summary：画像中记录的学习习惯

## 输出要求

为以下六个维度各撰写一段分析（每段 150-350 字），合并为一个自然流畅的报告：

### knowledgeBase（知识基础分析）
- 学生已经掌握了什么，程度如何
- 哪些领域是空白或薄弱
- 基于学生的目标和现有基础，指出"会"和"不会"之间的缺口
- 如果数据不足，诚实地说"目前这方面的数据还不够充分"

### cognitiveStyle（认知风格分析）
- 学生的学习偏好是什么（视觉/文本/听觉/动手）
- 这种风格在学生想学的领域中有什么优势和挑战
- 应该如何利用这种风格提高学习效率

### errorPreference（易错偏好分析）
- 学生容易在哪些类型的题目或知识点上出错
- 这些错误的根本可能原因是什么（概念不清 / 粗心 / 方法不对）
- 针对性地给出改善建议

### learningSpeed（学习节奏分析）
- 学生的学习节奏快慢
- 当前节奏是否匹配学生的学习目标和现有基础
- 如果太快可能导致基础不牢，太慢可能导致失去动力

### interestDirection（兴趣方向分析）
- 学生对哪些领域有明确的兴趣
- 这些兴趣之间有什么关联
- 结合职业目标，这个兴趣方向的发展前景如何

### goalOrientation（目标导向分析）
- 学生的学习目标是什么（求职/考试/项目/兴趣）
- 这个目标在当前阶段是否合理
- 实现这个目标需要补充哪些关键能力

## 写作风格

- 像一位有经验的导师在给学生写个性化学习建议，既专业又亲切
- 不要空洞的赞美，用具体的事实和数据支撑分析
- 如果某个维度数据不足，不要编造——直接说"还需要更多练习数据才能做出准确分析"
- 当你指出学生的薄弱点时，同时给出可操作的改进建议

## Markdown 排版

每个维度 150-350 字（字数仅统计正文，不含 Markdown 标记符）。
使用以下语法增强可读性：
- `**粗体**` 强调关键结论，`*斜体*` 标注次要信息
- `### 小标题` 拆分段落（2-3 段）
- `- 列表` 列出建议或步骤
- `` `代码` `` 标注技术术语

## 输出格式

严格返回 JSON，不要任何额外文字：
{
  "knowledgeBase": "分析文本（150-350字）",
  "cognitiveStyle": "分析文本（150-350字）",
  "errorPreference": "分析文本（150-350字）",
  "learningSpeed": "分析文本（150-350字）",
  "interestDirection": "分析文本（150-350字）",
  "goalOrientation": "分析文本（150-350字）",
  "summaries": {
    "knowledgeBase": "一句话评价（≤15字），如'Python扎实，但缺独立拆解能力'",
    "cognitiveStyle": "一句话评价（≤15字），如'动手实践型，适合项目驱动学习'",
    "errorPreference": "一句话评价（≤15字）",
    "learningSpeed": "一句话评价（≤15字）",
    "interestDirection": "一句话评价（≤15字）",
    "goalOrientation": "一句话评价（≤15字）"
  }
}

summaries 的写法：用"优势 + 但 + 不足"或"风格 + 建议"的句式，让读者一眼看懂。例如：
- knowledgeBase: "Python熟练，Java有基础，LangChain薄弱"
- cognitiveStyle: "动手实践型，缺少理论梳理"
- errorPreference: "卡在环境配置，非逻辑问题"
- learningSpeed: "学新快，但需防基础跳步"
- interestDirection: "聚焦AI开发，方向明确"
- goalOrientation: "求职导向，需补项目经验"

每个 summary 严格 ≤ 15 个汉字。"""


class ProfileAnalysisService:
    """Generate and cache deep-profile analysis reports."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()

    # ── Public API ──────────────────────────────────────────────

    def get_or_generate(
        self,
        user_id: int,
        profile_dimensions: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Return cached analysis, or launch async generation if stale/absent."""
        profile = self.db.get(UserProfile, user_id)
        if profile is None:
            raise ValueError("Profile not found")

        cached = profile.profile_analysis
        now = datetime.now(timezone.utc)

        # ── Check if cached result is still valid ──
        if cached and isinstance(cached, dict) and cached.get("generated_at"):
            gen_time = self._parse_time(cached["generated_at"])
            age = now - gen_time if gen_time else timedelta(hours=999)
            is_stale = cached.get("stale", False)

            if age < timedelta(hours=FORCE_REFRESH_HOURS):
                if not is_stale or age < timedelta(hours=COOLDOWN_HOURS):
                    return {"status": "completed", "analysis": self._format_analysis(cached)}

        # ── Start generation if not already running ──
        with _TASK_LOCK:
            existing = _analysis_tasks.get(user_id)
            if existing and existing.get("status") == "processing":
                return {
                    "status": "processing",
                    "progress": existing.get("progress", 0),
                    "current": existing.get("current", ""),
                }

            dims = profile_dimensions or self._read_profile_dimensions(profile)
            _analysis_tasks[user_id] = {
                "status": "processing",
                "progress": 0,
                "current": "准备分析数据…",
            }

        # Background thread
        thread = threading.Thread(
            target=self._run_analysis, args=(user_id, profile, dims), daemon=True
        )
        thread.start()

        return {"status": "processing", "progress": 0, "current": "准备分析数据…"}

    def get_status(self, user_id: int) -> dict[str, Any]:
        """Return current analysis status (polling endpoint)."""
        with _TASK_LOCK:
            task = _analysis_tasks.get(user_id)
            if task:
                return dict(task)

        # Check DB for completed
        profile = self.db.get(UserProfile, user_id)
        if profile and profile.profile_analysis:
            cached = profile.profile_analysis
            if isinstance(cached, dict):
                return {"status": "completed", "analysis": self._format_analysis(cached)}

        return {"status": "idle"}

    def mark_stale(self, user_id: int) -> None:
        """Mark cached analysis as stale (called when profile changes)."""
        profile = self.db.get(UserProfile, user_id)
        if not profile or not profile.profile_analysis:
            return
        cached = profile.profile_analysis
        if isinstance(cached, dict):
            cached["stale"] = True
            profile.profile_analysis = cached
            self.db.commit()

    def force_refresh(self, user_id: int) -> dict[str, Any]:
        """Force regeneration regardless of cache state."""
        profile = self.db.get(UserProfile, user_id)
        if profile is None:
            raise ValueError("Profile not found")

        # Clear cache so get_or_generate doesn't short-circuit
        if profile.profile_analysis:
            profile.profile_analysis = None
            self.db.commit()

        return self.get_or_generate(user_id)

    # ── Internal ────────────────────────────────────────────────

    def _run_analysis(self, user_id: int, profile: UserProfile, dims: dict[str, str]) -> None:
        """Run the LLM analysis in a background thread, update DB on completion."""
        try:
            self._update_task(user_id, progress=10, current="正在分析知识基础…")
            behavior = self._gather_behavior(user_id)
            habits = profile.habits if isinstance(profile.habits, dict) else {}

            # Build a rich prompt context
            context_parts = [
                "## 学生画像维度",
                *[
                    f"- {PROFILE_DIMENSION_LABELS.get(k, k)}：{v}"
                    for k, v in dims.items() if v
                ],
                "",
                "## 学习风格",
                f"编码：{profile.learning_style or '未知'}",
                f"认知能力记录：{json.dumps(profile.cognitive_abilities or {}, ensure_ascii=False)}",
                "",
                "## 学习行为摘要",
                f"总答题数：{behavior.get('total_answers', 0)}",
                f"正确率：{behavior.get('accuracy', 'N/A')}",
                f"最近学习时长：{behavior.get('recent_minutes', 0)} 分钟",
                f"错题分布：{json.dumps(behavior.get('mistake_distribution', {}), ensure_ascii=False)}",
                "",
                "## 习惯记录",
                json.dumps(habits, ensure_ascii=False),
            ]
            context = "\n".join(context_parts)

            self._update_task(user_id, progress=25, current="正在调用分析模型…")

            from langchain_core.messages import HumanMessage, SystemMessage

            model = LLMFactory(self.settings).build_chat_model(temperature=0.5)
            result = model.invoke([
                SystemMessage(content=ANALYSIS_PROMPT),
                HumanMessage(content=context),
            ])

            self._update_task(user_id, progress=80, current="正在保存分析结果…")

            parsed = self._parse_json(self._coerce_text(result.content))
            if parsed is None:
                self._update_task(user_id, status="failed", error="LLM 输出解析失败")
                return

            # Validate all 6 dimensions present
            for key in PROFILE_DIMENSION_KEYS:
                if key not in parsed:
                    parsed[key] = "数据不足，暂时无法提供该维度的深度分析。"

            now = datetime.now(timezone.utc)
            analysis_doc = {
                **parsed,
                "generated_at": now.isoformat(),
                "model": self.settings.deepseek_model or self.settings.openai_model,
                "stale": False,
                "profile_snapshot": dims,
            }

            # Write to DB — use a fresh session (background thread)
            from common.db.session import SessionLocal
            fresh_db = SessionLocal()
            try:
                p = fresh_db.get(UserProfile, user_id)
                if p is not None:
                    p.profile_analysis = analysis_doc
                    fresh_db.commit()
            finally:
                fresh_db.close()

            self._update_task(user_id, status="completed", analysis=self._format_analysis(analysis_doc))

        except Exception as exc:
            self._update_task(user_id, status="failed", error=str(exc)[:200])

    def _gather_behavior(self, user_id: int) -> dict[str, Any]:
        """Collect learning behaviour from evaluation-service if available."""
        try:
            import httpx
            r = httpx.get(
                f"{self.settings.evaluation_service_url}/evaluation/profiles/{user_id}/snapshot",
                timeout=5.0,
            )
            if r.status_code == 200:
                data = (r.json().get("data") or {})
                if isinstance(data, dict):
                    return {
                        "total_answers": data.get("total_answers", 0),
                        "accuracy": data.get("accuracy", 0),
                        "recent_minutes": data.get("recent_minutes", 0),
                        "mistake_distribution": data.get("mistake_distribution", {}),
                    }
        except Exception:
            pass
        return {}

    def _read_profile_dimensions(self, profile: UserProfile) -> dict[str, str]:
        habits = profile.habits if isinstance(profile.habits, dict) else {}
        raw = habits.get("profile_dimensions")
        if not isinstance(raw, dict):
            return {}
        return {
            k: str(v).strip()
            for k, v in raw.items()
            if k in PROFILE_DIMENSION_KEYS and str(v).strip()
        }

    def _format_analysis(self, cached: dict[str, Any]) -> dict[str, Any]:
        result = {k: cached.get(k, "") for k in [*PROFILE_DIMENSION_KEYS, "generated_at", "model"]}
        if cached.get("summaries") and isinstance(cached["summaries"], dict):
            result["summaries"] = cached["summaries"]
        return result

    def _update_task(self, user_id: int, **kwargs: Any) -> None:
        with _TASK_LOCK:
            task = _analysis_tasks.get(user_id, {})
            task.update(kwargs)
            _analysis_tasks[user_id] = task

    def _parse_json(self, text: str) -> dict[str, Any] | None:
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
            text = re.sub(r"```$", "", text).strip()
        if not text.startswith("{"):
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                text = text[start : end + 1]
        try:
            return json.loads(text)
        except Exception:
            return None

    def _coerce_text(self, content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, Iterable):
            parts = []
            for item in content:
                t = getattr(item, "text", None)
                if isinstance(t, str):
                    parts.append(t)
            return "".join(parts)
        return str(content)

    def _parse_time(self, ts: str) -> datetime | None:
        try:
            return datetime.fromisoformat(ts)
        except Exception:
            return None
