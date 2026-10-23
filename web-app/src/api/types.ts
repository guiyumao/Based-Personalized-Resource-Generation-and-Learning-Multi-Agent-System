export type UserCreatePayload = {
  username: string
  password: string
  role: string
  email?: string
}

export type UserRegisterPayload = {
  username: string
  password: string
  role: 'student' | 'teacher' | 'admin'
  email?: string
}

export type UserLoginPayload = {
  username: string
  password: string
}

export type AuthTokenResponse = {
  access_token: string
  token_type: string
  user_id: number
  username: string
  role: 'student' | 'teacher' | 'admin'
}

export type LearnerRadarMetric = {
  dimension: string
  score: number | null
}

export type LearnerHeatmapCell = {
  knowledge_point: string
  mastery: number
}

export type LearnerProfileDashboard = {
  user_id: number
  learning_style: string
  mastery_overview: number | null
  weekly_focus_minutes: number
  habit_summary: string
  radar_metrics: LearnerRadarMetric[]
  heatmap: LearnerHeatmapCell[]
  learning_content: {
    source: string
    total_answers: number
    sampled_answers: number
    accuracy: number | null
    latest_answer_id: number | null
    knowledge_point_count: number
    resource_interaction_count: number
    latest_resource_interaction_id: number | null
    explored_points: Array<{ name: string; interactions: number }>
    knowledge_points: Array<{
      name: string
      attempts: number
      wrong: number
      accuracy: number | null
      mastery: number | null
      weak: boolean
      latest_answer_id: number
    }>
  }
}

export type LearnerSuggestion = {
  user_id: number
  suggestions: string[]
  focus_areas: string[]
  recommended_action: string
}

export type LearnerProfileSnapshot = {
  user_id: number
  learning_style: string
  mastery_overview: number | null
  weekly_focus_minutes: number
  habit_summary: string
  radar_metrics: LearnerRadarMetric[]
  heatmap: LearnerHeatmapCell[]
}

export type UserProfileRead = {
  user_id: number
  mastery_json: Record<string, unknown>
  learning_style: string
  cognitive_abilities: Record<string, unknown>
  habits: Record<string, unknown>
  profile_dimensions: Record<string, string>
  zhishu_profile?: Record<string, unknown>
}

export type UserProfileUpdatePayload = {
  learning_style?: string
  profile_dimensions: Record<string, string>
}

export type ProfileChatPayload = {
  message: string
}

export type ProfileChatResponsePayload = {
  reply: string
  profile_updates: Record<string, string>
  profile_completeness: Record<string, string>
  estimated_remaining_rounds: number
}

export type ProfileAnalysisPayload = {
  knowledgeBase?: string
  cognitiveStyle?: string
  errorPreference?: string
  learningSpeed?: string
  interestDirection?: string
  goalOrientation?: string
  generated_at?: string
  model?: string
  summaries?: Record<string, string>
}

export type CoordinationPayload = {
  user_id: number
  intent: string
  knowledge_point?: string
  payload?: Record<string, unknown>
}

/**
 * Resource kinds this system can genuinely produce (mirrors
 * `common/schemas/agent.py::RESOURCE_TYPES`).
 */
export type ResourceType =
  | 'courseware'
  | 'exercise'
  | 'notes'
  | 'exam'
  | 'mind_map'
  | 'code_case'
  | 'video_script'

export type ResourcePayload = {
  user_id: number
  knowledge_point: string
  resource_style: 'concise' | 'case' | 'interactive'
  resource_type: ResourceType
  learner_profile: Record<string, unknown>
  request_text?: string
  preferred_word_count?: number
}

export type LearningPathPayload = {
  user_id: number
  subject: string
  knowledge_point: string
  daily_minutes: number
  learner_profile: Record<string, unknown>
}

export type LearningTaskItem = {
  task_id: string
  title: string
  task_type: 'courseware' | 'exercise' | 'review' | 'graph'
  knowledge_point: string
  objective: string
  estimated_minutes: number
  difficulty: 'foundation' | 'intermediate' | 'advanced'
  completed: boolean
  status?: 'pending' | 'completed' | 'skipped'
  /** Task ids the backend requires before this task can be completed. */
  depends_on?: string[]
  /** Per-task pass mark; omitted means the server default applies. */
  pass_threshold?: number | null
}

export type LearningStageItem = {
  stage_id: string
  title: string
  description: string
  tasks: LearningTaskItem[]
}

