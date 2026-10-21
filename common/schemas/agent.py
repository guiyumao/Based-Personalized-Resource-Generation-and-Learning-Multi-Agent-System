"""Schemas for agent-service requests and responses."""

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

# Resource kinds this system can genuinely produce.  ``mind_map``, ``code_case``
# and ``video_script`` are honest names for what the generators return: a
# structured map, a *static* code example, and a *script* (never a video file).
RESOURCE_TYPES = (
    "courseware",
    "exercise",
    "notes",
    "exam",
    "mind_map",
    "code_case",
    "video_script",
)
ResourceType = Literal[
    "courseware",
    "exercise",
    "notes",
    "exam",
    "mind_map",
    "code_case",
    "video_script",
]


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
    task_id: str | None = None
    session_id: str = ""
    task_state: dict[str, Any] = Field(default_factory=dict)
    agent_calls: list[dict[str, Any]] = Field(default_factory=list)


class ResourceGenerationRequest(BaseModel):
    """Payload for personalized resource generation."""

    user_id: int
    knowledge_point: str
    resource_style: Literal["concise", "case", "interactive"] = "interactive"
    resource_type: ResourceType = "courseware"
    learner_profile: dict[str, Any] = Field(default_factory=dict)
    request_text: str = ""
    preferred_word_count: int | None = Field(default=None, ge=300, le=6000)
    performance_mode: Literal["fast", "balanced", "quality"] = "balanced"
    subject: str = ""
    grade: str = ""
    chapter: str = ""
    section: str = ""
    knowledge_point_id: str = ""
    teaching_scope_id: str = ""
    retrieval_context: dict[str, Any] = Field(default_factory=dict, exclude=True)
    reference_materials: str = Field(default="", max_length=12000, exclude=True)
    assistant_operation_key: str = Field(default="", exclude=True)
    allow_web_knowledge: bool = True
    force_regenerate: bool = False


class ResourceGenerationPlan(BaseModel):
    """Deterministic generation plan inspired by the agent-core coordination flow."""

    request_summary: str
    knowledge_point: str
    resource_type: ResourceType
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


class MindMapNode(BaseModel):
    """One node of a structured mind map."""

    id: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=200)
    parent_id: str | None = None
    level: int = Field(default=1, ge=0, le=6)
    detail: str = Field(default="", max_length=500)


class MindMapEdge(BaseModel):
    """One parent -> child relation of a structured mind map."""

    source: str = Field(min_length=1, max_length=80)
    target: str = Field(min_length=1, max_length=80)
    label: str = Field(default="", max_length=80)


class MindMapResource(BaseModel):
    """A mind map as structured nodes and edges.

    ``mermaid_source`` is optional presentation sugar.  The nodes/edges remain
    the source of truth so the map can be rendered, searched and validated even
    when a Mermaid renderer is unavailable or the syntax is rejected.
    """

    title: str = Field(default="", max_length=200)
    knowledge_point: str = ""
    root_id: str = ""
    nodes: list[MindMapNode] = Field(default_factory=list)
    edges: list[MindMapEdge] = Field(default_factory=list)
    mermaid_source: str = ""


class CodeCaseResource(BaseModel):
    """A *static* code-practice case.

    This system has no isolated execution environment, so a code case never
    carries executed output.  ``expected_output`` is what the learner should
    observe when they run the code themselves, and ``run_steps`` are human
    instructions.  The model deliberately exposes no ``executed`` flag.
    """

    title: str = Field(default="", max_length=200)
    knowledge_point: str = ""
    language: str = Field(min_length=1, max_length=40)
    objective: str = Field(min_length=1, max_length=500)
    prerequisites: list[str] = Field(default_factory=list)
    example_code: str = Field(min_length=1)
    code_explanation: list[str] = Field(default_factory=list)
    expected_output: str = ""
    run_steps: list[str] = Field(default_factory=list)
    common_errors: list[str] = Field(default_factory=list)
    extension_exercises: list[str] = Field(default_factory=list)

    @field_validator("run_steps")
    @classmethod
    def _require_run_steps(cls, value: list[str]) -> list[str]:
        steps = [str(item).strip() for item in value if str(item).strip()]
        if not steps:
            raise ValueError("a code case must describe how to run the example")
        return steps


class VideoScriptChapter(BaseModel):
    """One chapter of a teaching video *script*."""

    chapter_id: str = Field(default="", max_length=40)
    title: str = Field(default="", max_length=200)
    narration: str = Field(min_length=1)
    visual: str = ""
    on_screen_text: str = ""
    duration_seconds: float = Field(gt=0, le=3600)


class VideoScriptResource(BaseModel):
    """A teaching video script.

    This is a script, not a video: no media file, URL or rendered frame is
    produced or referenced anywhere in the system.
    """

    title: str = Field(default="", max_length=200)
    knowledge_point: str = ""
    target_audience: str = Field(default="", max_length=120)
    total_duration_seconds: float = Field(default=0, ge=0, le=7200)
    chapters: list[VideoScriptChapter] = Field(default_factory=list)
    production_notes: list[str] = Field(default_factory=list)


