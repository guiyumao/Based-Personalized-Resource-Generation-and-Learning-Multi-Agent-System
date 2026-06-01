"""Resource generation service integrating RAG, LLM output, and real learner data."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re
from typing import Any

from common.config import get_settings
from common.db.session import SessionLocal
from common.schemas.agent import ResourceGenerationRequest
from services.agent_service.app.services.knowledge_base import KnowledgeBaseService
from services.agent_service.app.services.llm_factory import LLMFactory
from services.agent_service.app.services.personalization import (
    LearnerPersonalizationSnapshot,
    PersonalizationService,
)
from services.agent_service.app.services.rag import ChromaRetriever


@lru_cache(maxsize=1)
def _load_prompt_template(filename: str) -> str:
    prompt_path = Path("prompts") / filename
    return prompt_path.read_text(encoding="utf-8")


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
        knowledge_point = request.knowledge_point.strip() or "通用学习主题"
        article = self.knowledge_base.get_article(knowledge_point)
        if article is not None:
            return article.title

        matches = self.knowledge_base.search_by_keywords(request_text, top_k=1) if request_text else []
        if matches:
            generic_markers = ("python", "编程", "代码", "学习", "知识点", "主题")
            if len(knowledge_point) <= 4 or any(marker in knowledge_point.lower() for marker in generic_markers):
                return matches[0].title
        return knowledge_point

    def _infer_resource_type(self, request: ResourceGenerationRequest, request_text: str) -> str:
        if request.resource_type != "courseware":
            return request.resource_type

        lowered = request_text.lower()
        keyword_map = {
            "exercise": ("练习", "刷题", "习题", "题目", "自测", "测试"),
            "notes": ("笔记", "总结", "速记", "提纲"),
            "exam": ("考试", "模拟", "试卷", "测验", "冲刺"),
        }
        for resource_type, keywords in keyword_map.items():
            if any(keyword in lowered for keyword in keywords):
                return resource_type
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
        except Exception:
            return self._fallback_generation(variables)

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

    def _fallback_generation(self, variables: dict[str, Any]) -> str:
        knowledge_point = str(variables["knowledge_point"])
        resource_type = str(variables["resource_type"])
        resource_style = str(variables["resource_style"])
        context_text = str(variables["context_text"])
        grounding_text = str(variables.get("grounding_text", ""))
        learner_profile = variables.get("learner_profile", {})
        personalization_basis = variables.get("personalization_basis", [])
        if isinstance(personalization_basis, str):
            personalization_basis = [
                line.removeprefix("- ").strip()
                for line in personalization_basis.splitlines()
                if line.strip()
            ]
        recent_mistakes_text = str(variables.get("recent_mistakes_text", "暂无错题记录。"))

        if resource_type == "courseware":
            return self._build_fallback_courseware(
                knowledge_point=knowledge_point,
                resource_style=resource_style,
                learner_profile=learner_profile,
                context_text=context_text,
                grounding_text=grounding_text,
                personalization_basis=personalization_basis,
                recent_mistakes_text=recent_mistakes_text,
            )

        return (
            f"# {knowledge_point} {resource_type}\n\n"
            "## 本次个性化依据\n"
            + "\n".join(f"- {item}" for item in personalization_basis)
            + "\n\n## 知识底稿\n"
            + (grounding_text or "当前暂无结构化知识底稿。")
            + "\n\n## 检索参考\n"
            + (context_text or "当前暂无额外检索参考。")
        )

    def _build_fallback_courseware(
        self,
        knowledge_point: str,
        resource_style: str,
        learner_profile: dict[str, Any],
        context_text: str,
        grounding_text: str,
        personalization_basis: list[str],
        recent_mistakes_text: str,
    ) -> str:
        learning_style = str(learner_profile.get("learning_style", "visual"))
        mastery = learner_profile.get("mastery", "unknown")
        article = self.knowledge_base.get_article(knowledge_point)

        if article is None:
            return self._build_generic_courseware(
                knowledge_point=knowledge_point,
                resource_style=resource_style,
                learning_style=learning_style,
                mastery=mastery,
                context_text=context_text,
                grounding_text=grounding_text,
                personalization_basis=personalization_basis,
            )

        concept_points = "\n".join(f"- {item}" for item in article.concepts[:4])
        mistake_points = "\n".join(f"- {item}" for item in article.mistakes[:4])
        application_points = "\n".join(f"- {item}" for item in article.applications[:3])
        self_check_points = "\n".join(f"- {item}" for item in article.checks[:4])
        syntax_blocks = "\n\n".join(f"```python\n{item}\n```" for item in article.syntax[:2])
        example_block = article.examples[0] if article.examples else ""
        adaptive_hint = (
            "你已经有一定基础，这次重点要放在“为什么这样写更合适”“怎样避免低级错误重复出现”上。"
            if isinstance(mastery, (int, float)) and mastery >= 70
            else "这次先不要追求写得快，重点把循环在做什么、什么时候停、为什么会出错真正想清楚。"
        )

        basis_lines = "\n".join(f"- {item}" for item in personalization_basis)
        reference_text = context_text or grounding_text or "当前暂无额外参考材料。"

        return (
            f"# {knowledge_point} 学习课件\n\n"
            "## 课程导入\n"
            f"{article.summary} 你可以先想一个问题：如果程序里有一件事情需要重复做很多次，"
            "我们是把同样的代码写十遍，还是想办法让程序自动完成？这正是今天这个知识点要解决的问题。\n\n"
            "## 学习目标\n"
            f"- 说清 {knowledge_point} 解决的核心问题。\n"
            "- 能区分常见场景下应该用哪种写法。\n"
            "- 能根据题目要求写出一个基础示例，并检查边界和更新步骤。\n"
            "- 能识别自己最容易出错的位置，并知道如何修正。\n\n"
            "## 你的当前学习情况\n"
            f"{basis_lines}\n"
            f"- 呈现风格：{resource_style}\n"
            f"- 学习偏好参考：{learning_style}\n"
            f"- 个性化提醒：{adaptive_hint}\n\n"
            "## 知识讲解\n"
            f"{concept_points}\n\n"
            "理解这个知识点时，不要只记“怎么写”，一定要一起想清“为什么重复”“重复谁”“什么时候停”。"
            "只要这三个问题没有想清楚，真正做题时就很容易乱。\n\n"
            "## 重点难点突破\n"
            "很多同学表面上会写语法，但一到题目里就出错，通常卡在这两类地方：\n"
            "1. 不知道该怎么选思路，看到重复任务却分不清应该遍历已知对象，还是根据条件持续执行。\n"
            "2. 不会检查边界，尤其是循环次数、索引起止、条件是否会变化。\n\n"
            "结合你最近的真实作答记录，这次特别要注意下面这些问题：\n"
            f"{recent_mistakes_text}\n\n"
            "## 关键语法\n"
            f"{syntax_blocks}\n\n"
            "上面的语法不是让你机械背诵，而是帮助你建立一套判断方法："
            "先看任务对象，再看结束条件，最后看每一轮如何推进。\n\n"
            "## 示例讲解\n"
            "下面我们用一个最典型的例子，把“循环到底帮我们做了什么”讲透：\n\n"
            f"```python\n{example_block}\n```\n\n"
            "请重点观察：\n"
            "- 循环对象是谁。\n"
            "- 每一轮到底执行了哪些动作。\n"
            "- 判断条件在哪一层，为什么要放在那里。\n"
            "- 如果把缩进或条件写错，会出现什么后果。\n\n"
            "## 课堂小结\n"
            f"- {knowledge_point} 的本质，是把重复工作交给程序按规则自动执行。\n"
            "- 写题时不要只顾着敲代码，要先把对象、条件、边界、更新这四件事写明白。\n"
            "- 一旦出错，优先检查：循环对象、结束条件、变量更新、缩进层级。\n\n"
            "## 学完后自测\n"
            f"{self_check_points}\n\n"
            "## 拓展延伸\n"
            f"{application_points}\n\n"
            "学完这一节后，你可以继续尝试把它和条件判断、列表处理、函数封装结合起来。"
            "真正掌握一个知识点，不是会背定义，而是看到题目时知道什么时候该用它、为什么这样用、写完后怎么检查。\n\n"
            "## 参考材料\n"
            f"{reference_text}\n"
        )

    def _build_generic_courseware(
        self,
        knowledge_point: str,
        resource_style: str,
        learning_style: str,
        mastery: Any,
        context_text: str,
        grounding_text: str,
        personalization_basis: list[str],
    ) -> str:
        basis_lines = "\n".join(f"- {item}" for item in personalization_basis)
        return (
            f"# {knowledge_point} 学习课件\n\n"
            "## 课程导入\n"
            f"{knowledge_point} 是当前学习阶段的重要基础能力。真正学习它时，不能只停留在定义层面，而要想清楚它到底帮助我们解决什么问题。\n\n"
            "## 学习目标\n"
            f"- 理解 {knowledge_point} 的核心作用。\n"
            "- 能结合一个具体场景说明它的用法。\n"
            "- 能识别典型错误并进行修正。\n\n"
            "## 你的当前学习情况\n"
            f"{basis_lines}\n"
            f"- 呈现风格：{resource_style}\n"
            f"- 学习偏好参考：{learning_style}\n"
            f"- 当前掌握度参考：{mastery}\n\n"
            "## 知识讲解\n"
            f"{grounding_text or f'建议先从 {knowledge_point} 的定义、作用、场景和常见错误四个角度建立理解。'}\n\n"
            "## 重点难点突破\n"
            "学习任何新知识点，最容易出现的问题往往不是完全不会，而是“知道一点但没有真正理解为什么”。"
            "所以接下来要重点把概念、步骤、适用条件和错误边界连起来看。\n\n"
            "## 示例讲解\n"
            "建议你先自己尝试写一个最小示例，再回过头对照讲解检查哪里理解得还不够稳。\n\n"
            "## 课堂小结\n"
            f"- 先理解 {knowledge_point} 为什么存在，再记住它怎么使用。\n"
            "- 做题时主动检查条件、边界和步骤是否完整。\n\n"
            "## 学完后自测\n"
            f"- 我能不能用自己的话解释 {knowledge_point}？\n"
            f"- 我能不能举出一个 {knowledge_point} 的真实应用场景？\n"
            "- 我能不能指出这个知识点最容易错在哪里？\n\n"
            "## 拓展延伸\n"
            "接下来建议再配合几道练习题，把抽象概念真正转化成可输出的能力。\n\n"
            "## 参考材料\n"
            f"{context_text or grounding_text or '当前暂无额外参考材料。'}\n"
        )

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
        style_order = [request.resource_style, "concise", "case", "interactive"]
        variant_styles: list[str] = []
        for style in style_order:
            if style not in variant_styles:
                variant_styles.append(style)

        variants: list[dict[str, Any]] = []
        for index, style in enumerate(variant_styles[:3], start=1):
            variant_variables = self._build_variant_prompt(variables, style)
            content = self._invoke_llm(variant_variables)
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
        style_order = [request.resource_style, "concise", "case", "interactive"]
        variant_styles: list[str] = []
        for style in style_order:
            if style not in variant_styles:
                variant_styles.append(style)

        variants: list[dict[str, Any]] = []
        for index, style in enumerate(variant_styles[:3], start=1):
            variant_variables = self._build_variant_prompt(variables, style)
            content = self._invoke_llm(variant_variables)
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

        return {
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
