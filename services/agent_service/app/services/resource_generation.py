"""Resource generation service integrating RAG, LLM output, and real learner data."""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from common.config import get_settings
from common.db.session import SessionLocal
from common.models.learning import KnowledgePoint, Resource
from common.performance import get_current_trace, traced_invoke
from common.schemas.agent import ResourceGenerationRequest
from services.agent_service.app.services.knowledge_base import KnowledgeBaseService
from services.agent_service.app.services.llm_factory import LLMFactory
from services.agent_service.app.services.personalization import (
    LearnerPersonalizationSnapshot,
    PersonalizationService,
)
from services.agent_service.app.services.rag import ChromaRetriever

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _load_prompt_template(filename: str) -> str:
    prompt_path = Path("prompts") / filename
    return prompt_path.read_text(encoding="utf-8")


class ResourceGenerationError(RuntimeError):
    """Raised when the service cannot return a model-generated resource."""


class ResourceGenerationService:
    """Generate personalized educational resources."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.retriever = ChromaRetriever()
        self.knowledge_base = KnowledgeBaseService()
        self.llm_factory = LLMFactory(self.settings)
        self.prompt_template = _load_prompt_template("resource_gen.md")

    def _build_request_text(self, request: ResourceGenerationRequest) -> str:
        raw = request.request_text.strip()
        if raw:
            return raw
        return f"{request.knowledge_point} {request.resource_type} {request.resource_style}".strip()

    def _normalize_subject(self, subject: str) -> str:
        lowered = subject.strip().lower()
        exact_aliases = {
            "算法": "algorithms",
            "算法与数据结构": "algorithms",
            "人工智能": "artificial_intelligence",
            "c语言": "c_lang",
            "编译原理": "compilers",
            "计算机组成原理": "computer_architecture",
            "计算机网络": "computer_networks",
            "计算机科学": "computer_science",
            "c++": "cpp",
            "数据结构": "data_structures",
            "数据库": "databases",
            "深度学习": "deep_learning",
            "开发工具": "developer_tools",
            "离散数学": "discrete_math",
            "分布式系统": "distributed_systems",
            "线性代数": "linear_algebra",
            "机器学习": "machine_learning",
            "数学基础": "math",
            "操作系统": "operating_systems",
            "概率论": "probability",
            "python": "python",
            "java": "java",
            "软件工程": "software_eng",
            "web开发": "web_development",
        }
        if lowered in exact_aliases:
            return exact_aliases[lowered]
        aliases = (
            (("c语言", "c language"), "c_lang"),
            (("数据库", "mysql", "sql"), "databases"),
            (("算法",), "algorithms"),
            (("数学", "微积分", "概率"), "math"),
            (("软件工程", "spring", "http"), "software_eng"),
            (("计算机网络",), "computer_networks"),
        )
        for keywords, canonical in aliases:
            if any(keyword in lowered for keyword in keywords):
                return canonical
        return subject.strip()

    def _build_retrieval_filters(self, request: ResourceGenerationRequest) -> dict[str, Any]:
        filters: dict[str, Any] = {}
        if request.subject:
            filters["subject"] = self._normalize_subject(request.subject)
        if request.chapter:
            filters["chapter"] = request.chapter.strip()
        if request.section:
            filters["section"] = request.section.strip()
        if request.knowledge_point_id:
            filters["knowledge_point_id"] = request.knowledge_point_id.strip()
        if request.teaching_scope_id:
            filters["teacher_scope"] = request.teaching_scope_id.strip()
        return filters

    def _retrieval_limits(self, mode: str) -> tuple[int, int]:
        if mode == "fast":
            return 5, 3
        if mode == "quality":
            return 8, 5
        return max(5, self.settings.resource_rag_top_k), max(3, self.settings.rag_final_top_k)

    def _load_retrieval_context(
        self,
        request: ResourceGenerationRequest,
        *,
        knowledge_point: str,
        resource_type: str,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        supplied = request.retrieval_context
        if (
            isinstance(supplied, dict)
            and supplied.get("knowledge_base_version") == self.settings.knowledge_base_version
            and supplied.get("knowledge_point_id") in {"", request.knowledge_point_id, knowledge_point}
            and isinstance(supplied.get("retrieved_chunks"), list)
        ):
            chunks = list(supplied["retrieved_chunks"])
            trace = get_current_trace()
            if trace is not None:
                trace.record_retrieval(len(chunks), cache_hit=True, cache_type="retrieval_context")
            return chunks, supplied

        candidate_count, final_count = self._retrieval_limits(request.performance_mode)
        query = f"{knowledge_point} {resource_type}"
        if request.performance_mode != "fast" and self.retriever.should_rewrite_query(query):
            query = self.retriever.rewrite_query(query, context_hint=request.request_text)
        trace = get_current_trace()
        if trace is not None:
            manager = trace.stage("retrieval")
        else:
            from contextlib import nullcontext
            manager = nullcontext()
        with manager:
            context = self.retriever.build_context(
                query=query,
                knowledge_point_id=request.knowledge_point_id or knowledge_point,
                scope_id=request.teaching_scope_id or "public",
                filters=self._build_retrieval_filters(request),
                top_k=candidate_count,
                user_id=request.user_id,
                private=bool(request.teaching_scope_id),
            )
        chunks = self.retriever.rerank(
            query,
            context.retrieved_chunks,
            limit=final_count,
            mode=request.performance_mode,
        )
        payload = context.model_dump()
        payload["retrieved_chunks"] = chunks
        payload["source_ids"] = [str(item.get("id", "")) for item in chunks if item.get("id")]
        return chunks, payload

    def _normalize_knowledge_point(self, request: ResourceGenerationRequest, request_text: str) -> str:
        _ = request_text
        knowledge_point = request.knowledge_point.strip()
        if knowledge_point:
            return knowledge_point
        return "通用学习主题"

    def _infer_resource_type(self, request: ResourceGenerationRequest, request_text: str) -> str:
        if request.resource_type != "courseware":
            return request.resource_type

        lowered = request_text.lower()
        courseware_keywords = (
            "课件",
            "讲义",
            "教案",
            "课程",
            "courseware",
            "lesson",
            "slides",
        )
        keyword_map = {
            "exercise": ("练习", "刷题", "习题", "题目", "自测", "测试"),
            "notes": ("笔记", "总结", "速记", "提纲"),
            "exam": ("考试", "模拟", "试卷", "测验", "冲刺"),
        }
        matched_types = [
            resource_type
            for resource_type, keywords in keyword_map.items()
            if any(keyword in lowered for keyword in keywords)
        ]
        unique_matches = set(matched_types)
        if any(keyword in lowered for keyword in courseware_keywords) or len(unique_matches) > 1:
            return request.resource_type
        if len(unique_matches) == 1:
            return matched_types[0]
        return request.resource_type

    def _infer_difficulty(
        self,
        request_text: str,
        snapshot: LearnerPersonalizationSnapshot | None,
    ) -> str:
        lowered = request_text.lower()
        if any(keyword in lowered for keyword in ("入门", "基础", "零基础", "新手", "初学")):
            return "foundation"
        if any(keyword in lowered for keyword in ("拔高", "进阶", "综合", "面试", "项目", "实战", "迁移")):
            return "advanced"

        if snapshot is None:
            return "intermediate"
        if snapshot.answered_count and snapshot.mastery_score >= 78:
            return "advanced"
        if snapshot.answered_count < 3 or snapshot.mastery_score <= 45:
            return "foundation"
        return "intermediate"

    def _infer_target_word_count(
        self,
        request: ResourceGenerationRequest,
        resource_type: str,
        difficulty: str,
    ) -> int:
        if request.preferred_word_count is not None:
            return request.preferred_word_count

        defaults = {
            "courseware": {"foundation": 1500, "intermediate": 1300, "advanced": 1600},
            "exercise": {"foundation": 900, "intermediate": 1100, "advanced": 1300},
            "notes": {"foundation": 700, "intermediate": 850, "advanced": 1000},
            "exam": {"foundation": 1000, "intermediate": 1200, "advanced": 1400},
        }
        resource_defaults = defaults.get(resource_type, defaults["courseware"])
        return resource_defaults.get(difficulty, resource_defaults["intermediate"])

    def _build_outline(self, knowledge_point: str, resource_type: str, difficulty: str) -> list[str]:
        if resource_type == "exercise":
            return [
                f"{knowledge_point} 考点定位",
                "基础热身",
                "典型题拆解",
                "变式训练",
                "自查与订正提醒",
            ]
        if resource_type == "notes":
            return [
                f"{knowledge_point} 核心定义",
                "必记规则",
                "最小示例",
                "高频易错点",
                "复习清单",
            ]
        if resource_type == "exam":
            return [
                f"{knowledge_point} 高频考点",
                "题型分布",
                "答题策略",
                "典型陷阱",
                "冲刺自测",
            ]
        if difficulty == "advanced":
            return [
                "知识点回顾",
                "应用场景与迁移",
                "复杂案例拆解",
                "高频误区辨析",
                "综合自测",
            ]
        return [
            "课程导入",
            "核心概念",
            "重点难点",
            "示例讲解",
            "课堂小结",
            "自测与延伸",
        ]

    def _build_title_suggestion(self, knowledge_point: str, resource_type: str) -> str:
        suffix_map = {
            "courseware": "个性化课件",
            "exercise": "练习方案",
            "notes": "复习笔记",
            "exam": "测评卷",
        }
        return f"{knowledge_point}{suffix_map.get(resource_type, '学习资源')}"

    def _build_request_summary(
        self,
        request: ResourceGenerationRequest,
        knowledge_point: str,
        resource_type: str,
    ) -> str:
        request_text = re.sub(r"\s+", " ", request.request_text.strip())
        if request_text:
            return request_text[:160]
        return f"围绕 {knowledge_point} 生成一份 {resource_type} 类型的个性化学习资源。"

    def _build_personalization_hints(
        self,
        request: ResourceGenerationRequest,
        knowledge_point: str,
        snapshot: LearnerPersonalizationSnapshot | None,
    ) -> list[str]:
        hints: list[str] = []

        if snapshot is None or snapshot.answered_count == 0:
            hints.append(f"先用低门槛例子建立 {knowledge_point} 的基本理解，再逐步增加练习。")
        elif snapshot.mastery_score < 60:
            hints.append(f"当前对 {knowledge_point} 的掌握度偏弱，讲解要放慢节奏并强化步骤解释。")
        else:
            hints.append(f"当前对 {knowledge_point} 已有一定基础，可增加迁移应用和易错辨析。")

        if snapshot is not None:
            weak_types = snapshot.learner_profile.get("weak_question_types", [])
            if weak_types:
                hints.append(f"把 {', '.join(map(str, weak_types[:3]))} 题型作为重点训练对象。")
            if snapshot.recent_mistakes:
                latest = snapshot.recent_mistakes[-1]
                hints.append(
                    "显式回应最近一道错题暴露的问题："
                    f"{latest['question_type']} / {latest['difficulty']}。"
                )

        if request.resource_style == "concise":
            hints.append("优先输出规则、最小示例和快速自测，控制说明长度。")
        elif request.resource_style == "case":
            hints.append("用案例驱动结构组织内容，强调从题意到解法的迁移。")
        else:
            hints.append("保留课堂互动感，在关键处加入提问和自检提示。")

        if snapshot is not None:
            summaries = snapshot.learner_profile.get("profile_analysis_summaries", {})
            if isinstance(summaries, dict):
                for key in ("knowledgeBase", "cognitiveStyle", "errorPreference", "goalOrientation"):
                    summary = str(summaries.get(key) or "").strip()
                    if summary:
                        hints.append(f"结合深度画像结论：{summary}。")

        return hints[:4]

    def _build_generation_plan(
        self,
        request: ResourceGenerationRequest,
        snapshot: LearnerPersonalizationSnapshot | None = None,
        *,
        knowledge_point: str | None = None,
        resource_type: str | None = None,
    ) -> dict[str, Any]:
        request_text = self._build_request_text(request)
        resolved_knowledge_point = knowledge_point or self._normalize_knowledge_point(request, request_text)
        resolved_resource_type = resource_type or self._infer_resource_type(request, request_text)
        difficulty = self._infer_difficulty(request_text, snapshot)

        if snapshot is not None:
            analysis_source = "profile_enriched"
        elif request.request_text.strip():
            analysis_source = "request"
        else:
            analysis_source = "heuristic"

        return {
            "request_summary": self._build_request_summary(request, resolved_knowledge_point, resolved_resource_type),
            "knowledge_point": resolved_knowledge_point,
            "resource_type": resolved_resource_type,
            "resource_style": request.resource_style,
            "title_suggestion": self._build_title_suggestion(resolved_knowledge_point, resolved_resource_type),
            "suggested_outline": self._build_outline(resolved_knowledge_point, resolved_resource_type, difficulty),
            "target_word_count": self._infer_target_word_count(request, resolved_resource_type, difficulty),
            "difficulty": difficulty,
            "personalization_hints": self._build_personalization_hints(
                request,
                resolved_knowledge_point,
                snapshot,
            ),
            "analysis_source": analysis_source,
        }

    def _build_generation_plan_text(self, plan: dict[str, Any]) -> str:
        outline = "\n".join(f"- {item}" for item in plan.get("suggested_outline", []))
        hints = "\n".join(f"- {item}" for item in plan.get("personalization_hints", []))
        return (
            f"title: {plan['title_suggestion']}\n"
            f"difficulty: {plan['difficulty']}\n"
            f"target_word_count: {plan['target_word_count']}\n"
            f"analysis_source: {plan['analysis_source']}\n"
            f"outline:\n{outline or '- none'}\n"
            f"personalization_hints:\n{hints or '- none'}"
        )

    def _build_grounding_text(self, knowledge_point: str) -> str:
        article = self.knowledge_base.get_article(knowledge_point)
        if article is None:
            return ""

        sections = [
            f"主题：{article.title}",
            f"摘要：{article.summary}",
            "核心概念：",
            *[f"- {item}" for item in article.concepts[:4]],
            "关键语法：",
            *[f"- {item}" for item in article.syntax[:2]],
            "典型示例：",
            *[f"- {item}" for item in article.examples[:2]],
            "常见错误：",
            *[f"- {item}" for item in article.mistakes[:4]],
            "学完后自测：",
            *[f"- {item}" for item in article.checks[:4]],
        ]
        return "\n".join(sections)[:2000]

    def _build_personalization_payload(
        self,
        knowledge_point: str,
        snapshot: LearnerPersonalizationSnapshot,
    ) -> dict[str, Any]:
        recent_mistakes = [
            {
                "exercise_id": item["exercise_id"],
                "question_type": item["question_type"],
                "difficulty": item["difficulty"],
                "prompt": str(item["prompt"])[:160],
                "user_answer": str(item["user_answer"])[:120],
                "correct_answer": str(item["correct_answer"])[:120],
                "analysis": str(item["analysis"])[:180],
            }
            for item in snapshot.recent_mistakes[-3:]
        ]
        basis = self._build_personalization_basis(knowledge_point, snapshot)
        return {
            "knowledge_point": knowledge_point,
            "mastery_score": snapshot.mastery_score,
            "correct_rate": snapshot.correct_rate,
            "answered_count": snapshot.answered_count,
            "weak_question_types": snapshot.learner_profile.get("weak_question_types", []),
            "profile_analysis_summaries": snapshot.learner_profile.get("profile_analysis_summaries", {}),
            "basis": basis,
            "recent_mistakes": recent_mistakes,
        }

    def _build_personalization_basis(
        self,
        knowledge_point: str,
        snapshot: LearnerPersonalizationSnapshot,
    ) -> list[str]:
        basis: list[str] = []
        if snapshot.answered_count:
            basis.append(
                f"{knowledge_point} 当前掌握度约 {snapshot.mastery_score}/100，依据 {snapshot.answered_count} 次真实作答记录计算。"
            )
            basis.append(f"近期作答正确率约 {snapshot.correct_rate}%。")
        else:
            basis.append(
                f"{knowledge_point} 目前还没有真实作答记录，本次先结合历史画像和知识库生成一版入门内容。"
            )

        weak_types = snapshot.learner_profile.get("weak_question_types", [])
        if weak_types:
            basis.append(f"近期失分更集中在这些题型：{', '.join(map(str, weak_types[:3]))}。")

        if snapshot.recent_mistakes:
            latest = snapshot.recent_mistakes[-1]
            basis.append(
                "最近一次错题暴露的问题是："
                f"{latest['question_type']} / {latest['difficulty']}，"
                f"重点提醒：{str(latest['analysis'])[:80]}"
            )
        else:
            basis.append("当前还没有错题记录，本次课件会先用标准讲解帮助建立基础框架。")

        summaries = snapshot.learner_profile.get("profile_analysis_summaries", {})
        if isinstance(summaries, dict):
            for key in ("knowledgeBase", "cognitiveStyle", "errorPreference", "goalOrientation"):
                summary = str(summaries.get(key) or "").strip()
                if summary:
                    basis.append(f"深度画像提示：{summary}。")

        return basis

    def _build_recent_mistakes_text(self, snapshot: LearnerPersonalizationSnapshot) -> str:
        if not snapshot.recent_mistakes:
            return "暂无该知识点的错题记录。"

        lines = []
        for index, item in enumerate(snapshot.recent_mistakes[-3:], start=1):
            lines.append(
                f"{index}. 题型：{item['question_type']}，难度：{item['difficulty']}，"
                f"学生答案：{item['user_answer']}，标准答案：{item['correct_answer']}，"
                f"问题分析：{str(item['analysis'])[:120]}"
            )
        return "\n".join(lines)

    def _invoke_llm(self, variables: dict[str, Any], *, temperature: float = 0.2) -> str:
        try:
            from langchain_core.output_parsers import StrOutputParser
            from langchain_core.prompts import ChatPromptTemplate

            llm = self.llm_factory.build_chat_model(temperature=temperature)
            prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", self.prompt_template),
                    (
                        "human",
                        (
                            "请围绕下面的信息生成一份真正可学习的 Markdown 课件。\n"
                            "学科：{subject}\n"
                            "知识点：{knowledge_point}\n"
                            "资源类型：{resource_type}\n"
                            "呈现风格：{resource_style}\n"
                            "学习者画像：{learner_profile}\n"
                            "个性化依据：{personalization_basis_text}\n"
                            "近期错题：{recent_mistakes_text}\n"
                            "知识底稿：{grounding_text}\n"
                            "参考检索内容：{context_text}\n"
                            "要求：\n"
                            "1. 只输出 Markdown 正文。\n"
                            "2. 必须包含：课程导入、学习目标、你的当前学习情况、知识讲解、重点难点突破、示例讲解、课堂小结、学完后自测、拓展延伸。\n"
                            "3. 要写得像老师面对学生讲课，而不是材料堆砌。\n"
                            "4. 如果掌握度较低，解释更细、例子更基础；如果掌握度较高，增加迁移应用和易错辨析。\n"
                            "5. 必须显式回应近期真实错题暴露的问题，而不是泛泛而谈。\n"
                            "6. 如适合代码示例，请提供真实可运行的代码并解释关键行。\n"
                            "7. 正文控制在 1000 到 1800 字之间。\n"
                        ),
                    ),
                ]
            )
            chain = prompt | llm | StrOutputParser()
            return traced_invoke(chain, variables, stage="generation")
        except Exception as exc:
            logger.exception("Model-based courseware generation failed")
            raise ResourceGenerationError("Model-based courseware generation failed.") from exc

    def _resolve_variant_styles(self, preferred_style: str) -> list[str]:
        style_order = [preferred_style, "concise", "case", "interactive"]
        variant_styles: list[str] = []
        for style in style_order:
            if style not in variant_styles:
                variant_styles.append(style)

        max_variants = max(1, self.settings.resource_courseware_variant_count)
        return variant_styles[:max_variants]

    def _resolve_or_create_knowledge_point(self, db: Any, knowledge_point: str) -> KnowledgePoint:
        existing = db.query(KnowledgePoint).filter(KnowledgePoint.name == knowledge_point).first()
        if existing is not None:
            return existing

        article = self.knowledge_base.get_article(knowledge_point)
        record = KnowledgePoint(
            name=knowledge_point,
            description=article.summary if article is not None else f"{knowledge_point} 自动生成知识点",
            difficulty=2,
            importance=2,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    def _persist_generated_resource(
        self,
        db: Any,
        request: ResourceGenerationRequest,
        generation_plan: dict[str, Any],
        primary: dict[str, Any],
        *,
        audit_status: str = "pending",
        audit_reason: str = "",
    ) -> int:
        knowledge_point = self._resolve_or_create_knowledge_point(db, generation_plan["knowledge_point"])
        resource = Resource(
            title=primary.get("title"),
            type=generation_plan["resource_type"],
            content=primary["content"],
            format="markdown",
            knowledge_point_id=knowledge_point.id,
            generated_for_user_id=request.user_id,
            generation_status="generated",
            audit_status=audit_status,
            publish_status="draft",
            audit_reason=audit_reason,
        )
        db.add(resource)
        db.commit()
        db.refresh(resource)
        return resource.id

    def _build_variant_prompt(self, base_variables: dict[str, Any], style: str) -> dict[str, Any]:
        """Build one style-specific prompt payload."""

        variables = dict(base_variables)
        variables["resource_style"] = style
        basis = list(base_variables.get("personalization_basis", []))
        if style == "concise":
            basis.append("本版本请尽量短而清晰，突出关键规则、最小示例和快速自测。")
        elif style == "case":
            basis.append("本版本请用情境案例组织讲解，强调从题意到解法的迁移。")
        else:
            basis.append("本版本请强调互动式讲解，适合边学边练。")
        variables["personalization_basis"] = basis
        variables["personalization_basis_text"] = "\n".join(f"- {item}" for item in basis)
        return variables

    def _build_variant_summary(self, style: str) -> str:
        summaries = {
            "interactive": "按课堂讲解节奏展开，适合第一次系统学习。",
            "concise": "更短更快，适合先抓重点或临考前回顾。",
            "case": "通过案例和情境带入，适合理解应用场景。",
        }
        return summaries.get(style, "围绕当前知识点生成的学习课件。")

    def _extract_title(self, content: str, knowledge_point: str, style: str) -> str:
        first_line = content.strip().splitlines()[0] if content.strip() else ""
        if first_line.startswith("# "):
            return first_line[2:].strip()
        return f"{knowledge_point} {style} 课件"

    def generate_courseware(self, request: ResourceGenerationRequest) -> dict[str, Any]:
        retrieved_context = self.retriever.retrieve(
            query=f"{request.knowledge_point} {request.resource_type}",
            top_k=max(1, self.settings.resource_rag_top_k),
        )
        context_text = "\n\n".join(item["content"] for item in retrieved_context) or "当前暂无可用参考资料。"
        grounding_text = self._build_grounding_text(request.knowledge_point)

        with SessionLocal() as db:
            snapshot = PersonalizationService(db).build_snapshot(
                user_id=request.user_id,
                knowledge_point=request.knowledge_point,
                fallback_profile=request.learner_profile,
            )

        personalization = self._build_personalization_payload(request.knowledge_point, snapshot)
        variables = {
            "subject": request.subject.strip() or "由知识点推断",
            "knowledge_point": request.knowledge_point,
            "resource_type": request.resource_type,
            "resource_style": request.resource_style,
            "learner_profile": self._build_conditional_profile_text(request.knowledge_point, snapshot),
            "grounding_text": grounding_text[:1800],
            "context_text": context_text[:1400],
            "personalization_basis": personalization["basis"],
            "personalization_basis_text": "\n".join(f"- {item}" for item in personalization["basis"]),
            "recent_mistakes_text": self._build_recent_mistakes_text(snapshot),
        }
        variants: list[dict[str, Any]] = []
        for index, style in enumerate(self._resolve_variant_styles(request.resource_style), start=1):
            variant_variables = self._build_variant_prompt(variables, style)
            content = self._sanitize_generated_content(self._invoke_llm(variant_variables))
            variants.append(
                {
                    "variant_id": f"{style}-{index}",
                    "title": self._extract_title(content, request.knowledge_point, style),
                    "summary": self._build_variant_summary(style),
                    "resource_style": style,
                    "content": content,
                    "is_recommended": style == request.resource_style,
                }
            )

        primary = next((item for item in variants if item["is_recommended"]), variants[0])

        # ── Audit: validate content matches requested topic ──
        primary, audit = self._audit_and_retry_courseware(request, primary, variables)
        variants = [primary if item.get("is_recommended") else item for item in variants]

        return {
            "user_id": request.user_id,
            "knowledge_point": request.knowledge_point,
            "resource_type": request.resource_type,
            "resource_style": request.resource_style,
            "references": retrieved_context,
            "personalization": personalization,
            "content": primary["content"],
            "variants": variants,
            "generation_status": "generated",
            "audit_status": audit.status,
            "publish_status": "draft",
            "audit_reason": audit.reason,
        }

    def generate_courseware_with_plan(
        self,
        request: ResourceGenerationRequest,
        *,
        snapshot: LearnerPersonalizationSnapshot | None = None,
    ) -> dict[str, Any]:
        """Generate resources with an explicit coordination plan inspired by agent-core."""

        request_text = self._build_request_text(request)
        resolved_knowledge_point = self._normalize_knowledge_point(request, request_text)
        resolved_resource_type = self._infer_resource_type(request, request_text)

        retrieved_context, retrieval_context = self._load_retrieval_context(
            request,
            knowledge_point=resolved_knowledge_point,
            resource_type=resolved_resource_type,
        )
        context_text = "\n\n".join(item["content"] for item in retrieved_context) or "当前暂无可用参考资料。"
        grounding_text = self._build_grounding_text(resolved_knowledge_point)

        if snapshot is None:
            with SessionLocal() as db:
                snapshot = PersonalizationService(db).build_snapshot(
                    user_id=request.user_id,
                    knowledge_point=resolved_knowledge_point,
                    fallback_profile=request.learner_profile,
                )

        generation_plan = self._build_generation_plan(
            request,
            snapshot=snapshot,
            knowledge_point=resolved_knowledge_point,
            resource_type=resolved_resource_type,
        )
        personalization = self._build_personalization_payload(generation_plan["knowledge_point"], snapshot)
        plan_basis = list(personalization["basis"]) + [
            f"生成规划标题建议：{generation_plan['title_suggestion']}",
            f"目标难度：{generation_plan['difficulty']}",
            f"目标字数：约 {generation_plan['target_word_count']} 字",
            "建议结构：" + " / ".join(generation_plan["suggested_outline"]),
            *generation_plan["personalization_hints"],
        ]
        variables = {
            "subject": request.subject.strip() or "由知识点推断",
            "knowledge_point": generation_plan["knowledge_point"],
            "resource_type": generation_plan["resource_type"],
            "resource_style": generation_plan["resource_style"],
            "request_summary": generation_plan["request_summary"],
            "generation_plan": generation_plan,
            "generation_plan_text": self._build_generation_plan_text(generation_plan),
            "learner_profile": self._build_conditional_profile_text(request.knowledge_point, snapshot),
            "grounding_text": grounding_text[:1800],
            "context_text": context_text[:1400],
            "personalization_basis": plan_basis,
            "personalization_basis_text": "\n".join(f"- {item}" for item in plan_basis),
            "recent_mistakes_text": self._build_recent_mistakes_text(snapshot),
        }
        variants: list[dict[str, Any]] = []
        for index, style in enumerate(self._resolve_variant_styles(request.resource_style), start=1):
            variant_variables = self._build_variant_prompt(variables, style)
            content = self._sanitize_generated_content(self._invoke_llm(variant_variables))
            variants.append(
                {
                    "variant_id": f"{style}-{index}",
                    "title": self._extract_title(content, generation_plan["knowledge_point"], style),
                    "summary": self._build_variant_summary(style),
                    "resource_style": style,
                    "content": content,
                    "is_recommended": style == request.resource_style,
                }
            )

        primary = next((item for item in variants if item["is_recommended"]), variants[0])
        primary, audit = self._audit_and_retry_courseware(request, primary, variables)
        variants = [primary if item.get("is_recommended") else item for item in variants]
        trace = get_current_trace()
        if trace is not None:
            manager = trace.stage("persistence")
        else:
            from contextlib import nullcontext
            manager = nullcontext()
        with manager:
            with SessionLocal() as db:
                resource_id = self._persist_generated_resource(
                    db,
                    request,
                    generation_plan,
                    primary,
                    audit_status=audit.status,
                    audit_reason=audit.reason,
                )

        if audit.status == "rejected":
            raise ResourceGenerationError(
                f"Generated resource {resource_id} failed audit: {audit.reason}"
            )

        return {
            "id": resource_id,
            "user_id": request.user_id,
            "knowledge_point": generation_plan["knowledge_point"],
            "resource_type": generation_plan["resource_type"],
            "resource_style": generation_plan["resource_style"],
            "generation_plan": generation_plan,
            "references": retrieved_context,
            "retrieval_context": retrieval_context,
            "personalization": personalization,
            "content": primary["content"],
            "variants": variants,
            "generation_status": "generated",
            "audit_status": audit.status,
            "publish_status": "draft",
            "audit_reason": audit.reason,
        }

    def _audit_and_retry_courseware(
        self,
        request: ResourceGenerationRequest,
        primary: dict[str, Any],
        variables: dict[str, Any],
        max_retries: int = 2,
    ) -> tuple[dict[str, Any], Any]:
        """Audit courseware content; retry on rejection."""
        from services.agent_service.app.services.audit_service import AuditService

        auditor = AuditService(self.settings)
        retry_limit = min(max_retries, max(0, self.settings.max_total_retries))
        decision = auditor.audit_courseware(
            request.knowledge_point,
            str(primary.get("content", "")),
            str(primary.get("title", "")),
            mode=request.performance_mode,
        )

        for attempt in range(retry_limit + 1):
            if decision.passed:
                return primary, decision

            trace = get_current_trace()
            if attempt >= retry_limit or (trace is not None and not trace.can_retry()):
                break
            if trace is not None:
                trace.record_retry(stage="courseware_generation", reason=decision.reason, audit=True)

            try:
                retry_temp = 0.2 + (attempt + 1) * 0.2
                retry_variables = {
                    **variables,
                    "resource_style": "concise",
                    "personalization_basis_text": (
                        f"{variables.get('personalization_basis_text', '')}\n"
                        f"- 上次审核未通过：{decision.reason}，请修正后完整输出。"
                    ),
                }
                retry_content = self._sanitize_generated_content(
                    self._invoke_llm(retry_variables, temperature=retry_temp)
                )
                if retry_content:
                    primary = {
                        **primary,
                        "content": retry_content,
                        "title": self._extract_title(
                            retry_content,
                            request.knowledge_point,
                            str(primary.get("resource_style", "concise")),
                        ),
                        "is_recommended": True,
                    }
                decision = auditor.audit_courseware(
                    request.knowledge_point,
                    str(primary.get("content", "")),
                    str(primary.get("title", "")),
                    mode=request.performance_mode,
                )
            except Exception as exc:
                if trace is not None:
                    trace.retry_reason = str(exc)[:200]
                break

        return primary, decision

    def _build_conditional_profile_text(self, knowledge_point: str, snapshot) -> str:
        """Only inject learner profile when the topic matches known weak areas."""
        if not snapshot or not knowledge_point:
            return "无特殊画像要求，请按通用标准生成。"
        weak_areas = snapshot.learner_profile.get("weak_question_types", []) if isinstance(snapshot.learner_profile, dict) else []
        kp_lower = knowledge_point.lower()
        matches = any(area.lower() in kp_lower or kp_lower in area.lower() for area in weak_areas)
        if matches:
            summaries = snapshot.learner_profile.get("profile_analysis_summaries", {})
            summary_payload = {
                "mastery_score": snapshot.mastery_score,
                "correct_rate": snapshot.correct_rate,
                "answered_count": snapshot.answered_count,
                "weak_question_types": list(weak_areas)[:5],
                "preferred_resource_modes": list(
                    snapshot.learner_profile.get("preferred_resource_modes", [])
                )[:3],
                "analysis_summaries": {
                    str(key): str(value)[:160]
                    for key, value in summaries.items()
                    if str(value).strip()
                } if isinstance(summaries, dict) else {},
            }
            import json
            return json.dumps(summary_payload, ensure_ascii=False)
        return f"学生正在学习全新主题「{knowledge_point}」，请从基础概念出发生成课件，不要受学生历史画像影响。"

    def _sanitize_generated_content(self, content: str) -> str:
        sanitized_lines: list[str] = []
        blocked_patterns = (
            "VARK",
            "学习风格偏向",
            "学习风格是",
            "逻辑准确率",
            "准确率目前是",
            "掌握度约 62",
            "掌握度约62",
            "62/100",
        )
        for line in content.splitlines():
            if any(pattern in line for pattern in blocked_patterns):
                continue
            sanitized_lines.append(line)
        sanitized = "\n".join(sanitized_lines).strip()
        if sanitized:
            return sanitized
        raise ResourceGenerationError("Model returned empty courseware content.")
