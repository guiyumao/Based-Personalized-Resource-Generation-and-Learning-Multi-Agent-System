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
DEFAULT_QUESTION_TYPE_COUNTS = {"choice": 5, "judge": 3, "blank": 2}


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
                generated = self._try_generate_with_llm(
                    request,
                    snapshot,
                    agent_plan,
                    previous_signatures,
                )
            except TypeError:
                generated = self._try_generate_with_llm(request, snapshot)
            if generated is None:
                generated = self._build_fallback_exercises(request, snapshot, previous_signatures, agent_plan)
            else:
                # ── Audit: validate LLM output matches requested topic ──
                generated = self._audit_and_retry_exercises(
                    request, snapshot, generated, agent_plan, previous_signatures
                )
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
            question_type_counts=getattr(request, "question_type_counts", {}) or {},
            generation_mode=getattr(request, "generation_mode", "practice"),
            courseware_content=getattr(request, "courseware_content", "") or "",
        )

    def _try_generate_with_llm(
        self,
        request: ExerciseGenerationRequest,
        snapshot: LearnerPersonalizationSnapshot,
        agent_plan: dict[str, object] | None = None,
        previous_signatures: set[str] | None = None,
    ) -> dict[str, object] | None:
        previous_signatures = previous_signatures or set()
        article = self.knowledge_base.get_article(request.knowledge_point)
        grounding_text = self._build_grounding_text(article)
        courseware_focus = self._extract_courseware_focus(request.courseware_content)
        recent_mistakes_text = self._build_recent_mistakes_text(snapshot)

        # ── RAG retrieval ──
        context_text = ""
        try:
            from services.agent_service.app.services.rag import ChromaRetriever
            retriever = ChromaRetriever(self.settings)
            if retriever.is_available:
                context_text = retriever.retrieve_context_text(
                    query=f"{request.knowledge_point} {request.generation_mode}",
                    top_k=3,
                )
        except Exception:
            pass

        try:
            from langchain_core.output_parsers import StrOutputParser
            from langchain_core.prompts import ChatPromptTemplate

            llm = self.llm_factory.build_chat_model(temperature=0.15)
            prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", self._build_llm_system_prompt()),
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
                            "参考资料：{context_text}\n"
                            "知识底稿：{grounding_text}\n"
                            "课件重点：{courseware_focus}\n"
                            "课件摘要：{courseware_excerpt}\n"
                            "题目数量：{exercise_count}\n"
                            "难度比例：foundation 60%, intermediate 30%, advanced 10%\n"
                            "题型配比：{question_type_counts}\n"
                            "要求：\n"
                            "1. 每题都必须包含 prompt, options, answer, analysis。\n"
                            "2. 题干必须具体，不能出现占位描述。\n"
                            "3. 如果学生最近在某类题型或某个错误上反复失分，必须在题目设计里显式针对这个问题。\n"
                            "4. 选择题选项要有合理干扰性，解析要说明各选项对错原因。\n"
                            "5. 简答题和编程题解析要说明解题步骤、检查点和易错点。\n"
                            "6. 只输出 JSON，不要输出额外解释。\n"
                            "输出格式（严格 JSON）：\n"
                            "{{\n"
                            '  "summary": "字符串",\n'
                            '  "exercises": [\n'
                            "    {{\n"
                            '      "exercise_id": 1,\n'
                            '      "knowledge_point": "字符串",\n'
                            '      "question_type": "choice|blank|judge|short_answer|programming",\n'
                            '      "difficulty": "foundation|intermediate|advanced",\n'
                            '      "prompt": "题目内容",\n'
                            '      "options": ["A. ...", "B. ..."],\n'
                            '      "answer": "标准答案",\n'
                            '      "analysis": "详细解析"\n'
                            "    }}\n"
                            "  ]\n"
                            "}}\n"
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
                    "learner_profile": self._build_conditional_profile_text(request.knowledge_point, snapshot),
                    "personalization_basis": "\n".join(self._build_personalization_basis(snapshot)),
                    "recent_mistakes_text": recent_mistakes_text,
                    "context_text": context_text[:1200] if context_text else "暂无额外参考资料。",
                    "grounding_text": grounding_text[:1200],
                    "courseware_focus": courseware_focus[:500],
                    "agent_plan": json.dumps(agent_plan or {}, ensure_ascii=False),
                    "previous_question_signatures": json.dumps(
                        sorted(previous_signatures)[:40], ensure_ascii=False
                    ),
                    "courseware_excerpt": request.courseware_content[: self.settings.exercise_context_max_chars],
                    "exercise_count": request.exercise_count,
                    "question_type_counts": json.dumps(
                        self._question_type_counts(request), ensure_ascii=False
                    ),
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
                    previous_signatures=previous_signatures,
                    agent_plan=agent_plan,
                )

            normalized_exercises = self._enforce_question_type_counts(
                request=request,
                snapshot=snapshot,
                exercises=normalized_exercises,
                previous_signatures=previous_signatures,
                agent_plan=agent_plan,
            )

            return {
                "summary": str(payload.get("summary", "")),
                "exercises": normalized_exercises[: request.exercise_count],
            }
        except Exception as exc:
            import traceback, sys
            print("[exercise_generation] LLM call failed:", exc, file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            return None

    def _audit_and_retry_exercises(
        self,
        request: ExerciseGenerationRequest,
        snapshot: LearnerPersonalizationSnapshot,
        generated: dict[str, object],
        agent_plan: dict[str, object] | None,
        previous_signatures: set[str],
        max_retries: int = 2,
    ) -> dict[str, object]:
        """Audit LLM-generated exercises; retry with higher temperature on rejection."""
        from services.agent_service.app.services.audit_service import AuditService

        auditor = AuditService(self.settings)
        exercises = list(generated.get("exercises", []))

        for attempt in range(max_retries + 1):
            passed, reason = auditor.audit_exercises(request.knowledge_point, exercises)
            if passed:
                return generated  # ✅ passed audit

            # ❌ rejected — retry with higher temperature
            if attempt < max_retries:
                retry_temp = 0.15 + (attempt + 1) * 0.25  # 0.4, 0.65
                try:
                    from services.agent_service.app.services.llm_factory import LLMFactory
                    llm = LLMFactory(self.settings).build_chat_model(temperature=retry_temp)
                    from langchain_core.output_parsers import StrOutputParser
                    from langchain_core.prompts import ChatPromptTemplate
                    prompt = ChatPromptTemplate.from_messages([
                        ("system", self._build_llm_system_prompt()),
                        ("human", (
                            "请重新生成一组练习题，注意：\n"
                            "知识点：{knowledge_point}\n"
                            "生成模式：{generation_mode}\n"
                            "题目数量：{exercise_count}\n"
                            f"上次生成被驳回，原因：{reason}\n"
                            "请严格围绕知识点出题，不要跑题。只输出 JSON。"
                        )),
                    ])
                    chain = prompt | llm | StrOutputParser()
                    article = self.knowledge_base.get_article(request.knowledge_point)
                    grounding = self._build_grounding_text(article)[:800]
                    raw = chain.invoke({
                        "knowledge_point": request.knowledge_point,
                        "generation_mode": request.generation_mode,
                        "exercise_count": request.exercise_count,
                        "grounding_text": grounding,
                    })
                    parsed = self._extract_json(raw)
                    retry_exercises = parsed.get("exercises", [])
                    if retry_exercises:
                        generated = {**generated, "exercises": retry_exercises, "summary": str(parsed.get("summary", ""))}
                        exercises = retry_exercises
                except Exception:
                    pass  # retry failed → keep original

        return generated  # return whatever we have after max retries

    def _build_conditional_profile_text(self, knowledge_point: str, snapshot: LearnerPersonalizationSnapshot) -> str:
        """Only inject learner profile when the requested topic matches known weak areas."""
        if not snapshot or not knowledge_point:
            return "无特殊画像要求，请按通用标准出题。"
        weak_areas = snapshot.learner_profile.get("weak_question_types", []) if isinstance(snapshot.learner_profile, dict) else []
        # Check if the knowledge_point overlaps with any weak area
        kp_lower = knowledge_point.lower()
        matches = any(
            area.lower() in kp_lower or kp_lower in area.lower()
            for area in weak_areas
        )
        if matches:
            return json.dumps(snapshot.learner_profile, ensure_ascii=False)
        # New topic — don't force profile onto it
        return f"学生正在学习全新主题「{knowledge_point}」，请从基础概念出发出题，不要受学生历史画像影响。"

    def _extract_json(self, raw: str) -> dict[str, Any]:
        """Extract a JSON object from potentially noisy LLM output.

        Tries multiple strategies in order:
        1. Direct parse after stripping markdown fences.
        2. Balanced-brace extraction (handles nested objects / arrays).
        3. Common DeepSeek repair: unescape internal quotes, strip trailing
           text after the final closing brace.
        """
        cleaned = raw.strip()
        # ── strip markdown fences ──
        for prefix in ("```json", "```"):
            if cleaned.startswith(prefix):
                cleaned = cleaned.removeprefix(prefix).strip()
        if cleaned.endswith("```"):
            cleaned = cleaned.removesuffix("```").strip()

        # ── Strategy 1: direct parse ──
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # ── Strategy 2: balanced-brace extraction ──
        start = cleaned.find("{")
        if start >= 0:
            depth = 0
            in_string = False
            escape = False
            for i in range(start, len(cleaned)):
                ch = cleaned[i]
                if in_string:
                    if escape:
                        escape = False
                    elif ch == "\\":
                        escape = True
                    elif ch == '"':
                        in_string = False
                else:
                    if ch == '"':
                        in_string = True
                    elif ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0:
                            candidate = cleaned[start : i + 1]
                            try:
                                return json.loads(candidate)
                            except json.JSONDecodeError:
                                break  # balanced but invalid — fall through

        # ── Strategy 3: cut after last closing brace ──
        last_brace = cleaned.rfind("}")
        if last_brace >= 0:
            truncated = cleaned[: last_brace + 1]
            try:
                return json.loads(truncated)
            except json.JSONDecodeError:
                pass

        raise json.JSONDecodeError("Could not extract valid JSON", raw, 0)

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

    def _build_llm_system_prompt(self) -> str:
        return (
            f"{self.prompt_template}\n\n"
            "额外硬性要求：\n"
            "1. 先根据学习者画像、画像分析摘要、掌握度、近期错题和当前知识点确定出题角度，再生成题目。\n"
            "2. 题目必须体现个性化依据，尤其要针对薄弱题型、错误模式、学习速度、兴趣方向或目标导向中的至少一项。\n"
            "3. 不得生成与近期已生成题目签名相同或仅替换题号的题目。\n"
            "4. 如果近期题目签名很多，请改换考查场景、条件、数据、问法和干扰项，生成新的变式。\n"
            "5. 近期已生成题目签名如下：{previous_question_signatures}\n"
            "6. 智能体生成计划如下：{agent_plan}\n"
        )

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
            "profile_analysis_summaries": snapshot.learner_profile.get("profile_analysis_summaries", {}),
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
            "question_type_counts": self._question_type_counts(request),
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

        summaries = snapshot.learner_profile.get("profile_analysis_summaries", {})
        if isinstance(summaries, dict):
            for key in ("errorPreference", "learningSpeed", "knowledgeBase"):
                summary = str(summaries.get(key) or "").strip()
                if summary:
                    basis.append(f"深度画像提示：{summary}。")

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

    def _is_acceptable_generated_exercise(
        self,
        request: ExerciseGenerationRequest,
        exercise: dict[str, object],
    ) -> bool:
        if not self._is_calculus_topic(request.knowledge_point):
            return True

        fields = [
            str(exercise.get("prompt", "")),
            str(exercise.get("answer", "")),
            str(exercise.get("analysis", "")),
            " ".join(str(option) for option in exercise.get("options", []) or []),
        ]
        text = "\n".join(fields)
        blocked_fragments = (
            "??",
            "\ufffd",
            "哪一步最应该优先完成",
            "只会套模板",
            "写一个简单代码思路",
            "如何验证输出",
            "定义输入数据",
            "输出结果",
        )
        return not any(fragment in text for fragment in blocked_fragments)

    def _question_type_counts(self, request: ExerciseGenerationRequest) -> dict[str, int]:
        raw = request.question_type_counts or {}
        allowed = {"choice", "blank", "judge", "short_answer", "programming"}
        counts = {
            key: max(0, int(value))
            for key, value in raw.items()
            if key in allowed and isinstance(value, (int, float))
        }
        if not counts and request.exercise_count == 10:
            counts = dict(DEFAULT_QUESTION_TYPE_COUNTS)
        if not counts:
            return {}

        total = sum(counts.values())
        if total <= 0:
            return {}
        if total != request.exercise_count:
            scale = request.exercise_count / total
            scaled = {key: max(0, round(value * scale)) for key, value in counts.items()}
            while sum(scaled.values()) < request.exercise_count:
                key = max(counts, key=counts.get)
                scaled[key] = scaled.get(key, 0) + 1
            while sum(scaled.values()) > request.exercise_count:
                key = max(scaled, key=scaled.get)
                scaled[key] -= 1
            counts = {key: value for key, value in scaled.items() if value > 0}
        return counts

    def _question_type_sequence_for_request(self, request: ExerciseGenerationRequest) -> list[str]:
        counts = self._question_type_counts(request)
        if not counts:
            sequence = [QUESTION_TYPE_SEQUENCE[index % len(QUESTION_TYPE_SEQUENCE)] for index in range(request.exercise_count)]
            if self._is_calculus_topic(request.knowledge_point):
                return ["short_answer" if item == "programming" else item for item in sequence]
            return sequence
        sequence: list[str] = []
        for question_type in ("choice", "judge", "blank", "short_answer", "programming"):
            sequence.extend([question_type] * counts.get(question_type, 0))
        if self._is_calculus_topic(request.knowledge_point):
            sequence = ["short_answer" if item == "programming" else item for item in sequence]
        return sequence[: request.exercise_count]

    def _enforce_question_type_counts(
        self,
        *,
        request: ExerciseGenerationRequest,
        snapshot: LearnerPersonalizationSnapshot,
        exercises: list[dict[str, object]],
        previous_signatures: set[str],
        agent_plan: dict[str, object] | None,
    ) -> list[dict[str, object]]:
        sequence = self._question_type_sequence_for_request(request)
        if not sequence:
            return exercises[: request.exercise_count]

        remaining: dict[str, list[dict[str, object]]] = {}
        for exercise in exercises:
            if not self._is_acceptable_generated_exercise(request, exercise):
                continue
            remaining.setdefault(str(exercise.get("question_type")), []).append(dict(exercise))

        seen: set[str] = set()
        enforced: list[dict[str, object]] = []
        dynamic_pool = self._build_dynamic_fallback_candidates(
            request,
            snapshot,
            request.exercise_count * 20,
            agent_plan,
        )
        dynamic_by_type: dict[str, list[dict[str, object]]] = {}
        for candidate in dynamic_pool:
            dynamic_by_type.setdefault(str(candidate.get("question_type")), []).append(candidate)

        for index, question_type in enumerate(sequence, start=1):
            candidate = self._take_candidate_of_type(
                question_type,
                remaining,
                dynamic_by_type,
                request,
                snapshot,
                index,
            )
            candidate["question_type"] = question_type
            candidate["exercise_id"] = index
            candidate["knowledge_point"] = request.knowledge_point
            candidate["prompt"] = self._reindex_prompt(str(candidate["prompt"]), index)
            if question_type != "choice":
                candidate["options"] = []
            signature = self._exercise_signature(candidate)
            if signature in seen or signature in previous_signatures:
                candidate = self._fallback_candidate_of_type(question_type, request, snapshot, index)
                candidate["prompt"] = self._reindex_prompt(str(candidate["prompt"]), index)
                signature = self._exercise_signature(candidate)
                if signature in seen or signature in previous_signatures:
                    candidate = self._next_unique_candidate_of_type(
                        question_type=question_type,
                        request=request,
                        snapshot=snapshot,
                        index=index,
                        seen=seen,
                        previous_signatures=previous_signatures,
                    )
                    signature = self._exercise_signature(candidate)
            seen.add(signature)
            enforced.append(candidate)
        return enforced

    def _next_unique_candidate_of_type(
        self,
        *,
        question_type: str,
        request: ExerciseGenerationRequest,
        snapshot: LearnerPersonalizationSnapshot,
        index: int,
        seen: set[str],
        previous_signatures: set[str],
    ) -> dict[str, object]:
        for _ in range(request.exercise_count * 10):
            candidate = self._fallback_candidate_of_type(question_type, request, snapshot, index)
            candidate["question_type"] = question_type
            candidate["exercise_id"] = index
            candidate["knowledge_point"] = request.knowledge_point
            candidate["prompt"] = self._reindex_prompt(str(candidate["prompt"]), index)
            if question_type != "choice":
                candidate["options"] = []
            signature = self._exercise_signature(candidate)
            if signature not in seen and signature not in previous_signatures:
                return candidate

        nonce = random.SystemRandom().randrange(10000000, 99999999)
        candidate = self._fallback_candidate_of_type(question_type, request, snapshot, index)
        candidate["prompt"] = f"{self._reindex_prompt(str(candidate['prompt']), index)}（变式编号 {nonce}）"
        if question_type != "choice":
            candidate["options"] = []
        return candidate

    def _take_candidate_of_type(
        self,
        question_type: str,
        remaining: dict[str, list[dict[str, object]]],
        dynamic_by_type: dict[str, list[dict[str, object]]],
        request: ExerciseGenerationRequest,
        snapshot: LearnerPersonalizationSnapshot,
        index: int,
    ) -> dict[str, object]:
        while remaining.get(question_type):
            return remaining[question_type].pop(0)
        while dynamic_by_type.get(question_type):
            return dict(dynamic_by_type[question_type].pop(0))
        return self._fallback_candidate_of_type(question_type, request, snapshot, index)

    def _fallback_candidate_of_type(
        self,
        question_type: str,
        request: ExerciseGenerationRequest,
        snapshot: LearnerPersonalizationSnapshot,
        index: int,
    ) -> dict[str, object]:
        if self._is_calculus_topic(request.knowledge_point):
            fragment = self._calculus_knowledge_fragments()[(index - 1) % len(self._calculus_knowledge_fragments())]
            candidate = self._grounded_question_from_fragment(
                index=index,
                request=request,
                snapshot=snapshot,
                fragment=fragment,
                question_type=question_type,
                variant=index - 1,
            )
            candidate["question_type"] = question_type
            return candidate

        focus = f"{request.knowledge_point} 定向题型练习 {index}-{random.SystemRandom().randrange(100000, 999999)}"
        kwargs = {
            "index": index,
            "topic": request.knowledge_point,
            "focus": focus,
            "scenario": "课后自测",
            "action": "先分析条件再验证结果",
            "request": request,
            "weak_hint": "",
        }
        if question_type == "choice":
            return self._dynamic_choice_question(**kwargs)
        if question_type == "judge":
            return self._dynamic_judge_question(**kwargs)
        if question_type == "blank":
            return self._dynamic_blank_question(**kwargs)
        if question_type == "programming":
            return self._dynamic_programming_question(**kwargs)
        return self._dynamic_short_answer_question(**kwargs)

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
        for exercise in exercises:
            if self._exercise_signature(exercise) in previous_signatures:
                continue
            if not self._is_acceptable_generated_exercise(request, exercise):
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

        if len(completed) < request.exercise_count:
            unlimited_fallback = self._build_fallback_exercises(request, snapshot, set(), agent_plan)["exercises"]
            for fallback_exercise in unlimited_fallback:
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
            signature = self._exercise_signature(candidate)
            if signature in seen or signature in previous_signatures:
                continue
            seen.add(signature)
            completed.append(candidate)

        return self._enforce_question_type_counts(
            request=request,
            snapshot=snapshot,
            exercises=completed[: request.exercise_count],
            previous_signatures=previous_signatures,
            agent_plan=agent_plan,
        )

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
        pool = self._build_dynamic_fallback_candidates(
            request,
            snapshot,
            request.exercise_count * 24,
            agent_plan,
        )
        rng.shuffle(pool)

        selected: list[dict[str, object]] = []
        seen: set[str] = set()
        preferred_types = self._question_type_sequence_for_request(request)
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
            extra_pool = self._build_dynamic_fallback_candidates(
                request,
                snapshot,
                request.exercise_count * 40,
                agent_plan,
            )
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
        return self._enforce_question_type_counts(
            request=request,
            snapshot=snapshot,
            exercises=selected[: request.exercise_count],
            previous_signatures=previous_signatures,
            agent_plan=agent_plan,
        )

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

        grounded_candidates = self._build_grounded_knowledge_candidates(request, snapshot, target_count)
        if grounded_candidates:
            return grounded_candidates

        focus_points = self._collect_dynamic_focus_points(request, snapshot, article, agent_plan)

        scenarios = self._dynamic_scenarios(request, snapshot)
        actions = self._dynamic_actions(article, snapshot)
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
                    focus=self._normalize_focus_text(focus),
                    scenario=scenario,
                    action=action,
                    request=request,
                    weak_hint=weak_hint,
                )
            )
        return candidates

    def _build_grounded_knowledge_candidates(
        self,
        request: ExerciseGenerationRequest,
        snapshot: LearnerPersonalizationSnapshot,
        target_count: int,
    ) -> list[dict[str, object]]:
        if not self._is_calculus_topic(request.knowledge_point):
            return []

        fragments = self._calculus_knowledge_fragments()
        question_types = self._question_type_sequence_for_request(request)
        if not question_types:
            question_types = QUESTION_TYPE_SEQUENCE[:]

        candidates: list[dict[str, object]] = []
        desired_count = max(target_count, request.exercise_count * 12, len(fragments) * len(QUESTION_TYPE_SEQUENCE))
        for offset in range(desired_count):
            fragment = fragments[offset % len(fragments)]
            question_type = question_types[offset % len(question_types)]
            candidates.append(
                self._grounded_question_from_fragment(
                    index=offset + 1,
                    request=request,
                    snapshot=snapshot,
                    fragment=fragment,
                    question_type=question_type,
                    variant=offset // len(fragments),
                )
            )
        return candidates

    def _is_calculus_topic(self, knowledge_point: str) -> bool:
        normalized = self._normalize_focus_text(knowledge_point).lower()
        return any(token in normalized for token in ("高数", "高等数学", "微积分", "calculus", "极限", "导数", "积分"))

    def _calculus_knowledge_fragments(self) -> list[dict[str, object]]:
        return [
            {
                "name": "函数连续三条件",
                "core": "函数在点 x=a 连续需要 f(a) 有定义、lim_{x->a} f(x) 存在，并且二者相等。",
                "example": "分段函数在连接点 x=1 处，必须分别比较左极限、右极限和函数值。",
                "pitfall": "只算出极限存在就说连续，漏查 f(a) 是否有定义或是否等于该极限。",
                "choice_prompt": "判断分段函数在 x=1 处是否连续时，哪一组检查最完整？",
                "choice_options": [
                    "A. 只求 lim_{x->1} f(x)。",
                    "B. 分别检查 f(1) 是否有定义、左右极限是否相等、极限值是否等于 f(1)。",
                    "C. 只把 x=1 代入左右两段公式。",
                    "D. 只看函数图像是否大致连在一起。",
                ],
                "choice_answer": "B",
                "blank_prompt": "函数在点 x=a 连续的三个条件是：f(a) 有定义、lim_{x->a} f(x) 存在，并且 ______。",
                "blank_answer": "lim_{x->a} f(x) = f(a)",
                "judge_prompt": "判断正误：只要 lim_{x->a} f(x) 存在，就能说明 f(x) 在 x=a 处连续。",
                "judge_answer": "错误",
                "short_prompt": "给出判断分段函数在连接点是否连续的检查流程。",
                "short_answer": "先求左极限和右极限，确认二者相等得到极限；再检查该点函数值是否存在；最后比较极限值和函数值是否相等。",
            },
            {
                "name": "导数符号判断单调",
                "core": "一阶导数的符号可以判断函数单调性：f'(x)>0 的区间函数递增，f'(x)<0 的区间函数递减。",
                "example": "先求 f'(x)，找出驻点和不可导点，再按区间列导数符号表判断单调变化。",
                "pitfall": "只找到驻点就直接判定极值，没有检查导数符号是否在驻点两侧发生变化。",
                "choice_prompt": "用导数判断函数单调区间时，最关键的依据是什么？",
                "choice_options": [
                    "A. 函数表达式里最高次项的次数。",
                    "B. f'(x) 在各区间内的正负号。",
                    "C. 只看 f(x) 在某一个点的函数值。",
                    "D. 驻点越多，函数一定越复杂。",
                ],
                "choice_answer": "B",
                "blank_prompt": "若某区间内始终有 f'(x)>0，则 f(x) 在该区间内 ______。",
                "blank_answer": "单调递增",
                "judge_prompt": "判断正误：找到 f'(x)=0 的点后，不需要看导数符号变化也能直接确定极大值或极小值。",
                "judge_answer": "错误",
                "short_prompt": "说明如何用一阶导数符号表判断函数的单调区间。",
                "short_answer": "先求导并找驻点或不可导点，把定义域切成若干区间；再判断每个区间内 f'(x) 的符号；最后用正号对应递增、负号对应递减来写出单调区间。",
            },
            {
                "name": "定积分区间和符号",
                "core": "定积分表示区间上的累积量或带符号面积，计算前要明确上下限、被积函数符号和几何意义。",
                "example": "若 f(x) 在 [a,b] 上为负，integral_a^b f(x) dx 是负的带符号面积，几何面积要取相反数或分段取绝对值。",
                "pitfall": "把定积分值直接当几何面积，忽略被积函数在区间内可能为负。",
                "choice_prompt": "把定积分解释为几何面积时，下面哪一点必须额外检查？",
                "choice_options": [
                    "A. 被积函数在积分区间内的正负情况。",
                    "B. 积分号写得是否足够长。",
                    "C. 函数是否一定是一次函数。",
                    "D. 上下限能不能随便互换。",
                ],
                "choice_answer": "A",
                "blank_prompt": "若 f(x) 在 [a,b] 上小于 0，则 integral_a^b f(x) dx 表示的带符号面积为 ______。",
                "blank_answer": "负值",
                "judge_prompt": "判断正误：定积分 integral_a^b f(x) dx 的值总是等于曲线和 x 轴围成的几何面积。",
                "judge_answer": "错误",
                "short_prompt": "说明用定积分表示面积时为什么要先检查区间和函数符号。",
                "short_answer": "上下限决定累积方向，函数符号决定定积分是正面积还是负的带符号面积；若求几何面积，函数跨过 x 轴时应分段并取绝对值。",
            },
            {
                "name": "极限逼近方式",
                "core": "极限关注自变量的逼近过程，要区分左极限、右极限、点极限和无穷远处极限。",
                "example": "分段函数在分界点处求极限时，应分别从左侧和右侧逼近，只有两侧极限相等时点极限才存在。",
                "pitfall": "把代入某一点的函数值当成极限，或者没有检查左右逼近是否一致。",
                "choice_prompt": "分段函数在分界点 x=a 处存在极限的必要检查是什么？",
                "choice_options": [
                    "A. 只检查 f(a) 是否有定义。",
                    "B. 左极限和右极限都存在且相等。",
                    "C. 只看右侧表达式能不能代入。",
                    "D. 只要函数名相同，极限就一定存在。",
                ],
                "choice_answer": "B",
                "blank_prompt": "分段函数在 x=a 处的点极限存在，要求左极限和右极限都存在且 ______。",
                "blank_answer": "相等",
                "judge_prompt": "判断正误：函数在 x=a 处没有定义时，lim_{x->a} f(x) 一定不存在。",
                "judge_answer": "错误",
                "short_prompt": "说明求分段函数在分界点处极限的步骤。",
                "short_answer": "先按左侧表达式求左极限，再按右侧表达式求右极限；若二者相等，则点极限存在且等于该值；若不相等，则点极限不存在。",
            },
        ]

    def _grounded_question_from_fragment(
        self,
        *,
        index: int,
        request: ExerciseGenerationRequest,
        snapshot: LearnerPersonalizationSnapshot,
        fragment: dict[str, object],
        question_type: str,
        variant: int,
    ) -> dict[str, object]:
        name = str(fragment["name"])
        core = str(fragment["core"])
        pitfall = str(fragment["pitfall"])
        example = str(fragment["example"])
        prompt_style = self._grounded_prompt_style(variant)
        weak_hint = ""
        if snapshot.recent_mistakes:
            latest = self._normalize_focus_text(str(snapshot.recent_mistakes[-1].get("analysis", "")))
            if self._is_reusable_focus(request.knowledge_point, latest):
                weak_hint = f" 结合最近错因，还要避免：{latest[:80]}。"

        if question_type == "choice":
            analysis = f"这题考查{name}。{core} 常见错误是：{pitfall}{weak_hint}"
            return {
                "exercise_id": index,
                "knowledge_point": request.knowledge_point,
                "question_type": "choice",
                "difficulty": "foundation",
                "prompt": f"第 {index} 题：{prompt_style}{fragment['choice_prompt']}",
                "options": list(fragment["choice_options"]),
                "answer": str(fragment["choice_answer"]),
                "analysis": analysis,
            }

        if question_type == "blank":
            return {
                "exercise_id": index,
                "knowledge_point": request.knowledge_point,
                "question_type": "blank",
                "difficulty": "foundation",
                "prompt": f"第 {index} 题：{prompt_style}{fragment['blank_prompt']}",
                "options": [],
                "answer": str(fragment["blank_answer"]),
                "analysis": f"这题考查{name}的关键条件。{core}",
            }

        if question_type == "judge":
            return {
                "exercise_id": index,
                "knowledge_point": request.knowledge_point,
                "question_type": "judge",
                "difficulty": "intermediate",
                "prompt": f"第 {index} 题：{prompt_style}{fragment['judge_prompt']}",
                "options": [],
                "answer": str(fragment["judge_answer"]),
                "analysis": f"{pitfall} 正确理解是：{core}",
            }

        if question_type == "programming":
            return {
                "exercise_id": index,
                "knowledge_point": request.knowledge_point,
                "question_type": "short_answer",
                "difficulty": "advanced",
                "prompt": f"第 {index} 题：{prompt_style}以“{name}”为主题，设计一道具体例题，并写出判定或计算步骤。",
                "options": [],
                "answer": f"示例应包含具体函数或区间，并按知识片段展开：{example}",
                "analysis": f"高数题不强行生成代码题；这里改为综合简答，重点检查能否把知识片段落到具体函数和步骤上。{core}",
            }

        return {
            "exercise_id": index,
            "knowledge_point": request.knowledge_point,
            "question_type": "short_answer",
            "difficulty": "intermediate" if variant % 2 == 0 else "advanced",
            "prompt": f"第 {index} 题：{prompt_style}{fragment['short_prompt']}",
            "options": [],
            "answer": str(fragment["short_answer"]),
            "analysis": f"参考片段：{example} 易错提醒：{pitfall}{weak_hint}",
        }

    def _grounded_prompt_style(self, variant: int) -> str:
        styles = [
            "基础辨析：",
            "连接点专项：",
            "图像意义核对：",
            "错因复盘：",
            "同类变式：",
            "期末题口径：",
            "计算前检查：",
            "概念边界辨析：",
            "应用解释：",
            "综合小题：",
        ]
        return styles[variant % len(styles)]

    def _collect_dynamic_focus_points(
        self,
        request: ExerciseGenerationRequest,
        snapshot: LearnerPersonalizationSnapshot,
        article: Any,
        agent_plan: dict[str, object] | None,
    ) -> list[str]:
        raw_points: list[str] = []
        raw_points.extend(self._agent_focus_points(request, agent_plan))
        raw_points.extend(self._extract_mistake_focus(snapshot))

        if article is not None:
            raw_points.extend(article.concepts[:8])
            raw_points.extend(article.applications[:6])
            raw_points.extend(article.mistakes[:6])
            raw_points.extend(article.checks[:6])

        summaries = snapshot.learner_profile.get("profile_analysis_summaries", {})
        if isinstance(summaries, dict):
            raw_points.extend(str(value) for value in summaries.values() if str(value).strip())

        cleaned: list[str] = []
        seen: set[str] = set()
        for item in raw_points:
            normalized = self._normalize_focus_text(str(item))
            if len(normalized) < 4 or normalized in seen or not self._is_reusable_focus(request.knowledge_point, normalized):
                continue
            seen.add(normalized)
            cleaned.append(normalized)

        if cleaned:
            return cleaned

        base = self._normalize_focus_text(request.knowledge_point)
        return [
            f"{base} 的核心定义和成立条件",
            f"{base} 的典型题型与解题步骤",
            f"{base} 的易错点与边界检查",
            f"{base} 的应用场景与结果验证",
        ]

    def _dynamic_scenarios(
        self,
        request: ExerciseGenerationRequest,
        snapshot: LearnerPersonalizationSnapshot,
    ) -> list[str]:
        scenarios = [
            "课后自测",
            "错题复盘",
            "概念迁移",
            "结果验证",
            "综合应用",
            "同类变式",
        ]
        if request.generation_mode == "remedial":
            scenarios.insert(0, "薄弱点强化")
        if snapshot.recent_mistakes:
            scenarios.insert(1, "针对近期错因的变式训练")
        return list(dict.fromkeys(scenarios))

    def _dynamic_actions(
        self,
        article: Any,
        snapshot: LearnerPersonalizationSnapshot,
    ) -> list[str]:
        actions = [
            "先写出已知条件和目标",
            "明确公式或结论的适用前提",
            "拆分步骤并逐步验证",
            "补充边界与特殊情况检查",
            "对照错因解释为什么会错",
            "用另一种表示方式复核结果",
        ]
        weak_types = snapshot.learner_profile.get("weak_question_types", [])
        if weak_types:
            actions.insert(0, f"优先修正近期薄弱题型 {', '.join(map(str, weak_types[:2]))}")
        if article is not None and getattr(article, "checks", None):
            actions.extend(
                f"围绕“{self._normalize_focus_text(item)}”做自检"
                for item in article.checks[:3]
            )
        return list(dict.fromkeys(actions))

    def _normalize_focus_text(self, text: str) -> str:
        cleaned = re.sub(r"`+", "", text or "")
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" -:;,.，。；：")
        return cleaned.strip()

    def _is_reusable_focus(self, knowledge_point: str, focus: str) -> bool:
        normalized_focus = self._normalize_focus_text(focus)
        if not normalized_focus:
            return False

        blocked_fragments = (
            "基础理解与应用练习",
            "围绕",
            "输入、处理、输出的小任务",
            "只会套模板",
            "直接套用上一次见过的答案",
        )
        if any(fragment in normalized_focus for fragment in blocked_fragments):
            return False

        if "?" in normalized_focus or "\ufffd" in normalized_focus:
            return False

        if knowledge_point in {"高数", "高等数学", "微积分"}:
            lowered = normalized_focus.lower()
            if any(token in lowered for token in ("python", "while", "for ", "loop", "code")):
                return False

        return True

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
