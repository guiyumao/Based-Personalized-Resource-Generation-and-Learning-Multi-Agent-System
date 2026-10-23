"""Coordinator workflow for routing and synchronously composing local agents."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import Callable
from contextlib import nullcontext
from typing import Any, TypedDict

from sqlalchemy.orm import Session

from common.ai_errors import AIServiceError
from common.config import get_settings
from common.db.session import SessionLocal
from common.messaging.rabbitmq import RabbitMQPublisher
from common.models.learning import Exercise, KnowledgePoint, Resource, SystemSubject
from common.performance import get_current_trace
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
from services.agent_service.app.services.personalization import (
    LearnerPersonalizationSnapshot,
    PersonalizationService,
)
from services.agent_service.app.services.qa_service import QAService
from services.agent_service.app.services.resource_generation import (
    ResourceGenerationError,
    ResourceGenerationService,
)
from services.evaluation_service.app.services.report_service import ReportService

logger = logging.getLogger(__name__)

SUPPORTED_AGENTS = (
    "learner_profiling_agent",
    "knowledge_graph_agent",
    "knowledge_base_agent",
    "path_planning_agent",
    "resource_generation_agent",
    "exercise_generation_agent",
    "qa_agent",
    "evaluation_feedback_agent",
)
AGENT_VERSIONS = {name: "coordinator-local-v1" for name in SUPPORTED_AGENTS}


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
    task_id: str
    session_id: str
    intent_params: dict[str, Any]
    learner_profile: dict[str, Any]
    learning_evidence: list[dict[str, Any]]
    task_plan: list[dict[str, Any]]
    agent_handoff: dict[str, Any]
    intermediate_results: dict[str, Any]
    citations: list[dict[str, Any]]
    validation_results: list[dict[str, Any]]
    progress: float
    current_step: str
    error: str | None
    agent_calls: list[dict[str, Any]]


class CoordinatorWorkflow:
    """Route tasks and optionally execute selected agents as one workflow."""

    def __init__(self, db: Session | None = None) -> None:
        self.db = db
        self.cancellation_check: Callable[[], bool] | None = None
        self.stage_callback: Callable[[str], None] | None = None
        self.assistant_operation_root = ""
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
            invalid_agents = [name for name in deduped_agents if name not in SUPPORTED_AGENTS]
            if invalid_agents:
                return {
                    **state,
                    "selected_agents": [],
                    "outputs": {
                        "coordinator": {
                            "status": "failed",
                            "error_code": "AGENT_NOT_ALLOWED",
                            "error": "Requested agent is not exposed by this service.",
                            "invalid_agents": invalid_agents,
                        }
                    },
                    "status": "failed",
                    "error": "AGENT_NOT_ALLOWED",
                    "route_reason": (
                        f"Intent '{state['intent']}' requested unsupported agents: "
                        f"{', '.join(invalid_agents)}."
                    ),
                }
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

        if state.get("status") == "failed" or state.get("error"):
            # Validation failures from intent analysis must not reach a queue.
            return {
                **state,
                "outputs": state.get("outputs", {}),
                "intermediate_results": state.get("outputs", {}),
                "agent_calls": [],
                "current_step": "任务校验失败，未分发",
            }

        outputs: dict[str, Any] = {}
        agent_calls: list[dict[str, Any]] = []
        synchronous = state.get("payload", {}).get("execute") is True
        for agent_name in state["selected_agents"]:
            call = {
                "agent": agent_name,
                "version": AGENT_VERSIONS.get(agent_name, "unknown"),
                "input_summary": self._safe_input_summary(state.get("payload", {})),
                "output_status": "queued" if not synchronous else "pending",
                "elapsed_ms": 0,
                "retries": 0,
                "error_code": None,
            }
            agent_calls.append(call)
            if synchronous:
                outputs[agent_name] = {"message": "synchronous execution pending"}
            else:
                message = {
                    "user_id": state["user_id"],
                    "agent": agent_name,
                    "knowledge_point": state.get("knowledge_point"),
                    "payload": state.get("payload", {}),
                }
                self.publisher.publish(queue_name=agent_name, message=message)
                outputs[agent_name] = {"queue": agent_name, "message": "task dispatched"}

        return {
            **state,
            "outputs": outputs,
            "intermediate_results": outputs,
            "agent_calls": agent_calls,
            "status": "partial",
            "progress": 0.15,
            "current_step": "任务已分发",
        }

    def _resolve_conflicts(self, state: CoordinatorState) -> CoordinatorState:
        """Resolve simple agent ordering conflicts."""

        selected = state["selected_agents"]
        status = "success" if selected else "failed"
        route_reason = state["route_reason"]
        if "resource_generation_agent" in selected and "evaluation_feedback_agent" in selected:
            route_reason += " Coordinator scheduled evaluation after generation to avoid race conditions."
        return {
            **state,
            "status": state.get("status") if state.get("error") else status,
            "route_reason": route_reason,
            "task_plan": [
                {
                    "agent": agent,
                    "status": "pending",
                    "depends_on": self._agent_dependencies(agent, selected),
                }
                for agent in selected
            ],
        }

    def run(self, payload: CoordinationRequest) -> dict[str, Any]:
        """Invoke the workflow and optionally execute selected agents synchronously."""

        state: CoordinatorState = {
            "user_id": payload.user_id,
            "intent": payload.intent,
            "knowledge_point": payload.knowledge_point,
            "payload": payload.payload,
            "task_id": str(payload.payload.get("task_id") or uuid.uuid4()),
            "session_id": str(payload.payload.get("session_id") or ""),
            "intent_params": dict(payload.payload.get("intent_params") or {}),
            "learner_profile": dict(payload.payload.get("learner_profile") or {}),
            "learning_evidence": [],
            "task_plan": [],
            "agent_handoff": {},
            "intermediate_results": {},
            "citations": [],
            "validation_results": [],
            "progress": 0.0,
            "current_step": "准备任务",
            "error": None,
            "agent_calls": [],
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
            "task_id": result.get("task_id"),
            "session_id": result.get("session_id", ""),
            "task_state": self._build_task_state(result),
            "agent_calls": result.get("agent_calls", []),
        }
        if payload.payload.get("execute") is True:
            response = self._execute_agents(payload, response)
        return response

    def _execute_agents(self, payload: CoordinationRequest, result: dict[str, Any]) -> dict[str, Any]:
        """Run selected services in dependency order and return their outputs."""

        selected = set(result.get("selected_agents", []))
        if not selected:
            return result
        knowledge_point = self._resolve_knowledge_point(payload)
        knowledge_required_agents = selected - {"qa_agent", "evaluation_feedback_agent", "knowledge_base_agent"}
        if knowledge_required_agents and not knowledge_point:
            return {
                **result,
                "status": "failed",
                "route_reason": f"{result['route_reason']} Missing knowledge point for synchronous execution.",
            }

        context = dict(payload.payload or {})
        # Only the durable assistant executor can establish this identity.
        context["assistant_operation_root"] = self.assistant_operation_root
        outputs = dict(result.get("outputs", {}))
        agent_calls: list[dict[str, Any]] = []
        session = self.db or SessionLocal()
        owns_session = self.db is None
        if "path_planning_agent" in selected:
            from services.agent_service.app.services.plan_knowledge import assess_plan_knowledge
            if not context.get("subject"):
                points = session.query(KnowledgePoint).filter(KnowledgePoint.name == knowledge_point,
                    KnowledgePoint.subject_id.is_not(None)).limit(2).all()
                if len(points) == 1:
                    catalog = session.get(SystemSubject, points[0].subject_id)
                    if catalog:
                        context["subject"] = catalog.name
            # Constructive coverage check: record the gap and continue in personal-draft
            # mode instead of terminating the learner's request with a 409.
            coverage = assess_plan_knowledge(session, payload.user_id,
                                             str(context.get("subject") or knowledge_point), knowledge_point)
            context["knowledge_scope"] = coverage["mode"]
            context["knowledge_gap"] = {"reason": coverage.get("reason"), "gap_id": coverage.get("gap_id")}
        plan_parts: list[str] = []
        resource_result: dict[str, Any] | None = None
        snapshot: Any | None = None
        learner_profile = dict(context.get("learner_profile") or {})
        history_disabled = context.get("use_learning_context") is False
        if history_disabled:
            learner_profile = {"history_disabled": True}
            snapshot = LearnerPersonalizationSnapshot(
                learner_profile=learner_profile, mastery_score=0, recent_mistakes=[], answered_count=0, correct_rate=0,
            )
        teacher_scope = context.get("teacher_scope")
        if isinstance(teacher_scope, dict):
            learner_profile["teacher_scope"] = teacher_scope

        cancelled = False

        def can_run() -> bool:
            # Only trusted in-process callers can supply this callback. Never
            # accept a task id or cancellation callback from request payloads.
            nonlocal cancelled
            check = self.cancellation_check
            if check is not None and check():
                cancelled = True
            return not cancelled

        try:
            if isinstance(session, Session) and knowledge_point and not context.get("subject") and selected.intersection({"resource_generation_agent", "exercise_generation_agent"}):
                # Only a real ORM session can resolve the catalog; lightweight
                # callers that pass a stub skip this enrichment instead of failing.
                matches = session.query(KnowledgePoint).filter(KnowledgePoint.name == knowledge_point,
                    KnowledgePoint.subject_id.is_not(None)).limit(2).all()
                if len(matches) == 1:
                    catalog = session.get(SystemSubject, matches[0].subject_id)
                    if catalog:
                        context["subject"] = catalog.name
                        context["knowledge_point_id"] = str(matches[0].id)
            if (context.get("dynamic_knowledge") is True or selected.intersection({"resource_generation_agent", "exercise_generation_agent"})) and knowledge_point and context.get("subject") and not context.get("teaching_scope_id") and can_run():
                from services.agent_service.app.services.knowledge_acquisition import (
                    acquire_context,
                )
                knowledge_context = acquire_context(session, actor_user_id=payload.user_id,
                                                     subject=str(context["subject"]), knowledge_point=knowledge_point,
                                                     allow_web=context.get("allow_web_knowledge", True) is True,
                                                     enrich_sources=context.get("enrich_knowledge") is True)
                context["retrieval_context"] = knowledge_context["retrieval_context"]
                context["retrieval_context"]["knowledge_evidence"] = {key: value for key, value in knowledge_context.items() if key != "retrieval_context"}
                outputs["knowledge_acquisition"] = knowledge_context
            if "learner_profiling_agent" in selected and history_disabled and can_run():
                outputs["learner_profiling_agent"] = {"status": "skipped", "reason": "history_disabled"}
                self._record_agent_call(agent_calls, "learner_profiling_agent", outputs["learner_profiling_agent"], time.perf_counter(), context)
            if "learner_profiling_agent" in selected and not history_disabled and can_run():
                snapshot_result = self._run_isolated(
                    "learner_profiling_agent",
                    lambda: self._build_profile_snapshot(
                        session=session,
                        user_id=payload.user_id,
                        knowledge_point=knowledge_point,
                        fallback_profile=learner_profile,
                        subject=str(context.get("subject") or ""), point_id=context.get("knowledge_point_id"),
                    ),
                    context,
                    agent_calls,
                )
                if isinstance(snapshot_result, dict) and snapshot_result.get("status") == "failed":
                    outputs["learner_profiling_agent"] = snapshot_result
                    snapshot = None
                else:
                    snapshot = snapshot_result
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

            if "knowledge_graph_agent" in selected and can_run():
                outputs["knowledge_graph_agent"] = self._run_isolated(
                    "knowledge_graph_agent",
                    lambda: self._run_graph_agent_with_trace(knowledge_point, context),
                    context,
                    agent_calls,
                )
                plan_parts.append("知识图谱")

            if "knowledge_base_agent" in selected and can_run():
                outputs["knowledge_base_agent"] = self._run_isolated(
                    "knowledge_base_agent",
                    lambda: self._run_knowledge_base_agent(context),
                    context,
                    agent_calls,
                )
                plan_parts.append("knowledge-base")

            if "path_planning_agent" in selected and can_run():
                if self.stage_callback is not None:
                    self.stage_callback("path_planning_agent")
                started = time.perf_counter()
                path_request = LearningPathRequest(
                    user_id=payload.user_id,
                    subject=str(context.get("subject") or knowledge_point or ""),
                    knowledge_point=knowledge_point,
                    daily_minutes=int(context.get("daily_minutes") or 45),
                    learner_profile=learner_profile,
                    retrieval_context=dict(context.get("retrieval_context") or {}),
                )
                profile_handoff = self._agent_handoff(learner_profile, "path_planning_agent")
                try:
                    outputs["path_planning_agent"] = {
                        "status": "completed",
                        "learning_path": LearningPathService(session).generate_path(
                            path_request, persist=False,
                        ) if context.get("persist_path") is False else LearningPathService(session).generate_path(path_request),
                        "profile_handoff": profile_handoff,
                    }
                except AIServiceError as exc:
                    raw_error = getattr(exc, "raw_message", str(exc))
                    logger.warning(
                        "path_planning_agent_ai_failure code=%s raw_error=%s",
                        exc.code,
                        raw_error[:500],
                    )
                    outputs["path_planning_agent"] = {
                        "status": "failed",
                        "error_code": exc.code,
                        "error": exc.user_message,
                        "user_message": exc.user_message,
                        "profile_handoff": profile_handoff,
                    }
                except Exception as exc:
                    logger.warning("Path planning agent failed: %s", exc)
                    outputs["path_planning_agent"] = {
                        "status": "failed",
                        "error": str(exc),
                        "profile_handoff": profile_handoff,
                    }
                self._record_agent_call(agent_calls, "path_planning_agent", outputs["path_planning_agent"], started, context)
                plan_parts.append("学习路径")

            if "resource_generation_agent" in selected and can_run():
                if self.stage_callback is not None:
                    self.stage_callback("resource_generation_agent")
                started = time.perf_counter()
                outputs["resource_generation_agent"], resource_result = self._run_resource_agent(
                    payload=payload,
                    knowledge_point=knowledge_point,
                    learner_profile=learner_profile,
                    context=context,
                    snapshot=snapshot,
                )
                if knowledge_point and resource_result and can_run():
                    try:
                        KnowledgeGraphRepository().sync_courseware_to_graph(knowledge_point)
                    except Exception as exc:
                        logger.warning("Graph sync after resource generation failed: %s", exc)
                self._record_agent_call(agent_calls, "resource_generation_agent", outputs["resource_generation_agent"], started, context)
                plan_parts.append("课件资源")

            if ("exercise_generation_agent" in selected or context.get("include_exercises")) and can_run():
                outputs["exercise_generation_agent"] = self._run_isolated(
                    "exercise_generation_agent",
                    lambda: self._run_exercise_agent(
                        payload=payload,
                        knowledge_point=knowledge_point,
                        learner_profile=learner_profile,
                        context=context,
                        resource_result=resource_result,
                        snapshot=snapshot,
                    ),
                    context,
                    agent_calls,
                )
                plan_parts.append("配套练习")

            if "qa_agent" in selected and can_run():
                started = time.perf_counter()
                outputs["qa_agent"] = self._run_qa_agent(
                    payload=payload,
                    knowledge_point=knowledge_point,
                    learner_profile=learner_profile,
                    context=context,
                    session=session,
                    snapshot=snapshot,
                )
                self._record_agent_call(agent_calls, "qa_agent", outputs["qa_agent"], started, context)
                plan_parts.append("qa")

            if "evaluation_feedback_agent" in selected and can_run():
                outputs["evaluation_feedback_agent"] = self._run_isolated(
                    "evaluation_feedback_agent",
                    lambda: self._run_evaluation_agent(
                        payload=payload,
                        context=context,
                        learner_profile=learner_profile,
                        all_outputs=outputs,
                        knowledge_point=knowledge_point,
                    ),
                    context,
                    agent_calls,
                )
                plan_parts.append("evaluation")

            outputs["coordinator_summary"] = self._build_collaboration_summary(
                selected_agents=result.get("selected_agents", []),
                outputs=outputs,
                learner_profile=learner_profile,
                knowledge_point=knowledge_point,
            )

            failed = [name for name, output in outputs.items() if output.get("status") == "failed"]
            can_run()  # Also observe a request arriving during the last agent.
            status = "cancelled" if cancelled else "partial" if failed else "success"
            citations = self._collect_citations(outputs)
            validation_results = self._collect_validation_results(outputs)
            return {
                **result,
                "status": status,
                "route_reason": (
                    f"{result['route_reason']} Synchronous orchestration executed: "
                    f"{'、'.join(plan_parts) or 'no local agent'}."
                ),
                "outputs": outputs,
                "agent_calls": agent_calls,
                "citations": citations,
                "validation_results": validation_results,
                "task_state": {
                    **result.get("task_state", {}),
                    "status": status,
                    "progress": 1.0,
                    "current_step": "任务完成" if status == "success" else "任务部分完成",
                    "error": None,
                    "citations": citations,
                    "validation_results": validation_results,
                    "intermediate_results": {
                        name: output.get("status")
                        for name, output in outputs.items()
                        if isinstance(output, dict)
                    },
                },
            }

        finally:
            if owns_session:
                session.close()

    def _run_graph_agent(self, knowledge_point: str, context: dict[str, Any]) -> dict[str, Any]:
        # The repository is constructed *inside* the try block: building it can itself
        # fail (unreachable Neo4j, missing driver, bad configuration). Letting that
        # escape would abort the whole coordinated run instead of failing just this
        # stage, which is exactly what _run_isolated() guarantees must not happen.
        repository: KnowledgeGraphRepository | None = None
        try:
            repository = KnowledgeGraphRepository()
            # 1. Sync any existing courseware content into graph relations
            try:
                repository.sync_courseware_to_graph(knowledge_point)
            except Exception as exc:
                logger.warning("sync_courseware_to_graph failed: %s", exc)

            # 2. Query the graph
            max_depth = int(context.get("max_depth") or 3)
            warnings: list[str] = []
            dependencies: list[dict[str, Any]] = []
            related_resources: list[dict[str, Any]] = []
            visualization: dict[str, Any] = {"nodes": [], "edges": []}

            try:
                dependencies = repository.find_dependency_path(knowledge_point, max_depth)
            except Exception as exc:
                warnings.append(f"依赖路径暂缺：{exc}")
                logger.warning("Knowledge graph dependency lookup failed: %s", exc)

            try:
                if hasattr(repository, "find_related_resources"):
                    related_resources = repository.find_related_resources(knowledge_point)
            except Exception as exc:
                warnings.append(f"关联资源暂缺：{exc}")
                logger.warning("Knowledge graph resource lookup failed: %s", exc)

            try:
                visualization = repository.get_visualization_graph(knowledge_point, min(max_depth, 2))
            except Exception as exc:
                warnings.append(f"图谱可视化暂缺：{exc}")
                logger.warning("Knowledge graph visualization lookup failed: %s", exc)

            return {
                "status": "completed" if not warnings else "partial",
                "dependencies": dependencies,
                "related_resources": related_resources,
                "visualization": visualization,
                "warnings": warnings,
            }
        finally:
            if repository is not None:
                repository.close()

    def _build_profile_snapshot(
        self,
        *,
        session: Session,
        user_id: int,
        knowledge_point: str,
        fallback_profile: dict[str, Any],
        subject: str = "", point_id=None,
    ) -> Any:
        trace = get_current_trace()
        stage = trace.stage("learner_profile") if trace is not None else nullcontext()
        with stage:
            return PersonalizationService(session).build_snapshot(
                user_id=user_id,
                knowledge_point=knowledge_point,
                fallback_profile=fallback_profile, subject=subject, point_id=point_id,
            )

    def _run_graph_agent_with_trace(
        self,
        knowledge_point: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        trace = get_current_trace()
        stage = trace.stage("knowledge_graph") if trace is not None else nullcontext()
        with stage:
            return self._run_graph_agent(knowledge_point, context)

    def _run_isolated(
        self,
        agent_name: str,
        operation: Callable[[], Any],
        context: dict[str, Any],
        calls: list[dict[str, Any]],
    ) -> Any:
        """Run one stage without allowing an exception to abort sibling stages."""

        if self.stage_callback is not None:
            self.stage_callback(agent_name)
        started = time.perf_counter()
        try:
            output = operation()
        except AIServiceError as exc:
            logger.warning("%s_ai_failure code=%s", agent_name, exc.code)
            output = {
                "status": "failed",
                "error_code": exc.code,
                "error": exc.user_message,
                "user_message": exc.user_message,
            }
        except Exception as exc:
            logger.exception("%s_failed", agent_name)
            output = {
                "status": "failed",
                "error_code": "AGENT_EXECUTION_FAILED",
                "error": str(exc)[:500],
                "user_message": "该学习步骤暂时失败，其他可用结果仍会继续返回。",
            }
        self._record_agent_call(calls, agent_name, output, started, context)
        return output

    def _run_knowledge_base_agent(self, context: dict[str, Any]) -> dict[str, Any]:
        operation = str(context.get("operation") or "list")
        subject = context.get("subject")
        query = str(context.get("query") or "")
        top_k = int(context.get("top_k") or 6)
        shared = context.get("retrieval_context") or {}
        if operation == "search" and isinstance(shared.get("retrieved_chunks"), list) and shared.get("knowledge_base_version") == get_settings().knowledge_base_version:
            from services.agent_service.app.services.knowledge_publication import visible_chunks
            chunks = visible_chunks(shared["retrieved_chunks"])
            return {"status": "completed", "operation": operation, "query": query, "shared_context_reused": True,
                    "items": [{"id": row.get("id"), "title": (row.get("metadata") or {}).get("title") or query,
                               "content": row.get("content", ""), "source": row.get("metadata") or {}}
                              for row in chunks[:top_k]]}
        service = KnowledgeBaseService()

        if operation == "search":
            if not query.strip():
                items = [
                    service.article_to_dict(article)
                    for article in service.list_articles(subject=str(subject) if subject else None)[:top_k]
                ]
            else:
                curated = [
                    service.article_to_dict(article)
                    for article in service.search_by_keywords(
                        query,
                        top_k=top_k,
                        subject=str(subject) if subject else None,
                    )
                ]
                search_filters = {
                    key: context.get(key)
                    for key in (
                        "subject", "course", "chapter", "difficulty", "university",
                        "source", "source_site", "language", "license",
                    )
                    if context.get(key) not in (None, "")
                }
                indexed = service.search_indexed(
                    query,
                    top_k=top_k,
                    filters=search_filters,
                    retrieval_mode=str(context.get("retrieval_mode") or "hybrid"),
                )
                items = []
                seen_titles: set[str] = set()
                for item in [*curated, *indexed]:
                    title = str(item.get("title") or "")
                    if title and title not in seen_titles:
                        seen_titles.add(title)
                        items.append(item)
                    if len(items) >= top_k:
                        break
            return {
                "status": "completed",
                "operation": operation,
                "query": query,
                "items": items,
            }

        if operation == "article":
            article_id = str(context.get("article_id") or "")
            if article_id.startswith("indexed-"):
                indexed_article = service.get_indexed_article(article_id)
                if indexed_article is not None:
                    return {"status": "completed", "operation": operation, "article": indexed_article}
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
        snapshot: Any | None,
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        request = ResourceGenerationRequest(
            user_id=payload.user_id,
            knowledge_point=knowledge_point,
            resource_style=str(context.get("resource_style") or "interactive"),  # type: ignore[arg-type]
            resource_type=str(context.get("resource_type") or "courseware"),  # type: ignore[arg-type]
            learner_profile=learner_profile,
            request_text=str(context.get("request_text") or f"围绕 {knowledge_point} 生成可独立阅读的正式课件"),
            reference_materials=str(context.get("reference_materials") or ""),
            retrieval_context=dict(context.get("retrieval_context") or {}),
            performance_mode=str(context.get("performance_mode") or "balanced"),  # type: ignore[arg-type]
            subject=str(context.get("subject") or ""),
            grade=str(context.get("grade") or ""),
            chapter=str(context.get("chapter") or ""),
            section=str(context.get("section") or ""),
            knowledge_point_id=str(context.get("knowledge_point_id") or ""),
            teaching_scope_id=str(context.get("teaching_scope_id") or ""),
            assistant_operation_key=(f"assistant:{context['assistant_operation_root']}:resource"
                                     if context.get("assistant_operation_root") else ""),
            allow_web_knowledge=context.get("allow_web_knowledge", True) is True,
            force_regenerate=context.get("force_regenerate") is True or "重新生成" in str(context.get("request_text") or ""),
        )
        if request.assistant_operation_key:
            with SessionLocal() as receipt_db:
                saved = receipt_db.query(Resource).filter(
                    Resource.assistant_operation_key == request.assistant_operation_key,
                    Resource.generated_for_user_id == payload.user_id,
                ).first()
                if saved is not None and saved.generation_status == "generated":
                    logger.info("assistant_idempotency_hit key=%s agent=resource_generation_agent task_root=%s", request.assistant_operation_key, context.get("assistant_operation_root"))
                    if saved.audit_status == "rejected":
                        return {"status": "failed", "error": "已保存资源未通过审核，不能作为可用课件重放"}, None
                    resource = {"id": saved.id, "title": saved.title, "content": saved.content,
                                "resource_type": saved.type, "user_id": payload.user_id}
                    return {"status": "completed", "resource": resource, "idempotent_replay": True}, resource
        try:
            service = ResourceGenerationService()
            resource = self._generate_resource(
                service,
                request,
                resource_type=request.resource_type,
                snapshot=snapshot,
            )
        except ResourceGenerationError as exc:
            return {"status": "failed", "error": str(exc)}, None
        return {
            "status": "completed",
            "resource": resource,
            "profile_handoff": self._agent_handoff(learner_profile, "resource_generation_agent"),
        }, resource

    def _generate_resource(
        self,
        service: Any,
        request: ResourceGenerationRequest,
        *,
        resource_type: str,
        snapshot: Any | None,
    ) -> dict[str, Any]:
        """Dispatch to the generator registered for ``resource_type``.

        Prose kinds go through the courseware planner; the structured kinds each
        have their own JSON contract.  An unregistered type is rejected rather
        than silently downgraded to courseware, so a caller never receives a
        different artefact than the one it asked for.
        """

        if resource_type in {"courseware", "notes", "exam"}:
            return service.generate_courseware_with_plan(request, snapshot=snapshot)
        if resource_type == "mind_map":
            return service.generate_mind_map(request)
        if resource_type == "code_case":
            return service.generate_code_case(request)
        if resource_type == "video_script":
            return service.generate_video_script(request)
        if resource_type == "exercise":
            raise ResourceGenerationError(
                "Exercise sets are produced by the exercise generation agent, not the resource agent."
            )
        raise ResourceGenerationError(f"Unsupported resource type: {resource_type}")

    def _run_exercise_agent(
        self,
        *,
        payload: CoordinationRequest,
        knowledge_point: str,
        learner_profile: dict[str, Any],
        context: dict[str, Any],
        resource_result: dict[str, Any] | None,
        snapshot: Any | None,
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
            performance_mode=str(context.get("performance_mode") or "balanced"),  # type: ignore[arg-type]
            subject=str(context.get("subject") or ""),
            grade=str(context.get("grade") or ""),
            chapter=str(context.get("chapter") or ""),
            section=str(context.get("section") or ""),
            knowledge_point_id=str(context.get("knowledge_point_id") or ""),
            teaching_scope_id=str(context.get("teaching_scope_id") or ""),
            retrieval_context=dict((resource_result or {}).get("retrieval_context") or context.get("retrieval_context") or {}),
            reference_materials=str(context.get("reference_materials") or ""),
            assistant_operation_key=(f"assistant:{context['assistant_operation_root']}:exercise:{context.get('assistant_exercise_batch', 0)}"
                                     if context.get("assistant_operation_root") else ""),
            allow_web_knowledge=context.get("allow_web_knowledge", True) is True,
        )
        if request.assistant_operation_key:
            with SessionLocal() as receipt_db:
                saved = receipt_db.query(Exercise).filter(
                    Exercise.assistant_operation_key.like(request.assistant_operation_key + ":%"),
                ).order_by(Exercise.id).all()
                if saved:
                    logger.info("assistant_idempotency_hit key=%s agent=exercise_generation_agent task_root=%s", request.assistant_operation_key, context.get("assistant_operation_root"))
                    if len(saved) != request.exercise_count:
                        raise ValueError("已保存题组数量不完整，停止重复生成")
                    items = []
                    for row in saved:
                        body = json.loads(row.content)
                        if body.get("generated_for_user_id") != payload.user_id:
                            raise ValueError("已保存题组归属不匹配")
                        items.append({"exercise_id": row.id, "knowledge_point": body["knowledge_point"],
                                      "question_type": body["question_type"], "difficulty":
                                      {1: "foundation", 2: "intermediate", 3: "advanced"}.get(row.difficulty, "foundation"),
                                      "prompt": body["prompt"], "options": body.get("options", []),
                                      "answer": row.answer, "analysis": row.analysis})
                    return {"status": "completed", "exercise_set": {"exercises": items}, "idempotent_replay": True}
        return {
            "status": "completed",
            "exercise_set": ExerciseGenerationService().generate_exercises(request, snapshot=snapshot),
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
        snapshot: Any | None,
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
            retrieval_context=dict(context.get("retrieval_context") or {}),
            learning_history={
                **dict(context.get("learning_history") or {}),
                "learner_profile": learner_profile,
            },
        )
        try:
            return {
                "status": "completed",
                "qa": QAService(session, personalization_snapshot=snapshot).analyze_question(request),
                "profile_handoff": self._agent_handoff(learner_profile, "qa_agent"),
            }
        except AIServiceError as exc:
            logger.warning(
                "qa_agent_ai_failure code=%s raw_error=%s",
                exc.code,
                getattr(exc, "raw_message", str(exc))[:500],
            )
            return {
                "status": "failed",
                "error_code": exc.code,
                "error": getattr(exc, "raw_message", str(exc)),
                "user_message": exc.user_message,
            }
        except Exception as exc:
            logger.exception("qa_agent_failed raw_error=%s", str(exc)[:500])
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
        dashboard = self._run_async(service.generate_dashboard(payload.user_id))
        mistake_notebook = dashboard.mistake_notebook
        evaluation_data: dict[str, Any] = {
            "suggestions": self._to_plain_data(dashboard.learning_suggestions),
            "profile_snapshot": self._to_plain_data(dashboard.profile_snapshot),
            "mistake_statistics": {
                "user_id": payload.user_id,
                "mistake_count": mistake_notebook.mistake_count,
                "exercise_ids": [item.exercise_id for item in mistake_notebook.items],
            },
        }
        if context.get("include_stage_report"):
            evaluation_data["stage_report"] = self._to_plain_data(dashboard.stage_report)
        if context.get("include_comprehensive_report"):
            evaluation_data["comprehensive_report"] = self._to_plain_data(dashboard.comprehensive_report)

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

    def _safe_input_summary(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Summarize inputs without logging prompts, answers, tokens or secrets."""

        return {
            "keys": sorted(str(key) for key in payload.keys() if str(key) not in {"prompt", "token", "authorization"}),
            "has_learner_profile": bool(payload.get("learner_profile")),
            "has_teacher_scope": bool(payload.get("teacher_scope")),
        }

    def _record_agent_call(
        self,
        calls: list[dict[str, Any]],
        agent_name: str,
        output: Any,
        started: float,
        context: dict[str, Any],
    ) -> None:
        if isinstance(output, tuple) and output and isinstance(output[0], dict):
            payload = output[0]
        else:
            payload = output if isinstance(output, dict) else {}
        output_status = payload.get("status") if isinstance(payload, dict) else None
        if not output_status:
            output_status = "completed"
        calls.append(
            {
                "agent": agent_name,
                "version": AGENT_VERSIONS.get(agent_name, "unknown"),
                "input_summary": self._safe_input_summary(context),
                "output_status": output_status,
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                "retries": 0,
                "error_code": payload.get("error_code"),
            }
        )

    def _agent_dependencies(self, agent_name: str, selected: list[str]) -> list[str]:
        dependencies = {
            "path_planning_agent": ["learner_profiling_agent", "knowledge_graph_agent"],
            "resource_generation_agent": ["learner_profiling_agent", "knowledge_base_agent"],
            "exercise_generation_agent": ["learner_profiling_agent", "resource_generation_agent"],
            "qa_agent": ["learner_profiling_agent", "knowledge_graph_agent"],
            "evaluation_feedback_agent": list(selected),
        }
        return [name for name in dependencies.get(agent_name, []) if name in selected and name != agent_name]

    def _build_task_state(self, state: dict[str, Any]) -> dict[str, Any]:
        """Expose the full unified task state.

        Every documented field is always present, so a consumer never has to
        distinguish "absent" from "empty".  ``learner_profile`` is reduced to the
        facts other agents actually consume, and ``learning_evidence`` only ever
        carries counts and identifiers rather than raw answers or dialogue.
        """

        learner_profile = state.get("learner_profile") or {}
        return {
            "user_id": state.get("user_id"),
            "task_id": state.get("task_id"),
            "session_id": state.get("session_id", ""),
            "intent": state.get("intent", ""),
            "intent_params": state.get("intent_params", {}),
            "learner_profile": self._summarize_learner_profile(learner_profile),
            "learning_evidence": state.get("learning_evidence", []),
            "selected_agents": state.get("selected_agents", []),
            "task_plan": state.get("task_plan", []),
            "agent_handoff": state.get("agent_handoff", {}),
            "intermediate_results": state.get("intermediate_results", {}),
            "citations": state.get("citations", []),
            "validation_results": state.get("validation_results", []),
            "status": state.get("status", "pending"),
            "progress": state.get("progress", 0.0),
            "current_step": state.get("current_step", ""),
            "error": state.get("error"),
        }

    @staticmethod
    def _summarize_learner_profile(learner_profile: Any) -> dict[str, Any]:
        """Keep the profile facts downstream agents use, never raw answer text."""

        if not isinstance(learner_profile, dict):
            return {}
        allowed = (
            "mastery_score",
            "correct_rate",
            "answered_count",
            "weak_question_types",
            "preferred_resource_modes",
            "learning_style",
            "grade",
            "subject",
            "agent_handoff",
            "teacher_scope",
            "profile_dimensions",
            "zhishu_profile",
        )
        return {key: learner_profile[key] for key in allowed if key in learner_profile}


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

    def _collect_citations(self, outputs: dict[str, Any]) -> list[dict[str, Any]]:
        """Gather citations produced by content agents into the task state.

        Only citations that resolve to a chunk which really was retrieved are
        kept as sources; unresolvable markers are preserved with
        ``resolved=False`` so a fabricated reference stays visible instead of
        being silently dropped.
        """

        collected: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for agent_output in outputs.values():
            if not isinstance(agent_output, dict):
                continue
            resource = agent_output.get("resource")
            if not isinstance(resource, dict):
                continue
            validation = resource.get("content_validation")
            if not isinstance(validation, dict):
                continue
            for citation in validation.get("citations") or []:
                if not isinstance(citation, dict):
                    continue
                key = (str(citation.get("marker", "")), str(citation.get("reference", "")))
                if key in seen:
                    continue
                seen.add(key)
                collected.append(
                    {
                        "marker": citation.get("marker", ""),
                        "reference": citation.get("reference", ""),
                        "resolved": bool(citation.get("resolved")),
                        "chunk_id": citation.get("chunk_id", ""),
                        "source": citation.get("source", ""),
                        "agent": "resource_generation_agent",
                    }
                )
        return collected

    def _collect_validation_results(self, outputs: dict[str, Any]) -> list[dict[str, Any]]:
        """Summarize per-agent validation verdicts for the task state."""

        results: list[dict[str, Any]] = []
        for name, agent_output in outputs.items():
            if not isinstance(agent_output, dict):
                continue
            resource = agent_output.get("resource")
            if isinstance(resource, dict) and isinstance(resource.get("content_validation"), dict):
                validation = resource["content_validation"]
                results.append(
                    {
                        "agent": name,
                        "resource_type": validation.get("resource_type", ""),
                        "verdict": validation.get("verdict", "unknown"),
                        "structure_passed": bool(validation.get("structure_passed")),
                        "source_passed": bool(validation.get("source_passed")),
                        "source_coverage": validation.get("source_coverage", 0.0),
                        "audit_status": resource.get("audit_status", "pending"),
                    }
                )
        return results
