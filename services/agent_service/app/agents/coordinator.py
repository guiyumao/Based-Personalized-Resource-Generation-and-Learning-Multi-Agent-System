"""Coordinator workflow for routing and synchronously composing local agents."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, TypedDict

from sqlalchemy.orm import Session

from common.db.session import SessionLocal
from common.messaging.rabbitmq import RabbitMQPublisher
from common.schemas.agent import (
    CoordinationRequest,
    ExerciseGenerationRequest,
    LearningPathRequest,
    QARequest,
    ResourceGenerationRequest,
)
from services.agent_service.app.connectors.neo4j_connector import KnowledgeGraphRepository
from services.agent_service.app.services.exercise_generation import ExerciseGenerationService
from services.agent_service.app.services.knowledge_base import KnowledgeBaseService
from services.agent_service.app.services.learning_path import LearningPathService
from services.agent_service.app.services.personalization import PersonalizationService
from services.agent_service.app.services.qa_service import QAService
from services.agent_service.app.services.resource_generation import (
    ResourceGenerationError,
    ResourceGenerationService,
)
from services.evaluation_service.app.services.report_service import ReportService

logger = logging.getLogger(__name__)


class CoordinatorState(TypedDict, total=False):
    """State flowing through the coordinator graph."""

    user_id: int
    intent: str
    knowledge_point: str | None
    payload: dict[str, Any]
    selected_agents: list[str]
    route_reason: str
    outputs: dict[str, Any]
    status: str


class CoordinatorWorkflow:
    """Route tasks and optionally execute selected agents as one workflow."""

    def __init__(self, db: Session | None = None) -> None:
        self.db = db
        self.publisher = RabbitMQPublisher()
        self.graph = self._build_graph()

    def _build_graph(self):
        try:
            from langgraph.graph import END, START, StateGraph

            graph = StateGraph(CoordinatorState)
            graph.add_node("analyze_intent", self._analyze_intent)
            graph.add_node("dispatch_tasks", self._dispatch_tasks)
            graph.add_node("resolve_conflicts", self._resolve_conflicts)
            graph.add_edge(START, "analyze_intent")
            graph.add_edge("analyze_intent", "dispatch_tasks")
            graph.add_edge("dispatch_tasks", "resolve_conflicts")
            graph.add_edge("resolve_conflicts", END)
            return graph.compile()
        except ImportError:
            return None

    def _analyze_intent(self, state: CoordinatorState) -> CoordinatorState:
        """Select downstream agents based on request intent and context."""

        intent = state["intent"].lower()
        payload = state.get("payload", {})
        forced_agents = [str(agent) for agent in payload.get("force_agents", []) if str(agent).strip()]

        if forced_agents:
            deduped_agents = list(dict.fromkeys(forced_agents))
            return {
                **state,
                "selected_agents": deduped_agents,
                "route_reason": f"Intent '{state['intent']}' used forced agents: {', '.join(deduped_agents)}.",
            }

        selected_agents: list[str] = []

        if payload.get("only_exercises"):
            selected_agents.extend(["learner_profiling_agent", "exercise_generation_agent"])

        if payload.get("full_collaboration") or self._matches(
            intent,
            [
                "全部",
                "联合",
                "协同",
                "系统配合",
                "全系统",
                "all agents",
                "full collaboration",
                "orchestrate all",
            ],
        ):
            selected_agents.extend(
                [
                    "learner_profiling_agent",
                    "knowledge_graph_agent",
                    "knowledge_base_agent",
                    "path_planning_agent",
                    "resource_generation_agent",
                    "exercise_generation_agent",
                    "qa_agent",
                    "evaluation_feedback_agent",
                ]
            )
        if self._matches(intent, ["课件", "练习", "习题", "资源", "courseware", "exercise", "resource"]):
            selected_agents.extend(["learner_profiling_agent", "resource_generation_agent"])
        if self._matches(intent, ["路径", "计划", "学习路线", "path", "schedule", "plan"]):
            selected_agents.extend(["learner_profiling_agent", "knowledge_graph_agent", "path_planning_agent"])
        if self._matches(intent, ["评估", "测评", "报告", "反馈", "evaluation", "report", "feedback"]):
            selected_agents.append("evaluation_feedback_agent")
        if self._matches(intent, ["答疑", "解释", "问题", "debug", "question", "qa"]):
            selected_agents.extend(["knowledge_graph_agent", "qa_agent"])

        if payload.get("include_exercises"):
            selected_agents.append("exercise_generation_agent")
        if not selected_agents:
            selected_agents = ["learner_profiling_agent", "qa_agent"]

        deduped_agents = list(dict.fromkeys(selected_agents))
        return {
            **state,
            "selected_agents": deduped_agents,
            "route_reason": f"Intent '{state['intent']}' matched {', '.join(deduped_agents)}.",
        }

    def _dispatch_tasks(self, state: CoordinatorState) -> CoordinatorState:
        """Publish selected tasks for asynchronous workers while preserving local output metadata."""

        outputs: dict[str, Any] = {}
        for agent_name in state["selected_agents"]:
            message = {
                "user_id": state["user_id"],
                "agent": agent_name,
                "knowledge_point": state.get("knowledge_point"),
                "payload": state.get("payload", {}),
            }
            self.publisher.publish(queue_name=agent_name, message=message)
            outputs[agent_name] = {
                "queue": agent_name,
                "message": "task dispatched",
            }

        return {**state, "outputs": outputs, "status": "partial"}

    def _resolve_conflicts(self, state: CoordinatorState) -> CoordinatorState:
        """Resolve simple agent ordering conflicts."""

        selected = state["selected_agents"]
        status = "success" if selected else "failed"
        route_reason = state["route_reason"]
        if "resource_generation_agent" in selected and "evaluation_feedback_agent" in selected:
            route_reason += " Coordinator scheduled evaluation after generation to avoid race conditions."
        return {**state, "status": status, "route_reason": route_reason}

    def run(self, payload: CoordinationRequest) -> dict[str, Any]:
        """Invoke the workflow and optionally execute selected agents synchronously."""

        state: CoordinatorState = {
            "user_id": payload.user_id,
            "intent": payload.intent,
            "knowledge_point": payload.knowledge_point,
            "payload": payload.payload,
        }
        if self.graph is not None:
            result = self.graph.invoke(state)
        else:
            result = self._resolve_conflicts(self._dispatch_tasks(self._analyze_intent(state)))

        response = {
            "status": result["status"],
            "selected_agents": result["selected_agents"],
            "route_reason": result["route_reason"],
            "outputs": result["outputs"],
        }
        if payload.payload.get("execute") is True:
            response = self._execute_agents(payload, response)
        return response

    def _execute_agents(self, payload: CoordinationRequest, result: dict[str, Any]) -> dict[str, Any]:
        """Run selected services in dependency order and return their outputs."""

        selected = set(result.get("selected_agents", []))
        knowledge_point = self._resolve_knowledge_point(payload)
        knowledge_required_agents = selected - {"qa_agent", "evaluation_feedback_agent", "knowledge_base_agent"}
        if knowledge_required_agents and not knowledge_point:
            return {
                **result,
                "status": "failed",
                "route_reason": f"{result['route_reason']} Missing knowledge point for synchronous execution.",
            }

        context = dict(payload.payload or {})
        outputs = dict(result.get("outputs", {}))
        session = self.db or SessionLocal()
        owns_session = self.db is None
        plan_parts: list[str] = []
        resource_result: dict[str, Any] | None = None
        learner_profile = dict(context.get("learner_profile") or {})
        teacher_scope = context.get("teacher_scope")
        if isinstance(teacher_scope, dict):
            learner_profile["teacher_scope"] = teacher_scope

        try:
            if "learner_profiling_agent" in selected:
                snapshot = PersonalizationService(session).build_snapshot(
                    user_id=payload.user_id,
                    knowledge_point=knowledge_point,
                    fallback_profile=learner_profile,
                )
                learner_profile = snapshot.learner_profile
                outputs["learner_profiling_agent"] = {
                    "status": "completed",
                    "mastery_score": snapshot.mastery_score,
                    "correct_rate": snapshot.correct_rate,
                    "answered_count": snapshot.answered_count,
                    "weak_question_types": learner_profile.get("weak_question_types", []),
                    "recent_mistakes": snapshot.recent_mistakes,
                    "basis": self._build_profile_basis(snapshot),
                    "agent_handoff": learner_profile.get("agent_handoff", {}),
                    "profile_dimensions": learner_profile.get("profile_dimensions", {}),
                    "profile_analysis_summaries": learner_profile.get("profile_analysis_summaries", {}),
                    "profile_analysis": learner_profile.get("profile_analysis", {}),
                    "preferred_resource_modes": learner_profile.get("preferred_resource_modes", []),
                    "learner_profile": learner_profile,
                }
                plan_parts.append("画像")

            if "knowledge_graph_agent" in selected:
                outputs["knowledge_graph_agent"] = self._run_graph_agent(knowledge_point, context)
                plan_parts.append("知识图谱")

            if "knowledge_base_agent" in selected:
                outputs["knowledge_base_agent"] = self._run_knowledge_base_agent(context)
                plan_parts.append("knowledge-base")

            if "path_planning_agent" in selected:
                path_request = LearningPathRequest(
                    user_id=payload.user_id,
                    subject=str(context.get("subject") or knowledge_point or ""),
                    knowledge_point=knowledge_point,
                    daily_minutes=int(context.get("daily_minutes") or 45),
                    learner_profile=learner_profile,
                )
                outputs["path_planning_agent"] = {
                    "status": "completed",
                    "learning_path": LearningPathService(session).generate_path(path_request),
                    "profile_handoff": self._agent_handoff(learner_profile, "path_planning_agent"),
                }
                plan_parts.append("学习路径")

            if "resource_generation_agent" in selected:
                outputs["resource_generation_agent"], resource_result = self._run_resource_agent(
                    payload=payload,
                    knowledge_point=knowledge_point,
                    learner_profile=learner_profile,
                    context=context,
                )
                if knowledge_point and resource_result:
                    try:
                        KnowledgeGraphRepository().sync_courseware_to_graph(knowledge_point)
                    except Exception as exc:
                        logger.warning("Graph sync after resource generation failed: %s", exc)
                plan_parts.append("课件资源")

            if "exercise_generation_agent" in selected or context.get("include_exercises"):
                outputs["exercise_generation_agent"] = self._run_exercise_agent(
                    payload=payload,
                    knowledge_point=knowledge_point,
                    learner_profile=learner_profile,
                    context=context,
                    resource_result=resource_result,
                )
                plan_parts.append("配套练习")

            if "qa_agent" in selected:
                outputs["qa_agent"] = self._run_qa_agent(
                    payload=payload,
                    knowledge_point=knowledge_point,
                    learner_profile=learner_profile,
                    context=context,
                    session=session,
                )
                plan_parts.append("qa")

            if "evaluation_feedback_agent" in selected:
                outputs["evaluation_feedback_agent"] = self._run_evaluation_agent(
                    payload=payload,
                    context=context,
                    learner_profile=learner_profile,
                    all_outputs=outputs,
                    knowledge_point=knowledge_point,
                )
                plan_parts.append("evaluation")

            outputs["coordinator_summary"] = self._build_collaboration_summary(
                selected_agents=result.get("selected_agents", []),
                outputs=outputs,
                learner_profile=learner_profile,
                knowledge_point=knowledge_point,
            )

            failed = [name for name, output in outputs.items() if output.get("status") == "failed"]
            status = "partial" if failed else "success"
            return {
                **result,
                "status": status,
                "route_reason": (
                    f"{result['route_reason']} Synchronous orchestration executed: "
                    f"{'、'.join(plan_parts) or 'no local agent'}."
                ),
                "outputs": outputs,
            }
        finally:
            if owns_session:
                session.close()

    def _run_graph_agent(self, knowledge_point: str, context: dict[str, Any]) -> dict[str, Any]:
        repository = KnowledgeGraphRepository()
        try:
            # 1. Sync any existing courseware content into graph relations
            try:
                repository.sync_courseware_to_graph(knowledge_point)
            except Exception as exc:
                logger.warning("sync_courseware_to_graph failed: %s", exc)

            # 2. Query the graph
            max_depth = int(context.get("max_depth") or 3)
            return {
                "status": "completed",
                "dependencies": repository.find_dependency_path(knowledge_point, max_depth),
                "related_resources": (
                    repository.find_related_resources(knowledge_point)
                    if hasattr(repository, "find_related_resources")
                    else []
                ),
                "visualization": repository.get_visualization_graph(knowledge_point, min(max_depth, 2)),
            }
        finally:
            repository.close()

    def _run_knowledge_base_agent(self, context: dict[str, Any]) -> dict[str, Any]:
        service = KnowledgeBaseService()
        operation = str(context.get("operation") or "list")
        subject = context.get("subject")
        query = str(context.get("query") or "")
        top_k = int(context.get("top_k") or 6)

        if operation == "search":
            articles = service.list_articles()[:top_k] if not query.strip() else service.search_by_keywords(query, top_k=top_k)
            return {
                "status": "completed",
                "operation": operation,
                "query": query,
                "items": [service.article_to_dict(article) for article in articles],
            }

        if operation == "article":
            article_id = str(context.get("article_id") or "")
            for article in service.list_articles():
                payload = service.article_to_dict(article)
                if payload["id"] == article_id:
                    return {"status": "completed", "operation": operation, "article": payload}
            return {"status": "failed", "error": "Knowledge article not found"}

        articles = service.list_articles(subject=str(subject)) if subject else service.list_articles()
        return {
            "status": "completed",
            "operation": "list",
            "subjects": service.list_subjects(),
            "items": [service.article_to_dict(article) for article in articles],
        }

    def _run_resource_agent(
        self,
        *,
        payload: CoordinationRequest,
        knowledge_point: str,
        learner_profile: dict[str, Any],
        context: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        request = ResourceGenerationRequest(
            user_id=payload.user_id,
            knowledge_point=knowledge_point,
            resource_style=str(context.get("resource_style") or "interactive"),  # type: ignore[arg-type]
            resource_type=str(context.get("resource_type") or "courseware"),  # type: ignore[arg-type]
            learner_profile=learner_profile,
            request_text=str(context.get("request_text") or f"围绕 {knowledge_point} 生成可独立阅读的正式课件"),
        )
        try:
            resource = ResourceGenerationService().generate_courseware_with_plan(request)
        except ResourceGenerationError as exc:
            return {"status": "failed", "error": str(exc)}, None
        return {
            "status": "completed",
            "resource": resource,
            "profile_handoff": self._agent_handoff(learner_profile, "resource_generation_agent"),
        }, resource

    def _run_exercise_agent(
        self,
        *,
        payload: CoordinationRequest,
        knowledge_point: str,
        learner_profile: dict[str, Any],
        context: dict[str, Any],
        resource_result: dict[str, Any] | None,
    ) -> dict[str, Any]:
        courseware_content = str((resource_result or {}).get("content") or context.get("courseware_content") or "")
        request = ExerciseGenerationRequest(
            user_id=payload.user_id,
            knowledge_point=knowledge_point,
            resource_style=str(context.get("resource_style") or "interactive"),  # type: ignore[arg-type]
            learner_profile=learner_profile,
            exercise_count=int(context.get("exercise_count") or 5),
            question_type_counts=dict(context.get("question_type_counts") or {}),
            generation_mode=str(context.get("generation_mode") or "self_test"),  # type: ignore[arg-type]
            courseware_content=courseware_content,
        )
        return {
            "status": "completed",
            "exercise_set": ExerciseGenerationService().generate_exercises(request),
            "profile_handoff": self._agent_handoff(learner_profile, "exercise_generation_agent"),
        }

    def _run_qa_agent(
        self,
        *,
        payload: CoordinationRequest,
        knowledge_point: str,
        learner_profile: dict[str, Any],
        context: dict[str, Any],
        session: Session,
    ) -> dict[str, Any]:
        current_points = context.get("current_knowledge_points")
        if not isinstance(current_points, list):
            current_points = [knowledge_point] if knowledge_point else []

        session_id = context.get("qa_session_id", context.get("session_id"))
        request = QARequest(
            student_id=str(context.get("student_id") or payload.user_id),
            subject=str(context.get("subject") or ""),
            grade=str(context.get("grade") or context.get("learning_stage") or "university"),
            question=str(context.get("question") or context.get("request_text") or payload.intent).strip(),
            session_id=int(session_id) if session_id is not None else None,
            session_title=str(context.get("session_title") or ""),
            student_answer=str(context.get("student_answer") or ""),
            wrong_answer=str(context.get("wrong_answer") or ""),
            current_knowledge_points=[str(item) for item in current_points if str(item).strip()],
            learning_route=dict(context.get("learning_route") or {}),
            error_book=dict(context.get("error_book") or {}),
            learning_history={
                **dict(context.get("learning_history") or {}),
                "learner_profile": learner_profile,
            },
        )
        try:
            return {
                "status": "completed",
                "qa": QAService(session).analyze_question(request),
                "profile_handoff": self._agent_handoff(learner_profile, "qa_agent"),
            }
        except Exception as exc:
            return {"status": "failed", "error": str(exc)}

    def _run_evaluation_agent(
        self,
        *,
        payload: CoordinationRequest,
        context: dict[str, Any],
        learner_profile: dict[str, Any],
        all_outputs: dict[str, Any],
        knowledge_point: str,
    ) -> dict[str, Any]:
        """Run evaluation data collection + LLM cross-agent feedback synthesis.

        Phase 1: Gather raw evaluation data from ReportService (data-only).
        Phase 2: Invoke FeedbackSynthesisService to produce a unified,
        LLM-generated feedback that cross-references all upstream agent outputs.
        On LLM failure, gracefully degrade to data-driven feedback.
        """
        from services.agent_service.app.services.feedback_synthesis import (
            FeedbackSynthesisService,
        )

        service = ReportService()
        synthesis_service = FeedbackSynthesisService()

        evaluation_data: dict[str, Any] = {
            "suggestions": self._to_plain_data(
                self._run_async(service.generate_learning_suggestions(payload.user_id))
            ),
            "profile_snapshot": self._to_plain_data(
                self._run_async(service.generate_profile_snapshot(payload.user_id))
            ),
            "mistake_statistics": self._to_plain_data(
                self._run_async(service.get_mistake_statistics(payload.user_id))
            ),
        }
        if context.get("include_stage_report"):
            evaluation_data["stage_report"] = self._to_plain_data(
                self._run_async(service.generate_stage_report_detail(payload.user_id))
            )
        if context.get("include_comprehensive_report"):
            evaluation_data["comprehensive_report"] = self._to_plain_data(
                self._run_async(service.generate_comprehensive_report_detail(payload.user_id))
            )

        try:
            synthesis = synthesis_service.synthesize_from_agents(
                knowledge_point=knowledge_point,
                learner_profile=learner_profile,
                all_agent_outputs=all_outputs,
                evaluation_data=evaluation_data,
            )
        except Exception as exc:
            logger.exception("Feedback synthesis failed, falling back to data-driven feedback")
            synthesis = synthesis_service.build_fallback(
                knowledge_point=knowledge_point,
                evaluation_data=evaluation_data,
                error_message=str(exc),
            )

        return {
            "status": "completed",
            "evaluation": {
                **evaluation_data,
                "synthesis": synthesis,
            },
        }

    def _run_async(self, coroutine: Any) -> Any:
        """Run an async evaluation-service method from the sync coordinator path."""

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coroutine)

        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(asyncio.run, coroutine).result()

    def _to_plain_data(self, value: Any) -> Any:
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")
        if isinstance(value, dict):
            return {key: self._to_plain_data(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._to_plain_data(item) for item in value]
        return value

    def _resolve_knowledge_point(self, payload: CoordinationRequest) -> str:
        context = payload.payload or {}
        return str(payload.knowledge_point or context.get("knowledge_point") or "").strip()

    def _build_profile_basis(self, snapshot: Any) -> list[str]:
        basis: list[str] = []
        if snapshot.answered_count:
            basis.append(f"画像来自 {snapshot.answered_count} 次真实作答，近期正确率约 {snapshot.correct_rate}%。")
        else:
            basis.append("当前没有该知识点的真实作答记录，先使用基础画像生成学习方案。")

        weak_types = snapshot.learner_profile.get("weak_question_types", [])
        if weak_types:
            basis.append(f"近期薄弱题型：{', '.join(map(str, weak_types[:3]))}。")

        if snapshot.recent_mistakes:
            latest = snapshot.recent_mistakes[-1]
            basis.append(f"最近错题提示：{latest.get('question_type', 'unknown')} / {latest.get('difficulty', 'unknown')}。")
        return basis

    def _matches(self, intent: str, tokens: list[str]) -> bool:
        return any(token.lower() in intent for token in tokens)

    def _agent_handoff(self, learner_profile: dict[str, Any], agent_name: str) -> list[str]:
        handoff = learner_profile.get("agent_handoff", {})
        if isinstance(handoff, dict):
            values = handoff.get(agent_name, [])
            if isinstance(values, list):
                return [str(item) for item in values if str(item).strip()]
        return []

    def _build_collaboration_summary(
        self,
        *,
        selected_agents: list[str],
        outputs: dict[str, Any],
        learner_profile: dict[str, Any],
        knowledge_point: str,
    ) -> dict[str, Any]:
        """Summarize how agents cooperated and what context was shared."""

        completed_agents = [
            name
            for name in selected_agents
            if isinstance(outputs.get(name), dict) and outputs[name].get("status") == "completed"
        ]
        failed_agents = [
            name
            for name in selected_agents
            if isinstance(outputs.get(name), dict) and outputs[name].get("status") == "failed"
        ]
        handoff = learner_profile.get("agent_handoff", {})
        return {
            "status": "completed" if not failed_agents else "partial",
            "knowledge_point": knowledge_point,
            "completed_agents": completed_agents,
            "failed_agents": failed_agents,
            "shared_context": {
                "profile_dimensions": learner_profile.get("profile_dimensions", {}),
                "profile_analysis_summaries": learner_profile.get("profile_analysis_summaries", {}),
                "preferred_resource_modes": learner_profile.get("preferred_resource_modes", []),
                "known_background": learner_profile.get("known_background", ""),
                "interest_direction": learner_profile.get("interest_direction", ""),
                "goal_orientation": learner_profile.get("goal_orientation", ""),
                "weakness_hint": learner_profile.get("weakness_hint", ""),
                "learning_speed": learner_profile.get("learning_speed", ""),
            },
            "handoff_map": handoff if isinstance(handoff, dict) else {},
            "execution_order": [
                name
                for name in [
                    "learner_profiling_agent",
                    "knowledge_graph_agent",
                    "knowledge_base_agent",
                    "path_planning_agent",
                    "resource_generation_agent",
                    "exercise_generation_agent",
                    "qa_agent",
                    "evaluation_feedback_agent",
                ]
                if name in selected_agents
            ],
        }
