"""Structured exercise generation service for the student workspace."""

from __future__ import annotations

import json
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
            generated["exercises"] = self._dedupe_exercises(list(generated["exercises"]))
            generated["exercises"] = self._enforce_question_type_counts(
                request=request,
                exercises=generated["exercises"],
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
                raise ValueError("LLM returned no valid exercises after normalization.")
            if len(normalized_exercises) < request.exercise_count:
                raise ValueError(
                    f"LLM returned only {len(normalized_exercises)} valid exercises, fewer than requested {request.exercise_count}."
                )

            normalized_exercises = self._enforce_question_type_counts(
                request=request,
                exercises=normalized_exercises,
            )
            if len(normalized_exercises) < request.exercise_count:
                raise ValueError(
                    f"Exercises did not satisfy question type requirements; only {len(normalized_exercises)} items remained."
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
                "连续生成时优先避开近期已生成题，并持续调整场景、条件和问法",
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

    def _question_type_counts(self, request: ExerciseGenerationRequest) -> dict[str, int]:
        raw = request.question_type_counts or {}
        allowed = {"choice", "blank", "judge", "short_answer", "programming"}
        counts: dict[str, int] = {}
        for key, value in raw.items():
            if key not in allowed:
                raise ValueError(f"Unsupported question type count: {key}")
            if not isinstance(value, (int, float)):
                raise ValueError(f"Invalid question type count for {key}: {value!r}")
            counts[key] = max(0, int(value))
        if not counts:
            return {}

        total = sum(counts.values())
        if total <= 0:
            return {}
        if total != request.exercise_count:
            raise ValueError(
                f"Question type counts must sum to {request.exercise_count}, got {total}."
            )
        return counts

    def _enforce_question_type_counts(
        self,
        *,
        request: ExerciseGenerationRequest,
        exercises: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        if len(exercises) < request.exercise_count:
            raise ValueError(
                f"LLM returned only {len(exercises)} valid exercises, fewer than requested {request.exercise_count}."
            )

        expected = self._question_type_counts(request)
        if not expected:
            return exercises[: request.exercise_count]

        actual: dict[str, int] = {}
        for exercise in exercises[: request.exercise_count]:
            question_type = str(exercise.get("question_type", "")).strip()
            if not question_type:
                raise ValueError("LLM returned an exercise without a question type.")
            actual[question_type] = actual.get(question_type, 0) + 1

        unexpected = sorted(key for key in actual if key not in expected)
        if unexpected:
            raise ValueError(
                f"LLM returned unexpected question types: {', '.join(unexpected)}."
            )

        for question_type, expected_count in expected.items():
            actual_count = actual.get(question_type, 0)
            if actual_count != expected_count:
                raise ValueError(
                    f"LLM returned {actual_count} {question_type} exercises, expected {expected_count}."
                )

        return exercises[: request.exercise_count]

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
