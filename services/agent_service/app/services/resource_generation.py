"""Resource generation service integrating RAG, LLM output, and real learner data."""

from __future__ import annotations

from functools import lru_cache
import logging
from pathlib import Path
import re
from typing import Any

from common.config import get_settings
from common.db.session import SessionLocal
from common.models.learning import KnowledgePoint, Resource
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

    def _invoke_llm(self, variables: dict[str, Any]) -> str:
        try:
            from langchain_core.output_parsers import StrOutputParser
            from langchain_core.prompts import ChatPromptTemplate

            llm = self.llm_factory.build_chat_model(temperature=0.2)
            prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", self.prompt_template),
                    (
                        "human",
                        (
                            "请围绕下面的信息生成一份真正可学习的 Markdown 课件。\n"
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
            return chain.invoke(variables)
        except Exception as exc:
            logger.exception("Model-based courseware generation failed")
            raise ResourceGenerationError("Model-based courseware generation failed.") from exc

    def _build_fallback_markdown(self, variables: dict[str, Any]) -> str:
        knowledge_point = str(variables.get("knowledge_point") or "当前知识点")
        resource_style = str(variables.get("resource_style") or "interactive")
        grounding_text = str(variables.get("grounding_text") or "").strip()
        context_text = str(variables.get("context_text") or "").strip()
        basis_text = str(variables.get("personalization_basis_text") or "").strip()
        recent_mistakes_text = str(variables.get("recent_mistakes_text") or "").strip()

        source_text = "\n".join(part for part in [grounding_text, context_text] if part)
        extracted_points = self._extract_fallback_points(source_text)
        if not extracted_points:
            extracted_points = [
                f"先明确 {knowledge_point} 的定义、使用场景和边界条件。",
                "再通过一个最小示例观察输入、处理过程和输出结果。",
                "最后用自测题确认是否能独立迁移应用。",
            ]

        return "\n".join(
            [
                f"# {knowledge_point} 个性化学习课件",
                "",
                "## 课程导入",
                f"这节课围绕 **{knowledge_point}** 展开。当前模型生成通道暂时不可用，系统已根据知识库、检索资料和学习路径生成可阅读的备用正式课件。",
                "",
                "## 学习目标",
                *[f"- {point}" for point in extracted_points[:4]],
                "",
                "## 你的当前学习情况",
                basis_text or "- 暂无真实作答记录，本课件先按入门到巩固的节奏组织内容。",
                "",
                "## 知识讲解",
                f"- 核心主题：{knowledge_point}",
                "- 学习顺序：先理解概念，再看例子，最后完成自测。",
                "- 阅读方式：遇到不熟悉的术语时，先回到定义，再结合示例复述一遍。",
                "",
                "## 重点难点突破",
                *[f"- {point}" for point in extracted_points[4:8] or extracted_points[:3]],
                "",
                "## 示例讲解",
                "```python",
                f"# 围绕 {knowledge_point} 的最小示例",
                "steps = ['理解概念', '观察示例', '完成练习', '复盘错误']",
                "for index, step in enumerate(steps, start=1):",
                "    print(index, step)",
                "```",
                "这个示例强调把学习过程拆成可执行步骤：每一步都有明确目标，方便后续生成练习和错题复盘。",
                "",
                "## 近期错题提醒",
                recent_mistakes_text or "暂无该知识点的错题记录，先完成基础自测后再生成针对性练习。",
                "",
                "## 课堂小结",
                f"- 本节课先建立 {knowledge_point} 的基础框架。",
                f"- 当前课件风格：{resource_style}。",
                "- 学完后建议回到工作台生成练习题，用真实作答记录继续优化画像。",
                "",
                "## 学完后自测",
                f"1. 请用自己的话说明 {knowledge_point} 解决什么问题。",
                "2. 找出一个最小示例，并标注输入、处理逻辑、输出。",
                "3. 写出一个容易出错的点，以及对应规避方法。",
                "",
                "## 拓展延伸",
                "完成自测后，可继续生成练习题或进入知识图谱查看前置知识与相关资源。",
            ]
        )

    def _extract_fallback_points(self, source_text: str) -> list[str]:
        points: list[str] = []
        for line in source_text.splitlines():
            item = line.strip().lstrip("-•0123456789.、 ").strip()
            if not item or item in points:
                continue
            if len(item) > 120:
                item = item[:117] + "..."
            points.append(item)
            if len(points) >= 10:
                break
        return points

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
    ) -> int:
        knowledge_point = self._resolve_or_create_knowledge_point(db, generation_plan["knowledge_point"])
        resource = Resource(
            type=generation_plan["resource_type"],
            content=primary["content"],
            format="markdown",
            knowledge_point_id=knowledge_point.id,
            generated_for_user_id=request.user_id,
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
            "knowledge_point": request.knowledge_point,
            "resource_type": request.resource_type,
            "resource_style": request.resource_style,
            "learner_profile": snapshot.learner_profile,
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

        return {
            "user_id": request.user_id,
            "knowledge_point": request.knowledge_point,
            "resource_type": request.resource_type,
            "resource_style": request.resource_style,
            "references": retrieved_context,
            "personalization": personalization,
            "content": primary["content"],
            "variants": variants,
        }

    def generate_courseware_with_plan(self, request: ResourceGenerationRequest) -> dict[str, Any]:
        """Generate resources with an explicit coordination plan inspired by agent-core."""

        request_text = self._build_request_text(request)
        resolved_knowledge_point = self._normalize_knowledge_point(request, request_text)
        resolved_resource_type = self._infer_resource_type(request, request_text)

        retrieved_context = self.retriever.retrieve(
            query=f"{resolved_knowledge_point} {resolved_resource_type}",
            top_k=max(1, self.settings.resource_rag_top_k),
        )
        context_text = "\n\n".join(item["content"] for item in retrieved_context) or "当前暂无可用参考资料。"
        grounding_text = self._build_grounding_text(resolved_knowledge_point)

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
            "knowledge_point": generation_plan["knowledge_point"],
            "resource_type": generation_plan["resource_type"],
            "resource_style": generation_plan["resource_style"],
            "request_summary": generation_plan["request_summary"],
            "generation_plan": generation_plan,
            "generation_plan_text": self._build_generation_plan_text(generation_plan),
            "learner_profile": snapshot.learner_profile,
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
        with SessionLocal() as db:
            resource_id = self._persist_generated_resource(db, request, generation_plan, primary)

        return {
            "id": resource_id,
            "user_id": request.user_id,
            "knowledge_point": generation_plan["knowledge_point"],
            "resource_type": generation_plan["resource_type"],
            "resource_style": generation_plan["resource_style"],
            "generation_plan": generation_plan,
            "references": retrieved_context,
            "personalization": personalization,
            "content": primary["content"],
            "variants": variants,
        }

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
