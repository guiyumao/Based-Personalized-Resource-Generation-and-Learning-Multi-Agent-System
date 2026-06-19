"""Conversational learner-profile building helpers.

Architecture (three-agent pipeline):
  User message → Parser Agent (semantic decomposition, temp=0.7)
              → Analysis Agent (structured extraction, temp=0.2)
              → Output Agent (natural reply, temp=0.6)
  Keyword rules serve only as fallback when LLM is unavailable.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from typing import Any

from sqlalchemy.orm import Session

from common.config import Settings, get_settings
from common.models.learning import ProfileConversation, User, UserProfile
from common.schemas.user import ProfileChatResponse
from services.agent_service.app.services.llm_factory import LLMFactory


FIRST_QUESTION = (
    "你好！我是你的学习画像助手，接下来会通过几个简单的问题来了解你的学习情况，"
    "帮助你获得更个性化的学习体验。\n\n"
    "首先想了解一下，你之前学过哪些相关内容，或者已经掌握了哪些基础？"
    "可以随便聊聊，比如学过什么课程、做过什么项目、或者对哪些方向比较感兴趣。"
)

PROFILE_DIMENSION_KEYS = (
    "knowledgeBase",
    "cognitiveStyle",
    "errorPreference",
    "learningSpeed",
    "interestDirection",
    "goalOrientation",
)

PROFILE_DIMENSION_LABELS = {
    "knowledgeBase": "知识基础",
    "cognitiveStyle": "认知风格",
    "errorPreference": "易错偏好",
    "learningSpeed": "学习节奏",
    "interestDirection": "兴趣方向",
    "goalOrientation": "目标导向",
}

PROFILE_QUESTION_BANK = {
    "knowledgeBase": "你之前学过哪些相关内容，或者已经掌握了哪些基础？",
    "cognitiveStyle": "你更喜欢看图理解、读文字、听讲解，还是边做边学？",
    "errorPreference": "你通常最容易卡在哪类题目或知识点上？",
    "learningSpeed": "你觉得自己的学习节奏偏快、适中，还是需要慢一点分步来？",
    "interestDirection": "你现在更感兴趣的方向是什么，比如后端、前端、算法或数据分析？",
    "goalOrientation": "你当前的学习目标更偏向考试、项目实践、求职，还是长期兴趣？",
}

# ═══════════════════════════════════════════════════════════════════════
#  Agent prompts — three-agent pipeline
# ═══════════════════════════════════════════════════════════════════════

PARSER_PROMPT = """你是一个学习对话解析器。你的唯一任务是把学生的自然语言输入
拆解为清晰的语义要点，供下游 Agent 使用。你**不生成对话回复**，
**不提取画像维度**，**不做判断**——只做解析。

## 解析规则

1. **显性表达（explicit_points）**：学生字面上说了什么。
   - 拆成独立要点，每条一句话，去掉客套和 filler（"嗯""我觉得吧""就是说"）
   - 如果一句话里包含多个事实，拆成多条
   - 保留原话的领域术语和技术名词（如"langchain4j""Spring Boot"）

2. **隐含需求（implicit_needs）**：学生可能没说出口的需求、困惑或期望。
   - "照着教程能写但自己写就卡住" → 可能缺乏独立拆解问题的能力
   - "感觉还挺有意思的" → 兴趣驱动型学习者，适合案例/项目教学
   - "之前学过但好久没用了" → 需要唤醒记忆而非从零开始
   - "我不太确定自己适合哪个方向" → 需要引导性提问帮他梳理
   - 每条隐含需求必须是可操作的——下游 Agent 能据此追问或调整策略

3. **情感线索（sentiment）**：学生当前的情绪基调。
   只从以下四个值中选一个：
   - "positive" — 积极、兴奋、自信
   - "neutral" — 平静、客观陈述
   - "anxious" — 担心、不确定、犹豫
   - "frustrated" — 挫败、困惑、感到困难

4. **关键术语（key_terms）**：学生提到的具体技术、工具、课程等名词列表。

## 输出格式

