"""Schemas for agent-service requests and responses."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class CoordinationRequest(BaseModel):
    """Input payload for the coordinator agent."""

    user_id: int
    intent: str = Field(description="The high-level learner or teacher request.")
    knowledge_point: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class CoordinationResponse(BaseModel):
    """Response returned after the LangGraph workflow completes."""

    status: Literal["success", "partial", "failed"]
    selected_agents: list[str]
    route_reason: str
    outputs: dict[str, Any]


class ResourceGenerationRequest(BaseModel):
    """Payload for personalized resource generation."""

    user_id: int
    knowledge_point: str
    resource_style: Literal["concise", "case", "interactive"] = "interactive"
    resource_type: Literal["courseware", "exercise", "notes", "exam"] = "courseware"
    learner_profile: dict[str, Any] = Field(default_factory=dict)
    request_text: str = ""
    preferred_word_count: int | None = Field(default=None, ge=300, le=6000)


class ResourceGenerationPlan(BaseModel):
    """Deterministic generation plan inspired by the agent-core coordination flow."""

    request_summary: str
    knowledge_point: str
    resource_type: Literal["courseware", "exercise", "notes", "exam"]
    resource_style: Literal["concise", "case", "interactive"]
    title_suggestion: str
    suggested_outline: list[str] = Field(default_factory=list)
    target_word_count: int = Field(default=1200, ge=300, le=6000)
    difficulty: Literal["foundation", "intermediate", "advanced"] = "intermediate"
    personalization_hints: list[str] = Field(default_factory=list)
    analysis_source: Literal["request", "heuristic", "profile_enriched"] = "heuristic"


class ResourceVariant(BaseModel):
    """One selectable courseware variant returned to the frontend."""

    variant_id: str
    title: str
    summary: str
    resource_style: Literal["concise", "case", "interactive"]
    content: str
    is_recommended: bool = False


class ResourceGenerationResponse(BaseModel):
    """Response for personalized learning resource generation."""

    user_id: int
    knowledge_point: str
    resource_type: str
    resource_style: str
    generation_plan: ResourceGenerationPlan
    references: list[dict[str, Any]] = Field(default_factory=list)
    personalization: dict[str, Any] = Field(default_factory=dict)
    content: str
    variants: list[ResourceVariant] = Field(default_factory=list)


class GraphQueryRequest(BaseModel):
    """Payload for graph query operations."""

    knowledge_point: str
    max_depth: int = 3


class GraphNode(BaseModel):
    """One visual graph node."""

    id: str
    label: str
    category: Literal["current", "prerequisite", "recommended", "resource"]


class GraphEdge(BaseModel):
    """One visual graph edge."""

    source: str
    target: str
    label: str


class GraphVisualizationResponse(BaseModel):
    """Graph visualization payload for the frontend."""

    knowledge_point: str
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class LearningPathRequest(BaseModel):
    """Payload for generating a learning path."""

    user_id: int
    subject: str = Field(default="Python 程序设计")
    knowledge_point: str
    daily_minutes: int = Field(default=45, ge=15, le=180)
    learner_profile: dict[str, Any] = Field(default_factory=dict)


class LearningTaskItem(BaseModel):
    """One actionable task inside a learning path."""

    task_id: str
    title: str
    task_type: Literal["courseware", "exercise", "review", "graph"]
    knowledge_point: str
    objective: str
    estimated_minutes: int
    difficulty: Literal["foundation", "intermediate", "advanced"]
    completed: bool = False
    status: Literal["pending", "completed", "skipped"] = "pending"


class LearningStageItem(BaseModel):
    """A stage containing multiple learning tasks."""

    stage_id: str
    title: str
    description: str
    tasks: list[LearningTaskItem]


class LearningPathResponse(BaseModel):
    """Response for a generated personalized learning path."""

    user_id: int
    subject: str
    knowledge_point: str
    overview: str
    estimated_days: int
    stages: list[LearningStageItem]


class LearningPathAdjustRequest(BaseModel):
    """Payload for adjusting one generated learning-path task."""

    user_id: int
    task_id: str
    action: Literal["complete", "reset", "skip"]


class ExerciseGenerationRequest(BaseModel):
    """Payload for generating a structured exercise set."""

    user_id: int
    knowledge_point: str
    resource_style: Literal["concise", "case", "interactive"] = "interactive"
    learner_profile: dict[str, Any] = Field(default_factory=dict)
    exercise_count: int = Field(default=5, ge=3, le=10)
    generation_mode: Literal["practice", "self_test", "remedial"] = "practice"
    courseware_content: str = ""


class ExerciseItem(BaseModel):
    """Structured exercise item returned to the frontend."""

    exercise_id: int
    knowledge_point: str
    question_type: Literal["choice", "blank", "judge", "short_answer", "programming"]
    difficulty: Literal["foundation", "intermediate", "advanced"]
    prompt: str
    options: list[str] = Field(default_factory=list)
    answer: str
    analysis: str


class ExerciseGenerationResponse(BaseModel):
    """Structured exercise set for learner practice."""

    user_id: int
    knowledge_point: str
    summary: str
    personalization: dict[str, Any] = Field(default_factory=dict)
    exercises: list[ExerciseItem]


class QARequest(BaseModel):
    """Payload for intelligent tutoring Q&A with learning analysis."""

    student_id: str = Field(description="Unique student identifier.")
    subject: str = Field(description="Subject name, such as math or physics.")
    grade: str = Field(description="Grade level or learning stage.")
    question: str = Field(description="Student's full natural-language question.")
    session_id: int | None = Field(default=None, description="Existing QA conversation session id.")
    session_title: str = Field(default="", description="Optional title used when creating a new QA session.")
    student_answer: str = Field(default="", description="Student's own answer if available.")
    wrong_answer: str = Field(default="", description="Known wrong answer if available.")
    current_knowledge_points: list[str] = Field(default_factory=list)
    learning_route: dict[str, Any] = Field(default_factory=dict)
    error_book: dict[str, Any] = Field(default_factory=dict)
    learning_history: dict[str, Any] = Field(default_factory=dict)


class MistakeBookUpdate(BaseModel):
    """Structured wrong-question notebook update generated by the QA agent."""

    should_add: bool
    question_summary: str
    wrong_reason: str
    correct_approach: str


class LearningRouteUpdate(BaseModel):
    """Structured learning-route adjustment produced by the QA agent."""

    knowledge_point: str
    priority: Literal["high", "medium", "low"]
    action: str
    reason: str


class ResourceRecommendation(BaseModel):
    """Structured personalized recommendation item."""

    resource_type: Literal["courseware", "exercise", "review", "qa_followup"]
    title: str
    reason: str


class QAAnalysisPayload(BaseModel):
    """System-facing analysis extracted from one student question."""

    identified_knowledge_gaps: list[str] = Field(default_factory=list)
    misconceptions: list[str] = Field(default_factory=list)
    difficulty_level: Literal["foundation", "intermediate", "advanced"] = "foundation"
    learning_state: str = ""
    recommended_next_knowledge_points: list[str] = Field(default_factory=list)
    learning_route_updates: list[LearningRouteUpdate] = Field(default_factory=list)
    resource_recommendations: list[ResourceRecommendation] = Field(default_factory=list)
    study_suggestions: list[str] = Field(default_factory=list)
    mistake_book_update: MistakeBookUpdate


class QAConversationMessage(BaseModel):
    """One QA conversation turn returned for multi-round interaction."""

    id: int | None = None
    role: Literal["user", "assistant", "system"]
    content: str
    model_used: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str = ""


class QAResponse(BaseModel):
    """Student-facing answer plus system-facing learning analysis."""

    student_id: str
    subject: str
    grade: str
    session_id: int | None = None
    session_title: str = ""
    student_response: str
    structured_analysis: QAAnalysisPayload
    message_history: list[QAConversationMessage] = Field(default_factory=list)
    context_snippets: list[str] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)


class ChatSessionCreate(BaseModel):
    """Payload for creating a new chat session."""

    user_id: int
    title: str = Field(default="新对话", max_length=200)
    subject: str = Field(default="", max_length=50)


class ChatMessageInput(BaseModel):
    """Payload for sending a chat message."""

    session_id: int
    user_id: int
    content: str = Field(min_length=1)
    context: dict[str, Any] = Field(default_factory=dict)


class ChatMessageItem(BaseModel):
    """Individual chat message in response."""

    id: int
    role: Literal["user", "assistant", "system"]
    content: str
    model_used: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class ChatSessionDetail(BaseModel):
    """Detailed chat session with message history."""

    id: int
    user_id: int
    title: str
    subject: str
    is_active: bool
    created_at: str
    last_message_at: str
    message_count: int
    messages: list[ChatMessageItem] = Field(default_factory=list)


class ChatSessionSummary(BaseModel):
    """Summary of a chat session for list view."""

    id: int
    user_id: int
    title: str
    subject: str
    is_active: bool
    created_at: str
    last_message_at: str
    message_count: int


class ChatResponse(BaseModel):
    """Response for a chat message."""

    session_id: int
    message_id: int
    role: str
    content: str
    model_used: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str
