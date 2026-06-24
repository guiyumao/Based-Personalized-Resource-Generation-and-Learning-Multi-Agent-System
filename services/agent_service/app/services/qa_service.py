"""QA service for learning-oriented continuous conversations."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from common.config import get_settings
from common.models.learning import ChatMessage, ChatSession
from common.schemas.agent import (
    ExerciseGenerationRequest,
    QARequest,
    QAResponse,
    ResourceGenerationRequest,
)
from common.utils.text import is_placeholder_session_title, looks_like_unreadable_text
from common.utils.time import to_utc_isoformat
from services.agent_service.app.services.exercise_generation import ExerciseGenerationService
from services.agent_service.app.services.knowledge_base import KnowledgeArticle, KnowledgeBaseService
from services.agent_service.app.services.llm_factory import LLMFactory
from services.agent_service.app.services.resource_generation import ResourceGenerationService
from services.agent_service.app.services.web_search_service import WebSearchService


class QAService:
    """Answer questions, continue context, and optionally generate learning assets."""

    GENERIC_TOPIC_VALUES = {
        "这个",
        "这个知识点",
        "这部分",
        "这块内容",
        "上一题",
        "上一个",
        "题目",
        "练习",
        "练习题",
        "习题",
        "课件",
        "讲义",
        "知识点",
        "内容",
        "概念",
    }
    LEARNING_TOKENS = (
        "数学",
        "高数",
        "高等数学",
        "物理",
        "大学物理",
        "电磁场",
        "电磁学",
        "定积分",
        "积分",
        "导数",
        "极限",
        "知识点",
        "例题",
        "习题",
        "课件",
        "讲义",
        "学习",
        "复习",
        "python",
        "java",
        "算法",
        "编程",
        "数据结构",
        "概率",
        "线代",
    )
    FOLLOW_UP_HINTS = (
        "继续",
        "接着",
        "再来",
        "展开",
        "详细",
        "上一题",
        "上文",
        "刚才",
        "前面",
        "这个呢",
        "然后",
        "课件里",
        "刚才课件",
    )
    EXERCISE_HINTS = (
        "练习",
        "配套练习",
        "练习册",
        "练习题目",
        "习题",
        "练习题",
        "出题",
        "刷题",
        "来几道",
        "来5道",
        "来 5 道",
        "题目",
        "自测",
        "测试题",
    )
    RESOURCE_HINTS = (
        "课件",
        "讲义",
        "学习资料",
        "资料",
        "notes",
        "courseware",
        "总结",
        "提纲",
    )
    EXPLAIN_HINTS = (
        "讲解",
        "说明",
        "补充",
        "知识点",
        "概念",
        "展开",
        "详细",
        "为什么",
        "怎么理解",
        "应用题",
    )
    CURRENT_TIME_HINTS = (
        "星期几",
        "周几",
        "几号",
        "日期",
        "几点",
        "时间",
        "今天是",
    )
    GENERAL_HINTS = (
        "天气",
        "温度",
        "下雨",
        "晴",
        "阴",
        "空气质量",
        "星期几",
        "周几",
        "日期",
        "几号",
        "几点",
        "现在时间",
        "新闻",
        "热搜",
        "股价",
        "汇率",
        "票房",
    )
    SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")

    def __init__(self, db: Session | None = None) -> None:
        self.db = db
        self.settings = get_settings()
        self.knowledge_base = KnowledgeBaseService()
        self.web_search = WebSearchService(self.settings)
        self.llm_factory = LLMFactory(self.settings)

    def analyze_question(self, request: QARequest) -> dict[str, Any]:
        """Return a schema-valid tutoring response with optional generated assets."""

        clean_question = request.question.strip()
        session = self._get_or_create_session(request) if self.db is not None else None

        if session is not None:
            self._save_message(
                session_id=session.id,
                role="user",
                content=clean_question,
                metadata={
                    "subject": request.subject,
                    "grade": request.grade,
                    "student_answer": request.student_answer,
                    "wrong_answer": request.wrong_answer,
                    "current_knowledge_points": request.current_knowledge_points,
                },
            )

        history = self._get_message_history(session.id, limit=30) if session is not None else []
        conversation = self._build_conversation_context(request, history)
        flags = self._classify_question(conversation)
        context_snippets, confidence = self._build_context_snippets(conversation, flags)

        generated_resource = self._maybe_generate_resource(request, conversation, flags)
        generated_exercises = self._maybe_generate_exercises(
            request,
            conversation,
            flags,
            generated_resource,
        )

        if flags["has_learning_context"]:
            llm_learning_response = self._generate_learning_response_with_llm(
                conversation=conversation,
                flags=flags,
                context_snippets=context_snippets,
                generated_resource=generated_resource,
                generated_exercises=generated_exercises,
                history=history,
            )
            if llm_learning_response:
                student_response = llm_learning_response
                model_used = "qa_learning_llm"
            else:
                student_response = self._build_learning_response(
                    conversation=conversation,
                    flags=flags,
                    generated_resource=generated_resource,
                    generated_exercises=generated_exercises,
                )
                model_used = "qa_orchestrated"
        else:
            student_response, model_used = self._build_general_response(
                question=conversation["question"],
                context_snippets=context_snippets,
                follow_up=conversation["follow_up"],
                history=history,
            )
        structured_analysis = self._build_structured_analysis(
            request=request,
            conversation=conversation,
            flags=flags,
            generated_resource=generated_resource,
            generated_exercises=generated_exercises,
        )

        candidate = {
            "student_id": request.student_id,
            "subject": conversation["subject"],
            "grade": request.grade,
            "session_id": session.id if session is not None else request.session_id,
            "session_title": session.title if session is not None else request.session_title,
            "student_response": student_response,
            "structured_analysis": structured_analysis,
            "message_history": history,
            "context_snippets": context_snippets,
            "confidence": confidence,
            "generated_exercises": generated_exercises,
            "generated_resource": generated_resource,
            "model_used": model_used,
        }
        validated = self._validate_response(candidate, request, history)

        if session is None or self.db is None:
            return validated

        assistant_message = self._save_message(
            session_id=session.id,
            role="assistant",
            content=validated["student_response"],
            model_used=model_used,
            metadata={
                "structured_analysis": validated["structured_analysis"],
                "context_snippets": validated["context_snippets"],
                "confidence": validated["confidence"],
                "generated_exercises": validated.get("generated_exercises"),
                "generated_resource": validated.get("generated_resource"),
                "inferred_knowledge_point": conversation["knowledge_point"],
                "effective_question": conversation["effective_question"],
            },
        )
        session.last_message_at = datetime.utcnow()
        self.db.commit()

        validated["session_id"] = session.id
        validated["session_title"] = session.title
        validated["message_history"] = self._get_message_history(session.id, limit=30)
        if assistant_message is not None and validated["message_history"]:
            validated["message_history"][-1]["id"] = assistant_message.id
            validated["message_history"][-1]["model_used"] = assistant_message.model_used
            validated["message_history"][-1]["created_at"] = to_utc_isoformat(assistant_message.created_at)
        return validated

    def _get_or_create_session(self, request: QARequest) -> ChatSession:
        assert self.db is not None

        if request.session_id is not None:
            session = self.db.query(ChatSession).filter(ChatSession.id == request.session_id).first()
            if session is None:
                raise ValueError(f"QA session {request.session_id} not found")
            if self._should_refresh_session_title(session.title):
                session.title = self._build_session_title(request.question)
                self.db.commit()
                self.db.refresh(session)
            return session

        title = request.session_title.strip() or self._build_session_title(request.question) or "智能问答"
        try:
            user_id = int(request.student_id)
        except ValueError:
            user_id = 0

        session = ChatSession(
            user_id=user_id,
            title=title,
            subject=request.subject.strip(),
            is_active=True,
            last_message_at=datetime.utcnow(),
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def _build_session_title(self, question: str) -> str:
        cleaned = re.sub(r"\s+", " ", question.strip())
        return cleaned[:24]

    def _should_refresh_session_title(self, title: str) -> bool:
        if is_placeholder_session_title(title):
            return True
        return looks_like_unreadable_text(title)

    def _save_message(
        self,
        session_id: int,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        model_used: str = "",
    ) -> ChatMessage | None:
        if self.db is None:
            return None

        message = ChatMessage(
            session_id=session_id,
            role=role,
            content=content,
            model_used=model_used,
            metadata_json=metadata or {},
        )
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)
        return message

    def _get_message_history(self, session_id: int, limit: int = 30) -> list[dict[str, Any]]:
        if self.db is None:
            return []

        messages = (
            self.db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": msg.id,
                "role": msg.role,
                "content": msg.content,
                "model_used": msg.model_used,
                "metadata": msg.metadata_json or {},
                "created_at": to_utc_isoformat(msg.created_at),
            }
            for msg in messages
        ]

    def _build_conversation_context(
        self,
        request: QARequest,
        history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        question = request.question.strip()
        previous_history = history[:-1] if history and history[-1]["role"] == "user" else history
        last_assistant = next((item for item in reversed(previous_history) if item["role"] == "assistant"), None)
        last_assistant_meta = last_assistant.get("metadata", {}) if isinstance(last_assistant, dict) else {}
        latest_resource = (
            last_assistant_meta.get("generated_resource")
            if isinstance(last_assistant_meta.get("generated_resource"), dict)
            else None
        )
        latest_exercises = (
            last_assistant_meta.get("generated_exercises")
            if isinstance(last_assistant_meta.get("generated_exercises"), dict)
            else None
        )
        inferred_knowledge_point = self._infer_knowledge_point(
            request=request,
            question=question,
            previous_history=previous_history,
            latest_resource=latest_resource,
            latest_exercises=latest_exercises,
        )
        follow_up = self._is_follow_up(question, previous_history)
        effective_question = question
        if follow_up and inferred_knowledge_point:
            effective_question = f"继续围绕 {inferred_knowledge_point}：{question}"
        elif follow_up and previous_history:
            previous_user = next((item for item in reversed(previous_history) if item["role"] == "user"), None)
            if previous_user is not None:
                effective_question = f"基于上一轮“{previous_user['content']}”继续：{question}"

        article = self.knowledge_base.get_article(effective_question) or self.knowledge_base.get_article(
            inferred_knowledge_point
        )
        if article is None:
            matches = self.knowledge_base.search_by_keywords(effective_question, top_k=1)
            article = matches[0] if matches else None

        intent = self._detect_intent_mode(
            request=request,
            question=question,
            previous_history=previous_history,
            article=article,
            inferred_knowledge_point=inferred_knowledge_point,
        )
        subject = inferred_knowledge_point or request.subject.strip() or (article.subject if article is not None else "")
        return {
            "question": question,
            "effective_question": effective_question,
            "follow_up": follow_up,
            "intent_mode": intent["mode"],
            "intent_reason": intent["reason"],
            "knowledge_point": inferred_knowledge_point,
            "subject": subject,
            "article": article,
            "previous_history": previous_history,
            "latest_resource": latest_resource,
            "latest_exercises": latest_exercises,
            "exercise_count": self._extract_exercise_count(question),
        }

    def _infer_knowledge_point(
        self,
        *,
        request: QARequest,
        question: str,
        previous_history: list[dict[str, Any]],
        latest_resource: dict[str, Any] | None,
        latest_exercises: dict[str, Any] | None,
    ) -> str:
        for item in request.current_knowledge_points:
            cleaned = str(item).strip()
            if cleaned:
                return cleaned

        explicit_topic = self._extract_explicit_topic_from_question(question)
        if explicit_topic:
            return explicit_topic

        article = self.knowledge_base.get_article(question)
        if article is not None:
            return article.title

        matches = self.knowledge_base.search_by_keywords(question, top_k=1)
        if matches:
            return matches[0].title

        if latest_resource and str(latest_resource.get("knowledge_point") or "").strip():
            return str(latest_resource["knowledge_point"]).strip()
        if latest_exercises and str(latest_exercises.get("knowledge_point") or "").strip():
            return str(latest_exercises["knowledge_point"]).strip()

        for item in reversed(previous_history):
            metadata = item.get("metadata", {})
            inferred = str(metadata.get("inferred_knowledge_point") or "").strip()
            if inferred:
                return inferred
            points = metadata.get("current_knowledge_points")
            if isinstance(points, list):
                for point in points:
                    cleaned = str(point).strip()
                    if cleaned:
                        return cleaned

        return request.subject.strip()

    def _extract_explicit_topic_from_question(self, question: str) -> str:
        normalized = re.sub(r"\s+", "", question)
        if not normalized:
            return ""

        suffix_markers = (
            "的配套练习题",
            "的练习题",
            "配套练习题",
            "练习题目",
            "练习题",
            "配套练习",
            "练习",
            "习题",
            "题目",
            "课件",
            "讲义",
            "知识点",
            "总结",
            "资料",
        )
        prefix_markers = (
            "学习",
            "复习",
            "讲解",
            "解释",
            "补充",
            "生成",
            "整理",
            "总结",
            "关于",
            "围绕",
            "帮我",
            "给我",
            "请帮我",
            "我想学",
            "我要学",
            "我想要",
            "我要",
        )

        for suffix in suffix_markers:
            if suffix in normalized:
                candidate = normalized.split(suffix, 1)[0]
                cleaned = self._clean_explicit_topic(candidate)
                if cleaned:
                    return cleaned

        for prefix in prefix_markers:
            if prefix in normalized:
                candidate = normalized.split(prefix, 1)[1]
                cleaned = self._clean_explicit_topic(candidate)
                if cleaned:
                    return cleaned
        return ""

    def _clean_explicit_topic(self, topic: str) -> str:
        cleaned = topic.strip("“”\"'：:，。！？,.!?；; ")
        prefixes = (
            "我要",
            "我想",
            "想要",
            "请帮我",
            "帮我",
            "给我",
            "来点",
            "来几道",
            "来",
            "继续围绕",
            "围绕",
            "关于",
            "学习",
            "复习",
            "讲解",
            "解释",
            "补充",
            "生成",
            "整理",
            "总结",
        )
        suffixes = (
            "的配套练习题",
            "的练习题",
            "配套练习题",
            "练习题目",
            "练习题",
            "配套练习",
            "练习",
            "习题",
            "题目",
            "课件",
            "讲义",
            "知识点",
            "总结",
            "资料",
            "相关",
            "方面",
            "内容",
        )
        changed = True
        while changed and cleaned:
            changed = False
            for prefix in prefixes:
                if cleaned.startswith(prefix):
                    cleaned = cleaned[len(prefix) :].strip("“”\"'：:，。！？,.!?；; ")
                    changed = True
            for suffix in suffixes:
                if cleaned.endswith(suffix):
                    cleaned = cleaned[: -len(suffix)].strip("“”\"'：:，。！？,.!?；; ")
                    changed = True
        if len(cleaned) < 2 or cleaned in self.GENERIC_TOPIC_VALUES:
            return ""
        return cleaned[:24]

    def _is_follow_up(self, question: str, previous_history: list[dict[str, Any]]) -> bool:
        if not previous_history:
            return False

        lowered = question.lower()
        if any(token in question or token in lowered for token in self.FOLLOW_UP_HINTS):
            return True

        short_question = len(question) <= 18
        has_learning_keyword = any(token in lowered or token in question for token in self.LEARNING_TOKENS)
        return short_question and not has_learning_keyword

    def _classify_question(self, conversation: dict[str, Any]) -> dict[str, Any]:
        question = str(conversation["question"])
        lowered = question.lower()
        article = conversation.get("article")

        needs_exercise_generation = any(token in question or token in lowered for token in self.EXERCISE_HINTS)
        needs_resource_generation = any(token in question or token in lowered for token in self.RESOURCE_HINTS)
        explicitly_wants_explanation = any(token in question or token in lowered for token in self.EXPLAIN_HINTS)
        wants_explanation = explicitly_wants_explanation or (
            not needs_exercise_generation
            and not needs_resource_generation
            and (bool(article) or conversation["follow_up"])
        )
        has_learning_context = conversation.get("intent_mode") == "learning"
        needs_web_search = self.web_search.should_search(question) and not has_learning_context
        return {
            "has_learning_context": has_learning_context,
            "needs_exercise_generation": needs_exercise_generation,
            "needs_resource_generation": needs_resource_generation,
            "wants_explanation": wants_explanation,
            "needs_web_search": needs_web_search,
            "is_follow_up": conversation["follow_up"],
            "intent_reason": conversation.get("intent_reason", ""),
        }

    @classmethod
    def detect_intent_mode_from_request(cls, request: QARequest) -> dict[str, str]:
        service = cls(db=None)
        article = service.knowledge_base.get_article(request.question.strip())
        inferred_knowledge_point = next(
            (str(item).strip() for item in request.current_knowledge_points if str(item).strip()),
            "",
        ) or service._extract_explicit_topic_from_question(request.question.strip())
        return service._detect_intent_mode(
            request=request,
            question=request.question.strip(),
            previous_history=[],
            article=article,
            inferred_knowledge_point=inferred_knowledge_point,
        )

    @classmethod
    def infer_route_knowledge_point_from_request(cls, request: QARequest) -> str:
        service = cls(db=None)
        for item in request.current_knowledge_points:
            cleaned = str(item).strip()
            if cleaned:
                return cleaned

        question = request.question.strip()
        explicit_topic = service._extract_explicit_topic_from_question(question)
        if explicit_topic:
            return explicit_topic

        article = service.knowledge_base.get_article(question)
        if article is not None:
            return article.title

        matches = service.knowledge_base.search_by_keywords(question, top_k=1)
        if matches:
            return matches[0].title
        subject = request.subject.strip()
        if subject:
            return subject
        return ""

    def _detect_intent_mode(
        self,
        *,
        request: QARequest,
        question: str,
        previous_history: list[dict[str, Any]],
        article: KnowledgeArticle | None,
        inferred_knowledge_point: str,
    ) -> dict[str, str]:
        lowered = question.lower()
        has_current_points = any(str(item).strip() for item in request.current_knowledge_points)
        has_learning_keywords = any(token in question or token in lowered for token in self.LEARNING_TOKENS)
        has_generation_keywords = any(
            token in question or token in lowered
            for token in (*self.EXERCISE_HINTS, *self.RESOURCE_HINTS, *self.EXPLAIN_HINTS)
        )
        has_general_keywords = any(token in question or token in lowered for token in self.GENERAL_HINTS)
        has_recent_general_signal = self.web_search.should_search(question) or has_general_keywords
        subject = request.subject.strip()
        subject_looks_learning = bool(subject) and (
            self.knowledge_base.get_article(subject) is not None
            or any(token in subject.lower() or token in subject for token in self.LEARNING_TOKENS)
        )
        previous_learning_context = any(
            str((item.get("metadata") or {}).get("inferred_knowledge_point") or "").strip()
            or any(str(point).strip() for point in ((item.get("metadata") or {}).get("current_knowledge_points") or []))
            for item in previous_history
            if item.get("role") == "assistant"
        )

        if has_current_points:
            return {"mode": "learning", "reason": "current_knowledge_points provided"}
        if has_generation_keywords:
            return {"mode": "learning", "reason": "learning generation/explanation keywords detected"}
        if article is not None:
            return {"mode": "learning", "reason": "knowledge base article matched"}
        if inferred_knowledge_point and not has_recent_general_signal:
            return {"mode": "learning", "reason": "explicit learning topic detected"}
        if previous_learning_context and self._is_follow_up(question, previous_history):
            return {"mode": "learning", "reason": "follow-up continues prior learning context"}
        if has_recent_general_signal and not has_learning_keywords:
            return {"mode": "general", "reason": "general realtime/open-domain query detected"}
        if subject_looks_learning and not has_recent_general_signal:
            return {"mode": "learning", "reason": "subject suggests academic context"}
        if has_learning_keywords:
            return {"mode": "learning", "reason": "learning keywords detected"}
        return {"mode": "general", "reason": "defaulted to general conversation"}

    def _build_context_snippets(
        self,
        conversation: dict[str, Any],
        flags: dict[str, Any],
    ) -> tuple[list[str], float]:
        snippets: list[str] = []
        confidence = 0.45
        article: KnowledgeArticle | None = conversation.get("article")

        if article is not None:
            snippets.append(f"{article.title}: {article.summary}")
            snippets.extend(f"核心概念：{item}" for item in article.concepts[:3])
            snippets.extend(f"易错点：{item}" for item in article.mistakes[:2])
            confidence = 0.82
        else:
            matches = self.knowledge_base.search_by_keywords(conversation["effective_question"], top_k=3)
            for matched in matches:
                snippets.append(f"{matched.title}: {matched.summary}")
            if matches:
                confidence = 0.7

        if flags["needs_web_search"]:
            web_snippets = self.web_search.search(conversation["question"], max_results=4)
            snippets.extend(web_snippets)
            if web_snippets:
                confidence = max(confidence, 0.78)

        deduped: list[str] = []
        seen: set[str] = set()
        for item in snippets:
            cleaned = re.sub(r"\s+", " ", item).strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            deduped.append(cleaned)
        return deduped[:6], confidence

    def _maybe_generate_resource(
        self,
        request: QARequest,
        conversation: dict[str, Any],
        flags: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not flags["needs_resource_generation"]:
            return None

        knowledge_point = str(conversation["knowledge_point"] or request.subject).strip()
        if not knowledge_point:
            return None

        try:
            user_id = int(request.student_id)
        except ValueError:
            user_id = 0

        learner_profile = self._extract_learner_profile(request.learning_history)
        try:
            return ResourceGenerationService().generate_courseware_with_plan(
                ResourceGenerationRequest(
                    user_id=user_id,
                    knowledge_point=knowledge_point,
                    resource_style=self._infer_resource_style(request.question),
                    resource_type="courseware",
                    learner_profile=learner_profile,
                    request_text=conversation["effective_question"],
                )
            )
        except Exception:
            return None

    def _maybe_generate_exercises(
        self,
        request: QARequest,
        conversation: dict[str, Any],
        flags: dict[str, Any],
        generated_resource: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if not flags["needs_exercise_generation"]:
            return None

        knowledge_point = str(conversation["knowledge_point"] or request.subject).strip()
        if not knowledge_point:
            return None

        try:
            user_id = int(request.student_id)
        except ValueError:
            user_id = 0

        learner_profile = self._extract_learner_profile(request.learning_history)
        learner_profile = {
            **learner_profile,
            "difficulty_preference": self._infer_difficulty_preference(request.question),
            "qa_follow_up": True,
        }
        courseware_content = str(
            (generated_resource or {}).get("content")
            or (conversation.get("latest_resource") or {}).get("content")
            or ""
        )
        try:
            return ExerciseGenerationService().generate_exercises(
                ExerciseGenerationRequest(
                    user_id=user_id,
                    knowledge_point=knowledge_point,
                    resource_style=self._infer_resource_style(request.question),
                    learner_profile=learner_profile,
                    exercise_count=conversation["exercise_count"],
                    question_type_counts={},
                    generation_mode=self._infer_generation_mode(request.question),
                    courseware_content=courseware_content,
                )
            )
        except Exception:
            return None

    def _build_learning_response(
        self,
        *,
        conversation: dict[str, Any],
        flags: dict[str, Any],
        generated_resource: dict[str, Any] | None,
        generated_exercises: dict[str, Any] | None,
    ) -> str:
        article: KnowledgeArticle | None = conversation.get("article")
        knowledge_point = str(conversation["knowledge_point"] or "当前知识点").strip()
        lines: list[str] = []

        if conversation["follow_up"]:
            lines.append(f"我们接着上文继续，当前还是围绕“{knowledge_point}”。")
        else:
            lines.append(f"这次我们先围绕“{knowledge_point}”来处理你的需求。")

        if flags["wants_explanation"] and article is not None:
            lines.append("")
            lines.append("知识点补充：")
            lines.extend(f"1. {item}" for item in self._select_focus_points(conversation, article))

            if article.examples:
                lines.append("")
                lines.append("理解抓手：")
                lines.append(article.examples[0])

            if article.mistakes:
                lines.append("")
                lines.append("容易出错的地方：")
                lines.extend(f"- {item}" for item in article.mistakes[:2])
        elif flags["wants_explanation"]:
            lines.append("")
            lines.append("我先根据当前上下文继续讲解；如果你愿意，也可以再补一句更具体的知识点名称，我能讲得更聚焦。")

        if generated_resource is not None:
            lines.append("")
            title = str(
                generated_resource.get("generation_plan", {}).get("title_suggestion")
                or generated_resource.get("knowledge_point")
                or "课件"
            )
            lines.append(f"已根据当前上下文生成课件：{title}。你可以直接看下方课件卡片。")

        if generated_exercises is not None:
            lines.append("")
            summary = str(generated_exercises.get("summary") or "").strip()
            count = len(generated_exercises.get("exercises") or [])
            lines.append(f"已生成 {count} 道配套习题。{summary}".strip())

        if flags["needs_resource_generation"] and generated_resource is None:
            lines.append("")
            lines.append("我识别到你这轮想生成课件，但这次没有成功返回课件结果。你可以直接重试一次，我会继续沿用当前知识点。")

        if flags["needs_exercise_generation"] and generated_exercises is None:
            lines.append("")
            lines.append("我识别到你这轮想生成配套习题，但这次没有成功返回习题结果。你可以直接重试一次，我会继续沿用当前知识点。")

        if (
            generated_resource is None
            and generated_exercises is None
            and not flags["needs_resource_generation"]
            and not flags["needs_exercise_generation"]
        ):
            lines.append("")
            lines.append("如果你愿意，我下一轮可以继续为这个知识点生成课件、配套习题，或者只展开某一部分。")

        return "\n".join(lines).strip()

    def _build_general_response(
        self,
        question: str,
        context_snippets: list[str],
        follow_up: bool,
        history: list[dict[str, Any]],
    ) -> tuple[str, str]:
        current_info = self._build_current_time_response(question)
        if current_info is not None:
            return current_info, "qa_realtime"

        llm_response = self._generate_general_response_with_llm(
            question=question,
            context_snippets=context_snippets,
            history=history,
            follow_up=follow_up,
        )
        if llm_response:
            return llm_response, "qa_general_llm"

        if context_snippets:
            intro = "我先基于当前检索到的信息回答：" if not follow_up else "我接着上文补充回答："
            return "\n".join([intro, question, "", *[f"- {item}" for item in context_snippets[:4]]]), "qa_general_grounded"
        return (
            f"我理解你的问题是：{question}\n\n"
            "当前我还缺少足够可靠的上下文来给出更确定的回答。"
            "如果你补充具体对象、时间、范围，或者说明这是哪门课里的内容，我可以继续细化。"
        ), "qa_general_fallback"

    def _build_current_time_response(self, question: str) -> str | None:
        if not any(token in question for token in self.CURRENT_TIME_HINTS):
            return None

        now = datetime.now(self.SHANGHAI_TZ)
        weekday_names = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        parts: list[str] = []

        if any(token in question for token in ("今天是", "几号", "日期")):
            parts.append(f"今天是 {now.year} 年 {now.month} 月 {now.day} 日。")
        if any(token in question for token in ("星期几", "周几")):
            parts.append(f"今天是 {weekday_names[now.weekday()]}。")
        if any(token in question for token in ("几点", "时间")):
            parts.append(f"现在时间是 {now.strftime('%H:%M')}。")

        if not parts:
            return None
        return "\n".join(parts)

    def _generate_general_response_with_llm(
        self,
        *,
        question: str,
        context_snippets: list[str],
        history: list[dict[str, Any]],
        follow_up: bool,
    ) -> str | None:
        try:
            from langchain_core.output_parsers import StrOutputParser
            from langchain_core.prompts import ChatPromptTemplate

            llm = self.llm_factory.build_chat_model(temperature=0.25)
            context_text = "\n".join(f"- {item}" for item in context_snippets[:5]) if context_snippets else "无"
            system_prompt = (
                "你是一个通用中文助手，同时兼顾日常问答、信息解释和轻量陪伴式交流。\n"
                "要求：\n"
                "1. 先直接回答用户问题，不要强行转成学习诊断。\n"
                "2. 如果提供了参考片段，优先利用这些片段，但不要逐字复述。\n"
                "3. 如果信息不完整或可能过时，要明确说明不确定点。\n"
                "4. 语气自然、清楚、友好。"
            )
            messages: list[tuple[str, str]] = [("system", system_prompt)]
            for msg in history[-6:]:
                role = str(msg.get("role") or "")
                content = str(msg.get("content") or "").strip()
                if role in {"user", "assistant"} and content:
                    messages.append((role, content))
            prompt_text = (
                f"参考信息：\n{context_text}\n\n"
                f"当前问题：{question}\n\n"
                f"{'这是连续追问，请结合上下文。' if follow_up else '请直接自然作答。'}"
            )
            messages.append(("user", prompt_text))

            prompt = ChatPromptTemplate.from_messages(messages)
            chain = prompt | llm | StrOutputParser()
            response = chain.invoke({})
            cleaned = str(response).strip()
            return cleaned or None
        except Exception:
            return None

    def _generate_learning_response_with_llm(
        self,
        *,
        conversation: dict[str, Any],
        flags: dict[str, Any],
        context_snippets: list[str],
        generated_resource: dict[str, Any] | None,
        generated_exercises: dict[str, Any] | None,
        history: list[dict[str, Any]],
    ) -> str | None:
        try:
            from langchain_core.output_parsers import StrOutputParser
            from langchain_core.prompts import ChatPromptTemplate

            llm = self.llm_factory.build_chat_model(temperature=0.2)
            knowledge_point = str(conversation.get("knowledge_point") or conversation.get("subject") or "当前知识点")
            article: KnowledgeArticle | None = conversation.get("article")
            focus_notes: list[str] = []
            if article is not None:
                focus_notes.append(f"知识点：{article.title}")
                focus_notes.append(f"摘要：{article.summary}")
                focus_notes.extend(f"核心概念：{item}" for item in article.concepts[:3])
                focus_notes.extend(f"易错点：{item}" for item in article.mistakes[:2])
            focus_notes.extend(f"参考：{item}" for item in context_snippets[:4])
            if generated_resource is not None:
                resource_title = str(
                    generated_resource.get("generation_plan", {}).get("title_suggestion")
                    or generated_resource.get("knowledge_point")
                    or "课件"
                )
                focus_notes.append(f"已生成课件：{resource_title}")
            if generated_exercises is not None:
                exercise_count = len(generated_exercises.get("exercises") or [])
                focus_notes.append(f"已生成习题：{exercise_count} 道")

            system_prompt = (
                "你是一个中文学习辅导助手。\n"
                "要求：\n"
                "1. 先直接回应学生当前需求，必要时先讲解再给下一步建议。\n"
                "2. 如果已经生成课件或习题，要自然告诉学生可以继续使用下方结果。\n"
                "3. 解释要尽量具体，避免空泛套话。\n"
                "4. 不要输出 JSON，只输出面向学生的自然语言回答。"
            )
            messages: list[tuple[str, str]] = [("system", system_prompt)]
            for msg in history[-6:]:
                role = str(msg.get("role") or "")
                content = str(msg.get("content") or "").strip()
                if role in {"user", "assistant"} and content:
                    messages.append((role, content))
            user_prompt = (
                f"当前知识点：{knowledge_point}\n"
                f"学生问题：{conversation['question']}\n"
                f"是否追问：{'是' if conversation['follow_up'] else '否'}\n"
                f"是否需要讲解：{'是' if flags['wants_explanation'] else '否'}\n"
                f"是否需要课件：{'是' if flags['needs_resource_generation'] else '否'}\n"
                f"是否需要习题：{'是' if flags['needs_exercise_generation'] else '否'}\n"
                f"参考信息：\n" + ("\n".join(f"- {item}" for item in focus_notes) if focus_notes else "- 无")
            )
            messages.append(("user", user_prompt))

            prompt = ChatPromptTemplate.from_messages(messages)
            chain = prompt | llm | StrOutputParser()
            response = chain.invoke({})
            cleaned = str(response).strip()
            return cleaned or None
        except Exception:
            return None

    def _select_focus_points(self, conversation: dict[str, Any], article: KnowledgeArticle) -> list[str]:
        question = str(conversation["question"])
        if "应用" in question or "例题" in question:
            items = [*article.applications[:2], *article.concepts[:2]]
        elif "易错" in question or "错误" in question:
            items = [*article.mistakes[:3], *article.concepts[:1]]
        elif "知识点" in question or "概念" in question or "补充" in question:
            items = [*article.concepts[:4]]
        else:
            items = [*article.concepts[:3], *article.checks[:1]]
        return [item for item in items if str(item).strip()][:4]

    def _build_structured_analysis(
        self,
        *,
        request: QARequest,
        conversation: dict[str, Any],
        flags: dict[str, Any],
        generated_resource: dict[str, Any] | None,
        generated_exercises: dict[str, Any] | None,
    ) -> dict[str, Any]:
        knowledge_point = str(conversation["knowledge_point"] or request.subject or "当前主题").strip()
        article: KnowledgeArticle | None = conversation.get("article")
        recommendations: list[dict[str, str]] = []

        if not flags["has_learning_context"]:
            return {
                "identified_knowledge_gaps": [],
                "misconceptions": [],
                "difficulty_level": "foundation",
                "learning_state": "已完成通用问答",
                "recommended_next_knowledge_points": [],
                "learning_route_updates": [],
                "resource_recommendations": [],
                "study_suggestions": [],
                "mistake_book_update": {
                    "should_add": False,
                    "question_summary": request.question[:120],
                    "wrong_reason": "",
                    "correct_approach": "",
                },
            }

        if generated_resource is not None:
            recommendations.append(
                {
                    "resource_type": "courseware",
                    "title": str(
                        generated_resource.get("generation_plan", {}).get("title_suggestion")
                        or f"{knowledge_point} 课件"
                    ),
                    "reason": "已按当前上下文生成课件，可继续围绕其中某个部分展开。",
                }
            )
        if generated_exercises is not None:
            recommendations.append(
                {
                    "resource_type": "exercise",
                    "title": f"{knowledge_point} 配套习题",
                    "reason": "已生成练习题，可继续做更难版本、错题变式或专项训练。",
                }
            )
        if not recommendations and knowledge_point:
            recommendations.append(
                {
                    "resource_type": "qa_followup",
                    "title": f"{knowledge_point} 继续追问",
                    "reason": "可以继续追问例题、易错点、应用题或知识点之间的联系。",
                }
            )

        identified_gaps = request.current_knowledge_points[:2]
        if not identified_gaps and knowledge_point:
            identified_gaps = [knowledge_point]

        misconceptions = article.mistakes[:2] if article is not None else []
        next_points = article.checks[:2] if article is not None else []
        if generated_exercises is not None and not next_points:
            next_points = ["先完成当前习题，再根据错题继续加练"]

        return {
            "identified_knowledge_gaps": identified_gaps,
            "misconceptions": misconceptions,
            "difficulty_level": self._infer_analysis_difficulty(request.question),
            "learning_state": self._build_learning_state(conversation, flags, generated_resource, generated_exercises),
            "recommended_next_knowledge_points": next_points,
            "learning_route_updates": [
                {
                    "knowledge_point": knowledge_point or "当前主题",
                    "priority": "high" if conversation["follow_up"] else "medium",
                    "action": self._build_route_action(flags),
                    "reason": "本轮需求同时包含讲解、内容生成或继续追问，需要保持上下文连续。",
                }
            ],
            "resource_recommendations": recommendations,
            "study_suggestions": self._build_study_suggestions(article, generated_resource, generated_exercises),
            "mistake_book_update": {
                "should_add": bool(request.student_answer.strip() or request.wrong_answer.strip()),
                "question_summary": request.question[:120],
                "wrong_reason": request.wrong_answer.strip(),
                "correct_approach": "先补足知识点解释，再用配套练习验证理解并回看易错点。",
            },
        }

    def _build_learning_state(
        self,
        conversation: dict[str, Any],
        flags: dict[str, Any],
        generated_resource: dict[str, Any] | None,
        generated_exercises: dict[str, Any] | None,
    ) -> str:
        parts = []
        if conversation["follow_up"]:
            parts.append("本轮已承接上一轮上下文")
        if flags["wants_explanation"]:
            parts.append("已补充知识点说明")
        if generated_resource is not None:
            parts.append("已生成课件")
        if generated_exercises is not None:
            parts.append("已生成习题")
        return "，".join(parts) or "已完成本轮问答"

    def _build_route_action(self, flags: dict[str, Any]) -> str:
        actions: list[str] = []
        if flags["wants_explanation"]:
            actions.append("先继续讲清当前知识点")
        if flags["needs_resource_generation"]:
            actions.append("配套生成课件")
        if flags["needs_exercise_generation"]:
            actions.append("配套生成习题")
        return "，再".join(actions) if actions else "继续围绕当前问题追问"

    def _build_study_suggestions(
        self,
        article: KnowledgeArticle | None,
        generated_resource: dict[str, Any] | None,
        generated_exercises: dict[str, Any] | None,
    ) -> list[str]:
        suggestions: list[str] = []
        if article is not None:
            suggestions.append("先把核心概念和易错点对照看一遍，再继续做题。")
            if article.checks:
                suggestions.append(f"试着用自己的话回答：{article.checks[0]}")
        if generated_resource is not None:
            suggestions.append("先看课件里的概念和例子，再去做后面的习题。")
        if generated_exercises is not None:
            suggestions.append("做完习题后，把错题按概念错误、步骤错误、审题错误分类。")
        if not suggestions:
            suggestions.append("补充更具体的知识点名称后，我可以把建议细化到更可执行。")
        return suggestions[:4]

    def _infer_resource_style(self, question: str) -> str:
        if any(token in question for token in ("提纲", "简洁", "速记", "总结")):
            return "concise"
        if any(token in question for token in ("案例", "应用", "场景")):
            return "case"
        return "interactive"

    def _infer_generation_mode(self, question: str) -> str:
        if any(token in question for token in ("自测", "测试", "测验")):
            return "self_test"
        if any(token in question for token in ("错题", "薄弱", "纠错", "更正")):
            return "remedial"
        return "practice"

    def _infer_difficulty_preference(self, question: str) -> str:
        if any(token in question for token in ("更难", "提高", "拔高", "进阶")):
            return "advanced"
        if any(token in question for token in ("基础", "入门", "简单")):
            return "foundation"
        return "intermediate"

    def _infer_analysis_difficulty(self, question: str) -> str:
        if any(token in question for token in ("更难", "拔高", "综合", "应用")):
            return "advanced"
        if any(token in question for token in ("基础", "入门", "简单")):
            return "foundation"
        return "intermediate"

    def _extract_exercise_count(self, question: str) -> int:
        match = re.search(r"(\d+)\s*道", question)
        if match:
            value = int(match.group(1))
            return max(3, min(value, 10))
        return 5

    def _extract_learner_profile(self, learning_history: dict[str, Any]) -> dict[str, Any]:
        profile = learning_history.get("learner_profile")
        return dict(profile) if isinstance(profile, dict) else {}

    def _validate_response(
        self,
        candidate: dict[str, Any],
        request: QARequest,
        history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        try:
            return QAResponse(**candidate).model_dump()
        except Exception:
            fallback = {
                "student_id": request.student_id,
                "subject": request.subject,
                "grade": request.grade,
                "session_id": request.session_id,
                "session_title": request.session_title,
                "student_response": f"我已经收到你的问题：{request.question}",
                "structured_analysis": {
                    "identified_knowledge_gaps": request.current_knowledge_points[:1],
                    "misconceptions": [],
                    "difficulty_level": "foundation",
                    "learning_state": "已返回保底答复",
                    "recommended_next_knowledge_points": [],
                    "learning_route_updates": [],
                    "resource_recommendations": [],
                    "study_suggestions": ["可以继续补充更具体的知识点或要求，我会接着当前对话继续。"],
                    "mistake_book_update": {
                        "should_add": False,
                        "question_summary": request.question[:120],
                        "wrong_reason": "",
                        "correct_approach": "",
                    },
                },
                "message_history": history,
                "context_snippets": [],
                "confidence": 0.3,
                "generated_exercises": None,
                "generated_resource": None,
            }
            return QAResponse(**fallback).model_dump()