export type LearningPathResponse = {
  user_id: number
  subject: string
  knowledge_point: string
  overview: string
  estimated_days: number
  stages: LearningStageItem[]
  teacher_scope?: TeachingScopeItem | null
  generation_source?: 'llm' | null
  source_transcript_analysis_id?: number | null
  // P0-1/P0-2: personal AI-draft provenance (never public reviewed knowledge).
  knowledge_scope?: 'public' | 'personal_draft'
  knowledge_gap_reason?: string
  knowledge_gap_id?: string
  // Why the automatic knowledge-base backfill did not complete (honest state).
  knowledge_backfill_reason?: string
  knowledge_draft_task_id?: number
  knowledge_sources?: Array<{ url?: string; title?: string }>
  knowledge_draft?: {
    name: string
    description?: string
    chapters: Array<{ name: string; points: Array<{ name: string }> }>
  }
}

export type AgentExecutionOutput<T = unknown> = {
  status?: 'completed' | 'failed' | string
  error?: string
} & T

export type CoordinationResponse = {
  status: 'success' | 'partial' | 'failed'
  selected_agents: string[]
  route_reason: string
  outputs: Record<string, AgentExecutionOutput<Record<string, unknown>>>
}

export type ExerciseGenerationPayload = {
  user_id: number
  knowledge_point: string
  resource_style: 'concise' | 'case' | 'interactive'
  learner_profile: Record<string, unknown>
  exercise_count: number
  question_type_counts?: Partial<Record<'choice' | 'blank' | 'judge' | 'short_answer' | 'programming', number>>
  generation_mode?: 'practice' | 'self_test' | 'remedial'
  courseware_content?: string
}

export type ExerciseItem = {
  exercise_id: number
  knowledge_point: string
  question_type: 'choice' | 'blank' | 'judge' | 'short_answer' | 'programming'
  difficulty: 'foundation' | 'intermediate' | 'advanced'
  prompt: string
  options: string[]
  answer: string
  analysis: string
}

export type PersonalizationRecentMistake = {
  exercise_id: number
  question_type: string
  difficulty: string
  prompt: string
  analysis: string
  user_answer?: string
  correct_answer?: string
}

export type PersonalizationContext = {
  mastery_score: number | null
  evidence?: { version?: string; status?: string; sample_size?: number; uncertainty_interval?: number[] }
  correct_rate: number | null
  answered_count: number
  weak_question_types: string[]
  basis: string[]
  recent_mistakes: PersonalizationRecentMistake[]
}

export type ResourceVariant = {
  variant_id: string
  title: string
  summary: string
  resource_style: 'concise' | 'case' | 'interactive'
  content: string
  is_recommended: boolean
}

export type ResourceGenerationPlan = {
  request_summary: string
  knowledge_point: string
  resource_type: 'courseware' | 'exercise' | 'notes' | 'exam'
  resource_style: 'concise' | 'case' | 'interactive'
  title_suggestion: string
  suggested_outline: string[]
  target_word_count: number
  difficulty: 'foundation' | 'intermediate' | 'advanced'
  personalization_hints: string[]
  analysis_source: 'request' | 'heuristic' | 'profile_enriched'
}

export type ResourceResult = {
  user_id: number
  knowledge_point: string
  resource_type: string
  resource_style: string
  generation_plan?: ResourceGenerationPlan
  references: Array<{
    id?: string
    content?: string
    metadata?: Record<string, unknown>
  }>
  personalization?: PersonalizationContext
  content: string
  variants?: ResourceVariant[]
}

export type ExerciseGenerationResponse = {
  user_id: number
  knowledge_point: string
  summary: string
  personalization: PersonalizationContext
  exercises: ExerciseItem[]
}

export type QARequestPayload = {
  student_id: string
  subject: string
  grade: string
  question: string
  session_id?: number | null
  session_title?: string
  student_answer?: string
  wrong_answer?: string
  current_knowledge_points: string[]
  learning_route: Record<string, unknown>
  error_book: Record<string, unknown>
  learning_history: Record<string, unknown>
}

export type MistakeBookUpdate = {
  should_add: boolean
  question_summary: string
  wrong_reason: string
  correct_approach: string
}

export type LearningRouteUpdate = {
  knowledge_point: string
  priority: 'high' | 'medium' | 'low'
  action: string
  reason: string
}

