"""QA service for open-domain answering plus learning-aware analysis."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from common.config import get_settings
from common.schemas.agent import QARequest, QAResponse
from services.agent_service.app.services.knowledge_base import KnowledgeBaseService
from services.agent_service.app.services.llm_factory import LLMFactory
from services.agent_service.app.services.web_search_service import WebSearchService


def _load_prompt_template(filename: str) -> str:
    prompt_path = Path("prompts") / filename
    return prompt_path.read_text(encoding="utf-8")


class QAService:
    """Provide direct answers for general questions and tutoring for learning questions."""

    LEARNING_TOKENS = (
        "python",
        "java",
        "c++",
        "算法",
        "编程",
        "代码",
        "函数",
        "语法",
        "数学",
        "物理",
        "化学",
        "英语",
        "题目",
        "错题",
        "作业",
        "考试",
        "学习",
        "知识点",
        "证明",
        "推导",
        "作文",
        "阅读理解",
    )
    REVIEW_TOKENS = ("为什么错", "错在哪", "改错", "解析", "讲解这题", "订正", "复盘")

    def __init__(self) -> None:
        self.settings = get_settings()
        self.prompt_template = _load_prompt_template("qa.md")
        self.knowledge_base = KnowledgeBaseService()
        self.llm_factory = LLMFactory(self.settings)
        self.web_search = WebSearchService(self.settings)

    def analyze_question(self, request: QARequest) -> dict[str, Any]:
        """Return a student-readable answer with system-readable structured analysis."""

        flags = self._classify_question(request)
        context_snippets, confidence = self._build_context_snippets(request, flags)
        llm_result = self._try_invoke_llm(request, flags, context_snippets, confidence)
        candidate = (
            llm_result
            if llm_result is not None
            else self._build_fallback_response(request, flags, context_snippets, confidence)
        )
        return self._validate_response(candidate, request)

    def _classify_question(self, request: QARequest) -> dict[str, Any]:
        question = request.question.strip()
        normalized = question.lower()
        has_wrong_context = bool(request.student_answer.strip() or request.wrong_answer.strip())
        has_learning_context = self._has_learning_context(request, question, normalized)
        is_review = has_wrong_context or any(token in question for token in self.REVIEW_TOKENS)
        is_general_question = not has_learning_context and not is_review and not has_wrong_context
        should_analyze = has_learning_context or has_wrong_context or is_review
        should_add_mistake = bool(has_wrong_context and (has_learning_context or is_review))
        needs_web_search = self.web_search.should_search(question) or is_general_question
        return {
            "has_learning_context": has_learning_context,
            "has_wrong_context": has_wrong_context,
            "is_review": is_review,
            "is_general_question": is_general_question,
            "should_analyze": should_analyze,
            "should_add_mistake": should_add_mistake,
            "needs_web_search": needs_web_search,
        }

    def _has_learning_context(self, request: QARequest, question: str, normalized: str) -> bool:
        if any(token in normalized or token in question for token in self.LEARNING_TOKENS):
            return True

        if self._question_matches_knowledge_points(question, request.current_knowledge_points):
            return True

        return False

    def _question_matches_knowledge_points(self, question: str, knowledge_points: list[str]) -> bool:
        if not knowledge_points:
            return False

        for item in knowledge_points:
            cleaned = item.strip()
            if len(cleaned) >= 2 and (cleaned in question or question in cleaned):
                return True

            fragments = [part.strip() for part in re.split(r"[\s,，、/·()（）\-]+", cleaned) if len(part.strip()) >= 2]
            if any(fragment in question for fragment in fragments):
                return True

        return False

    def _pick_target_knowledge(self, request: QARequest, flags: dict[str, Any]) -> str:
        if flags["has_learning_context"] and request.current_knowledge_points:
            return request.current_knowledge_points[0]

        article = self.knowledge_base.get_article(request.question.strip())
        if article is not None:
            return article.title

        if flags["has_learning_context"]:
            return "当前学习问题"
        return "通用问答"

    def _build_context_snippets(self, request: QARequest, flags: dict[str, Any]) -> tuple[list[str], float]:
        """Mix local knowledge-base context with lightweight web context when needed."""

        snippets: list[str] = []
        confidence = 0.42

        if flags["has_learning_context"]:
            articles = self.knowledge_base.search_by_keywords(request.question, top_k=3)
            snippets.extend(f"{article.title}: {article.summary[:120]}" for article in articles)
            if snippets:
                confidence = max(confidence, 0.72)

        if flags["needs_web_search"]:
            web_snippets = self.web_search.search(request.question, max_results=5)
            snippets.extend(web_snippets)
            if web_snippets:
                confidence = max(confidence, 0.9)

        deduped: list[str] = []
        seen: set[str] = set()
        for item in snippets:
            cleaned = item.strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            deduped.append(cleaned)

        return deduped[:6], confidence

    def _build_grounding_text(self, article: Any, context_snippets: list[str]) -> str:
        sections: list[str] = []
        if article is not None:
            sections.append(
                "\n".join(
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
            )
        if context_snippets:
            sections.append("参考信息:\n" + "\n".join(f"- {item}" for item in context_snippets))
        return "\n\n".join(sections)

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

            llm = self.llm_factory.build_chat_model(temperature=0.3)
            system_prompt = (
                f"你是一个通用智能问答助手，同时也能承担学习辅导角色。今天的日期是 {date.today().isoformat()}。\n"
                "你的任务是优先回答用户真正问的问题，而不是把问题强行限定为学习类。\n"
                "如果提供了联网检索参考，请优先基于参考回答，不要声称自己不能联网、不能查资料、"
                "或者只能回答学习问题。\n"
                "如果问题属于学习类，请讲解清楚；如果属于通用生活、科技、时事、天气、工具使用等问题，"
                "也请直接正常回答。\n"
                "如果参考信息不足以支持确定结论，要明确说明不确定点，并告诉用户还缺什么信息。\n"
                "不要输出 JSON。"
            )
            human_prompt = (
                "学科: {subject}\n"
                "年级: {grade}\n"
                "问题: {question}\n"
                "学生已有答案: {student_answer}\n"
                "学生错误答案: {wrong_answer}\n"
                "当前知识点: {current_knowledge_points}\n"
                "参考信息: {grounding_text}\n"
                "额外要求:\n"
                "1. 先直接回答问题本身。\n"
                "2. 学习类问题要有讲解、示例、易错点和下一步建议。\n"
                "3. 非学习类问题不要套用学习分析腔调。\n"
                "4. 涉及今天、实时、最新、价格、天气、新闻等信息时，优先依据参考信息回答。\n"
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
                    "grounding_text": grounding_text[:1800] if grounding_text else "",
                }
            )
            answer = result.strip()
            return answer or None
        except Exception:
            return None

    def _try_invoke_llm(
        self,
        request: QARequest,
        flags: dict[str, Any],
        context_snippets: list[str],
        confidence: float,
    ) -> dict[str, Any] | None:
        target = self._pick_target_knowledge(request, flags)
        article = self.knowledge_base.get_article(target if flags["has_learning_context"] else request.question)
        grounding_text = self._build_grounding_text(article, context_snippets)
        direct_answer = self._build_direct_answer(request, grounding_text, flags)

        if not flags["should_analyze"]:
            if not direct_answer:
                return None
            fallback = self._build_fallback_response(request, flags, context_snippets, confidence)
            fallback["student_response"] = direct_answer
            return fallback

        try:
            from langchain_core.output_parsers import StrOutputParser
            from langchain_core.prompts import ChatPromptTemplate

            llm = self.llm_factory.build_chat_model(temperature=0.22)
            prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", self.prompt_template),
                    (
                        "human",
                        (
                            "请根据以下学生信息完成回答与分析。\n"
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
                            "1. 先输出 student_response: 后接自然语言回答。\n"
                            "2. 再输出 structured_analysis: 后接一个合法 JSON 对象。\n"
                            "3. 如果这是通用问答，不要凭空编造知识漏洞；相关字段可以留空。\n"
                            "4. 是否加入错题本要根据是否真的存在错误作答和学习复盘场景来判断。\n"
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
                    "grounding_text": grounding_text[:2000],
                }
            )
            parsed = self._parse_llm_output(raw)
            if direct_answer:
                parsed["student_response"] = direct_answer
            if not parsed["student_response"].strip():
                return None
            structured_analysis = self._hydrate_structured_analysis(parsed["structured_analysis"], request, flags)
            return {
                "student_id": request.student_id,
                "subject": request.subject,
                "grade": request.grade,
                "student_response": parsed["student_response"],
                "structured_analysis": structured_analysis,
                "context_snippets": context_snippets,
                "confidence": confidence,
            }
        except Exception:
            if not direct_answer:
                return None
            fallback = self._build_fallback_response(request, flags, context_snippets, confidence)
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

        try:
            structured_analysis = self._extract_structured_analysis(raw)
        except Exception:
            structured_analysis = {}

        if not student_response and raw.strip():
            stripped = raw.strip()
            if "```" in stripped:
                stripped = stripped.split("```", 1)[0].strip()
            student_response = stripped.split("{", 1)[0].replace("student_response:", "").strip()

        if not structured_analysis:
            raise ValueError("structured analysis missing")

        return {
            "student_response": student_response,
            "structured_analysis": self._normalize_structured_analysis(structured_analysis),
        }

    def _extract_structured_analysis(self, raw: str) -> dict[str, Any]:
        json_match = re.search(r"structured_analysis\s*:\s*(\{.*\})", raw, flags=re.S | re.I)
        if json_match:
            return self._extract_json(json_match.group(1))

        fenced_blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", raw, flags=re.S | re.I)
        for block in reversed(fenced_blocks):
            try:
                return self._extract_json(block)
            except Exception:
                continue

        decoder = json.JSONDecoder()
        for match in reversed(list(re.finditer(r"\{", raw))):
            try:
                parsed, _ = decoder.raw_decode(raw[match.start() :].strip())
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed

        raise ValueError("structured analysis missing")

    def _normalize_structured_analysis(self, analysis: dict[str, Any]) -> dict[str, Any]:
        gaps = analysis.get("identified_knowledge_gaps") or analysis.get("knowledge_gaps") or []
        misconceptions = analysis.get("misconceptions") or []
        next_points = analysis.get("recommended_next_knowledge_points") or analysis.get("next_knowledge_points") or []
        route_updates = self._normalize_learning_route_updates(analysis.get("learning_route_updates"))
        recommendations = self._normalize_resource_recommendations(analysis.get("resource_recommendations"))
        mistake_update = self._normalize_mistake_book_update(analysis.get("mistake_book_update"))

        return {
            "identified_knowledge_gaps": self._ensure_string_list(gaps),
            "misconceptions": self._ensure_string_list(misconceptions),
            "difficulty_level": self._normalize_difficulty_level(analysis.get("difficulty_level")),
            "learning_state": str(analysis.get("learning_state") or "已生成回答与分析。").strip(),
            "recommended_next_knowledge_points": self._ensure_string_list(next_points),
            "learning_route_updates": route_updates,
            "resource_recommendations": recommendations,
            "study_suggestions": self._ensure_string_list(analysis.get("study_suggestions")),
            "mistake_book_update": mistake_update,
        }

    def _hydrate_structured_analysis(
        self,
        analysis: dict[str, Any],
        request: QARequest,
        flags: dict[str, Any],
    ) -> dict[str, Any]:
        hydrated = dict(analysis)
        mistake_update = dict(hydrated.get("mistake_book_update") or {})
        mistake_update["should_add"] = bool(mistake_update.get("should_add"))
        mistake_update["question_summary"] = str(
            mistake_update.get("question_summary") or request.question[:120]
        ).strip()

        if mistake_update["should_add"] and not str(mistake_update.get("wrong_reason") or "").strip():
            mistake_update["wrong_reason"] = request.wrong_answer.strip() or request.student_answer.strip()

        if mistake_update["should_add"] and not str(mistake_update.get("correct_approach") or "").strip():
            mistake_update["correct_approach"] = "结合错误答案和正确思路逐步对照，提炼成可复用的改错规则。"

        if not mistake_update["should_add"] and not flags["should_add_mistake"]:
            mistake_update["wrong_reason"] = str(mistake_update.get("wrong_reason") or "").strip()
            mistake_update["correct_approach"] = str(mistake_update.get("correct_approach") or "").strip()

        hydrated["mistake_book_update"] = mistake_update
        return hydrated

    def _normalize_difficulty_level(self, raw_level: Any) -> str:
        normalized = str(raw_level or "foundation").strip().lower()
        mapping = {
            "beginner": "foundation",
            "easy": "foundation",
            "foundation": "foundation",
            "intermediate": "intermediate",
            "medium": "intermediate",
            "advanced": "advanced",
            "hard": "advanced",
        }
        return mapping.get(normalized, "foundation")

    def _normalize_learning_route_updates(self, raw_updates: Any) -> list[dict[str, str]]:
        if isinstance(raw_updates, dict):
            raw_updates = [raw_updates]
        if not isinstance(raw_updates, list):
            return []

        updates: list[dict[str, str]] = []
        for item in raw_updates:
            if not isinstance(item, dict):
                continue
            priority = str(item.get("priority") or "medium").strip().lower()
            if priority not in {"high", "medium", "low"}:
                priority = "medium"
            action = str(item.get("action") or item.get("adjustment") or item.get("suggestion") or "").strip()
            reason = str(item.get("reason") or item.get("why") or "").strip()
            knowledge_point = str(item.get("knowledge_point") or item.get("topic") or "当前问题").strip()
            if not action and not reason:
                continue
            updates.append(
                {
                    "knowledge_point": knowledge_point or "当前问题",
                    "priority": priority,
                    "action": action or "继续围绕当前问题补强。",
                    "reason": reason or "模型建议继续补充当前问题相关理解。",
                }
            )
        return updates

    def _normalize_resource_recommendations(self, raw_recommendations: Any) -> list[dict[str, str]]:
        if not isinstance(raw_recommendations, list):
            return []

        recommendations: list[dict[str, str]] = []
        type_mapping = {
            "courseware": "courseware",
            "video": "courseware",
            "article": "courseware",
            "interactive": "courseware",
            "tool": "courseware",
            "website": "courseware",
            "exercise": "exercise",
            "review": "review",
            "qa_followup": "qa_followup",
        }
        for item in raw_recommendations:
            if not isinstance(item, dict):
                continue
            raw_type = str(item.get("resource_type") or item.get("type") or "qa_followup").strip().lower()
            resource_type = type_mapping.get(raw_type, "qa_followup")
            title = str(item.get("title") or item.get("name") or "推荐资源").strip()
            reason = str(item.get("reason") or item.get("description") or "").strip()
            url = str(item.get("url") or "").strip()
            if url:
                reason = f"{reason} 参考链接: {url}".strip()
            if not title:
                continue
            recommendations.append(
                {
                    "resource_type": resource_type,
                    "title": title,
                    "reason": reason or "可作为当前问题的补充参考材料。",
                }
            )
        return recommendations

    def _normalize_mistake_book_update(self, raw_update: Any) -> dict[str, Any]:
        if not isinstance(raw_update, dict):
            raw_update = {}

        item = raw_update.get("item") if isinstance(raw_update.get("item"), dict) else {}
        question_summary = str(raw_update.get("question_summary") or item.get("question") or "").strip()
        wrong_reason = str(raw_update.get("wrong_reason") or item.get("wrong_answer") or "").strip()
        correct_approach = str(
            raw_update.get("correct_approach")
            or item.get("correct_concept")
            or item.get("correction")
            or ""
        ).strip()

        should_add = raw_update.get("should_add")
        if should_add is None:
            should_add = bool(wrong_reason or correct_approach)

        return {
            "should_add": bool(should_add),
            "question_summary": question_summary,
            "wrong_reason": wrong_reason,
            "correct_approach": correct_approach,
        }

    def _ensure_string_list(self, value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

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

    def _compose_general_fallback_answer(self, question: str, context_snippets: list[str]) -> str:
        if context_snippets:
            summary = "\n".join(f"{index + 1}. {item}" for index, item in enumerate(context_snippets[:4]))
            return (
                f"我先直接回答你的问题：{question}\n\n"
                "我已根据当前检索到的参考信息整理出以下要点：\n"
                f"{summary}\n\n"
                "如果你希望，我还可以继续把这些信息整理成更简洁的结论、对比表，或者继续追问某个细节。"
            )

        return (
            f"我理解你的问题是：{question}\n\n"
            "当前我没有拿到足够可靠的外部参考信息来给出确定答案。"
            "如果你补充更具体的对象、时间、地点或范围，我可以继续帮你细化。"
        )

    def _build_fallback_response(
        self,
        request: QARequest,
        flags: dict[str, Any],
        context_snippets: list[str],
        confidence: float,
    ) -> dict[str, Any]:
        target_knowledge = self._pick_target_knowledge(request, flags)

        if flags["is_general_question"]:
            student_response = self._compose_general_fallback_answer(request.question, context_snippets)
            structured_analysis = {
                "identified_knowledge_gaps": [],
                "misconceptions": [],
                "difficulty_level": "foundation",
                "learning_state": "本轮问题属于通用问答，未触发学习画像更新。",
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
        else:
            has_error_context = bool(request.student_answer.strip() or request.wrong_answer.strip())
            student_response = (
                f"你提到的问题是：{request.question}\n\n"
                f"这更接近“{target_knowledge}”相关的学习提问。"
                "我会优先围绕知识点本身讲清楚，再结合你是否提供了作答过程或错误答案，"
                "判断要不要进入错题复盘。"
            )
            structured_analysis = {
                "identified_knowledge_gaps": request.current_knowledge_points[:2] or [target_knowledge],
                "misconceptions": [
                    "可能把核心概念、适用条件和解题步骤混在一起理解。",
                    "可能更关注答案结果，而忽略了中间推理过程。",
                ],
                "difficulty_level": "intermediate",
                "learning_state": "当前问题具备明确学习语境，适合继续做讲解和按需分析。",
                "recommended_next_knowledge_points": request.current_knowledge_points[:3],
                "learning_route_updates": [
                    {
                        "knowledge_point": target_knowledge,
                        "priority": "medium",
                        "action": "先看讲解，再根据是否存在错误作答决定要不要进入专项复盘。",
                        "reason": "当前已识别为学习问题，但是否属于典型错题复盘还取决于更多作答上下文。",
                    }
                ],
                "resource_recommendations": [
                    {
                        "resource_type": "qa_followup",
                        "title": f"{target_knowledge} 追问讲解",
                        "reason": "可以继续追问例题、反例、易错点和边界条件。",
                    }
                ],
                "study_suggestions": [
                    "如果你是做题时卡住，可以补充原题、你的思路或错误答案。",
                    "如果你是概念没想明白，可以继续追问具体例子或反例。",
                    "先区分这是“概念不清”还是“做题出错”，再决定后续练习方向。",
                ],
                "mistake_book_update": {
                    "should_add": flags["should_add_mistake"],
                    "question_summary": request.question[:120],
                    "wrong_reason": request.wrong_answer or request.student_answer or "",
                    "correct_approach": (
                        "结合错误答案和正确思路逐步对照，提炼成可复用的改错规则。"
                        if has_error_context
                        else "如果后续补充你的作答过程，我可以继续帮你定位具体错因。"
                    ),
                },
            }

        return {
            "student_id": request.student_id,
            "subject": request.subject,
            "grade": request.grade,
            "student_response": student_response,
            "context_snippets": context_snippets,
            "confidence": confidence,
            "structured_analysis": structured_analysis,
        }

    def _validate_response(self, candidate: dict[str, Any], request: QARequest) -> dict[str, Any]:
        """Guarantee the router always returns a schema-valid payload."""

        try:
            return QAResponse(**candidate).model_dump()
        except Exception:
            flags = self._classify_question(request)
            context_snippets, confidence = self._build_context_snippets(request, flags)
            fallback = self._build_fallback_response(request, flags, context_snippets, confidence)
            return QAResponse(**fallback).model_dump()
