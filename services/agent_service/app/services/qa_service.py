"""QA service for open-domain answering plus learning-aware analysis."""

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

    LEARNING_TOKENS = (
        "python",
        "循环",
        "for",
        "while",
        "if",
        "编程",
        "代码",
        "算法",
        "函数",
        "知识点",
        "题目",
        "错题",
        "作业",
        "学习",
        "语法",
    )

    WEATHER_TOKENS = ("天气", "温度", "下雨", "晴", "阴", "风力")

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

    def _classify_question(self, request: QARequest) -> dict[str, Any]:
        question = request.question.strip().lower()
        has_wrong_context = bool(request.student_answer.strip() or request.wrong_answer.strip())
        has_learning_context = any(token in question for token in self.LEARNING_TOKENS)
        is_weather = any(token in question for token in self.WEATHER_TOKENS)
        is_review = has_wrong_context or any(token in question for token in ("为什么错", "错在哪", "改错", "解析", "讲解这题"))
        should_analyze = has_learning_context or has_wrong_context
        should_add_mistake = bool(
            has_wrong_context and (has_learning_context or any(token in question for token in ("错题", "作业", "题目", "答案")))
        )
        return {
            "has_learning_context": has_learning_context,
            "has_wrong_context": has_wrong_context,
            "is_weather": is_weather,
            "is_review": is_review,
            "should_analyze": should_analyze,
            "should_add_mistake": should_add_mistake,
        }

    def _pick_target_knowledge(self, request: QARequest, flags: dict[str, Any]) -> str:
        if request.current_knowledge_points:
            return request.current_knowledge_points[0]

        question = request.question.strip()
        article = self.knowledge_base.get_article(question)
        if article is not None:
            return article.title

        if flags["is_weather"]:
            return "通用问答"
        if flags["has_learning_context"]:
            return "当前学习问题"
        return "通用提问"

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

    def _build_direct_answer(
        self,
        request: QARequest,
        grounding_text: str,
        flags: dict[str, Any],
    ) -> str | None:
        """Generate a direct answer from the LLM without restricting question scope."""

        try:
            from langchain_core.output_parsers import StrOutputParser
            from langchain_core.prompts import ChatPromptTemplate

            llm = self.llm_factory.build_chat_model(temperature=0.35)
            system_prompt = (
                "你是一位经验丰富、非常耐心的老师和答疑助手。"
                "请先根据用户真实问题直接回答，不要强行限定在当前学习知识点里。"
                "如果问题是学习问题，就用教学方式讲清楚；如果问题是一般问答，也正常回答。"
                "不要输出 JSON。"
            )
            human_prompt = (
                "学科: {subject}\n"
                "年级: {grade}\n"
                "问题: {question}\n"
                "学生已有答案: {student_answer}\n"
                "学生错误答案: {wrong_answer}\n"
                "当前知识点: {current_knowledge_points}\n"
                "参考知识: {grounding_text}\n"
                "附加要求:\n"
                "1. 先围绕问题本身作答。\n"
                "2. 如果是学习类问题，请给具体讲解、必要例子、常见错误和后续建议。\n"
                "3. 如果不是学习类问题，不要硬套知识漏洞分析语气。\n"
                "4. 如果信息不足，明确说明还需要什么信息。\n"
            )
            prompt = ChatPromptTemplate.from_messages([("system", system_prompt), ("human", human_prompt)])
            chain = prompt | llm | StrOutputParser()
            result = chain.invoke(
                {
                    "subject": request.subject,
                    "grade": request.grade,
                    "question": request.question,
                    "student_answer": request.student_answer,
                    "wrong_answer": request.wrong_answer,
                    "current_knowledge_points": request.current_knowledge_points,
                    "grounding_text": grounding_text[:1200] if flags["has_learning_context"] else "",
                }
            )
            answer = result.strip()
            return answer or None
        except Exception:
            return None

    def _try_invoke_llm(self, request: QARequest) -> dict[str, Any] | None:
        flags = self._classify_question(request)
        target = self._pick_target_knowledge(request, flags)
        article = self.knowledge_base.get_article(target if flags["has_learning_context"] else request.question)
        grounding_text = self._build_grounding_text(article)
        direct_answer = self._build_direct_answer(request, grounding_text, flags)

        if not flags["should_analyze"]:
            if not direct_answer:
                return None
            fallback = self._build_fallback_response(request)
            fallback["student_response"] = direct_answer
            return fallback

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
                            "3. 是否加入错题本要根据问题内容、是否存在错误答案、是否属于错题复盘来判断，不能一律加入。\n"
                            "4. 如果问题并不明显暴露知识漏洞，identified_knowledge_gaps 可以为空。\n"
                            "5. 不要输出多余说明。\n"
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
        flags = self._classify_question(request)
        target_knowledge = self._pick_target_knowledge(request, flags)
        is_general_question = not flags["should_analyze"]

        if is_general_question:
            student_response = (
                f"你刚刚问的是：{request.question}\n\n"
                "这个问题本身不一定属于错题复盘或知识漏洞诊断场景。"
                "如果你只是想做一般问答，我会先按问题本身回答；"
                "如果你希望我从学习角度继续分析，也可以补充你的作答思路、错误答案或题目背景。"
            )
            identified_knowledge_gaps: list[str] = []
            misconceptions = ["当前问题未明显暴露具体知识漏洞，暂不强行归因。"]
            learning_state = "当前更像一般提问或信息型问答，暂不据此判定为明确学习薄弱点。"
            route_updates: list[dict[str, str]] = []
            recommendations: list[dict[str, str]] = []
            study_suggestions = [
                "如果你希望继续做学习分析，可以补充题目背景、你的思路或错误答案。",
                "如果只是一般问答，可以继续直接追问细节。",
            ]
        else:
            student_response = (
                f"你提到的问题是：{request.question}\n\n"
                f"这个问题目前更接近“{target_knowledge}”相关的学习提问。"
                "我会优先从问题本身讲解，再结合你有没有提供错误答案、作答过程，判断是否需要继续做错题分析。"
            )
            identified_knowledge_gaps = request.current_knowledge_points[:2] or [target_knowledge]
            misconceptions = [
                "可能把核心概念、适用条件和执行步骤混在一起理解。",
                "可能更关注答案结果，忽略中间推理过程。",
            ]
            learning_state = "学生能够主动提问，说明有学习投入，但当前理解还需要结合具体题目或过程进一步确认。"
            route_updates = [
                {
                    "knowledge_point": target_knowledge,
                    "priority": "medium",
                    "action": "先听讲解，再根据是否有错误作答决定要不要进入专项复盘。",
                    "reason": "当前提问有学习语境，但是否属于明确错题复盘还需要更多上下文。",
                }
            ]
            recommendations = [
                {
                    "resource_type": "courseware",
                    "title": f"{target_knowledge} 精讲课件",
                    "reason": "先把概念和典型错误讲清楚，再决定是否需要进入错题训练。",
                }
            ]
            study_suggestions = [
                "如果你是做题时卡住了，可以补充原题、你的思路或错误答案。",
                "如果你只是概念没想明白，可以继续追问具体例子或边界情况。",
                "先区分这是“概念不清”还是“做题出错”，再决定后续练习方向。",
            ]

        wrong_reason = request.wrong_answer or request.student_answer or "当前未提供具体错误作答内容。"
        return {
            "student_id": request.student_id,
            "subject": request.subject,
            "grade": request.grade,
            "student_response": student_response,
            "structured_analysis": {
                "identified_knowledge_gaps": identified_knowledge_gaps,
                "misconceptions": misconceptions,
                "difficulty_level": "intermediate" if flags["should_analyze"] else "foundation",
                "learning_state": learning_state,
                "recommended_next_knowledge_points": request.current_knowledge_points[:3] if flags["should_analyze"] else [],
                "learning_route_updates": route_updates,
                "resource_recommendations": recommendations,
                "study_suggestions": study_suggestions,
                "mistake_book_update": {
                    "should_add": flags["should_add_mistake"],
                    "question_summary": request.question[:120],
                    "wrong_reason": wrong_reason,
                    "correct_approach": (
                        "如果这是错题复盘，请补充错误答案或完整思路，再定位具体错因。"
                        if not flags["should_add_mistake"]
                        else "结合错误答案和正确思路逐步对照，提炼成可复用的改错规则。"
                    ),
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