export type ResourceRecommendation = {
  resource_type: 'courseware' | 'exercise' | 'review' | 'qa_followup'
  title: string
  reason: string
}

export type QAAnalysisPayload = {
  identified_knowledge_gaps: string[]
  misconceptions: string[]
  difficulty_level: 'foundation' | 'intermediate' | 'advanced'
  learning_state: string
  recommended_next_knowledge_points: string[]
  learning_route_updates: LearningRouteUpdate[]
  resource_recommendations: ResourceRecommendation[]
  study_suggestions: string[]
  mistake_book_update: MistakeBookUpdate
}

export type QAConversationMessage = {
  id?: number | null
  role: 'user' | 'assistant' | 'system'
  content: string
  model_used: string
  metadata: Record<string, unknown>
  created_at: string
}

export type QAResponsePayload = {
  student_id: string
  subject: string
  grade: string
  session_id?: number | null
  session_title?: string
  student_response: string
  structured_analysis: QAAnalysisPayload
  message_history: QAConversationMessage[]
  context_snippets: string[]
  confidence: number | null
  generated_exercises?: ExerciseGenerationResponse | null
  generated_resource?: ResourceResult | null
}

export type PracticeSubmissionPayload = {
  user_id: number
  client_request_id?: string
  exercise_id: number
  subject?: string
  knowledge_point: string
  question_type: 'choice' | 'blank' | 'judge' | 'short_answer' | 'programming'
  user_answer: string
  correct_answer: string
  analysis: string
  time_spent: number
  difficulty?: 'basic' | 'intermediate' | 'advanced'
  reference_answer?: string | null
  max_score?: number | null
  exercise_content?: string | null
  chapter_id?: string | null
  chapter_name?: string | null
}

export type QAMistakeSubmissionPayload = {
  user_id: number
  exercise_id: number
  subject?: string
  knowledge_point: string
  question_type: 'choice' | 'blank' | 'judge' | 'short_answer' | 'programming'
  question_summary: string
  wrong_answer: string
  correct_answer: string
  analysis: string
  suggested_action: string
  time_spent: number
  difficulty?: 'basic' | 'intermediate' | 'advanced'
  chapter_id?: string | null
  chapter_name?: string | null
}

export type PracticeFeedback = {
  user_id: number
  exercise_id: number
  is_correct: boolean
  score: number
  feedback: string
  suggested_action: string
  analysis: string
  mastery_after_update?: number | null
}

export type MistakeItem = {
  user_id?: number
  exercise_id: number
  subject?: string
  knowledge_point: string
  question_type: 'choice' | 'blank' | 'judge' | 'short_answer' | 'programming'
  prompt: string
  options: string
  user_answer: string
  correct_answer: string
  analysis: string
  suggested_action: string
}

export type MistakeNotebook = {
  user_id: number
  mistake_count: number
  items: MistakeItem[]
}

export type ExerciseFavoriteItem = {
  id: number
  exercise_id: number
  knowledge_point: string
  question_type: string
  difficulty: string
  prompt: string
  options: string[]
  answer: string
  analysis: string
  created_at: string
}

export type ExerciseFavoriteNotebook = {
  user_id: number
  favorite_count: number
  items: ExerciseFavoriteItem[]
}

export type ReportDetail = {
  report_type: 'stage' | 'comprehensive'
  user_id: number
  title: string
  summary: string
  strengths: string[]
  weaknesses: string[]
  next_actions: string[]
  evidence: {
    total_answers: number
    correct_answers: number
    accuracy: number
    average_time_spent: number
    average_score: number
    mistake_count: number
    strongest_question_types: string[]
    weakest_question_types: string[]
    weakest_knowledge_point: string | null
    weakest_knowledge_accuracy: number | null
    latest_mistake: {
      knowledge_point: string
      question_type: 'choice' | 'blank' | 'judge' | 'short_answer' | 'programming'
      user_answer: string
      correct_answer: string
      analysis: string
    } | null
  }
}

export type ReportDashboard = {
  stage_report: ReportDetail
  comprehensive_report: ReportDetail
  profile_snapshot: LearnerProfileSnapshot
  learning_suggestions: LearnerSuggestion
  mistake_notebook: MistakeNotebook
}

export type RemedialExerciseItem = {
  exercise_id: number
  knowledge_point: string
  question_type: 'choice' | 'blank' | 'judge' | 'short_answer' | 'programming'
  prompt: string
  options: string[]
  answer: string
  analysis: string
  source_exercise_id: number
}

