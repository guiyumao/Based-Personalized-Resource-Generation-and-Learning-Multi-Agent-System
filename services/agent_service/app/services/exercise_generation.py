"""Structured exercise generation service for the student workspace."""

from __future__ import annotations

import json
import re
from itertools import cycle
from pathlib import Path
from typing import Any

from common.config import get_settings
from common.schemas.agent import ExerciseGenerationRequest
from services.agent_service.app.services.knowledge_base import KnowledgeBaseService
from services.agent_service.app.services.llm_factory import LLMFactory


QUESTION_TYPE_SEQUENCE = ["choice", "blank", "judge", "short_answer", "programming"]


def _load_prompt_template(filename: str) -> str:
    prompt_path = Path("prompts") / filename
    return prompt_path.read_text(encoding="utf-8")


class ExerciseGenerationService:
    """Generate structured practice or self-test exercises for a knowledge point."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.knowledge_base = KnowledgeBaseService()
        self.llm_factory = LLMFactory(self.settings)
        self.prompt_template = _load_prompt_template("exercise_gen.md")

    def generate_exercises(self, request: ExerciseGenerationRequest) -> dict[str, object]:
        """Return a structured exercise set for frontend practice."""

        llm_result = self._try_generate_with_llm(request)
        if llm_result is not None:
            return llm_result
        return self._build_fallback_exercises(request)

    def _try_generate_with_llm(self, request: ExerciseGenerationRequest) -> dict[str, object] | None:
        article = self.knowledge_base.get_article(request.knowledge_point)
        grounding_text = self._build_grounding_text(article)
        courseware_focus = self._extract_courseware_focus(request.courseware_content)

        try:
            from langchain_core.output_parsers import StrOutputParser
            from langchain_core.prompts import ChatPromptTemplate

            llm = self.llm_factory.build_chat_model(temperature=0.2)
            prompt = ChatPromptTemplate.from_messages(
                [
                    (
                        "system",
                        self.prompt_template,
                    ),
                    (
                        "human",
                        (
                            "请围绕以下教学信息生成一组真实可作答的练习题。\n"
                            "知识点: {knowledge_point}\n"
                            "生成模式: {generation_mode}\n"
                            "呈现风格: {resource_style}\n"
                            "学习者画像: {learner_profile}\n"
                            "知识底稿: {grounding_text}\n"
                            "课件重点: {courseware_focus}\n"
                            "课件摘要: {courseware_excerpt}\n"
                            "题目数量: {exercise_count}\n"
                            "难度比例: foundation 60%, intermediate 30%, advanced 10%\n"
                            "题型覆盖: choice, blank, judge, short_answer, programming\n"
                            "要求:\n"
                            "1. 每题都必须包含 prompt, options, answer, analysis。\n"
                            "2. 题目表述要具体，不能写成占位语句。\n"
                            "3. 解析要明确指出考查点、解题思路和易错点。\n"
                            "4. 如果是选择题，选项要有合理干扰性。\n"
                            "5. 如果知识点适合编程，编程题要贴近真实代码场景。\n"
                            "输出格式:\n"
                            "{\n"
                            '  "summary": "字符串",\n'
                            '  "exercises": [\n'
                            "    {\n"
                            '      "exercise_id": 1,\n'
                            '      "knowledge_point": "字符串",\n'
                            '      "question_type": "choice|blank|judge|short_answer|programming",\n'
                            '      "difficulty": "foundation|intermediate|advanced",\n'
                            '      "prompt": "题目内容",\n'
                            '      "options": ["A. ...", "B. ..."],\n'
                            '      "answer": "标准答案",\n'
                            '      "analysis": "详细解析"\n'
                            "    }\n"
                            "  ]\n"
                            "}\n"
                            "请简洁输出，不要附加解释。"
                        ),
                    ),
                ]
            )
            chain = prompt | llm | StrOutputParser()
            raw = chain.invoke(
                {
                    "knowledge_point": request.knowledge_point,
                    "generation_mode": request.generation_mode,
                    "resource_style": request.resource_style,
                    "learner_profile": request.learner_profile,
                    "grounding_text": grounding_text[:1000],
                    "courseware_focus": courseware_focus[:500],
                    "courseware_excerpt": request.courseware_content[: self.settings.exercise_context_max_chars],
                    "exercise_count": request.exercise_count,
                }
            )
            payload = self._extract_json(raw)
            exercises = payload.get("exercises", [])
            if not exercises:
                return None

            normalized_exercises: list[dict[str, object]] = []
            for index, exercise in enumerate(exercises, start=1):
                prompt_text = str(exercise.get("prompt", "")).strip()
                answer_text = str(exercise.get("answer", "")).strip()
                analysis_text = str(exercise.get("analysis", "")).strip()
                if not prompt_text or not answer_text or not analysis_text:
                    continue

                question_type = self._normalize_question_type(str(exercise.get("question_type", "choice")))
                difficulty = self._normalize_difficulty(str(exercise.get("difficulty", "foundation")))
                options = exercise.get("options", [])
                normalized_options = [str(item).strip() for item in options if str(item).strip()] if isinstance(options, list) else []
                normalized_exercises.append(
                    {
                        "exercise_id": int(exercise.get("exercise_id", index)),
                        "knowledge_point": str(exercise.get("knowledge_point", request.knowledge_point)),
                        "question_type": question_type,
                        "difficulty": difficulty,
                        "prompt": prompt_text,
                        "options": normalized_options if question_type == "choice" else [],
                        "answer": answer_text,
                        "analysis": analysis_text,
                    }
                )

            if not normalized_exercises:
                return None

            return {
                "user_id": request.user_id,
                "knowledge_point": request.knowledge_point,
                "summary": str(
                    payload.get(
                        "summary",
                        self._build_summary_text(request, len(normalized_exercises)),
                    )
                ),
                "exercises": normalized_exercises[: request.exercise_count],
            }
        except Exception:
            return None

    def _extract_json(self, raw: str) -> dict[str, Any]:
        cleaned = raw.strip()
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
            if match:
                return json.loads(match.group(0))
            raise

    def _normalize_question_type(self, question_type: str) -> str:
        normalized = question_type.strip().lower()
        allowed = {"choice", "blank", "judge", "short_answer", "programming"}
        if normalized in allowed:
            return normalized
        mapping = {
            "multiple_choice": "choice",
            "select": "choice",
            "fill_blank": "blank",
            "true_false": "judge",
            "short": "short_answer",
            "coding": "programming",
            "code": "programming",
        }
        return mapping.get(normalized, "choice")

    def _normalize_difficulty(self, difficulty: str) -> str:
        normalized = difficulty.strip().lower()
        allowed = {"foundation", "intermediate", "advanced"}
        if normalized in allowed:
            return normalized
        mapping = {
            "basic": "foundation",
            "easy": "foundation",
            "medium": "intermediate",
            "hard": "advanced",
        }
        return mapping.get(normalized, "foundation")

    def _build_grounding_text(self, article: Any) -> str:
        if article is None:
            return ""
        return "\n".join(
            [
                f"摘要: {article.summary}",
                "核心概念:",
                *[f"- {item}" for item in article.concepts[:4]],
                "实际应用:",
                *[f"- {item}" for item in article.applications[:3]],
                "常见错误:",
                *[f"- {item}" for item in article.mistakes[:3]],
                "学完后自测:",
                *[f"- {item}" for item in article.checks[:3]],
            ]
        )

    def _build_fallback_exercises(self, request: ExerciseGenerationRequest) -> dict[str, object]:
        question_types = cycle(QUESTION_TYPE_SEQUENCE)
        difficulty_plan = self._build_difficulty_plan(request.exercise_count)
        self_test_points = self._extract_self_test_points(request)
        mistake_points = self._extract_mistake_points(request)
        exercises: list[dict[str, object]] = []

        for index in range(request.exercise_count):
            question_type = next(question_types)
            difficulty = difficulty_plan[index]
            focus_point = self_test_points[index % len(self_test_points)] if self_test_points else ""
            related_mistake = mistake_points[index % len(mistake_points)] if mistake_points else ""
            prompt, options, answer, analysis = self._build_question(
                knowledge_point=request.knowledge_point,
                question_type=question_type,
                difficulty=difficulty,
                index=index + 1,
                generation_mode=request.generation_mode,
                focus_point=focus_point,
                related_mistake=related_mistake,
            )
            exercises.append(
                {
                    "exercise_id": index + 1,
                    "knowledge_point": request.knowledge_point,
                    "question_type": question_type,
                    "difficulty": difficulty,
                    "prompt": prompt,
                    "options": options,
                    "answer": answer,
                    "analysis": analysis,
                }
            )

        return {
            "user_id": request.user_id,
            "knowledge_point": request.knowledge_point,
            "summary": self._build_summary_text(request, request.exercise_count),
            "exercises": exercises,
        }

    def _build_difficulty_plan(self, exercise_count: int) -> list[str]:
        foundation_count = max(2, round(exercise_count * 0.6))
        intermediate_count = max(1, round(exercise_count * 0.3))
        advanced_count = max(1, exercise_count - foundation_count - intermediate_count)
        return (
            ["foundation"] * foundation_count
            + ["intermediate"] * intermediate_count
            + ["advanced"] * advanced_count
        )[:exercise_count]

    def _extract_courseware_focus(self, courseware_content: str) -> str:
        if not courseware_content.strip():
            return ""
        lines = [line.strip() for line in courseware_content.splitlines() if line.strip()]
        picked = [line for line in lines if "常见错误" in line or "学完后自测" in line]
        return "\n".join(picked[:10]) or courseware_content[: self.settings.exercise_context_max_chars]

    def _extract_bullets_under_heading(self, content: str, heading: str) -> list[str]:
        if not content.strip():
            return []
        pattern = rf"{re.escape(heading)}\s*\n(?P<body>.*?)(?:\n## |\n# |\Z)"
        match = re.search(pattern, content, flags=re.S)
        if not match:
            return []
        body = match.group("body")
        return [
            re.sub(r"^[-*]\s*", "", line).strip()
            for line in body.splitlines()
            if re.match(r"^\s*[-*]\s+", line)
        ]

    def _extract_self_test_points(self, request: ExerciseGenerationRequest) -> list[str]:
        points = self._extract_bullets_under_heading(request.courseware_content, "## 学完后自测")
        if points:
            return points
        article = self.knowledge_base.get_article(request.knowledge_point)
        if article is not None:
            return article.checks
        return [f"围绕 {request.knowledge_point} 做应用型自测。"]

    def _extract_mistake_points(self, request: ExerciseGenerationRequest) -> list[str]:
        points = self._extract_bullets_under_heading(request.courseware_content, "## 常见错误")
        if points:
            return points
        article = self.knowledge_base.get_article(request.knowledge_point)
        if article is not None:
            return article.mistakes
        return []

    def _build_summary_text(self, request: ExerciseGenerationRequest, count: int) -> str:
        if request.generation_mode == "self_test":
            return f"已根据当前课件内容，为 {request.knowledge_point} 生成 {count} 道学完后自测题。"
        if request.generation_mode == "remedial":
            return f"已围绕 {request.knowledge_point} 的薄弱点生成 {count} 道重练题。"
        return f"已为 {request.knowledge_point} 生成 {count} 道分层练习题，覆盖基础、进阶和拓展。"

    def _build_question(
        self,
        knowledge_point: str,
        question_type: str,
        difficulty: str,
        index: int,
        generation_mode: str,
        focus_point: str,
        related_mistake: str,
    ) -> tuple[str, list[str], str, str]:
        if generation_mode == "self_test":
            return self._build_self_test_question(
                knowledge_point=knowledge_point,
                question_type=question_type,
                difficulty=difficulty,
                index=index,
                focus_point=focus_point,
                related_mistake=related_mistake,
            )
        return self._build_general_question(
            knowledge_point=knowledge_point,
            question_type=question_type,
            difficulty=difficulty,
            index=index,
        )

    def _build_self_test_question(
        self,
        knowledge_point: str,
        question_type: str,
        difficulty: str,
        index: int,
        focus_point: str,
        related_mistake: str,
    ) -> tuple[str, list[str], str, str]:
        scenario = focus_point or f"{knowledge_point} 的使用场景"
        if question_type == "choice":
            return (
                f"第 {index} 题：围绕“{scenario}”，下面哪一项理解最准确？",
                [
                    "A. `while` 一定比 `for` 更适合遍历固定次数任务，因为它写法更灵活",
                    "B. `for` 更适合遍历已知序列，`while` 更适合依赖条件持续执行的场景",
                    "C. `for` 和 `while` 只能二选一，不能在同一类任务中根据场景选择",
                    "D. 只要使用了 `range()`，循环体里就不应该再写 `if` 判断",
                ],
                "B",
                "这道题考查你是否真正理解两类循环的适用场景。`for` 适合遍历确定对象，`while` 更适合根据条件反复执行。A 把“灵活”误当成“更适合”；C 否认了按场景选工具的基本思路；D 错在把循环和条件判断对立起来，实际上它们经常配合使用。",
            )
        if question_type == "blank":
            return (
                f"第 {index} 题：如果 `while` 循环中忘记更新控制变量，程序最可能出现 ______。",
                [],
                "死循环",
                "这题对应循环中的典型易错点。`while` 是否结束，取决于条件是否会发生变化。如果控制变量一直不变，条件可能始终成立，程序就会一直执行下去，形成死循环。",
            )
        if question_type == "judge":
            return (
                f"第 {index} 题：判断正误。`range(5)` 表示会依次得到 1、2、3、4、5。",
                [],
                "错误",
                "`range(5)` 实际生成的是 0 到 4，共 5 个整数，不包含 5 本身。很多同学会把它误解成“从 1 到 5”，这是学习 `for` 循环时最常见的错误之一。",
            )
        if question_type == "short_answer":
            return (
                f"第 {index} 题：请结合“{scenario}”说明你会选择 `for` 还是 `while`，并写出你的判断理由。",
                [],
                "答案示例：如果任务是遍历列表、字符串或 `range()` 这样的确定序列，通常选 `for`；如果任务要根据某个条件反复执行，并且结束次数事先不固定，通常选 `while`。说明时要写清楚循环对象、退出条件和循环体操作。",
                "这道题不是让你背概念，而是看你能否把知识点放进真实场景中判断。答题时要先分析任务特征，再说明为什么选这种循环。",
            )
        return (
            f"第 {index} 题：编写一段 Python 代码，使用 {knowledge_point} 完成“遍历一个整数列表，并输出其中所有偶数”的任务。",
            [],
            "参考答案：\nnums = [3, 8, 11, 14, 20]\nfor num in nums:\n    if num % 2 == 0:\n        print(num)",
            "这道题把循环和条件判断结合在一起，考查你是否能把“遍历”和“筛选”同时写出来。循环负责逐个取数，`if num % 2 == 0` 负责判断是否为偶数。"
            + (f" 本题还特别提醒你避免这个错误：{related_mistake}" if related_mistake else ""),
        )

    def _build_general_question(
        self,
        knowledge_point: str,
        question_type: str,
        difficulty: str,
        index: int,
    ) -> tuple[str, list[str], str, str]:
        if question_type == "choice":
            return (
                f"第 {index} 题：关于 {knowledge_point}，下面哪一项说法最准确？",
                [
                    "A. 它只能用于输出结果，不能处理数据",
                    "B. 它主要用于让一组操作按照一定规则重复执行",
                    "C. 它只能和列表一起使用，不能处理字符串或范围对象",
                    "D. 它和条件判断不能同时出现，否则语法会出错",
                ],
                "B",
                f"{knowledge_point} 的核心作用是让程序重复执行某段逻辑，因此 B 正确。A 把循环的作用说得过于狭窄；C 错在把使用对象限制得太死；D 错在忽略了循环和条件判断常常配合出现。",
            )
        if question_type == "blank":
            return (
                f"第 {index} 题：请填写一个与 {knowledge_point} 直接相关的关键语法关键词：______。",
                [],
                "for / while",
                "这题考查你是否能迅速抓住该知识点最基础的语法入口。对于 Python 循环来说，最核心的两个关键词就是 `for` 和 `while`。",
            )
        if question_type == "judge":
            return (
                f"第 {index} 题：判断正误。{knowledge_point} 可以和条件判断配合使用来完成筛选、统计等任务。",
                [],
                "正确",
                f"{knowledge_point} 往往不是单独使用的，它通常会和条件判断一起完成筛选、累加、查找、计数等实际任务，因此这句话是正确的。",
            )
        if question_type == "short_answer":
            return (
                f"第 {index} 题：请用自己的话说明 {knowledge_point} 在实际编程中的一个应用场景，并说明它解决了什么问题。",
                [],
                "答案示例：可以用在遍历学生成绩列表、统计订单数据、批量处理文件内容等场景中，它解决的是“同一类操作需要重复执行很多次”的问题。",
                "这道主观题重点不在术语，而在于你能不能把知识点和真实任务连接起来，说清“为什么要用它”。",
            )
        return (
            f"第 {index} 题：编写一段示例代码，展示如何使用 {knowledge_point} 完成一个简单统计任务，并简要说明代码思路。",
            [],
            "答案示例：使用 `for` 遍历一组数据，并在循环中完成计数、求和或筛选等操作，再输出统计结果。",
            f"这道编程题更关注你是否能把 {knowledge_point} 落地成可执行步骤，而不是只会写一个关键词。",
        )