class ResourceGenerationResponse(BaseModel):
    """Response for personalized learning resource generation."""
    #: Persisted ``Resource.id``. Without it a caller cannot address the resource
    #: it just created through the read API, because the generator's response dict
    #: is narrowed to the fields declared here.
    id: int | None = None
    reused: bool = False
    knowledge_evidence: dict[str, Any] = Field(default_factory=dict)
    media: dict[str, Any] = Field(default_factory=dict)
    user_id: int
    knowledge_point: str
    resource_type: str
    resource_style: str
    generation_plan: ResourceGenerationPlan
    references: list[dict[str, Any]] = Field(default_factory=list)
    personalization: dict[str, Any] = Field(default_factory=dict)
    content: str
    variants: list[ResourceVariant] = Field(default_factory=list)
    generation_status: Literal["queued", "generating", "generated", "failed"] = "generated"
    audit_status: Literal["pending", "passed", "rejected", "unavailable"] = "pending"
    publish_status: Literal["draft", "published", "archived"] = "draft"
    audit_reason: str = ""
    # Structured payloads for the non-prose resource types.  ``content`` always
    # carries a human-readable rendering so existing consumers keep working.
    mind_map: MindMapResource | None = None
    code_case: CodeCaseResource | None = None
    video_script: VideoScriptResource | None = None
    # Deterministic structural + source validation, or ``None`` when the
    # resource type has no registered contract yet.
    content_validation: dict[str, Any] | None = None


class GraphQueryRequest(BaseModel):
    """Payload for graph query operations."""
    knowledge_point: str = Field(min_length=1, max_length=100)
    max_depth: int = Field(default=3, ge=1, le=5)
    resource_id: int | None = Field(default=None, gt=0)
    resource_version: str | None = Field(default=None, max_length=64)


class GraphNode(BaseModel):
    """One visual graph node.

    The url field is filled for resource nodes that trace back to a public
    reference (knowledge-base source or learning link) so the UI can render the
    resource list as real hyperlinks instead of plain labels.
    """

    id: str
    label: str
    category: Literal["current", "prerequisite", "recommended", "resource"]
    url: str = ""
    provider: str = ""
    kind: str = ""


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
    subject: str = Field(default="")
    knowledge_point: str
    daily_minutes: int = Field(default=45, ge=15, le=180)
    learner_profile: dict[str, Any] = Field(default_factory=dict)
    retrieval_context: dict[str, Any] = Field(default_factory=dict, exclude=True)


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
    # Dependencies the backend enforces before this task may be completed.
    # Empty means "positional": the task immediately before it in the path.
    depends_on: list[str] = Field(default_factory=list)
    # Optional per-task pass mark.  ``None`` means "use the configured default"
    # (``learning_path_pass_threshold``), so the threshold is never hardcoded in
    # the browser.
    pass_threshold: int | None = Field(default=None, ge=0, le=100)


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
    teacher_scope: dict[str, Any] | None = None
    generation_source: Literal["llm"] | None = None
    source_transcript_analysis_id: int | None = None


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
    # Dynamic exercise count: the learner picks 1-25 questions on the practice page.
    exercise_count: int = Field(default=10, ge=1, le=25)
    question_type_counts: dict[str, int] = Field(default_factory=dict)
    generation_mode: Literal["practice", "self_test", "remedial"] = "practice"
    courseware_content: str = ""
    performance_mode: Literal["fast", "balanced", "quality"] = "balanced"
    subject: str = ""
    grade: str = ""
    chapter: str = ""
    section: str = ""
    knowledge_point_id: str = ""
    teaching_scope_id: str = ""
    retrieval_context: dict[str, Any] = Field(default_factory=dict, exclude=True)
    reference_materials: str = Field(default="", max_length=12000, exclude=True)
    assistant_operation_key: str = Field(default="", exclude=True)
    allow_web_knowledge: bool = True


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
    generation_status: Literal["generated", "failed"] = "generated"
    audit_status: Literal["passed", "rejected", "unavailable"] = "passed"
    audit_reason: str = ""


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
    retrieval_context: dict[str, Any] = Field(default_factory=dict, exclude=True)
    use_knowledge_base: bool = False
    allow_web_knowledge: bool = True


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
    generated_exercises: ExerciseGenerationResponse | None = None
    generated_resource: ResourceGenerationResponse | None = None


class ChatSessionCreate(BaseModel):
    """Payload for creating a new chat session."""

    user_id: int
    title: str = Field(default="", max_length=200)
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


class FeedbackImprovementArea(BaseModel):
    """One specific improvement area identified by the Feedback Synthesis Agent."""

    area: str
    severity: Literal["high", "medium", "low"]
    evidence_from: str
    suggestion: str


class RecommendedResource(BaseModel):
    """A resource recommended by the Feedback Synthesis Agent."""

    type: Literal["courseware", "exercise", "review", "graph"]
    title: str
    reason: str


class NextStepPlan(BaseModel):
    """Concrete next-step actions from synthesis."""

    immediate_actions: list[str] = Field(default_factory=list)
    this_week_focus: list[str] = Field(default_factory=list)
    recommended_resources: list[RecommendedResource] = Field(default_factory=list)


class FeedbackSynthesisOutput(BaseModel):
    """Structured output from the Feedback Synthesis Agent."""

    overall_assessment: str
    core_strengths: list[str] = Field(default_factory=list)
    improvement_areas: list[FeedbackImprovementArea] = Field(default_factory=list)
    personalized_feedback: str
    next_step_plan: NextStepPlan
    agent_synthesis_summary: str
    learning_insight: str
    generated_at: str
