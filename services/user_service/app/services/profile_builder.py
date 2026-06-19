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
你是个性化学习平台里的学习者画像构建智能体。你需要对学生每一轮回答做语义分析，并把分析结果交给后续的学习路径、资源生成、练习生成和答疑智能体协作使用。

画像维度只能使用这些 key：
- knowledgeBase：学习基础、已学内容、当前正在学的学科/知识范围
- cognitiveStyle：偏好的理解方式，例如视觉型、文本型、听觉型、动手实践型、混合型
- errorPreference：学生自述的薄弱点、易错点、卡点、困惑点
- learningSpeed：学习节奏，例如较快、适中、较慢，或学生自己的描述
- interestDirection：兴趣方向、想深入的主题、偏好的应用场景
- goalOrientation：学习目标，例如考试、项目、求职、兴趣、补弱等

分析规则：
1. 必须结合最近对话和当前系统正在追问的维度理解短回答，不能只看关键词。
2. 如果学生只回答一个词或短语，也要判断它是在回答上一轮问题的哪个画像维度。
3. 不要内置或偏向任何特定学科；学生说什么领域，就按原文归纳。
4. 对每一轮回答都尽可能提取明确画像信息；无法确定时再少提取。
5. reply 要自然反馈已经理解到的信息，并继续追问当前最缺失、对协作最有用的一个维度。

请只返回 JSON，格式如下：
{
  "reply": "给学生的自然语言回复",
  "profileUpdates": {
    "knowledgeBase": "已识别内容",
    "cognitiveStyle": "已识别内容"
  }
}

缺失字段不要猜测。profileUpdates 中的值要短而具体，保留学生原意。
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

    def update_profile(self, user_id: int, learning_style: str | None, profile_dimensions: dict[str, str]) -> UserProfile:
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
        self._sync_agent_collaboration_context(profile, self._get_profile_dimensions(profile))
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
        heuristic_updates = self._extract_updates_from_text(message, history, existing_dimensions)
        llm_result = self._run_llm(message, history, existing_dimensions)
        llm_reply = ""
        llm_updates: dict[str, str] = {}
        if llm_result is not None:
            llm_reply, llm_updates = llm_result

        merged_updates = {**heuristic_updates, **llm_updates}
        reply = self._build_agent_feedback_reply(
            existing_dimensions=existing_dimensions,
            updates=merged_updates,
            model_reply=llm_reply,
        )
        return reply, merged_updates

    def _run_llm(
        self,
        message: str,
        history: list[ProfileConversation],
        existing_dimensions: dict[str, str],
    ) -> tuple[str, dict[str, str]] | None:
        try:
            from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

            model = LLMFactory(self.settings).build_chat_model(temperature=0.4)
            expected_dimension = self._infer_expected_dimension(history, existing_dimensions)
            prompt_messages: list[Any] = [SystemMessage(content=SYSTEM_PROMPT)]
            prompt_messages.append(
                SystemMessage(
                    content=(
                        "当前已获取画像维度："
                        f"{json.dumps(existing_dimensions, ensure_ascii=False)}\n"
                        f"当前优先分析/追问维度：{expected_dimension or '自动判断'}"
                    )
                )
            )
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

    def _extract_updates_from_text(
        self,
        message: str,
        history: list[ProfileConversation] | None = None,
        existing_dimensions: dict[str, str] | None = None,
    ) -> dict[str, str]:
        updates: dict[str, str] = self._extract_structured_dimension_updates(message)
        history = history or []
        existing_dimensions = existing_dimensions or {}
        expected_key = self._infer_expected_dimension(history, existing_dimensions)

        for sentence in self._split_sentences(message):
            if not sentence:
                continue
            normalized = sentence.strip()
            if self._looks_like_bulk_profile_dump(normalized):
                continue

            if (
                "knowledgeBase" not in updates
                and (
                    expected_key == "knowledgeBase"
                    or any(token in sentence for token in ("学过", "掌握", "基础", "了解过", "接触过", "做过"))
                )
            ):
                updates["knowledgeBase"] = normalized

            if "cognitiveStyle" not in updates:
                for tokens, label in COGNITIVE_STYLE_RULES:
                    if any(token in sentence for token in tokens):
                        updates["cognitiveStyle"] = label
                        break
                if "cognitiveStyle" not in updates and expected_key == "cognitiveStyle":
                    style = self._infer_cognitive_style_from_short_answer(normalized)
                    if style:
                        updates["cognitiveStyle"] = style

            if (
                "errorPreference" not in updates
                and (
                    expected_key == "errorPreference"
                    or any(token in sentence for token in ("不会", "不懂", "不太会", "困难", "难", "容易错", "卡", "薄弱"))
                )
            ):
                updates["errorPreference"] = normalized

            if "learningSpeed" not in updates:
                for tokens, label in LEARNING_SPEED_RULES:
                    if any(token in sentence for token in tokens):
                        updates["learningSpeed"] = label
                        break

            if (
                "interestDirection" not in updates
                and (
                    expected_key == "interestDirection"
                    or any(token in sentence for token in ("感兴趣", "喜欢", "想学", "偏向", "更想"))
                )
            ):
                updates["interestDirection"] = normalized

            if (
                "goalOrientation" not in updates
                and any(token in sentence for token in ("目标", "希望", "找工作", "求职", "实习", "考研", "考试", "项目"))
            ):
                updates["goalOrientation"] = normalized

        return updates

    def _extract_structured_dimension_updates(self, message: str) -> dict[str, str]:
        updates: dict[str, str] = {}
        for raw_line in message.splitlines():
            line = raw_line.strip().lstrip("-*• ").strip()
            if not line:
                continue
            match = re.match(r"^([^:：]{2,12})[:：]\s*(.+)$", line)
            if not match:
                continue
            raw_label, raw_value = match.groups()
            label = raw_label.strip()
            key = PROFILE_LABEL_TO_KEY.get(label)
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
        if not value:
            return ""
        if self._looks_like_bulk_profile_dump(value):
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
        if dimensions.get("learningSpeed") == "较慢":
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
        normalized = value.replace("\r\n", "\n").replace("\r", "\n")
        if "我想一次补充画像多维度" in normalized:
            return True
        marker_count = sum(
            marker in normalized
            for marker in PROFILE_DIMENSION_LABELS.values()
        )
        if marker_count >= 2:
            return True
        return normalized.count("\n") >= 2 and "：" in normalized

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

        parts: list[str] = []
        if captured:
            parts.append(f"我已分析并记录：{captured}。")
        elif model_reply.strip():
            parts.append(model_reply.strip())
        else:
            parts.append("我已分析了你的回答。")

        if missing:
            next_key = missing[0]
            parts.append(f"为了让画像智能体更好地和路径、资源、练习、答疑智能体协作，我还想了解：{PROFILE_QUESTION_BANK[next_key]}")
        else:
            parts.append("当前画像已经比较完整，后续会交给学习路径、资源生成、练习生成和答疑智能体协同使用。")
        return "".join(parts)

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