export type RemedialExerciseSet = {
  user_id: number
  generated_from_mistakes: number
  summary: string
  exercises: RemedialExerciseItem[]
}

export type GraphNode = {
  id: string
  label: string
  category: 'current' | 'prerequisite' | 'recommended' | 'resource'
  /** Public reference link for resource nodes; empty when no source is known. */
  url?: string
  provider?: string
  kind?: string
}

export type GraphEdge = {
  source: string
  target: string
  label: string
}

export type GraphVisualizationResponse = {
  knowledge_point: string
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export type KnowledgeBaseArticle = {
  id: string
  title: string
  subject: string
  level: string
  summary: string
  concepts: string[]
  syntax: string[]
  examples: string[]
  mistakes: string[]
  applications: string[]
  checks: string[]
  external_resources: Array<{
    title: string
    provider: string
    url: string
    kind: string
    license: string
    notes: string
  }>
}

export type ManagedResourceItem = {
  id: number
  title: string
  /**
   * Known kinds are listed in `ResourceType`. Typed as `string` because rows
   * written before a kind existed must still load; render unknown kinds with a
   * fallback label rather than failing the whole list.
   */
  type: ResourceType | string
  format: string
  status: 'draft' | 'ready' | 'archived'
  knowledge_point: string
  owner_user_id?: number | null
  source_type: 'generated' | 'external_import'
  provider?: string | null
  source_kind?: string | null
  external_url?: string | null
  download_url?: string | null
  notes?: string | null
  file_name?: string | null
  is_downloadable: boolean
  generation_status?: 'queued' | 'generating' | 'generated' | 'failed'
  audit_status?: 'pending' | 'passed' | 'rejected' | 'unavailable'
  publish_status?: 'draft' | 'published' | 'archived'
  audit_reason?: string
  /**
   * Only the single-resource detail endpoint returns these three fields; the
   * list endpoint leaves them undefined so browsing stays light.
   */
  version?: string | null
  teaching_json?: string | null
  content?: string | null
  structured?: StructuredResourcePayload | null
  content_validation?: ContentValidationReport | null
}

/**
 * Typed payload persisted for `mind_map` / `code_case` / `video_script`.
 *
 * Every field is optional because the shape is produced by a language model and
 * is rendered defensively: a missing section shows its own empty state instead
 * of an empty panel.
 */
export type StructuredResourcePayload = {
  title?: string
  knowledge_point?: string
  // mind_map
  root_id?: string
  nodes?: Array<{
    id?: string
    label?: string
    parent_id?: string | null
    level?: number
    detail?: string
  }>
  edges?: Array<{ source?: string; target?: string; label?: string }>
  mermaid_source?: string
  // code_case
  language?: string
  objective?: string
  prerequisites?: string[]
  example_code?: string
  code_explanation?: string[]
  expected_output?: string
  run_steps?: string[]
  common_errors?: string[]
  extension_exercises?: string[]
  // video_script
  target_audience?: string
  total_duration_seconds?: number
  chapters?: Array<{
    chapter_id?: string
    title?: string
    narration?: string
    visual?: string
    on_screen_text?: string
    duration_seconds?: number
  }>
  production_notes?: string[]
}

export type ContentValidationCheck = {
  check_id: string
  stage: 'structure' | 'source' | string
  status: 'passed' | 'failed' | 'skipped' | string
  passed: boolean
  detail: string
}

/** Mirrors `content_validation.ValidationReport.as_dict()`. */
export type ContentValidationReport = {
  resource_type?: string
  verdict?: 'valid' | 'needs_revision' | 'insufficient_evidence' | 'unsupported'
  structure_passed?: boolean
  source_passed?: boolean
  source_coverage?: number
  citations?: Array<Record<string, unknown>>
  checks?: ContentValidationCheck[]
  notes?: string[]
}

export type ResourceRecommendationItem = ManagedResourceItem & {
  recommendation_score: number
  recommendation_reason: string
  recommendation_strategy: 'hybrid_collaborative' | 'personalized_heuristic' | 'cold_start_popularity'
  collaborative_score: number
  user_cf_score: number
  item_cf_score: number
  view_count: number
  download_count: number
}

export type ResourceInteractionSummary = {
  resource_id: number
  recorded: boolean
  view_count: number
  download_count: number
}

export type ExternalResourceImportPayload = {
  title: string
  provider: string
  url: string
  kind: string
  license: string
  notes: string
  knowledge_point: string
  owner_user_id?: number | null
}

export type KnowledgeBaseListResponse = {
  subjects: string[]
  items: KnowledgeBaseArticle[]
}

export type KnowledgeSubjectOption = {
  value: string
  label: string
  resource_count: number
}

export type KnowledgeSubjectCatalogResponse = {
  total: number
  subjects: KnowledgeSubjectOption[]
}

export type KnowledgeBaseSearchResponse = {
  query: string
  items: KnowledgeBaseArticle[]
}

export type ApiEnvelope<T> = {
  code: number
  data: T
  message: string
}

export type TranscriptRow = {
  student_no: string
  student_name: string
  class_name: string
  subject: string
  score: number | null
  max_score: number
  exam_date?: string | null
  chapter: string
  question_scores: Record<string, number>
  confidence: Record<string, number>
  raw: Record<string, unknown>
}

export type TranscriptParseResponse = {
  import_id?: number | null
  file_name: string
  file_type: string
  headers: string[]
  rows: TranscriptRow[]
  field_mapping: Record<string, string | null>
  warnings: string[]
  quality_score: number
  ocr_mode: boolean
  low_confidence_cells: Array<{ row: number; column: string; confidence: number }>
}

export type TranscriptAnalysis = {
  analysis_id: number
  import_id: number
  status: string
  cache_hit: boolean
  scope: 'student' | 'class'
  data_quality: 'sufficient' | 'limited' | string
  report_text: string
  orchestration: { dispatcher: string; serial_agents: string[]; parallel_agents: string[]; fallback: string }
  score_statistics: { record_count: number; overall_average: number; subject_statistics: Record<string, { average: number; highest: number; lowest: number; pass_rate: number; excellent_rate: number; standard_deviation: number; score_bands: Record<string, number> }>; students: Array<{ student_name: string; student_no: string; total_score: number; average_score: number; rank: number; rank_band: string }> }
  student_profile: { learning_style: string; strong_subjects: string[]; weak_subjects: string[]; loss_reason_distribution: Record<string, number>; evidence: string }
  weakness_diagnosis: { granularity: string; confidence_note: string; weak_points: Array<{ knowledge_point: string; chapter: string; mastery: number; loss_contribution: number; priority: number; importance_tag: string; confidence: number }> }
  resource_recommendations: { resources: Array<{ name: string; knowledge_point: string; resource_type: string; difficulty: string; minutes: number; source: string }>; seven_day_plan: Array<{ day: number; focus: string; goal: string; minutes: number }> }
  exercise_recommendations: { distribution: Record<string, number>; source: string; items: Array<{ tier: string; question: string; answer: string; analysis: string; knowledge_point: string; minutes: number }> }
  report: { title: string; summary: string; strengths: string[]; weaknesses: string[]; next_actions: string[]; quality_note: string }
  student_reports?: TranscriptAnalysis[]
}

export type TranscriptHistoryItem = { id: number; import_id: number; file_name: string; scope: string; status: string; data_quality: string; created_at: string; summary: string }

export type TeacherClassItem = {
  invite_code?: string | null
  status: string
  assignment_count: number
  id: number
  name: string
  subject: string
  teacher_name: string
  course_id?: number | null
  student_count: number
  join_mode: 'invite' | 'open'
  description: string
  objective: string
  syllabus: string
  semester: string
  is_public: boolean
  capacity: number
}

export type TeacherClassCreatePayload = {
  name: string
  subject: string
  teacher_name: string
  join_mode?: 'invite' | 'open'
  description?: string
  objective?: string
  syllabus?: string
  semester?: string
  is_public?: boolean
  capacity?: number
}

export type PlazaClassItem = {
  invite_matched?: boolean
  id: number
  name: string
  subject: string
  teacher_name: string
  course_title: string
  course_description: string
  description: string
  objective: string
  syllabus: string
  semester: string
  student_count: number
  capacity: number
  is_public: boolean
  status: string
  join_mode: 'invite' | 'open'
  joined: boolean
  open_task_count: number
  latest_scope_title: string
}

export type ClassSessionItem = {
  id: number
  class_id: number
  class_name: string
  teacher_name: string
  topic: string
  weekday: number
  start_time: string
  end_time: string
  week_start: string
  week_end: string
  location: string
  mode: 'offline' | 'online'
  status: string
  created_at: string
}

export type ClassSessionPayload = {
  topic: string
  weekday: number
  start_time: string
  end_time: string
  week_start: string
  week_end: string
  location: string
  mode: 'offline' | 'online'
}

export type ScheduleExceptionItem = {
  id: number
  session_id: number
  class_id: number
  class_name: string
  date: string
  kind: 'cancel' | 'reschedule' | 'makeup'
  new_date: string | null
  new_start_time: string | null
  new_end_time: string | null
  location: string | null
  reason: string
  created_at: string
}

export type TeacherSchedule = {
  class_id: number
  class_name: string
  sessions: ClassSessionItem[]
  exceptions: ScheduleExceptionItem[]
}

export type StudentScheduleEntry = {
  date: string
  weekday: number
  start_time: string
  end_time: string
  topic: string
  location: string
  mode: 'offline' | 'online'
  class_id: number
  class_name: string
  teacher_name: string
  status: string
  session_id: number
  personal_id?: number | null
  source?: 'classroom' | 'personal'
  source_date?: string | null
}

export type PersonalSchedule = ClassSessionPayload & {
  id?: number
  class_id: number | null
  source_session_id: number | null
  source_date: string | null
  hidden: boolean
}

export type StudentSchedule = {
  week_start: string
  week_end: string
  today: string
  entries: StudentScheduleEntry[]
  classrooms: { class_id: number; class_name: string; teacher_name: string; scheduled: boolean }[]
  personal: PersonalSchedule[]
}

export type HomeworkAssignPayload = {
  class_id: number
  title: string
  description: string
  due_at?: string | null
}

export type HomeworkFileItem = {
  id: number
  file_name: string
  content_type: string
  size_bytes: number
  is_pending?: boolean
}

export type AssignmentItem = HomeworkAssignPayload & {
  target_student_id?: number | null
  practice_questions?: ReinforcementQuestion[]
  class_name: string
  student_count: number
  pending_count: number
  reviewed_count: number
  my_submission?: AssignmentSubmissionItem | null
  pending_attachments?: HomeworkFileItem[]
  id: number
  status: string
  created_at: string
  submission_count: number
}

export type ReinforcementQuestion = {
  knowledge_point: string
  question_type: 'choice' | 'short_answer'
  prompt: string
  options: string[]
  answer?: string
  analysis?: string
  evidence_ids?: number[]
}

export type CourseResourceDelivery = {
  id: number
  class_id: number
  student_user_id: number | null
  title: string
  content: string
  knowledge_points: string[]
  resource_id: number | null
  created_at: string
}

export type AssignmentSubmissionItem = {
  practice_result?: ReinforcementAttempt | null
  attachments?: HomeworkFileItem[]
  history?: { attachments?: HomeworkFileItem[]; content: string; status: string; score: number | null; teacher_comment: string; recorded_at: string }[]
  id: number
  assignment_id: number
  student_user_id: number
  student_name: string
  content: string
  attachment_url?: string | null
  status: string
  submitted_at: string
  score?: number | null
  teacher_comment: string
  reviewed_at?: string | null
}

export type ReinforcementAttempt = {
  id: number
  draft_id: number
  submission_id: number
  student_user_id: number
  status: string
  analysis: string
  recommendations: string[]
  model_name: string
  error: string
  results: { question_index: number; knowledge_point: string; prompt: string; student_answer: string; reference_answer: string; analysis: string; is_correct: boolean | null; score: number | null; status: string; comment?: string }[]
}

export type DiscussionReplyItem = {
  id: number
  author_user_id: number
  author_name: string
  content: string
  created_at: string
}

export type DiscussionItem = {
  id: number
  class_id?: number | null
  author_user_id: number
  author_name: string
  title: string
  content: string
  status: string
  created_at: string
  replies: DiscussionReplyItem[]
}

export type LearningNotificationItem = {
  id: number
  title: string
  content: string
  type: string
  related_type: string
  related_id?: number | null
  is_read: boolean
  created_at: string
}

export type HomeworkReviewPayload = {
  score: number
  comment: string
}

export type TeachingScopeCreatePayload = {
  class_id: number
  student_user_id?: number | null
  knowledge_points: string[]
  learning_direction: string
  courseware_title: string
  courseware_content: string
  teaching_goal: string
}

export type TeachingScopeItem = TeachingScopeCreatePayload & {
  id: number
}

export type KnowledgePointMistakeStat = {
  knowledge_point: string
  mistake_count: number
  affected_students: number
  suggested_direction: string
}

export type TeacherTeachingAnalytics = {
  homework_submissions: number
  homework_reviewed: number
  homework_average_score: number | null
  class_id: number
  student_count: number
  answered_students: number
  total_answers: number
  correct_rate: number | null
  total_mistakes: number
  weak_knowledge_points: KnowledgePointMistakeStat[]
  teaching_suggestions: string[]
}

export type StudentInsight = {
  user_id: number
  student_name: string
  mastery: number | null
  recent_focus: string
  mistake_count: number
  report_summary: string
}

export type TeacherMistakeNotebookItem = {
  exercise_id: number
  knowledge_point: string
  question_type: string
  user_answer: string
  correct_answer: string
  analysis: string
  suggested_action: string
}

export type TeacherReportDetail = {
  report_type: string
  user_id: number
  title: string
  summary: string
  strengths: string[]
  weaknesses: string[]
  next_actions: string[]
}

export type StudentLearningDetail = {
  user_id: number
  student_name: string
  mastery: number | null
  recent_focus: string
  mistake_count: number
  report_summary: string
  mistake_notebook: TeacherMistakeNotebookItem[]
  stage_report: TeacherReportDetail
  comprehensive_report: TeacherReportDetail
}

export type SubjectItem = {
  id: number
  name: string
  description: string
}

export type SubjectCreatePayload = {
  name: string
  description: string
}

export type SystemConfigItem = {
  key: string
  value: string
}

/** P1-07 prompt-template management. */
export type PromptTemplateSummary = {
  name: string
  chars: number
  placeholders: string[]
}

export type PromptTemplateDetail = PromptTemplateSummary & {
  content: string
}

/** P1-07 image-provider capability status (explicit BLOCKED entry). */
export type ImageProviderStatus = {
  configured: boolean
  enabled: boolean
  provider: string
  model: string
  status: 'configured' | 'blocked' | 'invalid' | 'disabled'
  health: 'unknown' | 'ok' | 'unavailable'
  reason: string
}

export type PromptVersionSummary = {
  version: string
  chars: number
  placeholders: string[]
}

export type ResourceSection = {
  title: string
  chars: number
}

export type ResourceIllustration = {
  id: string
  section_title: string
  model: string
  prompt: string
  status: 'pending' | 'approved' | 'rejected'
  storage_path: string
  version: string
}

export type IllustrateResult = {
  resource_id: number
  section_title: string
  status: 'generated' | 'blocked' | 'failed'
  reason?: string
  illustration_id?: string
  storage_path?: string
  model?: string
}

export type ResourceRewriteResult = {
  resource_id: number
  title: string | null
  status: 'generated' | 'blocked' | 'failed'
  reason?: string
  provider: string | null
  model: string | null
  rewritten_content: string
}

export type SystemConfigUpdatePayload = {
  value: string
}

export type RoleAssignmentPayload = {
  user_id: number
  role: string
}

export type AuditLogItem = {
  level: string
  event: string
  message: string
}

// ── 平台学习打卡、课堂任务与课堂签到 ──
export type DailyCheckinItem = {
  id: number
  checkin_date: string
  checkin_at: string
  goal: string
  reflection: string
}

export type PlatformCheckinStatus = {
  today: string
  checked_in: boolean
  today_checkin: DailyCheckinItem | null
  current_streak: number
  total_days: number
  week_days: number
  week_goal: number
  month_days: number
}

export type PlatformCalendarDay = {
  date: string
  checked_in: boolean
  goal: string
  reflection: string
}

export type PlatformCheckinCalendar = {
  month: string
  days: PlatformCalendarDay[]
  streak: number
  total_days: number
}

export type CheckinPeriodItem = {
  period_key: string
  due_at: string
  state: string
}

export type CheckinSubmissionItem = {
  id: number
  task_id: number
  task_title: string
  class_name: string
  student_user_id: number
  student_name: string
  period_key: string
  period_due_at: string
  content: string
  attachment_ids: number[]
  status: 'submitted' | 'approved' | 'returned'
  submitted_at: string
  reviewed_at: string | null
  review_comment: string
  score: number | null
  version: number
  late: boolean
  history: Array<Record<string, unknown>>
}

export type CheckinTaskItem = {
  id: number
  class_id: number
  class_name: string
  course_id: number | null
  title: string
  goal: string
  description: string
  frequency: 'once' | 'daily' | 'weekly'
  weekly_days: number[]
  start_at: string
  end_at: string
  due_time: string
  allow_late: boolean
  review_mode: 'auto' | 'manual'
  require_attachment: boolean
  knowledge_points: string[]
  status: 'draft' | 'published' | 'closed' | 'cancelled'
  created_at: string
  published_at: string | null
  closed_at: string | null
  student_count: number
  submitted_count: number
  approved_count: number
  pending_review_count: number
  expected_count: number
  completion_rate: number | null
  today_period: string | null
  my_state: string | null
  can_submit: boolean
  my_submission: CheckinSubmissionItem | null
}

export type CheckinTaskDetail = CheckinTaskItem & {
  teacher_name: string
  periods: CheckinPeriodItem[]
}

export type CheckinTaskCreatePayload = {
  class_id: number
  title: string
  goal?: string
  description?: string
  frequency: 'once' | 'daily' | 'weekly'
  weekly_days: number[]
  start_at: string
  end_at: string
  due_time: string
  allow_late: boolean
  review_mode: 'auto' | 'manual'
  require_attachment: boolean
  knowledge_points: string[]
}

export type CheckinSubmitPayload = {
  content: string
  attachment_ids?: number[]
  period_key?: string | null
}

export type CheckinReviewPayload = {
  verdict: 'approve' | 'return'
  comment?: string
  score?: number | null
}

export type StudentTaskSummary = {
  task_id: number
  title: string
  class_name: string
  task_type: string
  period_key: string | null
  due_at: string | null
  state: string
  can_submit: boolean
}

export type AttendanceRecordBrief = {
  id: number
  status: string
  checked_in_at: string | null
  source: string
  note: string
}

export type AttendanceSessionItem = {
  id: number
  class_id: number
  class_name: string
  title: string
  start_at: string
  end_at: string
  late_after_at: string | null
  status: 'open' | 'closed'
  code: string | null
  token: string | null
  my_record: AttendanceRecordBrief | null
  checked_in_count: number
  late_count: number
  leave_count: number
  absent_count: number
  missing_count: number
  student_count: number
}

export type AttendanceLiveRow = {
  student_user_id: number
  student_name: string
  status: string
  checked_in_at: string | null
  source: string
  note: string
  record_id: number | null
}

export type AttendanceLive = {
  session: AttendanceSessionItem
  rows: AttendanceLiveRow[]
}

export type CheckinHome = {
  today: string
  due_today: number
  completed_today: number
  current_streak: number
  total_days: number
  week_completion_rate: number | null
  week_expected: number
  week_approved: number
  pending_tasks: StudentTaskSummary[]
  upcoming_tasks: StudentTaskSummary[]
  available_attendance: AttendanceSessionItem[]
  latest_feedback: CheckinSubmissionItem[]
  recent_checkins: DailyCheckinItem[]
  today_checked_in: boolean
}

export type CheckinTaskCompletionRow = {
  student_user_id: number
  student_name: string
  state: string
  submitted_at: string | null
  review_comment: string
  score: number | null
  submission_id: number | null
  content: string
  attachment_ids: number[]
  version: number
}

export type CheckinTaskCompletion = {
  task: CheckinTaskItem
  period_key: string
  periods: CheckinPeriodItem[]
  rows: CheckinTaskCompletionRow[]
}

export type ClassCheckinStat = {
  class_id: number
  class_name: string
  student_count: number
  task_completion_rate: number | null
  attendance_rate: number | null
  pending_review: number
  low_participation: number
}

export type TeacherCheckinOverview = {
  class_count: number
  active_task_count: number
  pending_review_count: number
  today_attendance_count: number
  overdue_student_count: number
  classes: ClassCheckinStat[]
  trend: Array<{ date: string; approved: number; submitted: number; attendance: number }>
  recent_tasks: CheckinTaskItem[]
}

export type AdminCheckinOverview = {
  task_count: number
  published_task_count: number
  submission_count: number
  pending_review_count: number
  attendance_session_count: number
  attendance_record_count: number
  self_checkin_count: number
  recent_audits: Array<Record<string, unknown>>
}
