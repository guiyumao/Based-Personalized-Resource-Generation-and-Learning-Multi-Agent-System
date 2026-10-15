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
  score: number
}

export type LearnerHeatmapCell = {
  knowledge_point: string
  mastery: number
}

export type LearnerProfileDashboard = {
  user_id: number
  learning_style: string
  mastery_overview: number
  weekly_focus_minutes: number
  habit_summary: string
  radar_metrics: LearnerRadarMetric[]
  heatmap: LearnerHeatmapCell[]
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
  mastery_overview: number
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

export type ResourcePayload = {
  user_id: number
  knowledge_point: string
  resource_style: 'concise' | 'case' | 'interactive'
  resource_type: 'courseware' | 'exercise' | 'notes' | 'exam'
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
  mastery_score: number
  correct_rate: number
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
  type: 'courseware' | 'exercise' | 'notes' | 'exam'
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
  id: number
  name: string
  subject: string
  teacher_name: string
  course_id?: number | null
  student_count: number
}

export type TeacherClassCreatePayload = {
  name: string
  subject: string
  teacher_name: string
}

export type HomeworkAssignPayload = {
  class_id: number
  title: string
  description: string
  due_at?: string | null
}

export type AssignmentItem = HomeworkAssignPayload & {
  id: number
  status: string
  created_at: string
  submission_count: number
}

export type AssignmentSubmissionItem = {
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
  mastery: number
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
  mastery: number
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
