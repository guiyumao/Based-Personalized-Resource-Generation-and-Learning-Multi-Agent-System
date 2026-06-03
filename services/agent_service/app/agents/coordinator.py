"""LangGraph coordinator workflow example."""

from __future__ import annotations

from typing import Any, TypedDict

from common.messaging.rabbitmq import RabbitMQPublisher
from common.schemas.agent import CoordinationRequest


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
    """Task router built with LangGraph."""

    def __init__(self) -> None:
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
        selected_agents: list[str] = []

        if any(token in intent for token in ["课件", "习题", "资源", "courseware", "exercise"]):
            selected_agents.extend(["learner_profiling_agent", "resource_generation_agent"])
        if any(token in intent for token in ["路径", "计划", "path", "schedule"]):
            selected_agents.extend(["learner_profiling_agent", "knowledge_graph_agent", "path_planning_agent"])
        if any(token in intent for token in ["评估", "报告", "evaluation", "report"]):
            selected_agents.append("evaluation_feedback_agent")
        if any(token in intent for token in ["答疑", "解释", "debug", "question"]):
            selected_agents.extend(["knowledge_graph_agent", "qa_agent"])
        if not selected_agents:
            selected_agents = ["learner_profiling_agent", "qa_agent"]

        deduped_agents = list(dict.fromkeys(selected_agents))
        return {
            **state,
            "selected_agents": deduped_agents,
            "route_reason": f"Intent '{state['intent']}' matched {', '.join(deduped_agents)}.",
        }

    def _dispatch_tasks(self, state: CoordinatorState) -> CoordinatorState:
        """Publish each selected task to RabbitMQ for asynchronous execution."""

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
        """Resolve simple agent conflicts by setting final status metadata."""

        selected = state["selected_agents"]
        status = "success" if selected else "failed"
        route_reason = state["route_reason"]
        if "resource_generation_agent" in selected and "evaluation_feedback_agent" in selected:
            route_reason += " Coordinator scheduled evaluation after generation to avoid race conditions."
        return {**state, "status": status, "route_reason": route_reason}

    def run(self, payload: CoordinationRequest) -> dict[str, Any]:
        """Invoke the compiled workflow and normalize output."""

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
        return {
            "status": result["status"],
            "selected_agents": result["selected_agents"],
            "route_reason": result["route_reason"],
            "outputs": result["outputs"],
        }
