"""Resource generation service integrating knowledge grounding, RAG, and LLM output."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from common.config import get_settings
from common.schemas.agent import ResourceGenerationRequest
from services.agent_service.app.services.knowledge_base import KnowledgeBaseService
from services.agent_service.app.services.llm_factory import LLMFactory
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

    def _build_grounding_text(self, knowledge_point: str) -> str:
        article = self.knowledge_base.get_article(knowledge_point)
        if article is None:
            return ""

        sections = [
            f"主题: {article.title}",
            f"摘要: {article.summary}",
            "核心概念:",
            *[f"- {item}" for item in article.concepts[:4]],
            "关键语法:",
            *[f"- {item}" for item in article.syntax[:2]],
            "典型示例:",
            *[f"- {item}" for item in article.examples[:2]],
            "常见错误:",
            *[f"- {item}" for item in article.mistakes[:3]],
            "学完后自测:",
            *[f"- {item}" for item in article.checks[:3]],
        ]
        return "\n".join(sections)[:1400]

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
                            "请围绕以下教学信息生成一份学生可以直接阅读学习的正式 Markdown 课件。\n"
                            "知识点: {knowledge_point}\n"
                            "资源类型: {resource_type}\n"
                            "呈现风格: {resource_style}\n"
                            "学习者画像: {learner_profile}\n"
                            "知识底稿: {grounding_text}\n"
                            "参考上下文: {context_text}\n"
                            "要求:\n"
                            "1. 只输出 Markdown 正文。\n"
                            "2. 控制在 900 到 1500 字。\n"
                            "3. 必须包含: 课程导入、学习目标、知识讲解、重难点突破、示例讲解、课堂小结、学完后自测、拓展延伸。\n"
                            "4. 内容必须像真实老师讲课，不能只列提纲，也不能出现模板化占位语言。\n"
                            "5. 如果适合代码讲解，必须给出真实代码示例，并解释代码每一步作用。\n"
                            "6. 如果学生掌握度偏低，要解释得更细；如果掌握度较高，要加入迁移应用分析。\n"
                        ),
                    ),
                ]
            )
            chain = prompt | llm | StrOutputParser()
            return chain.invoke(variables)
        except Exception:
            return self._fallback_generation(variables)

    def _fallback_generation(self, variables: dict[str, Any]) -> str:
        knowledge_point = str(variables["knowledge_point"])
        resource_type = str(variables["resource_type"])
        resource_style = str(variables["resource_style"])
        context_text = str(variables["context_text"])
        grounding_text = str(variables.get("grounding_text", ""))
        learner_profile = variables.get("learner_profile", {})

        if resource_type == "courseware":
            return self._build_fallback_courseware(
                knowledge_point=knowledge_point,
                resource_style=resource_style,
                learner_profile=learner_profile,
                context_text=context_text,
                grounding_text=grounding_text,
            )

        return (
            f"# {knowledge_point} {resource_type}\n\n"
            "## 学习目标\n"
            f"- 围绕 {knowledge_point} 形成一份可执行学习材料\n\n"
            "## 呈现风格\n"
            f"- {resource_style}\n\n"
            "## 知识基础\n"
            f"{grounding_text or '当前暂无结构化知识底稿。'}\n\n"
            "## 参考资料\n"
            f"{context_text}\n"
        )

    def _build_fallback_courseware(
        self,
        knowledge_point: str,
        resource_style: str,
        learner_profile: dict[str, Any],
        context_text: str,
        grounding_text: str,
    ) -> str:
        learning_style = learner_profile.get("learning_style", "visual")
        mastery = learner_profile.get("mastery", "unknown")
        article = self.knowledge_base.get_article(knowledge_point)

        if article is not None:
            syntax_example = "\n\n".join(f"```python\n{item}\n```" for item in article.syntax[:2])
            case_example = "\n\n".join(f"```python\n{item}\n```" for item in article.examples[:2])
            concept_lines = "\n".join(f"- {item}" for item in article.concepts[:4])
            mistake_lines = "\n".join(f"- {item}" for item in article.mistakes[:3])
            application_lines = "\n".join(f"- {item}" for item in article.applications[:3])
            check_lines = "\n".join(f"- {item}" for item in article.checks[:3])

            return (
                f"# {knowledge_point} 学习课件\n\n"
                "## 课程导入\n"
                f"{article.summary} 在编程学习中，如果同样的操作要重复做很多次，手动一行一行去写不仅麻烦，还容易出错，所以我们需要学会用 {knowledge_point} 来提高效率。\n\n"
                "## 学习目标\n"
                f"- 理解 {knowledge_point} 的核心作用和适用场景\n"
                "- 会根据任务特点选择合适的写法\n"
                "- 能读懂示例、发现错误，并完成基础应用\n\n"
                "## 学习者适配提示\n"
                f"- 推荐呈现风格：{resource_style}\n"
                f"- 学习偏好参考：{learning_style}\n"
                f"- 当前掌握度参考：{mastery}\n\n"
                "## 知识讲解\n"
                f"{concept_lines}\n\n"
                "## 关键语法\n"
                f"{syntax_example}\n\n"
                "## 重难点突破\n"
                "很多同学刚开始学习这部分内容时，容易把“会写语法”和“会解决问题”混为一谈。真正重要的不是死记语法，而是看到任务后，能判断什么时候该重复执行、重复什么、什么时候停止。\n\n"
                "另一个常见难点是把循环范围和循环条件理解错。比如 `range(5)` 并不是 1 到 5，而是 0 到 4；又比如 `while` 如果不更新条件变量，就会一直执行下去。\n\n"
                "## 示例讲解\n"
                f"{case_example}\n\n"
                "## 实际应用\n"
                f"{application_lines}\n\n"
                "## 常见错误\n"
                f"{mistake_lines}\n\n"
                "## 课堂小结\n"
                f"- {knowledge_point} 的本质，是让程序按照一定规则重复执行任务。\n"
                "- 看到“遍历一组数据”时，优先想到 `for`；看到“只要条件成立就继续执行”时，可以考虑 `while`。\n"
                "- 做题时一定要检查循环对象、退出条件和循环体缩进是否正确。\n\n"
                "## 学完后自测\n"
                f"{check_lines}\n\n"
                "## 拓展延伸\n"
                "学完这一节后，可以尝试把循环和条件判断、列表、函数组合起来，完成更完整的小任务，比如统计成绩、筛选数据、打印图形等。真正掌握一个知识点，不是会背定义，而是能把它用到具体问题里。\n\n"
                "## 参考材料\n"
                f"{context_text}\n"
            )

        return (
            f"# {knowledge_point} 学习课件\n\n"
            "## 课程导入\n"
            f"{knowledge_point} 是程序设计中的基础知识点。很多任务看起来复杂，其实本质上只是把同一类操作按规则重复执行，因此理解这一点，会让你写程序时更有条理。\n\n"
            "## 学习目标\n"
            f"- 理解 {knowledge_point} 的基本作用\n"
            "- 知道它适合解决什么问题\n"
            "- 能通过示例形成初步应用意识\n\n"
            "## 学习者适配提示\n"
            f"- 推荐呈现风格：{resource_style}\n"
            f"- 学习偏好参考：{learning_style}\n"
            f"- 当前掌握度参考：{mastery}\n\n"
            "## 知识讲解\n"
            f"{grounding_text or f'{knowledge_point} 建议先理解定义，再结合具体例子去判断它在什么场景下最有用。'}\n\n"
            "## 课堂小结\n"
            f"- 先理解 {knowledge_point} 为什么存在，再记住它怎么写。\n"
            "- 学习时不要只看定义，要结合任务场景思考。\n\n"
            "## 拓展延伸\n"
            "建议继续通过练习题和应用示例把抽象概念转化成实际能力。\n\n"
            "## 参考材料\n"
            f"{context_text}\n"
        )

    def generate_courseware(self, request: ResourceGenerationRequest) -> dict[str, Any]:
        retrieved_context = self.retriever.retrieve(
            query=f"{request.knowledge_point} {request.resource_type}",
            top_k=max(1, self.settings.resource_rag_top_k),
        )
        context_text = "\n\n".join(item["content"] for item in retrieved_context) or "暂无可用参考资料。"
        grounding_text = self._build_grounding_text(request.knowledge_point)

        variables = {
            "knowledge_point": request.knowledge_point,
            "resource_type": request.resource_type,
            "resource_style": request.resource_style,
            "learner_profile": request.learner_profile,
            "grounding_text": grounding_text[:1400],
            "context_text": context_text[:900],
        }
        content = self._invoke_llm(variables)

        return {
            "user_id": request.user_id,
            "knowledge_point": request.knowledge_point,
            "resource_type": request.resource_type,
            "resource_style": request.resource_style,
            "references": retrieved_context,
            "content": content,
        }
