"""Conversational learner-profile building helpers."""

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


FIRST_QUESTION = "为了更方便地了解您的需求，提供个性化服务，请您简单地描述一下您现在的情况——比如您的学习基础、目标、感兴趣的领域以及平时的学习习惯。"

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

COGNITIVE_STYLE_RULES = (
    (("动手", "实践", "上机", "写代码", "实操"), "动手实践型"),
    (("看图", "图示", "图表", "可视化", "视觉"), "视觉型"),
    (("阅读", "文字", "文本", "文档"), "文本型"),
    (("听", "讲解", "讲一遍", "语音"), "听觉型"),
)

LEARNING_SPEED_RULES = (
    (("学得快", "上手快", "节奏快", "比较快"), "较快"),
    (("慢", "吃力", "跟不上", "慢一点"), "较慢"),
    (("适中", "正常", "还行"), "适中"),
)

SYSTEM_PROMPT = """
你是个性化学习平台里的画像构建助手。你需要自然地回复学生，同时从当前对话中提取学习画像信息。

请只返回 JSON，格式如下：
{
  "reply": "给学生的自然语言回复",
  "profileUpdates": {
    "knowledgeBase": "已识别内容",
    "cognitiveStyle": "已识别内容"
  }
}

只能提取本轮对话里明确出现的信息，缺失字段不要猜测。
""".strip()


class ProfileBuilderService:
    """Build and update learner profile dimensions from conversation turns."""

    def __init__(self, db: Session, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()

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
        reply, updates = self._generate_reply_and_updates(message, history, existing_dimensions)

        if updates:
            self._apply_updates(profile, updates)

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

    def update_profile(self, user_id: int, learning_style: str | None, profile_dimensions: dict[str, str]) -> UserProfile:
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

    def _generate_reply_and_updates(
        self,
        message: str,
        history: list[ProfileConversation],
        existing_dimensions: dict[str, str],
    ) -> tuple[str, dict[str, str]]:
        heuristic_updates = self._extract_updates_from_text(message)
        llm_result = self._run_llm(message, history)
        if llm_result is not None:
            reply, llm_updates = llm_result
            if reply.strip():
                return reply.strip(), {**heuristic_updates, **llm_updates}

        return self._build_fallback_reply(existing_dimensions, heuristic_updates), heuristic_updates

    def _run_llm(self, message: str, history: list[ProfileConversation]) -> tuple[str, dict[str, str]] | None:
        try:
            from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

            model = LLMFactory(self.settings).build_chat_model(temperature=0.4)
            prompt_messages: list[Any] = [SystemMessage(content=SYSTEM_PROMPT)]
            for item in history[-12:]:
                if item.role == "assistant":
                    prompt_messages.append(AIMessage(content=item.content))
                else:
                    prompt_messages.append(HumanMessage(content=item.content))
            prompt_messages.append(HumanMessage(content=message))

            result = model.invoke(prompt_messages)
            parsed = self._parse_llm_payload(self._coerce_llm_text(result.content))
            if parsed is None:
                return None
            reply = str(parsed.get("reply") or "").strip()
            updates = self._normalize_updates(parsed.get("profileUpdates") or {})
            if not reply:
                return None
            return reply, updates
        except Exception:
            return None

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

    def _parse_llm_payload(self, raw_text: str) -> dict[str, Any] | None:
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

    def _extract_updates_from_text(self, message: str) -> dict[str, str]:
        updates: dict[str, str] = {}
        for sentence in self._split_sentences(message):
            if not sentence:
                continue

            if (
                "knowledgeBase" not in updates
                and any(token in sentence for token in ("学过", "掌握", "基础", "了解过", "接触过", "做过"))
            ):
                updates["knowledgeBase"] = sentence

            if "cognitiveStyle" not in updates:
                for tokens, label in COGNITIVE_STYLE_RULES:
                    if any(token in sentence for token in tokens):
                        updates["cognitiveStyle"] = label
                        break

            if (
                "errorPreference" not in updates
                and any(token in sentence for token in ("容易错", "总是错", "老是错", "卡在", "薄弱", "不会"))
            ):
                updates["errorPreference"] = sentence

            if "learningSpeed" not in updates:
                for tokens, label in LEARNING_SPEED_RULES:
                    if any(token in sentence for token in tokens):
                        updates["learningSpeed"] = label
                        break

            if (
                "interestDirection" not in updates
                and any(token in sentence for token in ("感兴趣", "喜欢", "想学", "偏向", "更想", "后端", "前端", "算法", "数据分析"))
            ):
                updates["interestDirection"] = sentence

            if (
                "goalOrientation" not in updates
                and any(token in sentence for token in ("目标", "希望", "找工作", "求职", "实习", "考研", "考试", "项目"))
            ):
                updates["goalOrientation"] = sentence

        return updates

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

    def _build_fallback_reply(self, existing_dimensions: dict[str, str], updates: dict[str, str]) -> str:
        merged = {**existing_dimensions, **updates}
        missing = [key for key in PROFILE_DIMENSION_KEYS if not merged.get(key)]
        if updates:
            captured = "；".join(
                f"{PROFILE_DIMENSION_LABELS.get(key, key)}：{value}"
                for key, value in updates.items()
            )
            if not missing:
                return f"我已经记录下这些画像信息：{captured}。当前画像已经比较完整，可以开始进入学习路径和资源生成了。"
            next_key = missing[0]
            return f"我先记下这些关键信息：{captured}。接下来想继续了解一下，{PROFILE_QUESTION_BANK[next_key]}"

        if not missing:
            return "你的学习画像已经比较完整了，如果愿意，我们可以直接开始生成学习路径、课件或练习。"
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
