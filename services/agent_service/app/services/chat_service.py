"""Chat service with large-small model collaboration for continuous conversations."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from common.config import get_settings
from common.models.learning import ChatMessage, ChatSession
from common.schemas.agent import ChatMessageInput, ChatResponse, ChatSessionCreate, ChatSessionDetail, ChatSessionSummary
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
            title=request.title or "新对话",
            subject=request.subject,
            is_active=True,
            last_message_at=datetime.utcnow(),
        )
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
            created_at=assistant_message.created_at.isoformat(),
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
        try:
            from langchain_core.output_parsers import StrOutputParser
            from langchain_core.prompts import ChatPromptTemplate

            # Use Haiku or smaller model
            llm = self.llm_factory.build_chat_model(temperature=0.2, model_name="haiku")

            kb_context = "\n\n".join(kb_result.get("snippets", []))

            system_prompt = (
                "你是一个智能学习助手。基于提供的知识库内容回答学生问题。\n"
                "要求：\n"
                "1. 直接回答问题，语言简洁清晰\n"
                "2. 优先使用知识库内容，不要编造信息\n"
                "3. 如果知识库内容不足，明确说明并建议学生提供更多上下文\n"
                "4. 保持友好和鼓励的语气\n"
            )

            messages = [("system", system_prompt)]

            # Add conversation history
            for msg in history[-6:]:  # Last 3 rounds
                messages.append((msg["role"], msg["content"]))

            # Add current question with KB context
            current_prompt = f"知识库参考：\n{kb_context}\n\n学生问题：{question}\n\n请基于知识库内容回答问题。"
            messages.append(("user", current_prompt))

            prompt = ChatPromptTemplate.from_messages(messages)
            chain = prompt | llm | StrOutputParser()

            response = chain.invoke({})
            return response.strip(), "small_model"

        except Exception as e:
            # Fallback to simple KB summary
            if kb_result["found"]:
                content = f"根据知识库内容，关于「{question}」：\n\n"
                content += "\n\n".join(kb_result["snippets"])
                content += "\n\n需要更详细的解释吗？"
                return (content, "fallback")
            return "抱歉，我在知识库中没有找到相关内容。请提供更多上下文，或者换个方式提问。", "fallback"

    def _generate_with_large_model(
        self,
        question: str,
        history: list[dict[str, str]],
        kb_result: dict[str, Any],
        context: dict[str, Any],
    ) -> tuple[str, str]:
        """Generate comprehensive answer using large model."""
        try:
            from langchain_core.output_parsers import StrOutputParser
            from langchain_core.prompts import ChatPromptTemplate

            # Use Sonnet or Opus
            llm = self.llm_factory.build_chat_model(temperature=0.3)

            kb_context = "\n\n".join(kb_result.get("snippets", [])) if kb_result["found"] else "无相关知识库内容"

            system_prompt = (
                "你是一个智能学习助手，擅长深入讲解和分析。\n"
                "要求：\n"
                "1. 提供全面、深入的回答\n"
                "2. 结合知识库内容（如有）和你的知识\n"
                "3. 使用例子、类比帮助理解\n"
                "4. 指出常见误区和易错点\n"
                "5. 提供学习建议和下一步方向\n"
                "6. 保持友好、鼓励的语气\n"
            )

            messages = [("system", system_prompt)]

            # Add conversation history
            for msg in history[-8:]:  # Last 4 rounds
                messages.append((msg["role"], msg["content"]))

            # Add current question with context
            current_prompt = f"知识库参考：\n{kb_context}\n\n学生问题：{question}\n\n请提供详细的讲解和分析。"
            messages.append(("user", current_prompt))

            prompt = ChatPromptTemplate.from_messages(messages)
            chain = prompt | llm | StrOutputParser()

            response = chain.invoke({})
            return response.strip(), "large_model"

        except Exception:
            # Fallback
            content = f"关于「{question}」，这是一个需要深入分析的问题。\n\n"
            content += "请允许我从以下几个方面来解答：\n"
            content += "1. 核心概念和原理\n"
            content += "2. 实际应用和例子\n"
            content += "3. 常见误区\n\n"
            content += "由于系统原因，完整回答暂时无法生成。请稍后重试或分解问题提问。"
            return (content, "fallback")

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
        messages = [
            ChatMessageItem(
                id=msg.id,
                role=msg.role,
                content=msg.content,
                model_used=msg.model_used,
                metadata=msg.metadata_json,
                created_at=msg.created_at.isoformat(),
            )
            for msg in session.messages
        ]

        return ChatSessionDetail(
            id=session.id,
            user_id=session.user_id,
            title=session.title,
            subject=session.subject,
            is_active=session.is_active,
            created_at=session.created_at.isoformat(),
            last_message_at=session.last_message_at.isoformat(),
            message_count=len(messages),
            messages=messages,
        )

    def _session_to_summary(self, session: ChatSession) -> ChatSessionSummary:
        """Convert session to summary response."""
        message_count = self.db.query(ChatMessage).filter(ChatMessage.session_id == session.id).count()

        return ChatSessionSummary(
            id=session.id,
            user_id=session.user_id,
            title=session.title,
            subject=session.subject,
            is_active=session.is_active,
            created_at=session.created_at.isoformat(),
            last_message_at=session.last_message_at.isoformat(),
            message_count=message_count,
        )