严格返回 JSON，不要任何额外文字：
{
  "explicit_points": ["要点1", "要点2", "要点3"],
  "implicit_needs": ["隐含需求1", "隐含需求2"],
  "sentiment": "positive|neutral|anxious|frustrated",
  "key_terms": ["术语1", "术语2"]
}

注意：
- explicit_points 至少 1 条，最多 5 条
- implicit_needs 可以为空数组，有把握才写
- key_terms 只列专有名词，不列通用词"""

ANALYSIS_PROMPT = """你是一个学习画像分析器。你的唯一任务是根据上游解析结果，
提取结构化的学习画像事实。你**不生成对话回复**。

你需要从以下六个维度分析：
- knowledgeBase（知识基础）：学生已经学过、掌握或不了解的内容。
  对每个知识点标注掌握程度：
  - "needs_basics: <领域>" — 完全不会或零基础
  - "has_foundation: <领域>" — 有基础了解但不够扎实
  - "proficient: <领域>" — 已熟练掌握
  - "wants_deeper: <领域>" — 已熟悉但希望进阶深入
- cognitiveStyle（认知风格）：视觉型 / 文本型 / 听觉型 / 动手实践型
- errorPreference（易错偏好）：学生常卡住的题型或知识点
- learningSpeed（学习节奏）：较快 / 适中 / 较慢
- interestDirection（兴趣方向）：学生想学的具体技术、领域或方向
- goalOrientation（目标导向）：考试 / 项目实践 / 求职 / 长期兴趣

## 分析规则

1. **区分掌握程度（重要）**：
   - "我对XX完全没有基础" → "needs_basics: XX"
   - "我了解过XX但还不熟" → "has_foundation: XX"
   - "我XX用得很熟" / "XX是我的强项" → "proficient: XX"
   - "XX我比较熟悉，但想更深入学一下" → "wants_deeper: XX"
   特别注意：利用上游解析的 explicit_points 和 implicit_needs 来交叉验证——
   如果 explicit 说"学过Python"但 implicit 暗示"缺乏独立解决问题能力"，
   则 knowledgeBase 应为 "has_foundation: Python" 而非 "proficient"。

2. **识别否定表达**："没有基础""不会""不了解"→ "needs_basics: <领域>"。

3. **拆分复合实体**："AI开发、数字孪生技术"→ ["AI开发", "数字孪生技术"]。

4. **区分确定与推测**：每个事实标注 confidence（high/medium/low）。

5. **不要编造**：学生没说的维度留空。

## 输出格式

严格返回 JSON：
{
  "facts_extracted": {
    "knowledgeBase": {"value": "...", "confidence": "high|medium|low"},
    "cognitiveStyle": {"value": "...", "confidence": "high|medium|low"},
    "errorPreference": {"value": "...", "confidence": "high|medium|low"},
    "learningSpeed": {"value": "...", "confidence": "high|medium|low"},
    "interestDirection": {"value": "...", "confidence": "high|medium|low"},
    "goalOrientation": {"value": "...", "confidence": "high|medium|low"}
  },
  "clarification_needed": ["具体追问1", "具体追问2"],
  "suggested_next_dimension": "knowledgeBase",
  "suggested_next_reason": "为什么建议追问这个维度"
}

没提取到的字段填 null。"""

OUTPUT_PROMPT = """你是一个专业、真诚的学习画像访谈助手。你正在和一个学生进行一对一的
学习画像访谈，目的是了解学生的学习情况以便提供个性化学习体验。

## 核心原则

- **用追问代替赞美**：你不需要夸奖学生。学生说"我学过Python"时，
  不要回"太棒了！Python 是很棒的起点！"——而是回"你说的Python，是主要用来写脚本，
  还是做过完整的项目？"
- **每轮只共情一次**：选择学生表达中最具体的那个点做一句话共情。
  例如学生提到"照着教程能写但自己写就卡住"→ 共情："这个感觉我懂，'看懂'和'会写'
  之间确实有一道坎。" 然后立刻转入追问。
- **问题要窄不要宽**：避免"你还想学什么？"，改为"你提到想学AI开发——
  你是对模型训练感兴趣，还是更想学怎么调用API做应用？"
