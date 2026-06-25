"""Chat service with large-small model collaboration for continuous conversations."""

from __future__ import annotations

import json
from datetime import datetime
import re
from typing import Any

from sqlalchemy.orm import Session

from common.config import get_settings
from common.models.learning import ChatMessage, ChatSession
from common.schemas.agent import (
    ChatMessageInput,
    ChatMessageItem,
    ChatResponse,
    ChatSessionCreate,
    ChatSessionDetail,
    ChatSessionSummary,
)
from common.utils.text import is_placeholder_session_title, looks_like_unreadable_text
from common.utils.time import to_utc_isoformat
from services.agent_service.app.services.knowledge_base import KnowledgeBaseService
from services.agent_service.app.services.llm_factory import LLMFactory


class ChatService:
    """Manage continuous conversations with large-small model collaboration."""


    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()
        self.knowledge_base = KnowledgeBaseService()
        self.llm_factory = LLMFactory(self.settings)

    def create_session(self, request: ChatSessionCreate) -> ChatSessionDetail:
        """Create a new chat session."""
        session = ChatSession(
            user_id=request.user_id,
            title=request.title or "",
            subject=request.subject,
            is_active=True,
            last_message_at=datetime.utcnow(),
        )
        session.title = self._normalize_session_title(session.title)
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)

        return self._session_to_detail(session)

    def get_session(self, session_id: int, user_id: int | None = None) -> ChatSessionDetail | None:
        """Get a chat session with its message history."""
        query = self.db.query(ChatSession).filter(ChatSession.id == session_id)
        if user_id is not None:
            query = query.filter(ChatSession.user_id == user_id)

        session = query.first()
        if session is None:
            return None

        self._repair_session_title(session)
        return self._session_to_detail(session)

    def list_sessions(self, user_id: int, limit: int = 50) -> list[ChatSessionSummary]:
        """List all chat sessions for a user."""
        sessions = (
            self.db.query(ChatSession)
            .filter(ChatSession.user_id == user_id)
            .order_by(ChatSession.last_message_at.desc())
            .limit(limit)
            .all()
        )

        return [self._session_to_summary(session) for session in sessions]

    def send_message(self, request: ChatMessageInput) -> ChatResponse:
        """Send a message and get AI response with large-small model collaboration."""
        # Verify session exists and belongs to user
        session = self.db.query(ChatSession).filter(
            ChatSession.id == request.session_id,
            ChatSession.user_id == request.user_id,
        ).first()

        if session is None:
            raise ValueError(f"Chat session {request.session_id} not found or access denied")

        self._repair_session_title(session, fallback_question=request.content)

        # Save user message
        user_message = ChatMessage(
            session_id=request.session_id,
            role="user",
            content=request.content,
            model_used="",
            metadata_json=request.context,
        )
        self.db.add(user_message)
        self.db.commit()

        # Get conversation history
        history = self._get_message_history(request.session_id, limit=10)

        # Step 1: Small model searches knowledge base
        kb_result = self._search_knowledge_base(request.content)

        # Step 2: Decide which model to use
        use_large_model = self._should_use_large_model(request.content, kb_result)

        # Step 3: Generate response
        if use_large_model:
            # Large model generates comprehensive answer
            response_content, model_used = self._generate_with_large_model(
                request.content,
                history,
                kb_result,
                request.context,
            )
            # Small model analyzes the response
            metadata = self._analyze_with_small_model(request.content, response_content)
        else:
            # Small model generates answer directly from knowledge base
            response_content, model_used = self._generate_with_small_model(
                request.content,
                history,
                kb_result,
            )
            metadata = {"source": "knowledge_base", "confidence": "high"}

        # Save assistant message
        assistant_message = ChatMessage(
            session_id=request.session_id,
            role="assistant",
            content=response_content,
            model_used=model_used,
            metadata_json=metadata,
        )
        self.db.add(assistant_message)

        # Update session last message time
        session.last_message_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(assistant_message)

        return ChatResponse(
            session_id=request.session_id,
            message_id=assistant_message.id,
            role="assistant",
            content=response_content,
            model_used=model_used,
            metadata=metadata,
            created_at=to_utc_isoformat(assistant_message.created_at),
        )

    def delete_session(self, session_id: int, user_id: int) -> bool:
        """Delete a chat session and all its messages."""
        session = self.db.query(ChatSession).filter(
            ChatSession.id == session_id,
            ChatSession.user_id == user_id,
        ).first()

        if session is None:
            return False

        self.db.delete(session)
        self.db.commit()
        return True

    def _get_message_history(self, session_id: int, limit: int = 10) -> list[dict[str, str]]:
        """Get recent message history for context."""
        messages = (
            self.db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(limit)
            .all()
        )

        # Reverse to chronological order
        messages = list(reversed(messages))

        return [
            {
                "role": msg.role,
                "content": msg.content,
            }
            for msg in messages
        ]

    def _search_knowledge_base(self, question: str) -> dict[str, Any]:
        """Search knowledge base for relevant content."""
        articles = self.knowledge_base.search_by_keywords(question, top_k=3)

        if not articles:
            return {
                "found": False,
                "articles": [],
                "snippets": [],
            }

        snippets = []
        for article in articles:
            snippet = f"**{article.title}**\n{article.summary[:200]}"
            if article.concepts:
                snippet += f"\n核心概念: {', '.join(article.concepts[:3])}"
            snippets.append(snippet)

        return {
            "found": True,
            "articles": [self.knowledge_base.article_to_dict(article) for article in articles],
            "snippets": snippets,
        }

    def _should_use_large_model(self, question: str, kb_result: dict[str, Any]) -> bool:
        """Decide whether to use large model based on question complexity and KB coverage."""
        # Use large model if:
        # 1. Knowledge base has no relevant content
        if not kb_result["found"]:
            return True

        # 2. Question is complex (has multiple clauses, asks for analysis/comparison)
        complex_keywords = ["为什么", "如何", "分析", "对比", "区别", "解释", "证明", "推导"]
        if any(keyword in question for keyword in complex_keywords):
            return True

        # 3. Question is long (likely needs comprehensive answer)
        if len(question) > 100:
            return True

        # Otherwise, use small model with KB content
        return False

    def _generate_with_small_model(
        self,
        question: str,
        history: list[dict[str, str]],
        kb_result: dict[str, Any],
    ) -> tuple[str, str]:
        """Generate answer using small model based on knowledge base."""
        from langchain_core.output_parsers import StrOutputParser
        from langchain_core.prompts import ChatPromptTemplate

        llm = self.llm_factory.build_chat_model(temperature=0.2, model_name="haiku")
        kb_context = "\n\n".join(kb_result.get("snippets", []))

        system_prompt = (
            "You are a learning assistant answering with knowledge-base grounding.\n"
            "Requirements:\n"
            "1. Answer directly and clearly.\n"
            "2. Prefer the provided knowledge-base context.\n"
            "3. If context is insufficient, say so explicitly.\n"
            "4. Keep a supportive tone.\n"
        )

        messages = [("system", system_prompt)]
        for msg in history[-6:]:
            messages.append((msg["role"], msg["content"]))

        current_prompt = (
            f"Knowledge base context:\n{kb_context}\n\n"
            f"Student question: {question}\n\n"
            "Answer based on the knowledge-base context."
        )
        messages.append(("user", current_prompt))

        prompt = ChatPromptTemplate.from_messages(messages)
        chain = prompt | llm | StrOutputParser()
        response = chain.invoke({})
        return response.strip(), "small_model"

    def _generate_with_large_model(
        self,
        question: str,
        history: list[dict[str, str]],
        kb_result: dict[str, Any],
        context: dict[str, Any],
    ) -> tuple[str, str]:
        """Generate comprehensive answer using large model."""
        from langchain_core.output_parsers import StrOutputParser
        from langchain_core.prompts import ChatPromptTemplate

        llm = self.llm_factory.build_chat_model(temperature=0.3)
        kb_context = "\n\n".join(kb_result.get("snippets", [])) if kb_result["found"] else "No knowledge-base context available."

        system_prompt = (
            "You are a learning assistant for deeper explanation and analysis.\n"
            "Requirements:\n"
            "1. Provide a comprehensive answer.\n"
            "2. Use the knowledge-base context when available.\n"
            "3. Use examples or analogies when helpful.\n"
            "4. Point out common misconceptions.\n"
            "5. Suggest next learning steps.\n"
            "6. Keep a supportive tone.\n"
        )

        messages = [("system", system_prompt)]
        for msg in history[-8:]:
            messages.append((msg["role"], msg["content"]))

        current_prompt = (
            f"Knowledge base context:\n{kb_context}\n\n"
            f"Student question: {question}\n\n"
            "Provide a detailed explanation and analysis."
        )
        messages.append(("user", current_prompt))

        prompt = ChatPromptTemplate.from_messages(messages)
        chain = prompt | llm | StrOutputParser()
        response = chain.invoke({})
        return response.strip(), "large_model"

    def _analyze_with_small_model(self, question: str, response: str) -> dict[str, Any]:
        """Use small model to analyze the large model's response."""
        try:
            from langchain_core.output_parsers import StrOutputParser
            from langchain_core.prompts import ChatPromptTemplate

            llm = self.llm_factory.build_chat_model(temperature=0.1, model_name="haiku")

            system_prompt = (
                "你是一个分析助手。分析大模型的回答质量。\n"
                "输出一个JSON对象，包含：\n"
                "- completeness: 完整性评分 (1-5)\n"
                "- clarity: 清晰度评分 (1-5)\n"
                "- key_points: 关键要点列表\n"
                "- suggestions: 学习建议列表\n"
            )

            prompt = ChatPromptTemplate.from_messages([
                ("system", system_prompt),
                ("user", f"问题：{question}\n\n回答：{response[:1000]}\n\n请分析这个回答。"),
            ])

            chain = prompt | llm | StrOutputParser()
            result = chain.invoke({})

            # Try to parse JSON
            try:
                # Extract JSON from response
                import re
                json_match = re.search(r'\{.*\}', result, re.DOTALL)
                if json_match:
                    analysis = json.loads(json_match.group())
                    return {
                        "source": "large_model_with_analysis",
                        "analysis": analysis,
                    }
            except Exception:
                pass

            return {
                "source": "large_model",
                "analysis_raw": result[:200],
            }

        except Exception:
            return {
                "source": "large_model",
                "confidence": "medium",
            }

    def _session_to_detail(self, session: ChatSession) -> ChatSessionDetail:
        """Convert session to detail response."""
        resolved_title = self._resolve_session_title(session)
        messages = [
            ChatMessageItem(
                id=msg.id,
                role=msg.role,
                content=msg.content,
                model_used=msg.model_used,
                metadata=msg.metadata_json,
                created_at=to_utc_isoformat(msg.created_at),
            )
            for msg in session.messages
        ]

        return ChatSessionDetail(
            id=session.id,
            user_id=session.user_id,
            title=resolved_title,
            subject=session.subject,
            is_active=session.is_active,
            created_at=to_utc_isoformat(session.created_at),
            last_message_at=to_utc_isoformat(session.last_message_at),
            message_count=len(messages),
            messages=messages,
        )

    def _session_to_summary(self, session: ChatSession) -> ChatSessionSummary:
        """Convert session to summary response."""
        resolved_title = self._resolve_session_title(session)
        message_count = self.db.query(ChatMessage).filter(ChatMessage.session_id == session.id).count()

        return ChatSessionSummary(
            id=session.id,
            user_id=session.user_id,
            title=resolved_title,
            subject=session.subject,
            is_active=session.is_active,
            created_at=to_utc_isoformat(session.created_at),
            last_message_at=to_utc_isoformat(session.last_message_at),
            message_count=message_count,
        )

    def _resolve_session_title(self, session: ChatSession) -> str:
        self._repair_session_title(session)
        return self._normalize_session_title(session.title)

    def _repair_session_title(self, session: ChatSession, fallback_question: str = "") -> None:
        normalized_title = self._normalize_session_title(session.title)
        if normalized_title != session.title and not self._looks_like_invalid_session_title(session.title):
            session.title = normalized_title
            self.db.commit()
            self.db.refresh(session)
            return

        if not self._looks_like_invalid_session_title(session.title):
            return

        rebuilt_title = self._build_title_from_messages(session)
        if not rebuilt_title and fallback_question.strip():
            rebuilt_title = self._build_title_from_question(fallback_question)
        if not rebuilt_title:
            rebuilt_title = ""

        if rebuilt_title != session.title:
            session.title = rebuilt_title
            self.db.commit()
            self.db.refresh(session)

    def _build_title_from_messages(self, session: ChatSession) -> str:
        first_user_message = (
            self.db.query(ChatMessage)
            .filter(ChatMessage.session_id == session.id, ChatMessage.role == "user")
            .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
            .first()
        )
        if first_user_message is None:
            return ""
        return self._build_title_from_question(first_user_message.content)

    def _build_title_from_question(self, question: str) -> str:
        cleaned = re.sub(r"\s+", " ", question.strip())
        return cleaned[:24]

    def _looks_like_invalid_session_title(self, title: str) -> bool:
        normalized = (title or "").strip()
        if not normalized:
            return True
        if is_placeholder_session_title(normalized):
            return False
        return looks_like_unreadable_text(normalized)

    def _normalize_session_title(self, title: str | None) -> str:
        normalized = (title or "").strip()
        if not normalized or self._looks_like_invalid_session_title(normalized):
            return ""
        return normalized

    def _looks_like_broken_title(self, title: str) -> bool:
        return self._looks_like_invalid_session_title(title)
