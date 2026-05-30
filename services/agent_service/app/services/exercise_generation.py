"""Structured exercise generation service for the student workspace."""

from __future__ import annotations

import json
import re
from itertools import cycle
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from common.config import get_settings
from common.db.session import SessionLocal
from common.models.learning import Exercise, KnowledgePoint
from common.schemas.agent import ExerciseGenerationRequest
from services.agent_service.app.services.knowledge_base import KnowledgeBaseService
from services.agent_service.app.services.llm_factory import LLMFactory
from services.agent_service.app.services.personalization import (
    LearnerPersonalizationSnapshot,
    PersonalizationService,
)


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

        request = self._coerce_request(request)
        with SessionLocal() as db:
            snapshot = PersonalizationService(db).build_snapshot(
                user_id=request.user_id,
                knowledge_point=request.knowledge_point,
                fallback_profile=request.learner_profile,
            )

            generated = self._try_generate_with_llm(request, snapshot)
            if generated is None:
                generated = self._build_fallback_exercises(request, snapshot)

            persisted_exercises = self._persist_exercises(
                db=db,
                request=request,
                exercises=generated["exercises"],
            )
            return {
                "user_id": request.user_id,
                "knowledge_point": request.knowledge_point,
                "summary": self._build_summary_text(request, len(persisted_exercises), snapshot),
                "personalization": self._build_personalization_payload(snapshot),
                "exercises": persisted_exercises,
            }

    def _coerce_request(self, request: ExerciseGenerationRequest | Any) -> ExerciseGenerationRequest:
        """Accept both Pydantic requests and lightweight test payload objects."""

        if isinstance(request, ExerciseGenerationRequest):
            return request

        return ExerciseGenerationRequest(
            user_id=int(getattr(request, "user_id")),
            knowledge_point=str(getattr(request, "knowledge_point")),
            resource_style=getattr(request, "resource_style", "interactive"),
            learner_profile=getattr(request, "learner_profile", {}) or {},
            exercise_count=int(getattr(request, "exercise_count", 5)),
            generation_mode=getattr(request, "generation_mode", "practice"),
            courseware_content=getattr(request, "courseware_content", "") or "",
        )

    def _try_generate_with_llm(
        self,
        request: ExerciseGenerationRequest,
        snapshot: LearnerPersonalizationSnapshot,
    ) -> dict[str, object] | None:
        article = self.knowledge_base.get_article(request.knowledge_point)
        grounding_text = self._build_grounding_text(article)
        courseware_focus = self._extract_courseware_focus(request.courseware_content)
        recent_mistakes_text = self._build_recent_mistakes_text(snapshot)

        try:
            from langchain_core.output_parsers import StrOutputParser
            from langchain_core.prompts import ChatPromptTemplate

            llm = self.llm_factory.build_chat_model(temperature=0.15)
            prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", self.prompt_template),
                    (
                        "human",
                        (
                            "请围绕下面的信息生成一组真正可作答、可评估的练习题。\n"
                            "知识点：{knowledge_point}\n"
                            "生成模式：{generation_mode}\n"
                            "呈现风格：{resource_style}\n"
                            "学习者画像：{learner_profile}\n"
                            "个性化依据：{personalization_basis}\n"
                            "近期错题：{recent_mistakes_text}\n"
                            "知识底稿：{grounding_text}\n"
                            "课件重点：{courseware_focus}\n"
                            "课件摘要：{courseware_excerpt}\n"
                            "题目数量：{exercise_count}\n"
                            "难度比例：foundation 60%, intermediate 30%, advanced 10%\n"
                            "题型覆盖：choice, blank, judge, short_answer, programming\n"
                            "要求：\n"
                            "1. 每题都必须包含 prompt, options, answer, analysis。\n"
                            "2. 题干必须具体，不能出现占位描述。\n"
                            "3. 如果学生最近在某类题型或某个错误上反复失分，必须在题目设计里显式针对这个问题。\n"
                            "4. 选择题选项要有合理干扰性，解析要说明各选项对错原因。\n"
                            "5. 简答题和编程题解析要说明解题步骤、检查点和易错点。\n"
                            "6. 只输出 JSON，不要输出额外解释。\n"
                            "输出格式：\n"
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
                    "learner_profile": snapshot.learner_profile,
                    "personalization_basis": "\n".join(self._build_personalization_basis(snapshot)),
                    "recent_mistakes_text": recent_mistakes_text,
                    "grounding_text": grounding_text[:1200],
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
                "summary": str(payload.get("summary", "")),
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
                f"摘要：{article.summary}",
                "核心概念：",
                *[f"- {item}" for item in article.concepts[:4]],
                "实际应用：",
                *[f"- {item}" for item in article.applications[:3]],
                "常见错误：",
                *[f"- {item}" for item in article.mistakes[:4]],
                "学完后自测：",
                *[f"- {item}" for item in article.checks[:3]],
            ]
        )

    def _build_personalization_payload(self, snapshot: LearnerPersonalizationSnapshot) -> dict[str, object]:
        return {
            "mastery_score": snapshot.mastery_score,
            "correct_rate": snapshot.correct_rate,
            "answered_count": snapshot.answered_count,
            "weak_question_types": snapshot.learner_profile.get("weak_question_types", []),
            "basis": self._build_personalization_basis(snapshot),
            "recent_mistakes": [
                {
                    "exercise_id": item["exercise_id"],
                    "question_type": item["question_type"],
                    "difficulty": item["difficulty"],
                    "prompt": str(item["prompt"])[:160],
                    "analysis": str(item["analysis"])[:180],
                }
                for item in snapshot.recent_mistakes[-3:]
            ],
        }

    def _build_personalization_basis(self, snapshot: LearnerPersonalizationSnapshot) -> list[str]:
        basis: list[str] = []
        if snapshot.answered_count:
            basis.append(
                f"当前掌握度约 {snapshot.mastery_score}/100，来自 {snapshot.answered_count} 次真实作答。"
            )
            basis.append(f"近期正确率约 {snapshot.correct_rate}%。")
        else:
            basis.append("当前还没有该知识点的真实作答记录，本次先生成一组基础摸底题。")

        weak_types = snapshot.learner_profile.get("weak_question_types", [])
        if weak_types:
            basis.append(f"近期薄弱题型更集中在：{', '.join(map(str, weak_types[:3]))}。")

        if snapshot.recent_mistakes:
            latest = snapshot.recent_mistakes[-1]
            basis.append(
                f"最近一次错题分析提示：{latest['question_type']} / {latest['difficulty']}，"
                f"{str(latest['analysis'])[:80]}"
            )
        else:
            basis.append("当前暂无错题记录，本次题组会先覆盖标准概念、基本应用和常见易错点。")

        return basis

    def _build_recent_mistakes_text(self, snapshot: LearnerPersonalizationSnapshot) -> str:
        if not snapshot.recent_mistakes:
            return "暂无错题记录。"
        lines = []
        for index, item in enumerate(snapshot.recent_mistakes[-3:], start=1):
            lines.append(
                f"{index}. 题型：{item['question_type']}；难度：{item['difficulty']}；"
                f"学生答案：{item['user_answer']}；标准答案：{item['correct_answer']}；"
                f"错误分析：{str(item['analysis'])[:120]}"
            )
        return "\n".join(lines)

    def _build_fallback_exercises(
        self,
        request: ExerciseGenerationRequest,
        snapshot: LearnerPersonalizationSnapshot,
    ) -> dict[str, object]:
        question_types = cycle(QUESTION_TYPE_SEQUENCE)
        difficulty_plan = self._build_difficulty_plan(request.exercise_count)
        self_test_points = self._extract_self_test_points(request)
        mistake_focus = self._extract_mistake_focus(snapshot)
        exercises: list[dict[str, object]] = []

        for index in range(request.exercise_count):
            question_type = next(question_types)
            difficulty = difficulty_plan[index]
            focus_point = self_test_points[index % len(self_test_points)] if self_test_points else ""
            mistake_hint = mistake_focus[index % len(mistake_focus)] if mistake_focus else ""
            prompt, options, answer, analysis = self._build_question(
                knowledge_point=request.knowledge_point,
                question_type=question_type,
                difficulty=difficulty,
                index=index + 1,
                generation_mode=request.generation_mode,
                focus_point=focus_point,
                mistake_hint=mistake_hint,
                mastery_score=snapshot.mastery_score,
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

        return {"exercises": exercises}

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
        picked = [line for line in lines if "常见错误" in line or "学完后自测" in line or "重点难点" in line]
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
        return [f"围绕 {request.knowledge_point} 做基础理解与应用练习。"]

    def _extract_mistake_focus(self, snapshot: LearnerPersonalizationSnapshot) -> list[str]:
        focus_items = []
        for item in snapshot.recent_mistakes[-3:]:
            focus_items.append(str(item["analysis"])[:120])
        return focus_items

    def _build_summary_text(
        self,
        request: ExerciseGenerationRequest,
        count: int,
        snapshot: LearnerPersonalizationSnapshot,
    ) -> str:
        prefix = {
            "self_test": "已生成一组课后自测题。",
            "remedial": "已根据真实错题生成一组变式重练题。",
            "practice": "已生成一组分层练习题。",
        }.get(request.generation_mode, "已生成一组练习题。")

        if snapshot.answered_count:
            summary = (
                f"{prefix} 当前掌握度约 {snapshot.mastery_score}/100，"
                f"该知识点已有 {snapshot.answered_count} 次真实作答记录，"
                f"近期正确率约 {snapshot.correct_rate}%，本次共生成 {count} 道题。"
            )
        else:
            summary = f"{prefix} 当前还没有该知识点的真实作答记录，本次先用 {count} 道题做基础摸底。"

        weak_types = snapshot.learner_profile.get("weak_question_types", [])
        if weak_types:
            summary += f" 题目已针对近期薄弱题型 {', '.join(map(str, weak_types[:2]))} 做了强化。"

        if snapshot.recent_mistakes and request.generation_mode in {"self_test", "remedial"}:
            summary += " 其中部分题目直接围绕你最近错题暴露的问题做了变式设计。"

        return summary

    def _build_question(
        self,
        knowledge_point: str,
        question_type: str,
        difficulty: str,
        index: int,
        generation_mode: str,
        focus_point: str,
        mistake_hint: str,
        mastery_score: int,
    ) -> tuple[str, list[str], str, str]:
        article = self.knowledge_base.get_article(knowledge_point)
        topic = article.title if article is not None else knowledge_point
        novice_hint = mastery_score < 60

        if question_type == "choice":
            prompt = f"第 {index} 题：关于 {topic}，下面哪一项理解最准确？"
            options = [
                "A. 只要语法写对，就不用关心边界或条件变化。",
                "B. 写这类题时要同时关注对象、条件、边界和更新步骤。",
                "C. 只要结果能运行出来，中间逻辑是否清楚并不重要。",
                "D. 所有场景都适合用同一种写法解决。",
            ]
            answer = "B"
            analysis = (
                "这道题考查的是对知识点本质的理解。真正稳定的解题能力，不是只记住语法，"
                "而是能够同时检查对象、条件、边界和推进步骤。A、C、D 都忽略了程序设计里最关键的思考过程。"
            )
            if mistake_hint:
                analysis += f" 结合你最近的错题，这题特别提醒你：{mistake_hint}"
            return prompt, options, answer, analysis

        if question_type == "blank":
            prompt = (
                f"第 {index} 题：请填空。围绕 {topic} 做题时，如果只关注结果而没有检查边界，"
                "最容易出现的后果之一是 ______。"
            )
            answer = "程序逻辑出错或陷入死循环"
            analysis = (
                "这道题在检查你是否真正知道“为什么边界检查重要”。很多错误并不是语法错，"
                "而是条件、次数、索引或停止时机判断不清造成的。"
            )
            return prompt, [], answer, analysis

        if question_type == "judge":
            prompt = f"第 {index} 题：判断正误。学习 {topic} 时，只要会背定义，就说明已经真正掌握。"
            answer = "错误"
            analysis = (
                "真正掌握一个知识点，不只是会背定义，更重要的是能结合场景判断什么时候该用、为什么这样用、"
                "写完后怎么检查。"
            )
            return prompt, [], answer, analysis

        if question_type == "short_answer":
            prompt = (
                f"第 {index} 题：请用自己的话说明 {topic} 在实际学习或编程中能解决什么问题，"
                "并写出你在做这类题时最需要检查的两个步骤。"
            )
            answer = (
                "示例答案：它可以帮助我们按规则处理重复任务或分支决策。"
                "做题时需要重点检查对象/条件是否明确，以及边界和更新步骤是否完整。"
            )
            analysis = (
                "这道题不只是让你重复定义，而是要求你把知识点和真实任务连接起来。"
                "如果你能清楚说出作用、场景和检查步骤，说明理解已经开始从“知道”走向“会用”。"
            )
            if novice_hint:
                analysis += " 如果你觉得难，可以先从“它帮我省掉了哪些重复劳动”这个角度组织答案。"
            return prompt, [], answer, analysis

        prompt = (
            f"第 {index} 题：编写一段简单代码，围绕 {topic} 完成一个基础任务，并简要说明你的代码思路。"
        )
        answer = (
            "参考答案示例：\n"
            "nums = [3, 8, 11, 14, 20]\n"
            "result = []\n"
            "for num in nums:\n"
            "    if num % 2 == 0:\n"
            "        result.append(num)\n"
            "print(result)\n"
            "思路说明：先遍历数据，再在循环中完成筛选，最后输出处理结果。"
        )
        analysis = (
            "这道题考查你是否能把概念落到实际代码。写这类题时，要先明确处理对象，再明确每一轮做什么，"
            "最后检查条件和输出是否对应题意。"
        )
        if generation_mode == "remedial" and mistake_hint:
            analysis += f" 这道题还专门针对你最近的错误做了提醒：{mistake_hint}"
        return prompt, [], answer, analysis

    def _persist_exercises(
        self,
        db: Session,
        request: ExerciseGenerationRequest,
        exercises: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        knowledge_point = self._resolve_or_create_knowledge_point(db, request.knowledge_point)
        persisted: list[dict[str, object]] = []

        for exercise in exercises[: request.exercise_count]:
            payload = {
                "knowledge_point": str(exercise["knowledge_point"]),
                "question_type": str(exercise["question_type"]),
                "prompt": str(exercise["prompt"]),
                "options": exercise.get("options", []),
                "generation_mode": request.generation_mode,
            }
            row = Exercise(
                knowledge_point_id=knowledge_point.id,
                type=str(exercise["question_type"]),
                difficulty=self._difficulty_to_level(str(exercise["difficulty"])),
                content=json.dumps(payload, ensure_ascii=False),
                answer=str(exercise["answer"]),
                analysis=str(exercise["analysis"]),
            )
            db.add(row)
            db.flush()
            persisted.append(
                {
                    "exercise_id": row.id,
                    "knowledge_point": str(exercise["knowledge_point"]),
                    "question_type": str(exercise["question_type"]),
                    "difficulty": str(exercise["difficulty"]),
                    "prompt": str(exercise["prompt"]),
                    "options": list(exercise.get("options", [])),
                    "answer": str(exercise["answer"]),
                    "analysis": str(exercise["analysis"]),
                }
            )

        db.commit()
        return persisted

    def _resolve_or_create_knowledge_point(self, db: Session, knowledge_point: str) -> KnowledgePoint:
        existing = db.query(KnowledgePoint).filter(KnowledgePoint.name == knowledge_point).first()
        if existing is not None:
            return existing

        article = self.knowledge_base.get_article(knowledge_point)
        record = KnowledgePoint(
            name=knowledge_point,
            description=article.summary if article is not None else f"{knowledge_point} 自动生成知识点。",
            difficulty=2,
            importance=3,
            subject_id=1,
        )
        db.add(record)
        db.flush()
        return record

    def _difficulty_to_level(self, difficulty: str) -> int:
        return {"foundation": 1, "intermediate": 2, "advanced": 3}.get(difficulty, 1)