- **利用隐意识别**：如果上游解析发现了隐含需求，顺着它追问。
  例如 implicit 说"可能缺乏独立拆解问题的能力"→ 追问："当你拿到一个新需求时，
  你通常从哪一步开始？是直接写代码还是先画流程图？"

## 对话节奏

- 第 1-2 轮：了解知识基础，问题轻松但具体
- 第 3-4 轮：深入了解认知风格、学习节奏和易错偏好
- 第 5-6 轮：确认目标导向，补全缺失维度
- 已填充 ≥4 个维度后：可在末尾温柔提醒"随时可以点击'完成'进入学习"

## 输入说明

你会收到：
- parser_result：解析 Agent 的输出（explicit_points, implicit_needs, sentiment, key_terms）
- analysis_result：分析 Agent 的输出（facts_extracted, clarification_needed, suggested_next 等）
- filled_dimensions：已填充维度数 / 6
- conversation_round：当前对话轮次

## 输出

只输出你的自然语言回复文本，不要 JSON，不要任何格式标记。
回复长度控制在 80-150 字，让学生有空间继续输入。

如果 filled_dimensions 为 0（第 1 轮），使用开场语气：
先打招呼，再根据 parser 的 key_terms 和 explicit_points 自然地引出第一个问题。"""

# ═══════════════════════════════════════════════════════════════════════
#  Keyword rules (fallback only when LLM is unavailable)
# ═══════════════════════════════════════════════════════════════════════

NEGATION_PATTERNS = [
    r"没有.*基础", r"没学过", r"不会", r"不了解", r"不懂",
    r"零基础", r"完全没", r"没接触过", r"不太会", r"不太懂",
    r"不熟悉", r"不擅长", r"没做过", r"很少",
]

WANTS_DEEPER_PATTERNS = [
    r"熟悉.*(?:深入|进阶|提高|加强|更进|学好|系统)",
    r"(?:学过|会|了解|掌握).*(?:深入|进阶|提高|加强|更进|学好|系统)",
    r"(?:想|希望|打算).*(?:深入|进阶|提高|加强).*",
    r"(?:有.*基础).*(?:但|不过|然而|只是|但是).*(?:深入|进阶|加强|提高)",
    r"(?:做过|写过|用过).*(?:但|不过|然而|但是|只是).*(?:不够|不足|还需要).*",
]

COGNITIVE_STYLE_RULES = (
    (("动手", "实践", "上机", "写代码", "实操", "边做边学"), "动手实践型"),
    (("看图", "图示", "图表", "可视化", "视觉"), "视觉型"),
    (("阅读", "文字", "文本", "文档"), "文本型"),
    (("听", "讲解", "讲一遍", "语音"), "听觉型"),
)

LEARNING_SPEED_RULES = (
    (("学得快", "上手快", "节奏快", "比较快"), "较快"),
    (("慢", "吃力", "跟不上", "慢一点"), "较慢"),
    (("适中", "正常", "还行"), "适中"),
)


class ProfileBuilderService:
    """Build and update learner profile dimensions from conversation turns."""

    # ── Temperature constants — one place to tune ──────────────────

    PARSER_TEMPERATURE = 0.7     # higher: divergent thinking, implicit needs
    ANALYSIS_TEMPERATURE = 0.2   # lower: consistent structured extraction
    OUTPUT_TEMPERATURE = 0.6     # medium: natural language, not chaotic

    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()

    # ── Public API ──────────────────────────────────────────────────

    def chat(self, user_id: int, message: str) -> ProfileChatResponse:
        """Process one profile-building chat turn."""

        user = self.db.get(User, user_id)
        if user is None:
            raise ValueError("User not found")

        profile = self._get_or_create_profile(user_id)

        # First interaction: return the standard opening question
        history = self._load_recent_history(user_id)
        if not history and not message.strip():
            return ProfileChatResponse(
                reply=FIRST_QUESTION,
                profile_updates={},
                profile_completeness={k: "未获取" for k in PROFILE_DIMENSION_KEYS},
                estimated_remaining_rounds=6,
            )

        self._save_message(user_id, "user", message)

        existing_dimensions = self._get_profile_dimensions(profile)
        reply, updates = self._generate_reply_and_updates(
            message, history, existing_dimensions
        )

        if updates:
            self._apply_updates(profile, updates)
            # Mark profile analysis as stale since dimensions changed
            self._mark_analysis_stale(user_id)

        self._save_message(user_id, "assistant", reply)
        self.db.commit()
        self.db.refresh(profile)

        latest_dimensions = self._get_profile_dimensions(profile)
        completeness = self._build_completeness(latest_dimensions)
        return ProfileChatResponse(
            reply=reply,
            profile_updates=updates,
            profile_completeness=completeness,
            estimated_remaining_rounds=self._estimate_remaining_rounds(completeness),
        )

    def update_profile(
        self,
        user_id: int,
        learning_style: str | None,
        profile_dimensions: dict[str, str],
    ) -> UserProfile:
        """Apply a manual learner-profile update."""

        user = self.db.get(User, user_id)
        if user is None:
            raise ValueError("User not found")

        profile = self._get_or_create_profile(user_id)
        if learning_style and learning_style.strip():
            profile.learning_style = learning_style.strip()

        if profile_dimensions:
            self._apply_updates(profile, self._normalize_updates(profile_dimensions))

        self.db.commit()
        self.db.refresh(profile)
        return profile

    # ── Core pipeline: Parser → Analysis → Output ────────────────────

    def _generate_reply_and_updates(
        self,
        message: str,
        history: list[ProfileConversation],
        existing_dimensions: dict[str, str],
    ) -> tuple[str, dict[str, str]]:
        """Three-agent pipeline (main path), with keyword fallback."""

        # ── Main path ──
        parsed = self._run_parser_agent(message, history)
        if parsed is not None:
            analysis = self._run_analysis_agent(parsed, existing_dimensions)
            if analysis is not None:
                reply, updates = self._run_output_agent(
                    parsed, analysis, history, existing_dimensions
                )
                if reply and reply.strip():
                    return reply.strip(), updates

        # ── Fallback: keyword rules + template reply ──
        heuristic_updates = self._extract_updates_from_text(message)
        fallback_reply = self._build_fallback_reply(existing_dimensions, heuristic_updates)
        return fallback_reply, heuristic_updates

    # ── Parser Agent (temp=0.7) ─────────────────────────────────────

    def _run_parser_agent(
        self,
        message: str,
        history: list[ProfileConversation],
    ) -> dict[str, Any] | None:
        """Decompose raw user text into structured semantic points."""
        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            model = LLMFactory(self.settings).build_chat_model(
                temperature=self.PARSER_TEMPERATURE
            )

            # Include the last AI message for context if available
            last_ai_msg = ""
            for item in reversed(history):
                if item.role == "assistant":
                    last_ai_msg = item.content
                    break

            context = f"学生本轮输入：{message}"
            if last_ai_msg:
                context = (
                    f"上一轮 AI 问了什么：{last_ai_msg[:200]}\n"
                    f"学生本轮输入：{message}"
                )

            prompt_messages = [
                SystemMessage(content=PARSER_PROMPT),
                HumanMessage(content=context),
            ]
            result = model.invoke(prompt_messages)
            parsed = self._parse_json_payload(self._coerce_llm_text(result.content))
            if parsed is None:
                return None
            return parsed
        except Exception:
            return None

    # ── Analysis Agent (temp=0.2) ───────────────────────────────────

    def _run_analysis_agent(
        self,
        parsed: dict[str, Any],
        existing_dimensions: dict[str, str],
    ) -> dict[str, Any] | None:
        """Extract structured profile dimensions from parser output."""
        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            model = LLMFactory(self.settings).build_chat_model(
                temperature=self.ANALYSIS_TEMPERATURE
            )

            filled_list = [
                f"{PROFILE_DIMENSION_LABELS[k]}：{v}"
                for k, v in existing_dimensions.items() if v
            ]
            missing_list = [
                PROFILE_DIMENSION_LABELS[k]
                for k in PROFILE_DIMENSION_KEYS if not existing_dimensions.get(k)
            ]

            context = (
                f"解析结果 — 显性表达：{json.dumps(parsed.get('explicit_points') or [], ensure_ascii=False)}\n"
                f"解析结果 — 隐含需求：{json.dumps(parsed.get('implicit_needs') or [], ensure_ascii=False)}\n"
                f"解析结果 — 情感线索：{parsed.get('sentiment', 'neutral')}\n"
                f"解析结果 — 关键术语：{json.dumps(parsed.get('key_terms') or [], ensure_ascii=False)}\n"
                f"已填充维度：{'; '.join(filled_list) if filled_list else '无'}\n"
                f"待填充维度：{'; '.join(missing_list)}"
            )

            prompt_messages = [
                SystemMessage(content=ANALYSIS_PROMPT),
                HumanMessage(content=context),
            ]
            result = model.invoke(prompt_messages)
            parsed_result = self._parse_json_payload(self._coerce_llm_text(result.content))
            if parsed_result is None:
                return None
            return parsed_result
        except Exception:
            return None

    # ── Output Agent (temp=0.6) ─────────────────────────────────────

    def _run_output_agent(
        self,
        parsed: dict[str, Any],
        analysis: dict[str, Any],
        history: list[ProfileConversation],
        existing_dimensions: dict[str, str],
    ) -> tuple[str, dict[str, str]]:
        """Generate a natural reply from parser + analysis results."""
        try:
            from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

            model = LLMFactory(self.settings).build_chat_model(
                temperature=self.OUTPUT_TEMPERATURE
            )

            # Extract new facts from analysis
            facts = analysis.get("facts_extracted") or {}
            updates: dict[str, str] = {}
            for key in PROFILE_DIMENSION_KEYS:
                fact = facts.get(key)
                if fact and isinstance(fact, dict) and fact.get("value"):
                    conf = fact.get("confidence", "medium")
                    if conf in ("high", "medium"):
                        updates[key] = str(fact["value"])

            filled_count = len([v for v in existing_dimensions.values() if v])
            filled_after = filled_count + len(updates)
            conversation_round = (len(history) // 2) + 1

            context = (
                f"解析结果：\n"
                f"  显性表达：{json.dumps(parsed.get('explicit_points') or [], ensure_ascii=False)}\n"
                f"  隐含需求：{json.dumps(parsed.get('implicit_needs') or [], ensure_ascii=False)}\n"
                f"  情感：{parsed.get('sentiment', 'neutral')}\n"
                f"  关键术语：{json.dumps(parsed.get('key_terms') or [], ensure_ascii=False)}\n"
                f"\n"
                f"分析结果：\n"
                f"  新事实：{json.dumps(updates, ensure_ascii=False)}\n"
                f"  需要追问：{json.dumps(analysis.get('clarification_needed') or [], ensure_ascii=False)}\n"
                f"  建议追问维度：{analysis.get('suggested_next_dimension', 'knowledgeBase')}\n"
                f"  追问理由：{analysis.get('suggested_next_reason', '了解学生基础')}\n"
                f"\n"
                f"已填充维度：{filled_after}/6\n"
                f"对话轮次：第 {conversation_round} 轮\n"
                f"\n"
                f"请基于以上信息生成一段自然的对话回复。记住：追问比赞美更有价值。"
            )

            # Build prompt with conversation history (last 4 turns)
            prompt_messages: list[Any] = [SystemMessage(content=OUTPUT_PROMPT)]
            for item in history[-4:]:
                if item.role == "assistant":
                    prompt_messages.append(AIMessage(content=item.content))
                else:
                    prompt_messages.append(HumanMessage(content=item.content))
            prompt_messages.append(HumanMessage(content=context))

            result = model.invoke(prompt_messages)
            reply = self._coerce_llm_text(result.content).strip()
            if not reply:
                return "", {}
            return reply, updates
        except Exception:
            return "", {}

    # ── Keyword extraction (fallback) ───────────────────────────────

    def _extract_updates_from_text(self, message: str) -> dict[str, str]:
        """Keyword-based extraction, used only as LLM fallback."""

        updates: dict[str, str] = {}
        for sentence in self._split_sentences(message):
            if not sentence:
                continue

            negated = any(re.search(pat, sentence) for pat in NEGATION_PATTERNS)
            wants_deeper = any(re.search(pat, sentence) for pat in WANTS_DEEPER_PATTERNS)

            if "knowledgeBase" not in updates and wants_deeper:
                updates["knowledgeBase"] = f"wants_deeper：{sentence}"
            elif (
                "knowledgeBase" not in updates
                and not negated
                and any(
                    token in sentence
                    for token in ("学过", "掌握", "基础", "了解过", "接触过", "做过", "熟悉", "会写", "熟练")
                )
            ):
                updates["knowledgeBase"] = f"proficient / has_foundation：{sentence}"

            if "knowledgeBase" not in updates and negated:
                updates["knowledgeBase"] = f"needs_basics：{sentence}"

            if "cognitiveStyle" not in updates:
                for tokens, label in COGNITIVE_STYLE_RULES:
                    if any(token in sentence for token in tokens):
                        updates["cognitiveStyle"] = label
                        break

            if (
                "errorPreference" not in updates
                and any(
                    token in sentence
                    for token in ("容易错", "总是错", "老是错", "卡在", "薄弱", "不会")
                )
            ):
                updates["errorPreference"] = sentence

            if "learningSpeed" not in updates:
                for tokens, label in LEARNING_SPEED_RULES:
                    if any(token in sentence for token in tokens):
                        updates["learningSpeed"] = label
                        break

            if (
                "interestDirection" not in updates
                and any(
                    token in sentence
                    for token in (
                        "感兴趣", "喜欢", "想学", "偏向", "更想",
                        "后端", "前端", "算法", "数据分析", "AI", "人工智能",
                        "数字孪生", "开发", "机器学习", "深度学习",
                    )
                )
            ):
                updates["interestDirection"] = sentence

            if (
                "goalOrientation" not in updates
                and any(
                    token in sentence
                    for token in ("目标", "希望", "找工作", "求职", "实习", "考研", "考试", "项目")
                )
            ):
                updates["goalOrientation"] = sentence

        return updates

    # ── Helpers ─────────────────────────────────────────────────────

    def _parse_json_payload(self, raw_text: str) -> dict[str, Any] | None:
        text = raw_text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
            text = re.sub(r"```$", "", text).strip()
        if not text.startswith("{"):
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                text = text[start : end + 1]
        try:
            parsed = json.loads(text)
        except Exception:
            return None
        return parsed if isinstance(parsed, dict) else None

    def _split_sentences(self, text: str) -> list[str]:
        return [part.strip() for part in re.split(r"[，。；;！？!?]\s*", text) if part.strip()]

    def _normalize_updates(self, updates: dict[str, Any]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for key, value in updates.items():
            if key not in PROFILE_DIMENSION_KEYS:
                continue
            text = self._canonicalize_update(key, str(value).strip())
            if text:
                normalized[key] = text
        return normalized

    def _canonicalize_update(self, key: str, value: str) -> str:
        if not value:
            return ""
        if key == "cognitiveStyle":
            for tokens, label in COGNITIVE_STYLE_RULES:
                if any(token in value for token in tokens):
                    return label
        if key == "learningSpeed":
            for tokens, label in LEARNING_SPEED_RULES:
                if any(token in value for token in tokens):
                    return label
        return value

    def _coerce_llm_text(self, content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, Iterable):
            parts: list[str] = []
            for item in content:
                text = getattr(item, "text", None)
                if isinstance(text, str):
                    parts.append(text)
            return "".join(parts)
        return str(content)

    def _mark_analysis_stale(self, user_id: int) -> None:
        """Notify the analysis service that cached analysis is out of date."""
        try:
            from services.user_service.app.services.profile_analysis import ProfileAnalysisService
            ProfileAnalysisService(self.db).mark_stale(user_id)
        except Exception:
            pass  # Non-critical — analysis will be regenerated on next access

    def _get_or_create_profile(self, user_id: int) -> UserProfile:
        profile = self.db.get(UserProfile, user_id)
        if profile is not None:
            return profile
        profile = UserProfile(
            user_id=user_id,
            mastery_json={},
            learning_style="",
            cognitive_abilities={},
            habits={},
        )
        self.db.add(profile)
        self.db.flush()
        return profile

    def _save_message(self, user_id: int, role: str, content: str) -> None:
        self.db.add(ProfileConversation(user_id=user_id, role=role, content=content.strip()))
        self.db.flush()

    def _load_recent_history(self, user_id: int, limit: int = 20) -> list[ProfileConversation]:
        records = (
            self.db.query(ProfileConversation)
            .filter(ProfileConversation.user_id == user_id)
            .order_by(ProfileConversation.id.desc())
            .limit(limit)
            .all()
        )
        return list(reversed(records))

    def _apply_updates(self, profile: UserProfile, updates: dict[str, str]) -> None:
        habits = profile.habits if isinstance(profile.habits, dict) else {}
        raw_dimensions = habits.get("profile_dimensions")
        profile_dimensions = raw_dimensions if isinstance(raw_dimensions, dict) else {}
        profile_dimensions = {**profile_dimensions, **updates}
        profile.habits = {**habits, "profile_dimensions": profile_dimensions}

        if "cognitiveStyle" in updates:
            profile.learning_style = self._map_learning_style(updates["cognitiveStyle"])

        if "knowledgeBase" in updates:
            mastery_json = profile.mastery_json if isinstance(profile.mastery_json, dict) else {}
            profile.mastery_json = {**mastery_json, "_self_reported_background": updates["knowledgeBase"]}

        cognitive = profile.cognitive_abilities if isinstance(profile.cognitive_abilities, dict) else {}
        profile.cognitive_abilities = {
            **cognitive,
            **{
                key: value
                for key, value in {
                    "learningSpeed": updates.get("learningSpeed"),
                    "errorPreference": updates.get("errorPreference"),
                    "goalOrientation": updates.get("goalOrientation"),
                }.items()
                if value
            },
        }

    def _get_profile_dimensions(self, profile: UserProfile) -> dict[str, str]:
        habits = profile.habits if isinstance(profile.habits, dict) else {}
        raw_dimensions = habits.get("profile_dimensions")
        if not isinstance(raw_dimensions, dict):
            return {}
        return {
            str(key): str(value).strip()
            for key, value in raw_dimensions.items()
            if key in PROFILE_DIMENSION_KEYS and str(value).strip()
        }

    def _build_completeness(self, dimensions: dict[str, str]) -> dict[str, str]:
        return {
            key: "已获取" if dimensions.get(key) else "未获取"
            for key in PROFILE_DIMENSION_KEYS
        }

    def _estimate_remaining_rounds(self, completeness: dict[str, str]) -> int:
        filled = sum(1 for value in completeness.values() if value == "已获取")
        if filled == 0:
            return 5
        if filled <= 2:
            return 4
        if filled <= 4:
            return 2
        if filled == 5:
            return 1
        return 0

    def _build_fallback_reply(
        self, existing_dimensions: dict[str, str], updates: dict[str, str]
    ) -> str:
        merged = {**existing_dimensions, **updates}
        missing = [key for key in PROFILE_DIMENSION_KEYS if not merged.get(key)]
        if updates:
            captured = "；".join(
                f"{PROFILE_DIMENSION_LABELS.get(key, key)}：{value}"
                for key, value in updates.items()
            )
            if not missing:
                return (
                    f"我已经记录下这些画像信息：{captured}。"
                    "当前画像已经比较完整，可以开始进入学习路径和资源生成了。"
                )
            next_key = missing[0]
            return (
                f"我先记下这些关键信息：{captured}。"
                f"接下来想继续了解一下，{PROFILE_QUESTION_BANK[next_key]}"
            )

        if not missing:
            return (
                "你的学习画像已经比较完整了，如果愿意，我们可以直接开始"
                "生成学习路径、课件或练习。"
            )
        return f"我还想再多了解你一些，{PROFILE_QUESTION_BANK[missing[0]]}"

    def _map_learning_style(self, cognitive_style: str) -> str:
        if "视觉" in cognitive_style:
            return "visual"
        if "文本" in cognitive_style:
            return "reading"
        if "听觉" in cognitive_style:
            return "auditory"
        if "实践" in cognitive_style or "动手" in cognitive_style:
            return "kinesthetic"
        return cognitive_style
