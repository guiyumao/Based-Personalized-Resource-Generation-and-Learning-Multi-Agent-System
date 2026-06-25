"""Conversational learner-profile building helpers."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from typing import Any

from sqlalchemy.orm import Session

from common.config import Settings, get_settings
from common.models.learning import ProfileConversation, User, UserProfile
from common.schemas.user import ProfileChatResponse, sanitize_profile_dimensions
from services.agent_service.app.services.llm_factory import LLMFactory


FIRST_QUESTION = (
    "为了更方便地了解您的需求，提供个性化服务，请您简单地描述一下您现在的情况"
    "——比如您的学习基础、目标、感兴趣的领域以及平时的学习习惯。"
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

PROFILE_LABEL_TO_KEY = {
    **{label: key for key, label in PROFILE_DIMENSION_LABELS.items()},
    "基础": "knowledgeBase",
    "偏好": "cognitiveStyle",
    "认知方式": "cognitiveStyle",
    "易错点": "errorPreference",
    "薄弱点": "errorPreference",
    "节奏": "learningSpeed",
    "兴趣": "interestDirection",
    "方向": "interestDirection",
    "目标": "goalOrientation",
}

PROFILE_QUESTION_BANK = {
    "knowledgeBase": "你之前学过哪些相关内容，或者已经掌握了哪些基础？",
    "cognitiveStyle": "你更喜欢看图理解、读文字、听讲解，还是边做边学？",
    "errorPreference": "你通常最容易卡在哪类题目或知识点上？",
    "learningSpeed": "你觉得自己的学习节奏偏快、适中，还是需要慢一点分步来？",
    "interestDirection": "你现在更感兴趣的方向是什么，比如后端、前端、算法或数据分析？",
    "goalOrientation": "你当前的学习目标更偏向考试、项目实践、求职，还是长期兴趣？",
}

PARSER_PROMPT = """你是一个学习对话解析器。你的唯一任务是把学生的自然语言输入
拆解为清晰的语义要点，供下游 Agent 使用。你不生成对话回复，
不提取画像维度，不做判断，只做解析。

1. explicit_points：学生字面上说了什么，拆成独立要点。
2. implicit_needs：学生没明说但可能存在的学习需求、困惑或期待。
3. sentiment：只从 positive / neutral / anxious / frustrated 中选一个。
4. key_terms：学生提到的课程、技术、工具、领域名词。

严格返回 JSON：
{
  "explicit_points": ["要点1"],
  "implicit_needs": ["隐含需求1"],
  "sentiment": "neutral",
  "key_terms": ["术语1"]
}
"""

ANALYSIS_PROMPT = """你是一个学习画像分析器。你的唯一任务是根据上游解析结果，
提取结构化的学习画像事实。你不生成对话回复。

六个维度：
- knowledgeBase：知识基础，可使用 needs_basics / has_foundation / proficient / wants_deeper
- cognitiveStyle：视觉型 / 文本型 / 听觉型 / 动手实践型
- errorPreference：常卡住的题型或知识点
- learningSpeed：较快 / 适中 / 较慢
- interestDirection：想学的技术、领域、方向
- goalOrientation：考试 / 项目实践 / 求职 / 长期兴趣

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
  "clarification_needed": ["具体追问1"],
  "suggested_next_dimension": "knowledgeBase",
  "suggested_next_reason": "为什么建议追问这个维度"
}

没提取到的字段填 null。
"""

OUTPUT_PROMPT = """你是一个专业、真诚的学习画像访谈助手，正在和学生做一对一访谈。

原则：
- 用追问代替赞美。
- 每轮最多一句共情，然后立刻转入具体追问。
- 问题要窄，不要宽泛。
- 如果上游识别到隐含需求，顺着它追问。
- 已填充 4 个及以上维度时，可以自然提醒学生随时点击“完成，进入学习”。

