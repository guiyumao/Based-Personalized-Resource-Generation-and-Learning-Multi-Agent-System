"""QA service for student-facing tutoring and system-facing learning analysis."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from common.config import get_settings
from common.schemas.agent import QARequest, QAResponse
from services.agent_service.app.services.knowledge_base import KnowledgeBaseService
from services.agent_service.app.services.llm_factory import LLMFactory


def _load_prompt_template(filename: str) -> str:
    prompt_path = Path("prompts") / filename
    return prompt_path.read_text(encoding="utf-8")


class QAService:
    """Provide concrete teacher answers plus structured learning analysis."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.prompt_template = _load_prompt_template("qa.md")
        self.knowledge_base = KnowledgeBaseService()
        self.llm_factory = LLMFactory(self.settings)

    def analyze_question(self, request: QARequest) -> dict[str, Any]:
        """Return a student-readable answer with system-readable structured analysis."""

        llm_result = self._try_invoke_llm(request)
        candidate = llm_result if llm_result is not None else self._build_fallback_response(request)
        return self._validate_response(candidate, request)

    def _build_grounding_text(self, article: Any) -> str:
        if article is None:
            return ""
        return "\n".join(
            [
                f"主题: {article.title}",
                f"摘要: {article.summary}",
                "核心概念:",
                *[f"- {item}" for item in article.concepts[:4]],
                "常见错误:",
                *[f"- {item}" for item in article.mistakes[:4]],
                "自测点:",
                *[f"- {item}" for item in article.checks[:4]],
            ]
        )

    def _build_direct_answer(self, request: QARequest, grounding_text: str) -> str | None:
        """Generate a direct teaching answer from the LLM."""

        try:
            from langchain_core.output_parsers import StrOutputParser
            from langchain_core.prompts import ChatPromptTemplate

            llm = self.llm_factory.build_chat_model(temperature=0.35)
            prompt = ChatPromptTemplate.from_messages(
                [
                    (
                        "system",
                        (
                            "你是一位经验丰富、非常耐心的老师。"
                            "请直接回答学生问题，给出具体讲解、必要的最小示例、常见错误提醒和练习建议。"
                            "不要只做抽象分析，不要输出 JSON。"
                        ),
                    ),
                    (
                        "human",
                        (
                            "学科: {subject}\n"
                            "年级: {grade}\n"
                            "问题: {question}\n"
                            "学生已有答案: {student_answer}\n"
                            "学生错误答案: {wrong_answer}\n"
                            "当前知识点: {current_knowledge_points}\n"
                            "参考知识: {grounding_text}\n"
                            "要求:\n"
                            "1. 先直接解释学生真正没想明白的点。\n"
                            "2. 如果适合，用一个尽量小的例子一步一步讲。\n"
                            "3. 明确指出最容易犯错的地方。\n"
                            "4. 最后给 2-3 条具体练习建议。\n"
                        ),
                    ),
                ]
            )
            chain = prompt | llm | StrOutputParser()
            result = chain.invoke(
                {
                    "subject": request.subject,
                    "grade": request.grade,
                    "question": request.question,
                    "student_answer": request.student_answer,
                    "wrong_answer": request.wrong_answer,
                    "current_knowledge_points": request.current_knowledge_points,
                    "grounding_text": grounding_text[:1200],
                }
            )
            answer = result.strip()
            return answer or None
        except Exception:
            return None

    def _try_invoke_llm(self, request: QARequest) -> dict[str, Any] | None:
        target = "、".join(request.current_knowledge_points) or request.question
        article = self.knowledge_base.get_article(target)
        grounding_text = self._build_grounding_text(article)
        direct_answer = self._build_direct_answer(request, grounding_text)

        try:
            from langchain_core.output_parsers import StrOutputParser
            from langchain_core.prompts import ChatPromptTemplate

            llm = self.llm_factory.build_chat_model(temperature=0.25)
            prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", self.prompt_template),
                    (
                        "human",
                        (
                            "请根据以下学生信息完成答疑和学习分析。\n"
                            "student_id: {student_id}\n"
                            "subject: {subject}\n"
                            "grade: {grade}\n"
                            "question: {question}\n"
                            "student_answer: {student_answer}\n"
                            "wrong_answer: {wrong_answer}\n"
                            "current_knowledge_points: {current_knowledge_points}\n"
                            "learning_route: {learning_route}\n"
                            "error_book: {error_book}\n"
                            "learning_history: {learning_history}\n"
                            "grounding_text: {grounding_text}\n"
                            "输出要求:\n"
                            "1. 先输出 student_response: 后跟自然语言讲解。\n"
                            "2. 再输出 structured_analysis: 后跟一个合法 JSON 对象。\n"
                            "3. JSON 中必须包含 identified_knowledge_gaps, misconceptions, difficulty_level, learning_state,\n"
                            "recommended_next_knowledge_points, learning_route_updates, resource_recommendations,\n"
                            "study_suggestions, mistake_book_update。\n"
                            "4. 不要输出多余说明。\n"
                        ),
                    ),
                ]
            )
            chain = prompt | llm | StrOutputParser()
            raw = chain.invoke(
                {
                    "student_id": request.student_id,
                    "subject": request.subject,
                    "grade": request.grade,
                    "question": request.question,
                    "student_answer": request.student_answer,
                    "wrong_answer": request.wrong_answer,
                    "current_knowledge_points": request.current_knowledge_points,
                    "learning_route": request.learning_route,
                    "error_book": request.error_book,
                    "learning_history": request.learning_history,
                    "grounding_text": grounding_text[:1200],
                }
            )
            parsed = self._parse_llm_output(raw)
            if direct_answer:
                parsed["student_response"] = direct_answer
            if not parsed["student_response"].strip():
                return None
            return {
                "student_id": request.student_id,
                "subject": request.subject,
                "grade": request.grade,
                "student_response": parsed["student_response"],
                "structured_analysis": parsed["structured_analysis"],
            }
        except Exception:
            if not direct_answer:
                return None
            fallback = self._build_fallback_response(request)
            fallback["student_response"] = direct_answer
            return fallback

    def _parse_llm_output(self, raw: str) -> dict[str, Any]:
        student_response = ""
        structured_analysis: dict[str, Any] = {}

        response_match = re.search(
            r"student_response\s*:\s*(?P<body>.*?)(?:structured_analysis\s*:|\Z)",
            raw,
            flags=re.S | re.I,
        )
        if response_match:
            student_response = response_match.group("body").strip()

        json_match = re.search(r"structured_analysis\s*:\s*(\{.*\})", raw, flags=re.S | re.I)
        if json_match:
            structured_analysis = self._extract_json(json_match.group(1))

        if not student_response and raw.strip():
            student_response = raw.strip().split("{", 1)[0].replace("student_response:", "").strip()

        if not structured_analysis:
            raise ValueError("structured analysis missing")

        return {
            "student_response": student_response,
            "structured_analysis": structured_analysis,
        }

    def _extract_json(self, raw_json: str) -> dict[str, Any]:
        cleaned = raw_json.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned.removeprefix("```json").strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.removeprefix("```").strip()
        if cleaned.endswith("```"):
            cleaned = cleaned.removesuffix("```").strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", cleaned, flags=re.S)
            if not match:
                raise
            return json.loads(match.group(0))

    def _build_fallback_response(self, request: QARequest) -> dict[str, Any]:
        target_knowledge = request.current_knowledge_points[0] if request.current_knowledge_points else request.subject
        student_response = (
            f"你提到的问题是：{request.question}\n\n"
            f"这个问题主要围绕“{target_knowledge}”展开。先不要急着只记答案，"
            "我们要先想清楚它解决的是什么问题、什么时候使用、最容易错在哪里。\n\n"
            "如果你之前已经做过类似题但还是容易出错，通常不是完全不会，"
            "而是对概念边界、使用条件或步骤顺序还不够稳定。\n\n"
            "建议你先回到这个知识点最核心的定义，再对照自己的答案，"
            "看看到底是概念理解错了、步骤漏了，还是条件判断出了问题。"
            "如果你愿意，也可以继续把你的完整思路发出来，我可以继续带你逐步拆解。"
        )

        wrong_reason = request.wrong_answer or request.student_answer or "当前未提供具体错误作答内容。"
        return {
            "student_id": request.student_id,
            "subject": request.subject,
            "grade": request.grade,
            "student_response": student_response,
            "structured_analysis": {
                "identified_knowledge_gaps": request.current_knowledge_points[:2] or [target_knowledge],
                "misconceptions": [
                    "可能把知识点的定义、使用条件或适用场景混在一起理解。",
                    "可能更关注结果，忽略了中间推理步骤。",
                ],
                "difficulty_level": "intermediate",
                "learning_state": "学生能够主动提问，说明有学习投入，但当前理解还不够稳定，处于会接触但未真正内化的状态。",
                "recommended_next_knowledge_points": request.current_knowledge_points[:3] or [target_knowledge],
                "learning_route_updates": [
                    {
                        "knowledge_point": target_knowledge,
                        "priority": "high",
                        "action": "先补概念，再做 2-3 道同类基础题。",
                        "reason": "当前提问暴露出核心知识点理解还不牢固。",
                    }
                ],
                "resource_recommendations": [
                    {
                        "resource_type": "courseware",
                        "title": f"{target_knowledge} 概念精讲",
                        "reason": "先把概念、规则和典型错误讲清楚，再练习更有效。",
                    },
                    {
                        "resource_type": "exercise",
                        "title": f"{target_knowledge} 基础巩固题",
                        "reason": "通过少量同类题验证是否真正理解。",
                    },
                ],
                "study_suggestions": [
                    "先用自己的话复述这个知识点在解决什么问题。",
                    "把错误答案和正确思路逐步对照，找出具体分叉点。",
                    "做下一题时不只看对错，还要解释自己为什么这么做。",
                ],
                "mistake_book_update": {
                    "should_add": bool(request.wrong_answer or request.student_answer),
                    "question_summary": request.question[:120],
                    "wrong_reason": wrong_reason,
                    "correct_approach": "重新梳理题目考查的核心知识点，再按步骤完成推理和验证。",
                },
            },
        }

    def _validate_response(self, candidate: dict[str, Any], request: QARequest) -> dict[str, Any]:
        """Guarantee the router always returns a schema-valid payload."""

        try:
            return QAResponse(**candidate).model_dump()
        except Exception:
            fallback = self._build_fallback_response(request)
            return QAResponse(**fallback).model_dump()
