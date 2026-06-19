"""Structured exercise generation service for the student workspace."""

from __future__ import annotations

import json
import random
import re
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
            knowledge_point = self._resolve_or_create_knowledge_point(db, request.knowledge_point)
            previous_signatures = self._load_recent_exercise_signatures(db, knowledge_point.id)
            agent_plan = self._build_exercise_agent_plan(request, snapshot, previous_signatures)

            try:
                generated = self._try_generate_with_llm(request, snapshot, agent_plan)
            except TypeError:
                generated = self._try_generate_with_llm(request, snapshot)
            if generated is None:
                generated = self._build_fallback_exercises(request, snapshot, previous_signatures, agent_plan)
            generated["exercises"] = self._complete_with_fallback_exercises(
                request=request,
                snapshot=snapshot,
                exercises=self._dedupe_exercises(list(generated["exercises"])),
                previous_signatures=previous_signatures,
                agent_plan=agent_plan,
            )

            persisted_exercises = self._persist_exercises(
                db=db,
                request=request,
                knowledge_point=knowledge_point,
                exercises=generated["exercises"],
            )
            personalization = self._build_personalization_payload(snapshot)
            personalization["exercise_generation_agent"] = agent_plan
            return {
                "user_id": request.user_id,
                "knowledge_point": request.knowledge_point,
                "summary": self._build_summary_text(request, len(persisted_exercises), snapshot),
                "personalization": personalization,
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
        agent_plan: dict[str, object] | None = None,
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
                    "agent_plan": json.dumps(agent_plan or {}, ensure_ascii=False),
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

            normalized_exercises = self._dedupe_exercises(normalized_exercises)
            if not normalized_exercises:
                return None
            if len(normalized_exercises) < request.exercise_count:
                normalized_exercises = self._complete_with_fallback_exercises(
                    request=request,
                    snapshot=snapshot,
                    exercises=normalized_exercises,
                )

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

    def _build_exercise_agent_plan(
        self,
        request: ExerciseGenerationRequest,
        snapshot: LearnerPersonalizationSnapshot,
        previous_signatures: set[str],
    ) -> dict[str, object]:
        """Analyze learner context before the exercise-generation agent creates questions."""

        article = self.knowledge_base.get_article(request.knowledge_point)
        self_test_points = self._extract_self_test_points(request)
        courseware_focus = self._extract_courseware_focus(request.courseware_content)
        weak_types = [str(item) for item in snapshot.learner_profile.get("weak_question_types", [])][:3]
        recent_mistakes = [
            {
                "question_type": str(item.get("question_type", "")),
                "difficulty": str(item.get("difficulty", "")),
                "analysis": str(item.get("analysis", ""))[:120],
            }
            for item in snapshot.recent_mistakes[-3:]
        ]

        focus_points = [item for item in self_test_points if str(item).strip()]
        if article is not None:
            focus_points.extend(article.concepts[:3])
            focus_points.extend(article.applications[:3])
            focus_points.extend(article.mistakes[:3])
        if courseware_focus:
            focus_points.insert(0, courseware_focus[:180])
        if not focus_points:
            focus_points = [
                f"{request.knowledge_point} 核心概念",
                f"{request.knowledge_point} 应用场景",
                f"{request.knowledge_point} 易错点",
            ]

        if snapshot.mastery_score < 40:
            difficulty_mix = {"foundation": 0.7, "intermediate": 0.3, "advanced": 0.0}
        elif snapshot.mastery_score < 70:
            difficulty_mix = {"foundation": 0.5, "intermediate": 0.4, "advanced": 0.1}
        else:
            difficulty_mix = {"foundation": 0.3, "intermediate": 0.5, "advanced": 0.2}

        question_type_targets = QUESTION_TYPE_SEQUENCE[:]
        if weak_types:
            question_type_targets = list(dict.fromkeys([*weak_types, *QUESTION_TYPE_SEQUENCE]))

        return {
            "agent": "exercise_generation_agent",
            "analysis_source": "learner_profile+knowledge_base+courseware+mistake_history",
            "learning_scope": request.knowledge_point,
            "generation_mode": request.generation_mode,
            "mastery_score": snapshot.mastery_score,
            "correct_rate": snapshot.correct_rate,
            "answered_count": snapshot.answered_count,
            "recent_generated_count": len(previous_signatures),
            "focus_points": focus_points[:8],
            "weak_question_types": weak_types,
            "recent_mistake_focus": recent_mistakes,
            "difficulty_mix": difficulty_mix,
            "question_type_targets": question_type_targets[: request.exercise_count],
            "strategy": [
                "先覆盖学习范围内的核心概念和应用场景",
                "再针对错题或薄弱题型生成变式",
                "同一组内题干、题型和考查角度不得重复",
                "连续生成时优先避开近期已生成题，但不足时必须补足新变式",
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

    def _dedupe_exercises(self, exercises: list[dict[str, object]]) -> list[dict[str, object]]:
        """Remove repeated questions before they reach the frontend."""

        seen: set[str] = set()
        unique: list[dict[str, object]] = []
        for exercise in exercises:
            signature = self._exercise_signature(exercise)
            if signature in seen:
                continue
            seen.add(signature)
            unique.append(exercise)
        return unique

    def _exercise_signature(self, exercise: dict[str, object]) -> str:
        prompt = str(exercise.get("prompt", ""))
        prompt = re.sub(r"第\s*\d+\s*题[:：]?", "", prompt)
        prompt = re.sub(r"第\s*\d+\s*题[:：]?", "", prompt)
        prompt = re.sub(r"\s+", "", prompt).lower()
        return f"{exercise.get('question_type')}::{prompt}"

    def _load_recent_exercise_signatures(self, db: Session, knowledge_point_id: int) -> set[str]:
        rows = (
            db.query(Exercise)
            .filter(Exercise.knowledge_point_id == knowledge_point_id)
            .order_by(Exercise.id.desc())
            .limit(80)
            .all()
        )
        signatures: set[str] = set()
        for row in rows:
            try:
                payload = json.loads(row.content or "{}")
            except json.JSONDecodeError:
                payload = {}
            signatures.add(
                self._exercise_signature(
                    {
                        "question_type": payload.get("question_type", row.type),
                        "prompt": payload.get("prompt", row.content),
                    }
                )
            )
        return signatures

    def _complete_with_fallback_exercises(
        self,
        request: ExerciseGenerationRequest,
        snapshot: LearnerPersonalizationSnapshot,
        exercises: list[dict[str, object]],
        previous_signatures: set[str] | None = None,
        agent_plan: dict[str, object] | None = None,
    ) -> list[dict[str, object]]:
        """Fill missing slots when an LLM returns duplicate or incomplete questions."""

        previous_signatures = previous_signatures or set()
        completed = []
        skipped_existing = []
        for exercise in exercises:
            if self._exercise_signature(exercise) in previous_signatures:
                skipped_existing.append(exercise)
                continue
            completed.append(exercise)
        seen = {self._exercise_signature(exercise) for exercise in completed}
        fallback = self._build_fallback_exercises(request, snapshot, previous_signatures | seen, agent_plan)["exercises"]

        for _ in range(request.exercise_count * 3):
            for fallback_exercise in fallback:
                if len(completed) >= request.exercise_count:
                    break
                candidate = dict(fallback_exercise)
                candidate["exercise_id"] = len(completed) + 1
                candidate["prompt"] = self._reindex_prompt(str(candidate["prompt"]), len(completed) + 1)
                signature = self._exercise_signature(candidate)
                if signature in seen or signature in previous_signatures:
                    continue
                seen.add(signature)
                completed.append(candidate)
            if len(completed) >= request.exercise_count:
                break

        for exercise in skipped_existing:
            if len(completed) >= request.exercise_count:
                break
            signature = self._exercise_signature(exercise)
            if signature in seen:
                continue
            seen.add(signature)
            completed.append(exercise)

        if len(completed) < request.exercise_count:
            unlimited_fallback = self._build_fallback_exercises(request, snapshot, set(), agent_plan)["exercises"]
            for fallback_exercise in unlimited_fallback:
                if len(completed) >= request.exercise_count:
                    break
                candidate = dict(fallback_exercise)
                candidate["exercise_id"] = len(completed) + 1
                candidate["prompt"] = self._reindex_prompt(str(candidate["prompt"]), len(completed) + 1)
                signature = self._exercise_signature(candidate)
                if signature in seen:
                    continue
                seen.add(signature)
                completed.append(candidate)

        while len(completed) < request.exercise_count:
            index = len(completed) + 1
            candidate = self._dynamic_short_answer_question(
                index=index,
                topic=request.knowledge_point,
                focus=f"{request.knowledge_point} 持续生成变式 {random.SystemRandom().randrange(1000000, 9999999)}",
                scenario="学习范围内综合应用",
                action="先分析条件再验证结果",
                request=request,
                weak_hint="",
            )
            completed.append(candidate)

        return completed[: request.exercise_count]

    def _reindex_prompt(self, prompt: str, index: int) -> str:
        return re.sub(r"第\s*\d+\s*题", f"第 {index} 题", prompt, count=1)

    def _build_fallback_exercises(
        self,
        request: ExerciseGenerationRequest,
        snapshot: LearnerPersonalizationSnapshot,
        previous_signatures: set[str] | None = None,
        agent_plan: dict[str, object] | None = None,
    ) -> dict[str, object]:
        return {"exercises": self._build_varied_fallback_exercises(request, snapshot, previous_signatures or set(), agent_plan)}

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

    def _build_varied_fallback_exercises(
        self,
        request: ExerciseGenerationRequest,
        snapshot: LearnerPersonalizationSnapshot,
        previous_signatures: set[str],
        agent_plan: dict[str, object] | None = None,
    ) -> list[dict[str, object]]:
        rng = random.SystemRandom()
        difficulty_plan = self._build_agent_difficulty_plan(request.exercise_count, agent_plan)
        pool = self._build_fallback_candidate_pool(request, snapshot, agent_plan)
        pool.extend(self._build_dynamic_fallback_candidates(request, snapshot, request.exercise_count * 12, agent_plan))
        rng.shuffle(pool)

        selected: list[dict[str, object]] = []
        seen: set[str] = set()
        preferred_types = QUESTION_TYPE_SEQUENCE[:]
        rng.shuffle(preferred_types)

        def try_add(candidate: dict[str, object]) -> bool:
            signature = self._exercise_signature(candidate)
            if signature in seen or signature in previous_signatures:
                return False
            selected.append(candidate)
            seen.add(signature)
            return True

        for question_type in preferred_types:
            for candidate in pool:
                if len(selected) >= request.exercise_count:
                    break
                if candidate["question_type"] == question_type and try_add(dict(candidate)):
                    break

        for candidate in pool:
            if len(selected) >= request.exercise_count:
                break
            try_add(dict(candidate))

        if len(selected) < request.exercise_count:
            extra_pool = self._build_dynamic_fallback_candidates(request, snapshot, request.exercise_count * 20, agent_plan)
            rng.shuffle(extra_pool)
            for candidate in extra_pool:
                if len(selected) >= request.exercise_count:
                    break
                try_add(dict(candidate))

        if len(selected) < request.exercise_count:
            for candidate in pool:
                if len(selected) >= request.exercise_count:
                    break
                signature = self._exercise_signature(candidate)
                if signature in seen:
                    continue
                selected.append(dict(candidate))
                seen.add(signature)

        while len(selected) < request.exercise_count:
            index = len(selected) + 1
            selected.append(
                self._dynamic_short_answer_question(
                    index=index,
                    topic=request.knowledge_point,
                    focus=f"{request.knowledge_point} 变式练习 {index}-{random.SystemRandom().randrange(100000, 999999)}",
                    scenario="学习范围内综合应用",
                    action="先分析条件再验证结果",
                    request=request,
                    weak_hint="",
                )
            )

        for index, exercise in enumerate(selected[: request.exercise_count], start=1):
            exercise["exercise_id"] = index
            exercise["knowledge_point"] = request.knowledge_point
            exercise["difficulty"] = difficulty_plan[(index - 1) % len(difficulty_plan)]
            exercise["prompt"] = re.sub(r"^第\s*\d+\s*题[:：]?", f"第 {index} 题：", str(exercise["prompt"]))
        return selected[: request.exercise_count]

    def _build_fallback_candidate_pool(
        self,
        request: ExerciseGenerationRequest,
        snapshot: LearnerPersonalizationSnapshot,
        agent_plan: dict[str, object] | None = None,
    ) -> list[dict[str, object]]:
        article = self.knowledge_base.get_article(request.knowledge_point)
        topic = article.title if article is not None else request.knowledge_point
        focus_points = self._agent_focus_points(request, agent_plan)
        if article is not None:
            focus_points = [*focus_points, *article.concepts[:4], *article.applications[:4], *article.mistakes[:4]]
        focus_points = [item.strip() for item in focus_points if str(item).strip()]
        if not focus_points:
            focus_points = [
                f"{topic} 的核心概念",
                f"{topic} 的适用场景",
                f"{topic} 的边界条件",
                f"{topic} 的常见错误",
                f"{topic} 的实践应用",
            ]

        weak_hint = ""
        if snapshot.recent_mistakes:
            weak_hint = str(snapshot.recent_mistakes[-1].get("analysis", ""))[:80]

        pool: list[dict[str, object]] = []
        for focus_index, focus in enumerate(focus_points[:10], start=1):
            pool.extend(
                [
                    {
                        "exercise_id": 0,
                        "knowledge_point": request.knowledge_point,
                        "question_type": "choice",
                        "difficulty": "foundation",
                        "prompt": f"第 0 题：学习 {topic} 时，针对“{focus}”，下面哪一种做法最可靠？",
                        "options": [
                            "A. 先明确对象、条件和目标，再选择方法。",
                            "B. 只记住一个固定答案，遇到相似题直接套用。",
                            "C. 先看最终结果，过程是否合理可以忽略。",
                            "D. 不需要检查边界条件，只要语法正确即可。",
                        ],
                        "answer": "A",
                        "analysis": f"这道题考查你能否把 {topic} 放到具体学习范围“{focus}”中理解。可靠做法是先分析对象、条件和目标，再决定解法。",
                    },
                    {
                        "exercise_id": 0,
                        "knowledge_point": request.knowledge_point,
                        "question_type": "choice",
                        "difficulty": "intermediate",
                        "prompt": f"第 0 题：如果要判断自己是否真正掌握“{focus}”，最能说明问题的是哪一项？",
                        "options": [
                            "A. 能背出相关定义。",
                            "B. 能在新场景中说明使用条件、步骤和检查方法。",
                            "C. 看过一次例题。",
                            "D. 能把答案写得很长。",
                        ],
                        "answer": "B",
                        "analysis": "真正掌握不是只会复述，而是能迁移到新场景，并解释为什么这样做、如何验证。",
                    },
                    {
                        "exercise_id": 0,
                        "knowledge_point": request.knowledge_point,
                        "question_type": "blank",
                        "difficulty": "foundation",
                        "prompt": f"第 0 题：围绕“{focus}”做题时，除了关注结论，还要检查条件、步骤和 ______。",
                        "options": [],
                        "answer": "边界情况",
                        "analysis": "边界情况常常决定答案是否稳定。只看一般情况，容易漏掉特殊输入、极端条件或停止条件。",
                    },
                    {
                        "exercise_id": 0,
                        "knowledge_point": request.knowledge_point,
                        "question_type": "blank",
                        "difficulty": "intermediate",
                        "prompt": f"第 0 题：把 {topic} 用到“{focus}”时，第一步通常不是直接写答案，而是先明确 ______ 和 ______。",
                        "options": [],
                        "answer": "处理对象；约束条件",
                        "analysis": "先明确处理对象和约束条件，才能判断后续步骤是否符合题意。",
                    },
                    {
                        "exercise_id": 0,
                        "knowledge_point": request.knowledge_point,
                        "question_type": "judge",
                        "difficulty": "foundation",
                        "prompt": f"第 0 题：判断正误。只要记住 {topic} 的定义，就一定能解决“{focus}”相关问题。",
                        "options": [],
                        "answer": "错误",
                        "analysis": "定义只是起点。解决具体问题还需要识别场景、分析条件、选择步骤并检查结果。",
                    },
                    {
                        "exercise_id": 0,
                        "knowledge_point": request.knowledge_point,
                        "question_type": "judge",
                        "difficulty": "intermediate",
                        "prompt": f"第 0 题：判断正误。复盘“{focus}”相关错题时，应先定位错在概念、条件、步骤还是检查环节。",
                        "options": [],
                        "answer": "正确",
                        "analysis": "错题复盘的核心是定位错误来源。知道错在哪里，才能产生下一次可执行的改进。",
                    },
                    {
                        "exercise_id": 0,
                        "knowledge_point": request.knowledge_point,
                        "question_type": "short_answer",
                        "difficulty": "intermediate",
                        "prompt": f"第 0 题：请用自己的话说明 {topic} 和“{focus}”之间的关系，并写出你解这类题时会检查的两个点。",
                        "options": [],
                        "answer": "示例：先说明该知识点在这个范围内解决什么问题，再检查处理对象是否明确、条件和边界是否完整。",
                        "analysis": "这道题考查迁移表达。好的回答要包含作用、适用条件和检查点，而不是只重复定义。",
                    },
                    {
                        "exercise_id": 0,
                        "knowledge_point": request.knowledge_point,
                        "question_type": "short_answer",
                        "difficulty": "advanced",
                        "prompt": f"第 0 题：如果同学在“{focus}”上反复出错，请设计一个排查流程，至少包含三步。",
                        "options": [],
                        "answer": "示例：先复述题意并标出已知条件；再定位使用的概念或步骤；最后用边界情况或反例检查答案。",
                        "analysis": f"排查流程要能把错误从“不会”拆成可观察的问题。{weak_hint}" if weak_hint else "排查流程要能把错误从“不会”拆成可观察的问题。",
                    },
                    {
                        "exercise_id": 0,
                        "knowledge_point": request.knowledge_point,
                        "question_type": "programming",
                        "difficulty": "intermediate",
                        "prompt": f"第 0 题：请写一段简单伪代码或 Python 代码，演示如何围绕“{focus}”完成一个输入、处理、输出的小任务。",
                        "options": [],
                        "answer": "示例：先定义输入数据，再按条件处理，最后输出结果。代码可用列表遍历、条件判断或函数封装表达思路。",
                        "analysis": "编程题重点不在代码长度，而在是否有清楚的数据对象、处理规则和输出验证。",
                    },
                    {
                        "exercise_id": 0,
                        "knowledge_point": request.knowledge_point,
                        "question_type": "programming",
                        "difficulty": "advanced",
                        "prompt": f"第 0 题：针对“{focus}”，写一个包含正常情况和边界情况检查的代码思路，并说明为什么要这样检查。",
                        "options": [],
                        "answer": "示例：先处理正常输入，再补充空值、极端值或不满足条件的情况，最后说明每个检查对应的风险。",
                        "analysis": "进阶题关注稳定性。能主动补充边界检查，说明你不只是会写流程，也在验证流程是否可靠。",
                    },
                ]
            )

        for index, item in enumerate(pool, start=1):
            item["exercise_id"] = index
            if "第 0 题" in str(item["prompt"]):
                item["prompt"] = str(item["prompt"]).replace("第 0 题", f"第 {index} 题", 1)
            item["variant_key"] = f"fallback-{focus_index}-{index}"
        return pool

    def _build_dynamic_fallback_candidates(
        self,
        request: ExerciseGenerationRequest,
        snapshot: LearnerPersonalizationSnapshot,
        target_count: int,
        agent_plan: dict[str, object] | None = None,
    ) -> list[dict[str, object]]:
        rng = random.SystemRandom()
        article = self.knowledge_base.get_article(request.knowledge_point)
        topic = article.title if article is not None else request.knowledge_point
        focus_points = self._agent_focus_points(request, agent_plan)
        if article is not None:
            focus_points.extend(article.concepts[:6])
            focus_points.extend(article.applications[:6])
            focus_points.extend(article.mistakes[:6])
        focus_points = [str(item).strip() for item in focus_points if str(item).strip()]
        if not focus_points:
            focus_points = [
                "核心概念理解",
                "典型应用场景",
                "边界条件检查",
                "常见错误修正",
                "解题步骤迁移",
                "代码实现验证",
            ]

        scenarios = [
            "课堂例题变式",
            "课后自测",
            "错题复盘",
            "真实应用",
            "同伴讲解",
            "代码调试",
            "边界案例",
            "流程设计",
            "结果验证",
            "概念迁移",
        ]
        actions = [
            "先定位输入和输出",
            "拆分条件和步骤",
            "补充边界检查",
            "比较两种解法",
            "解释错误原因",
            "设计验证用例",
            "把概念迁移到新场景",
            "用自己的话复述规则",
        ]
        weak_hint = ""
        if snapshot.recent_mistakes:
            weak_hint = str(snapshot.recent_mistakes[-1].get("analysis", ""))[:80]

        builders = [
            self._dynamic_choice_question,
            self._dynamic_blank_question,
            self._dynamic_judge_question,
            self._dynamic_short_answer_question,
            self._dynamic_programming_question,
        ]
        candidates: list[dict[str, object]] = []
        for index in range(max(target_count, request.exercise_count * 10)):
            focus = rng.choice(focus_points)
            scenario = rng.choice(scenarios)
            action = rng.choice(actions)
            builder = builders[index % len(builders)]
            candidates.append(
                builder(
                    index=index + 1,
                    topic=topic,
                    focus=focus,
                    scenario=scenario,
                    action=action,
                    request=request,
                    weak_hint=weak_hint,
                )
            )
        return candidates

    def _dynamic_choice_question(
        self,
        index: int,
        topic: str,
        focus: str,
        scenario: str,
        action: str,
        request: ExerciseGenerationRequest,
        weak_hint: str,
    ) -> dict[str, object]:
        return {
            "exercise_id": index,
            "knowledge_point": request.knowledge_point,
            "question_type": "choice",
            "difficulty": "foundation",
            "prompt": f"第 {index} 题：在{scenario}中学习 {topic} 的“{focus}”时，哪一步最应该优先完成？",
            "options": [
                f"A. {action}，再根据条件选择方法。",
                "B. 直接套用上一次见过的答案。",
                "C. 只检查最后结果，不看过程。",
                "D. 遇到不确定条件时先忽略。",
            ],
            "answer": "A",
            "analysis": f"这题考查学习范围内的具体处理顺序。围绕“{focus}”，应先把对象、条件和步骤说清楚，再求结果。",
        }

    def _dynamic_blank_question(
        self,
        index: int,
        topic: str,
        focus: str,
        scenario: str,
        action: str,
        request: ExerciseGenerationRequest,
        weak_hint: str,
    ) -> dict[str, object]:
        return {
            "exercise_id": index,
            "knowledge_point": request.knowledge_point,
            "question_type": "blank",
            "difficulty": "foundation",
            "prompt": f"第 {index} 题：在{scenario}里处理“{focus}”时，为了避免只会套模板，应先明确处理对象、约束条件和 ______。",
            "options": [],
            "answer": "检查标准",
            "analysis": f"检查标准决定你如何判断答案是否正确。{action} 也需要围绕明确标准展开。",
        }

    def _dynamic_judge_question(
        self,
        index: int,
        topic: str,
        focus: str,
        scenario: str,
        action: str,
        request: ExerciseGenerationRequest,
        weak_hint: str,
    ) -> dict[str, object]:
        return {
            "exercise_id": index,
            "knowledge_point": request.knowledge_point,
            "question_type": "judge",
            "difficulty": "intermediate",
            "prompt": f"第 {index} 题：判断正误。在{scenario}中，只要能说出 {topic} 的定义，就可以不用分析“{focus}”的适用条件。",
            "options": [],
            "answer": "错误",
            "analysis": "定义不能替代条件分析。真正会用，需要说明什么时候能用、为什么能用、怎样检查。",
        }

    def _dynamic_short_answer_question(
        self,
        index: int,
        topic: str,
        focus: str,
        scenario: str,
        action: str,
        request: ExerciseGenerationRequest,
        weak_hint: str,
    ) -> dict[str, object]:
        hint = f" 可结合最近错因：{weak_hint}" if weak_hint else ""
        return {
            "exercise_id": index,
            "knowledge_point": request.knowledge_point,
            "question_type": "short_answer",
            "difficulty": "intermediate",
            "prompt": f"第 {index} 题：请说明在{scenario}中如何用 {topic} 解决“{focus}”相关问题，并写出两个检查点。",
            "options": [],
            "answer": f"示例：先说明问题对象和条件，再执行“{action}”，最后检查边界情况与结果是否符合题意。",
            "analysis": f"简答题重点是把知识点和具体学习范围连接起来，回答应包含场景、步骤和检查点。{hint}",
        }

    def _dynamic_programming_question(
        self,
        index: int,
        topic: str,
        focus: str,
        scenario: str,
        action: str,
        request: ExerciseGenerationRequest,
        weak_hint: str,
    ) -> dict[str, object]:
        return {
            "exercise_id": index,
            "knowledge_point": request.knowledge_point,
            "question_type": "programming",
            "difficulty": "advanced",
            "prompt": f"第 {index} 题：围绕“{focus}”，写一个简单代码思路，体现{action}，并说明如何验证输出。",
            "options": [],
            "answer": "示例：定义输入数据；按条件处理；输出结果；再用正常输入、空输入或边界输入验证。",
            "analysis": "编程题关注思路完整性：输入是什么、处理规则是什么、输出如何验证，都要清楚。",
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

    def _build_agent_difficulty_plan(
        self,
        exercise_count: int,
        agent_plan: dict[str, object] | None,
    ) -> list[str]:
        mix = (agent_plan or {}).get("difficulty_mix")
        if not isinstance(mix, dict):
            return self._build_difficulty_plan(exercise_count)

        difficulties: list[str] = []
        for difficulty in ("foundation", "intermediate", "advanced"):
            ratio = float(mix.get(difficulty, 0) or 0)
            difficulties.extend([difficulty] * max(0, round(exercise_count * ratio)))
        while len(difficulties) < exercise_count:
            difficulties.append("intermediate")
        return difficulties[:exercise_count]

    def _agent_focus_points(
        self,
        request: ExerciseGenerationRequest,
        agent_plan: dict[str, object] | None,
    ) -> list[str]:
        plan_points = (agent_plan or {}).get("focus_points")
        if isinstance(plan_points, list):
            points = [str(item).strip() for item in plan_points if str(item).strip()]
            if points:
                return points
        return self._extract_self_test_points(request)

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
            prompt, options, answer, analysis = self._build_choice_variant(
                topic=topic,
                index=index,
                difficulty=difficulty,
                focus_point=focus_point,
            )
            if mistake_hint:
                analysis += f" 结合你最近的错题，这题特别提醒你：{mistake_hint}"
            return prompt, options, answer, analysis
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

    def _build_choice_variant(
        self,
        topic: str,
        index: int,
        difficulty: str,
        focus_point: str,
    ) -> tuple[str, list[str], str, str]:
        focus = focus_point or topic
        variants = [
            (
                f"第 {index} 题：关于 {topic}，下面哪一项理解最准确？",
                [
                    "A. 只要语法写对，就不用关心边界或条件变化。",
                    "B. 解题时要同时关注对象、条件、边界和推导步骤。",
                    "C. 只要结果能运行出来，中间逻辑是否清楚并不重要。",
                    "D. 所有场景都适合同一种方法解决。",
                ],
                "B",
                "这道题考查基础理解。稳定的解题能力来自对对象、条件、边界和步骤的同时检查。",
            ),
            (
                f"第 {index} 题：围绕 {focus} 做练习时，最应该先确认什么？",
                [
                    "A. 题目要处理的对象和已知条件。",
                    "B. 最后答案写得越长越好。",
                    "C. 先套一个固定公式，再看是否合适。",
                    "D. 只检查最终结果，不需要检查过程。",
                ],
                "A",
                "先确认对象和条件，才能判断该用哪个方法以及每一步是否有依据。",
            ),
            (
                f"第 {index} 题：如果一道 {topic} 题做错了，最有效的复盘方式是哪一项？",
                [
                    "A. 只记住正确答案，下次照抄。",
                    "B. 找出错在概念、条件、边界还是计算步骤。",
                    "C. 直接换下一题，不看解析。",
                    "D. 把所有类似题都归为同一种题型。",
                ],
                "B",
                "复盘要定位错误来源，才能形成可迁移的修正策略。",
            ),
            (
                f"第 {index} 题：面对一个稍复杂的 {topic} 应用场景，下面哪种做法更可靠？",
                [
                    "A. 先拆成小步骤，再逐步验证每一步。",
                    "B. 直接凭直觉选择答案。",
                    "C. 跳过条件分析，只看关键词。",
                    "D. 遇到不会的部分就默认不重要。",
                ],
                "A",
                "复杂题更需要拆解和验证。这样可以减少漏条件、漏边界和过程错误。",
            ),
        ]
        prompt, options, answer, analysis = variants[(index - 1) % len(variants)]
        if difficulty == "advanced":
            analysis += " 这题的进阶点在于要把条件拆解和过程验证结合起来。"
        return prompt, options, answer, analysis

    def _persist_exercises(
        self,
        db: Session,
        request: ExerciseGenerationRequest,
        exercises: list[dict[str, object]],
        knowledge_point: KnowledgePoint | None = None,
    ) -> list[dict[str, object]]:
        knowledge_point = knowledge_point or self._resolve_or_create_knowledge_point(db, request.knowledge_point)
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