输入包含 parser_result、analysis_result、filled_dimensions、conversation_round。
只输出自然语言回复，不要 JSON，不要额外格式，控制在 80-150 字。
"""

NEGATION_PATTERNS = [
    r"没有.*基础",
    r"没学过",
    r"不会",
    r"不了解",
    r"不懂",
    r"零基础",
    r"完全没",
    r"没接触过",
    r"不太会",
    r"不太懂",
    r"不熟悉",
    r"不擅长",
    r"没做过",
    r"很少",
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
    (("学得快", "上手快", "节奏快", "比较快", "较快推进"), "较快"),
    (("慢", "吃力", "跟不上", "慢一点", "分步讲"), "较慢"),
    (("适中", "正常", "还行", "适中节奏"), "适中"),
)


class ProfileBuilderService:
    """Build and update learner profile dimensions from conversation turns."""

    PARSER_TEMPERATURE = 0.7
    ANALYSIS_TEMPERATURE = 0.2
    OUTPUT_TEMPERATURE = 0.6

    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()

    def chat(self, user_id: int, message: str) -> ProfileChatResponse:
        """Process one profile-building chat turn."""

        user = self.db.get(User, user_id)
        if user is None:
            raise ValueError("User not found")

        profile = self._get_or_create_profile(user_id)
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
        reply, updates = self._generate_reply_and_updates(message, history, existing_dimensions)

        if updates:
            self._apply_updates(profile, updates)

        self._save_message(user_id, "assistant", reply)
        self.db.commit()
        self.db.refresh(profile)

        latest_dimensions = self._get_profile_dimensions(profile)
        self._sync_agent_collaboration_context(profile, latest_dimensions)
        self.db.commit()
        self.db.refresh(profile)

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
            deleted_keys = self._delete_blank_dimensions(profile, profile_dimensions)
            for key in deleted_keys:
                self._clear_dimension_side_effect(profile, key)
            self._apply_updates(profile, self._normalize_updates(profile_dimensions))
            if deleted_keys:
                self._mark_analysis_stale(user_id)

        self._sync_agent_collaboration_context(profile, self._get_profile_dimensions(profile))
        self.db.commit()
        self.db.refresh(profile)
        return profile

    def delete_profile_dimension(self, user_id: int, dimension_key: str) -> UserProfile:
        """Delete one stored profile dimension and refresh downstream agent context."""

        user = self.db.get(User, user_id)
        if user is None:
            raise ValueError("User not found")
        if dimension_key not in PROFILE_DIMENSION_KEYS:
            raise ValueError("Invalid profile dimension")

        profile = self._get_or_create_profile(user_id)
        habits = profile.habits if isinstance(profile.habits, dict) else {}
        raw_dimensions = habits.get("profile_dimensions")
        profile_dimensions = dict(raw_dimensions) if isinstance(raw_dimensions, dict) else {}
        profile_dimensions.pop(dimension_key, None)
        profile.habits = {**habits, "profile_dimensions": profile_dimensions}

        self._clear_dimension_side_effect(profile, dimension_key)
        self._mark_analysis_stale(user_id)
        self._sync_agent_collaboration_context(profile, self._get_profile_dimensions(profile))
        self.db.commit()
        self.db.refresh(profile)
        return profile

    def _generate_reply_and_updates(
        self,
        message: str,
        history: list[ProfileConversation],
        existing_dimensions: dict[str, str],
    ) -> tuple[str, dict[str, str]]:
        structured_updates = self._extract_structured_dimension_updates(message)
        heuristic_updates = self._extract_updates_from_text(message, history, existing_dimensions)
        agent_reply = ""
        agent_updates: dict[str, str] = {}

        if not structured_updates:
            parsed = self._run_parser_agent(message, history)
            if parsed is not None:
                analysis = self._run_analysis_agent(parsed, history, existing_dimensions)
                if analysis is not None:
                    agent_reply, agent_updates = self._run_output_agent(
                        parsed,
                        analysis,
                        history,
                        existing_dimensions,
                    )

        merged_updates = {
            **agent_updates,
            **heuristic_updates,
            **structured_updates,
        }
        normalized_updates = self._normalize_updates(merged_updates)
        reply = self._build_agent_feedback_reply(
            existing_dimensions=existing_dimensions,
            updates=normalized_updates,
            model_reply=agent_reply,
        )
        return reply, normalized_updates

    def _run_parser_agent(
        self,
        message: str,
        history: list[ProfileConversation],
    ) -> dict[str, Any] | None:
        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            model = LLMFactory(self.settings).build_chat_model(
                temperature=self.PARSER_TEMPERATURE
            )
            last_ai_message = ""
            for item in reversed(history):
                if item.role == "assistant":
                    last_ai_message = item.content
                    break

            context = f"学生本轮输入：{message}"
            if last_ai_message:
                context = f"上一轮 AI 提问：{last_ai_message[:200]}\n学生本轮输入：{message}"

            result = model.invoke(
                [
                    SystemMessage(content=PARSER_PROMPT),
                    HumanMessage(content=context),
                ]
            )
            return self._parse_json_payload(self._coerce_llm_text(result.content))
        except Exception:
            return None

    def _run_analysis_agent(
        self,
        parsed: dict[str, Any],
        history: list[ProfileConversation],
        existing_dimensions: dict[str, str],
    ) -> dict[str, Any] | None:
        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            model = LLMFactory(self.settings).build_chat_model(
                temperature=self.ANALYSIS_TEMPERATURE
            )
            expected_dimension = self._infer_expected_dimension(history, existing_dimensions)
            filled_list = [
                f"{PROFILE_DIMENSION_LABELS[key]}：{value}"
                for key, value in existing_dimensions.items()
                if value
            ]
            missing_list = [
                PROFILE_DIMENSION_LABELS[key]
                for key in PROFILE_DIMENSION_KEYS
                if not existing_dimensions.get(key)
            ]
            context = (
                f"解析结果-显性表达：{json.dumps(parsed.get('explicit_points') or [], ensure_ascii=False)}\n"
                f"解析结果-隐含需求：{json.dumps(parsed.get('implicit_needs') or [], ensure_ascii=False)}\n"
                f"解析结果-情感：{parsed.get('sentiment', 'neutral')}\n"
                f"解析结果-关键术语：{json.dumps(parsed.get('key_terms') or [], ensure_ascii=False)}\n"
                f"当前优先维度：{expected_dimension or '自动判断'}\n"
                f"已填充维度：{'; '.join(filled_list) if filled_list else '无'}\n"
                f"待填充维度：{'; '.join(missing_list) if missing_list else '无'}"
            )
            result = model.invoke(
                [
                    SystemMessage(content=ANALYSIS_PROMPT),
                    HumanMessage(content=context),
                ]
            )
            return self._parse_json_payload(self._coerce_llm_text(result.content))
        except Exception:
            return None

    def _run_output_agent(
        self,
        parsed: dict[str, Any],
        analysis: dict[str, Any],
        history: list[ProfileConversation],
        existing_dimensions: dict[str, str],
    ) -> tuple[str, dict[str, str]]:
        try:
            from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

            facts = analysis.get("facts_extracted") or {}
            extracted_updates: dict[str, str] = {}
            for key in PROFILE_DIMENSION_KEYS:
                fact = facts.get(key)
                if not isinstance(fact, dict):
                    continue
                value = str(fact.get("value") or "").strip()
                confidence = str(fact.get("confidence") or "medium").lower()
                if value and confidence in {"high", "medium"}:
                    extracted_updates[key] = value

            model = LLMFactory(self.settings).build_chat_model(
                temperature=self.OUTPUT_TEMPERATURE
            )
            filled_after = len(
                [
                    key
                    for key in PROFILE_DIMENSION_KEYS
                    if existing_dimensions.get(key) or extracted_updates.get(key)
                ]
            )
            conversation_round = (len(history) // 2) + 1
            output_context = (
                f"parser_result={json.dumps(parsed, ensure_ascii=False)}\n"
                f"analysis_result={json.dumps(analysis, ensure_ascii=False)}\n"
                f"filled_dimensions={filled_after}\n"
                f"conversation_round={conversation_round}\n"
                f"new_updates={json.dumps(extracted_updates, ensure_ascii=False)}"
            )
            prompt_messages: list[Any] = [SystemMessage(content=OUTPUT_PROMPT)]
            for item in history[-4:]:
                if item.role == "assistant":
                    prompt_messages.append(AIMessage(content=item.content))
                else:
                    prompt_messages.append(HumanMessage(content=item.content))
            prompt_messages.append(HumanMessage(content=output_context))

            result = model.invoke(prompt_messages)
            reply = self._coerce_llm_text(result.content).strip()
            return reply, extracted_updates
        except Exception:
            return "", {}

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

    def _extract_updates_from_text(
        self,
        message: str,
        history: list[ProfileConversation] | None = None,
        existing_dimensions: dict[str, str] | None = None,
    ) -> dict[str, str]:
        """Extract profile dimensions from the FULL user message (no sentence splitting).

        The parser/analysis/output agent pipeline handles complex multi-dimensional
        input.  The heuristic extraction below provides a fast keyword-based
        fallback that operates on the entire message at once, without splitting
        on commas or other punctuation.
        """
        updates: dict[str, str] = self._extract_structured_dimension_updates(message)
        history = history or []
        existing_dimensions = existing_dimensions or {}
        expected_key = self._infer_expected_dimension(history, existing_dimensions)
        normalized = message.strip()

        negated = any(re.search(pattern, normalized) for pattern in NEGATION_PATTERNS)
        wants_deeper = any(re.search(pattern, normalized) for pattern in WANTS_DEEPER_PATTERNS)

        # ── knowledgeBase ──
        if "knowledgeBase" not in updates:
            if wants_deeper:
                updates["knowledgeBase"] = f"wants_deeper: {normalized}"
            elif negated:
                updates["knowledgeBase"] = f"needs_basics: {normalized}"
            elif expected_key == "knowledgeBase" or any(
                token in normalized
                for token in ("学过", "掌握", "基础", "了解过", "接触过", "做过", "熟悉", "会写", "熟练")
            ):
                updates["knowledgeBase"] = normalized

        # ── cognitiveStyle ──
        if "cognitiveStyle" not in updates:
            for tokens, label in COGNITIVE_STYLE_RULES:
                if any(token in normalized for token in tokens):
                    updates["cognitiveStyle"] = label
                    break
            if "cognitiveStyle" not in updates and expected_key == "cognitiveStyle":
                style = self._infer_cognitive_style_from_short_answer(normalized)
                if style:
                    updates["cognitiveStyle"] = style

        # ── errorPreference ──
        if "errorPreference" not in updates and (
            expected_key == "errorPreference"
            or any(
                token in normalized
                for token in ("不会", "不懂", "不太会", "困难", "难", "容易错", "卡", "薄弱")
            )
        ):
            updates["errorPreference"] = normalized

        # ── learningSpeed ──
        if "learningSpeed" not in updates:
            for tokens, label in LEARNING_SPEED_RULES:
                if any(token in normalized for token in tokens):
                    updates["learningSpeed"] = label
                    break

        # ── interestDirection ──
        if "interestDirection" not in updates and (
            expected_key == "interestDirection"
            or any(
                token in normalized
                for token in (
                    "感兴趣", "喜欢", "想学", "偏向", "更想",
                    "后端", "前端", "算法", "数据分析", "AI", "人工智能",
                )
            )
        ):
            updates["interestDirection"] = normalized

        # ── goalOrientation ──
        if "goalOrientation" not in updates and (
            expected_key == "goalOrientation"
            or any(
                token in normalized
                for token in ("目标", "希望", "找工作", "求职", "实习", "考研", "考试", "项目", "面试")
            )
        ):
            updates["goalOrientation"] = normalized

        return updates

    def _extract_structured_dimension_updates(self, message: str) -> dict[str, str]:
        """Parse dimension key-value pairs from the full message.

        Supports formats like:
          - 知识基础：学过Python和Java
          - 目标导向：找工作，兴趣方向：算法和AI
          - 认知风格 视觉型 (label-only match)
        Multi-pair single-line input (separated by ， or ；) is handled by
        splitting before matching.
        """
        updates: dict[str, str] = {}
        # Split single-line multi-pair input on Chinese punctuation separators
        segments: list[str] = []
        for raw_line in message.splitlines():
            line = raw_line.strip().lstrip("-*• ").strip()
            if not line:
                continue
            # If the line contains multiple dimension labels, split before each label
            label_positions: list[tuple[int, str]] = []
            for label in PROFILE_DIMENSION_LABELS.values():
                idx = line.find(label)
                if idx >= 0:
                    label_positions.append((idx, label))
            if len(label_positions) >= 2:
                label_positions.sort(key=lambda x: x[0])
                for i, (pos, label) in enumerate(label_positions):
                    start = pos
                    end = label_positions[i + 1][0] if i + 1 < len(label_positions) else len(line)
                    segments.append(line[start:end].strip().rstrip("，,;；"))
            else:
                segments.append(line)

        for segment in segments:
            match = re.match(r"^([^:：]{1,20})[:：\s]+(.+)$", segment)
            if not match:
                continue
            raw_label, raw_value = match.groups()
            key = PROFILE_LABEL_TO_KEY.get(raw_label.strip())
            if not key:
                continue
            value = re.sub(r"\s+", " ", raw_value).strip(" ，,;；")
            if value:
                updates[key] = value
        return updates

    def _infer_expected_dimension(
        self,
        history: list[ProfileConversation],
        existing_dimensions: dict[str, str],
    ) -> str | None:
        for item in reversed(history):
            if item.role != "assistant":
                continue
            content = item.content
            for key, question in PROFILE_QUESTION_BANK.items():
                if key not in existing_dimensions and question in content:
                    return key
            if "看图理解" in content or "读文字" in content or "听讲解" in content or "边做边学" in content:
                return "cognitiveStyle"
            if "卡在" in content or "哪类题目" in content or "知识点" in content:
                return "errorPreference"
            if "学习节奏" in content:
                return "learningSpeed"
        missing = [key for key in PROFILE_DIMENSION_KEYS if not existing_dimensions.get(key)]
        return missing[0] if missing else None

    def _infer_cognitive_style_from_short_answer(self, value: str) -> str:
        if any(token in value for token in ("图", "图形", "图表", "看图", "可视化")):
            return "视觉型"
        if any(token in value for token in ("文字", "阅读", "文档")):
            return "文本型"
        if any(token in value for token in ("听", "讲解", "视频", "老师讲")):
            return "听觉型"
        if any(token in value for token in ("做题", "动手", "实践", "练习", "写代码")):
            return "动手实践型"
        return ""

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
        if not value or self._looks_like_bulk_profile_dump(value):
            return ""

        if key == "cognitiveStyle":
            if any(separator in value for separator in ("、", "，", ",")):
                return value
            for tokens, label in COGNITIVE_STYLE_RULES:
                if any(token in value for token in tokens):
                    return label

        if key == "learningSpeed":
            for tokens, label in LEARNING_SPEED_RULES:
                if value == label or any(token == value for token in tokens):
                    return label

        return value

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
            profile.mastery_json = {
                **mastery_json,
                "_self_reported_background": updates["knowledgeBase"],
            }

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
        self._mark_analysis_stale(profile.user_id)

    def _delete_blank_dimensions(self, profile: UserProfile, updates: dict[str, Any]) -> list[str]:
        blank_keys = [
            key
            for key, value in updates.items()
            if key in PROFILE_DIMENSION_KEYS and not str(value).strip()
        ]
        if not blank_keys:
            return []

        habits = profile.habits if isinstance(profile.habits, dict) else {}
        raw_dimensions = habits.get("profile_dimensions")
        profile_dimensions = dict(raw_dimensions) if isinstance(raw_dimensions, dict) else {}
        for key in blank_keys:
            profile_dimensions.pop(key, None)
        profile.habits = {**habits, "profile_dimensions": profile_dimensions}
        return blank_keys

    def _clear_dimension_side_effect(self, profile: UserProfile, dimension_key: str) -> None:
        if dimension_key == "cognitiveStyle":
            profile.learning_style = ""

        if dimension_key == "knowledgeBase":
            mastery_json = profile.mastery_json if isinstance(profile.mastery_json, dict) else {}
            profile.mastery_json = {
                key: value
                for key, value in mastery_json.items()
                if key != "_self_reported_background"
            }

        cognitive_key_map = {
            "learningSpeed": "learningSpeed",
            "errorPreference": "errorPreference",
            "goalOrientation": "goalOrientation",
        }
        cognitive_key = cognitive_key_map.get(dimension_key)
        if cognitive_key:
            cognitive = profile.cognitive_abilities if isinstance(profile.cognitive_abilities, dict) else {}
            profile.cognitive_abilities = {
                key: value
                for key, value in cognitive.items()
                if key != cognitive_key
            }

    def _sync_agent_collaboration_context(self, profile: UserProfile, dimensions: dict[str, str]) -> None:
        habits = profile.habits if isinstance(profile.habits, dict) else {}
        context = {
            "source": "learner_profile_agent",
            "profile_dimensions": dimensions,
            "learning_style": profile.learning_style or self._map_learning_style(dimensions.get("cognitiveStyle", "")),
            "preferred_resource_modes": self._resource_modes_from_dimensions(dimensions),
            "known_background": dimensions.get("knowledgeBase", ""),
            "interest_direction": dimensions.get("interestDirection", ""),
            "goal_orientation": dimensions.get("goalOrientation", ""),
            "weakness_hint": dimensions.get("errorPreference", ""),
            "learning_speed": dimensions.get("learningSpeed", ""),
            "agent_handoff": {
                "path_planning_agent": self._path_handoff(dimensions),
                "resource_generation_agent": self._resource_handoff(dimensions),
                "exercise_generation_agent": self._exercise_handoff(dimensions),
                "qa_agent": self._qa_handoff(dimensions),
            },
        }
        profile.habits = {**habits, "agent_collaboration_context": context}

    def _resource_modes_from_dimensions(self, dimensions: dict[str, str]) -> list[str]:
        style = dimensions.get("cognitiveStyle", "")
        if "视觉" in style:
            return ["diagram", "step_visualization", "worked_example"]
        if "文本" in style:
            return ["structured_notes", "definition_first", "summary"]
        if "听觉" in style:
            return ["teacher_explanation", "dialogue", "recap"]
        if "实践" in style or "动手" in style:
            return ["hands_on_task", "code_example", "guided_practice"]
        return ["worked_example", "guided_practice"]

    def _path_handoff(self, dimensions: dict[str, str]) -> list[str]:
        hints = []
        if dimensions.get("knowledgeBase"):
            hints.append(f"从学习者已说明的基础出发：{dimensions['knowledgeBase']}")
        if dimensions.get("goalOrientation"):
            hints.append(f"路径目标对齐：{dimensions['goalOrientation']}")
        if dimensions.get("learningSpeed"):
            hints.append(f"节奏安排参考：{dimensions['learningSpeed']}")
        return hints

    def _resource_handoff(self, dimensions: dict[str, str]) -> list[str]:
        hints = []
        if dimensions.get("cognitiveStyle"):
            hints.append(f"资源呈现适配认知风格：{dimensions['cognitiveStyle']}")
        if dimensions.get("interestDirection"):
            hints.append(f"案例优先贴近兴趣方向：{dimensions['interestDirection']}")
        return hints

    def _exercise_handoff(self, dimensions: dict[str, str]) -> list[str]:
        hints = []
        if dimensions.get("errorPreference"):
            hints.append(f"练习优先覆盖易卡点：{dimensions['errorPreference']}")
        learning_speed = dimensions.get("learningSpeed", "")
        if learning_speed == "较慢" or any(token in learning_speed for token in ("慢", "分步")):
            hints.append("题组先基础后进阶，降低单题跨度")
        return hints

    def _qa_handoff(self, dimensions: dict[str, str]) -> list[str]:
        hints = []
        if dimensions.get("cognitiveStyle"):
            hints.append(f"答疑解释方式匹配：{dimensions['cognitiveStyle']}")
        if dimensions.get("knowledgeBase"):
            hints.append(f"答疑默认衔接已有基础：{dimensions['knowledgeBase']}")
        return hints

    def _get_profile_dimensions(self, profile: UserProfile) -> dict[str, str]:
        habits = profile.habits if isinstance(profile.habits, dict) else {}
        return sanitize_profile_dimensions(habits.get("profile_dimensions"))

    def _looks_like_bulk_profile_dump(self, value: str) -> bool:
        """Detect multi-dimension input so the caller can route it to agent parsing.

        Returns True when the input clearly contains 2+ profile dimensions
        that should be handled by the AI analysis pipeline rather than
        simple keyword matching.
        """
        normalized = value.replace("\r\n", "\n").replace("\r", "\n")
        if "我想一次补充画像多维度" in normalized:
            return True
        marker_count = sum(marker in normalized for marker in PROFILE_DIMENSION_LABELS.values())
        return marker_count >= 2

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

    def _build_fallback_reply(self, existing_dimensions: dict[str, str], updates: dict[str, str]) -> str:
        merged = {**existing_dimensions, **updates}
        missing = [key for key in PROFILE_DIMENSION_KEYS if not merged.get(key)]
        if updates:
            captured = "；".join(
                f"{PROFILE_DIMENSION_LABELS.get(key, key)}：{value}"
                for key, value in updates.items()
            )
            if not missing:
                return f"我已分析并记录：{captured}。当前画像已经比较完整，可以开始进入学习路径和资源生成了。"
            next_key = missing[0]
            return f"我已分析并记录：{captured}。接下来想继续了解一下，{PROFILE_QUESTION_BANK[next_key]}"

        if not missing:
            return "你的学习画像已经比较完整了，如果愿意，我们可以直接开始生成学习路径、课件或练习。"
        return f"我还想再多了解你一些，{PROFILE_QUESTION_BANK[missing[0]]}"

    def _build_agent_feedback_reply(
        self,
        *,
        existing_dimensions: dict[str, str],
        updates: dict[str, str],
        model_reply: str,
    ) -> str:
        merged = {**existing_dimensions, **updates}
        missing = [key for key in PROFILE_DIMENSION_KEYS if not merged.get(key)]
        captured = "；".join(
            f"{PROFILE_DIMENSION_LABELS.get(key, key)}：{value}"
            for key, value in updates.items()
        )

        if model_reply.strip():
            reply = model_reply.strip()
            if captured and captured not in reply:
                reply = f"我已记录这些信息：{captured}。{reply}"
        elif updates:
            reply = self._build_fallback_reply(existing_dimensions, updates)
        else:
            reply = self._build_fallback_reply(existing_dimensions, updates)

        if not missing:
            if "完成，进入学习" not in reply and "完成" not in reply:
                reply = f"{reply} 当前画像已经比较完整，随时可以点击“完成，进入学习”。"
            return reply

        next_question = PROFILE_QUESTION_BANK[missing[0]]
        if next_question in reply:
            return reply
        if reply.endswith("。") or reply.endswith("？"):
            return f"{reply} {next_question}"
        return f"{reply}。{next_question}"

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

    def _mark_analysis_stale(self, user_id: int) -> None:
        """Invalidate cached deep analysis after profile changes."""

        try:
            from services.user_service.app.services.profile_analysis import ProfileAnalysisService

            ProfileAnalysisService(self.db).mark_stale(user_id)
        except Exception:
            pass

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
