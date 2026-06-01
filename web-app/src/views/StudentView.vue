<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  CircleCheck,
  Connection,
  Document,
  EditPen,
  Lock,
  MagicStick,
  Promotion,
  School,
  TrendCharts,
} from '@element-plus/icons-vue'
import { DataSet, Network } from 'vis-network/standalone'

import {
  agentApi,
  contentApi,
  evaluationApi,
  qaApi,
  userApi,
  type ApiEnvelope,
  type CoordinationPayload,
  type ExerciseGenerationPayload,
  type ExerciseGenerationResponse,
  type GraphVisualizationResponse,
  type LearnerProfileDashboard,
  type LearningPathPayload,
  type LearningPathResponse,
  type MistakeItem,
  type MistakeNotebook,
  type PersonalizationContext,
  type ProfileChatResponsePayload,
  type PracticeFeedback,
  type PracticeSubmissionPayload,
  type QAMistakeSubmissionPayload,
  type QARequestPayload,
  type QAResponsePayload,
  type RemedialExerciseSet,
  type ReportDetail,
  type ResourcePayload,
  type ResourceResult,
  type ResourceVariant,
  type UserProfileRead,
} from '../api'
import { useAuthStore } from '../stores/auth'

type CoordinationResult = {
  status?: string
  selected_agents?: string[]
  route_reason?: string
  outputs?: Record<string, { queue?: string; message?: string }>
}

type GraphDependency = {
  path?: string[]
}

type GraphResult = {
  knowledge_point?: string
  dependencies?: GraphDependency[]
}

type LocalPracticeRecord = PracticeSubmissionPayload & {
  is_correct: boolean
  score: number
}

type LocalMistakeRecord = MistakeItem & {
  user_id: number
  source: 'practice' | 'qa'
}

type CoursewareBlock =
  | { type: 'paragraph'; lines: string[] }
  | { type: 'unordered'; lines: string[] }
  | { type: 'ordered'; lines: string[] }
  | { type: 'code'; lines: string[]; language: string }

type CoursewareSection = {
  heading: string
  anchor: string
  blocks: CoursewareBlock[]
}

type StoredCoursewareSnapshot = {
  subject: string
  topic: string
  goal: string
  selectedVariantId: string
  generatedAt: number
  resourceResult: ResourceResult
}

type StoredMistakeSnapshot = {
  userId: number
  generatedAt: number
  mistakeNotebook: MistakeNotebook | null
  remedialExerciseSet: RemedialExerciseSet | null
}

type SubmittedExerciseState = {
  exerciseId: number
  userAnswer: string
  correctAnswer: string
  analysis: string
  submittedAt: number
  feedback: PracticeFeedback
}

type EnvelopeLike<T> = T | ApiEnvelope<T>

type GenerationKind = 'courseware' | 'exercises'
type AsyncStatusKey = 'profile' | 'graph' | 'mistakes' | 'remedial' | 'reports' | 'qa' | 'path' | 'coordinate'

type GenerationPhaseStatus = 'idle' | 'running' | 'background' | 'done' | 'fallback' | 'error'
type AsyncPhaseStatus = 'idle' | 'waiting' | 'slow' | 'stalled'

type GenerationProgressState = {
  hint: string
  progress: number
  startedAt: number | null
  elapsedSeconds: number
  status: GenerationPhaseStatus
}

type GenerationStageDefinition = {
  threshold: number
  title: string
  description: string
}

type GenerationProgressStepView = {
  index: number
  title: string
  description: string
  state: 'completed' | 'current' | 'pending'
}

type GenerationProgressView = {
  title: string
  detail: string
  stageIndex: number
  totalStages: number
  elapsedLabel: string
  remainingLabel: string
  statusLabel: string
  steps: GenerationProgressStepView[]
}

type AsyncRequestState = {
  active: boolean
  label: string
  startedAt: number | null
  elapsedSeconds: number
  phase: AsyncPhaseStatus
}

type AsyncStatusView = {
  title: string
  detail: string
  elapsedLabel: string
  tone: 'info' | 'warning' | 'danger'
}

type GlobalGenerationBannerView = {
  label: string
  progress: number
  statusLabel: string
  stageLabel: string
}

const router = useRouter()
const authStore = useAuthStore()
const fallbackAnnouncements = new Set<string>()
const QA_MISTAKE_STORAGE_KEY = 'student-workspace-qa-mistakes'
const COURSEWARE_STORAGE_KEY = 'student-workspace-courseware'
const MISTAKE_NOTEBOOK_STORAGE_KEY = 'student-workspace-mistakes'

const serviceStatus = reactive({
  user: 'checking',
  agent: 'checking',
  evaluation: 'checking',
})

const learner = reactive({
  mastery: 62,
  style: '视觉型',
  habit: '晚间学习',
})

const profileDashboard = ref<LearnerProfileDashboard | null>(null)
const profileRecord = ref<UserProfileRead | null>(null)
const profileChatMessage = ref('')
const profileChatResult = ref<ProfileChatResponsePayload | null>(null)
const profileChatError = ref('')
const coordinationResult = ref<CoordinationResult | null>(null)
const resourceResult = ref<ResourceResult | null>(null)
const graphResult = ref<GraphResult | null>(null)
const graphVisualization = ref<GraphVisualizationResponse | null>(null)
const learningPath = ref<LearningPathResponse | null>(null)
const exerciseSet = ref<ExerciseGenerationResponse | null>(null)
const mistakeNotebook = ref<MistakeNotebook | null>(null)
const remedialExerciseSet = ref<RemedialExerciseSet | null>(null)
const stageReport = ref<ReportDetail | null>(null)
const comprehensiveReport = ref<ReportDetail | null>(null)
const coursewareGenerationError = ref('')
const exerciseGenerationError = ref('')
const lastCoursewareRequest = ref<Record<string, unknown> | null>(null)
const lastCoursewareRawResponse = ref<unknown>(null)
const lastExerciseRequest = ref<Record<string, unknown> | null>(null)
const lastExerciseRawResponse = ref<unknown>(null)
const qaResult = ref<QAResponsePayload | null>(null)
const qaError = ref('')
const lastQaRequest = ref<Record<string, unknown> | null>(null)
const lastQaRawResponse = ref<unknown>(null)
const exerciseDeliveryMode = ref<'remote' | 'fallback' | 'upgrading'>('remote')
const selectedCoursewareVariantId = ref('')
const generationStatus = reactive<Record<GenerationKind, GenerationProgressState>>({
  courseware: {
    hint: '',
    progress: 0,
    startedAt: null,
    elapsedSeconds: 0,
    status: 'idle',
  },
  exercises: {
    hint: '',
    progress: 0,
    startedAt: null,
    elapsedSeconds: 0,
    status: 'idle',
  },
})

const asyncRequestStatus = reactive<Record<AsyncStatusKey, AsyncRequestState>>({
  profile: { active: false, label: '', startedAt: null, elapsedSeconds: 0, phase: 'idle' },
  graph: { active: false, label: '', startedAt: null, elapsedSeconds: 0, phase: 'idle' },
  mistakes: { active: false, label: '', startedAt: null, elapsedSeconds: 0, phase: 'idle' },
  remedial: { active: false, label: '', startedAt: null, elapsedSeconds: 0, phase: 'idle' },
  reports: { active: false, label: '', startedAt: null, elapsedSeconds: 0, phase: 'idle' },
  qa: { active: false, label: '', startedAt: null, elapsedSeconds: 0, phase: 'idle' },
  path: { active: false, label: '', startedAt: null, elapsedSeconds: 0, phase: 'idle' },
  coordinate: { active: false, label: '', startedAt: null, elapsedSeconds: 0, phase: 'idle' },
})

const activeTaskId = ref('')
const currentExerciseIndex = ref(0)
const localPracticeRecords = ref<LocalPracticeRecord[]>([])
const localQaMistakeRecords = ref<LocalMistakeRecord[]>(readStoredQaMistakeRecords())

const exerciseDrafts = reactive<Record<number, string>>({})
const submittedExercises = reactive<Record<number, SubmittedExerciseState>>({})

const loading = reactive({
  coordinate: false,
  courseware: false,
  graph: false,
  path: false,
  profileChat: false,
  exercises: false,
  mistakes: false,
  remedial: false,
  reports: false,
  submit: false,
  qa: false,
})

const answerStartAt = ref<number | null>(null)
const graphCanvas = ref<HTMLDivElement | null>(null)
const exerciseResultAnchor = ref<HTMLElement | null>(null)
const qaResultAnchor = ref<HTMLElement | null>(null)
let graphNetwork: Network | null = null
let autoAdvanceExerciseTimer: ReturnType<typeof setTimeout> | null = null
const generationProgressTimers: Partial<Record<GenerationKind, ReturnType<typeof setInterval>>> = {}
const asyncStatusTimers: Partial<Record<AsyncStatusKey, ReturnType<typeof setInterval>>> = {}
let coursewareRequestVersion = 0
let exerciseRequestVersion = 0

const DEFAULT_SUBJECT = ''
const DEFAULT_TOPIC = ''
const DEFAULT_GRADE = ''
const DEFAULT_QA_PROMPT = ''

const learningRequestForm = reactive({
  subject: DEFAULT_SUBJECT,
  topic: DEFAULT_TOPIC,
  goal: '',
})

const coordinationForm = reactive<CoordinationPayload>({
  user_id: authStore.user?.userId ?? 1,
  intent: '',
  knowledge_point: DEFAULT_TOPIC,
  payload: {
    subject: DEFAULT_SUBJECT,
    grade: DEFAULT_GRADE,
  },
})

const resourceForm = reactive<ResourcePayload>({
  user_id: authStore.user?.userId ?? 1,
  knowledge_point: DEFAULT_TOPIC,
  resource_style: 'interactive',
  resource_type: 'courseware',
  request_text: '',
  learner_profile: {
    learning_style: 'visual',
    mastery: 62,
    habits: ['晚间学习', '偏好案例'],
  },
})

const pathForm = reactive<LearningPathPayload>({
  user_id: authStore.user?.userId ?? 1,
  subject: DEFAULT_SUBJECT,
  knowledge_point: DEFAULT_TOPIC,
  daily_minutes: 45,
  learner_profile: {
    learning_style: 'visual',
    mastery: 62,
  },
})

const exerciseForm = reactive<ExerciseGenerationPayload>({
  user_id: authStore.user?.userId ?? 1,
  knowledge_point: DEFAULT_TOPIC,
  resource_style: 'interactive',
  learner_profile: {
    learning_style: 'visual',
    mastery: 62,
  },
  exercise_count: 5,
  generation_mode: 'self_test',
  courseware_content: '',
})

const qaForm = reactive<QARequestPayload>({
  student_id: String(authStore.user?.userId ?? 1),
  subject: DEFAULT_SUBJECT,
  grade: DEFAULT_GRADE,
  question: DEFAULT_QA_PROMPT,
  student_answer: '',
  wrong_answer: '',
  current_knowledge_points: [],
  learning_route: {},
  error_book: {},
  learning_history: {},
})

const systemCards = computed(() => [
  {
    title: '学习路径',
    subtitle: '阶段任务',
    value: learningPath.value ? `${learningPath.value.estimated_days} 天计划` : '待生成',
    icon: Promotion,
  },
  {
    title: '学习课件',
    subtitle: '可直接阅读',
    value: resourceResult.value ? '已生成' : '待生成',
    icon: Document,
  },
  {
    title: '在线练习',
    subtitle: '分层题组',
    value: exerciseSet.value ? `${exerciseSet.value.exercises.length} 题` : '待生成',
    icon: EditPen,
  },
  {
    title: '掌握度',
    subtitle: '实时画像',
    value: `${learner.mastery}%`,
    icon: TrendCharts,
  },
])

const allTasks = computed(() => learningPath.value?.stages.flatMap((stage) => stage.tasks) ?? [])

const activeTask = computed(() => {
  if (!activeTaskId.value) {
    return allTasks.value[0] ?? null
  }
  return allTasks.value.find((task) => task.task_id === activeTaskId.value) ?? null
})

const completionStats = computed(() => {
  const tasks = allTasks.value
  return {
    total: tasks.length,
    completed: tasks.filter((task) => task.completed).length,
  }
})

const currentExercise = computed(() => exerciseSet.value?.exercises[currentExerciseIndex.value] ?? null)

const currentSubmission = computed(() => {
  const exerciseId = currentExercise.value?.exercise_id
  if (!exerciseId) {
    return null
  }
  return submittedExercises[exerciseId] ?? null
})

const currentAnswerDraft = computed({
  get: () => {
    const exerciseId = currentExercise.value?.exercise_id
    if (!exerciseId) {
      return ''
    }
    return currentSubmission.value?.userAnswer ?? exerciseDrafts[exerciseId] ?? ''
  },
  set: (value: string) => {
    const exerciseId = currentExercise.value?.exercise_id
    if (!exerciseId || currentSubmission.value) {
      return
    }
    exerciseDrafts[exerciseId] = value
  },
})

const answeredCount = computed(() => Object.keys(submittedExercises).length)
const hasMistakes = computed(() => Boolean(mistakeNotebook.value?.mistake_count))
const remedialCount = computed(() => remedialExerciseSet.value?.exercises.length ?? 0)
const sidebarOverviewMetrics = computed(() => {
  const totalTasks = completionStats.value.total
  const totalExercises = exerciseSet.value?.exercises.length ?? 0
  const completedRatio = totalTasks ? Math.round((completionStats.value.completed / totalTasks) * 100) : 0
  const activeDifficulty = activeTask.value ? difficultyLabelMap[activeTask.value.difficulty] ?? activeTask.value.difficulty : ''
  const activeProgress =
    totalExercises && currentExercise.value
      ? `当前第 ${Math.min(currentExerciseIndex.value + 1, totalExercises)}/${totalExercises} 题`
      : '练习生成后显示'

  return [
    {
      label: '当前任务',
      value: activeTask.value?.knowledge_point ?? '待选择',
      hint: activeTask.value ? `${activeTask.value.title} · ${activeDifficulty}` : '从左侧任务列表选择任务',
    },
    {
      label: '任务完成',
      value: totalTasks ? `${completionStats.value.completed}/${totalTasks}` : '待开始',
      hint: totalTasks ? `当前完成率 ${completedRatio}%` : '学习路径生成后显示',
    },
    {
      label: '答题进度',
      value: totalExercises ? `${answeredCount.value}/${totalExercises}` : '未生成',
      hint: activeProgress,
    },
    {
      label: '错题 / 重练',
      value: `${mistakeNotebook.value?.mistake_count ?? 0} / ${remedialCount.value}`,
      hint: remedialCount.value ? '左侧可直接进入变式重练' : hasMistakes.value ? '当前暂无待重练题目' : '继续保持当前节奏',
    },
  ]
})
const sidebarGenerationItems = computed(() => {
  const items: Array<{ label: string; progress: number; status: string; detail: string }> = []

  if (generationStatus.courseware.status !== 'idle' || resourceResult.value) {
    items.push({
      label: '学习课件',
      progress:
        resourceResult.value && generationStatus.courseware.status === 'idle'
          ? 100
          : generationStatus.courseware.progress,
      status:
        resourceResult.value && generationStatus.courseware.status === 'idle'
          ? '已完成'
          : coursewareProgressView.value.statusLabel,
      detail:
        resourceResult.value && generationStatus.courseware.status === 'idle'
          ? coursewareTitle.value
          : coursewareProgressView.value.title,
    })
  }

  if (generationStatus.exercises.status !== 'idle' || exerciseSet.value) {
    items.push({
      label: '练习题组',
      progress:
        exerciseSet.value && generationStatus.exercises.status === 'idle'
          ? 100
          : generationStatus.exercises.progress,
      status:
        exerciseSet.value && generationStatus.exercises.status === 'idle'
          ? '已完成'
          : exerciseProgressView.value.statusLabel,
      detail:
        exerciseSet.value && generationStatus.exercises.status === 'idle'
          ? `${exerciseSet.value.exercises.length} 道练习已返回`
          : exerciseProgressView.value.title,
    })
  }

  return items
})
const sidebarActionItems = computed(() => {
  const items: string[] = []

  if (stageReport.value?.evidence.weakest_knowledge_point) {
    const accuracy = stageReport.value.evidence.weakest_knowledge_accuracy
    items.push(
      `优先补强 ${stageReport.value.evidence.weakest_knowledge_point}${accuracy !== null ? `，当前正确率 ${accuracy}%` : ''}。`,
    )
  }

  if (stageReport.value?.next_actions.length) {
    items.push(...stageReport.value.next_actions.slice(0, 2))
  }

  if (comprehensiveReport.value?.evidence.weakest_question_types.length) {
    items.push(`重点训练题型：${comprehensiveReport.value.evidence.weakest_question_types.slice(0, 2).join('、')}`)
  }

  if (!items.length) {
    items.push(activeTask.value ? `先完成“${activeTask.value.title}”这一项任务。` : '先在左侧选择任务并开始生成课件。')
  }

  return items.slice(0, 4)
})
const dependencyPaths = computed(() => {
  const dependencies = graphResult.value?.dependencies ?? []
  return dependencies.map((item) => item.path ?? []).filter((path) => path.length > 0)
})
const radarMetrics = computed(() => profileDashboard.value?.radar_metrics ?? [])
const heatmapMetrics = computed(() => profileDashboard.value?.heatmap ?? [])
const profileDimensionEntries = computed(() => Object.entries(profileRecord.value?.profile_dimensions ?? {}))
const qaRecommendations = computed(() => qaResult.value?.structured_analysis.resource_recommendations ?? [])
const qaRouteUpdates = computed(() => qaResult.value?.structured_analysis.learning_route_updates ?? [])
const qaKnowledgeGaps = computed(() => qaResult.value?.structured_analysis.identified_knowledge_gaps ?? [])
const qaMisconceptions = computed(() => qaResult.value?.structured_analysis.misconceptions ?? [])
const qaStudySuggestions = computed(() => qaResult.value?.structured_analysis.study_suggestions ?? [])
const showQaLearningAnalysis = computed(() => {
  const analysis = qaResult.value?.structured_analysis
  if (!analysis) {
    return false
  }

  return Boolean(
    qaKnowledgeGaps.value.length ||
      qaMisconceptions.value.length ||
      qaRouteUpdates.value.length ||
      qaRecommendations.value.length ||
      qaStudySuggestions.value.length ||
      analysis.recommended_next_knowledge_points.length ||
      analysis.mistake_book_update.should_add,
  )
})
const coursewareVariants = computed<ResourceVariant[]>(() => resourceResult.value?.variants ?? [])
const activeCoursewareVariant = computed<ResourceVariant | null>(() => {
  const variants = coursewareVariants.value
  if (!variants.length) {
    return null
  }
  return (
    variants.find((item) => item.variant_id === selectedCoursewareVariantId.value) ??
    variants.find((item) => item.is_recommended) ??
    variants[0]
  )
})

const coursewareTitle = computed(() => {
  const raw = activeCoursewareVariant.value?.content?.trim() ?? resourceResult.value?.content?.trim()
  const firstLine = raw?.split(/\r?\n/)[0] ?? ''
  return firstLine.startsWith('# ') ? firstLine.replace(/^#\s+/, '') : '学习课件'
})

const resourceSections = computed<CoursewareSection[]>(() => {
  const content = activeCoursewareVariant.value?.content?.trim() ?? resourceResult.value?.content?.trim()
  if (!content) {
    return []
  }

  const normalized = content.replace(/\r\n/g, '\n')
  const titleRemoved = normalized.replace(/^# .+\n?/, '').trim()
  const chunks = titleRemoved.split(/\n##\s+/).filter(Boolean)

  return chunks.map((chunk, index) => {
    const lines = chunk.trim().split('\n')
    const firstLine = lines.shift() ?? `章节 ${index + 1}`
    return {
      heading: firstLine.trim(),
      anchor: `courseware-section-${index + 1}`,
      blocks: parseMarkdownBlocks(lines.join('\n').trim()),
    }
  })
})

const coursewareOutline = computed(() => resourceSections.value.map((section) => section.heading))
const coursewarePersonalization = computed(() => resourceResult.value?.personalization ?? null)
const exercisePersonalization = computed(() => exerciseSet.value?.personalization ?? null)
const coursewareProgressView = computed(() => buildGenerationProgressView('courseware'))
const exerciseProgressView = computed(() => buildGenerationProgressView('exercises'))
const globalGenerationBannerView = computed<GlobalGenerationBannerView | null>(() => {
  if (generationStatus.courseware.hint && generationStatus.courseware.status !== 'idle') {
    return {
      label: '学习课件',
      progress: generationStatus.courseware.progress,
      statusLabel: coursewareProgressView.value.statusLabel,
      stageLabel: coursewareProgressView.value.title,
    }
  }

  if (generationStatus.exercises.hint && generationStatus.exercises.status !== 'idle') {
    return {
      label: '练习题',
      progress: generationStatus.exercises.progress,
      statusLabel: exerciseProgressView.value.statusLabel,
      stageLabel: exerciseProgressView.value.title,
    }
  }

  return null
})
const pathStatusView = computed(() => buildAsyncStatusView('path'))
const coordinationStatusView = computed(() => buildAsyncStatusView('coordinate'))
const profileStatusView = computed(() => buildAsyncStatusView('profile'))
const graphStatusView = computed(() => buildAsyncStatusView('graph'))
const mistakeStatusView = computed(() => buildAsyncStatusView(asyncRequestStatus.remedial.active ? 'remedial' : asyncRequestStatus.mistakes.active ? 'mistakes' : null))
const reportStatusView = computed(() => buildAsyncStatusView('reports'))
const qaStatusView = computed(() => buildAsyncStatusView('qa'))
const globalStatusView = computed(() => {
  return (
    buildGenerationStatusView('courseware', '学习课件') ??
    buildGenerationStatusView('exercises', '练习题') ??
    pathStatusView.value ??
    coordinationStatusView.value ??
    profileStatusView.value ??
    graphStatusView.value ??
    mistakeStatusView.value ??
    qaStatusView.value ??
    reportStatusView.value
  )
})

const questionTypeLabelMap: Record<string, string> = {
  choice: '选择题',
  blank: '填空题',
  judge: '判断题',
  short_answer: '简答题',
  programming: '编程题',
}

const difficultyLabelMap: Record<string, string> = {
  foundation: '基础',
  intermediate: '进阶',
  advanced: '拓展',
}

const generationStageDefinitions: Record<GenerationKind, GenerationStageDefinition[]> = {
  courseware: [
    {
      threshold: 0,
      title: '读取学习任务',
      description: '正在确认当前知识点、课件风格和学习目标。',
    },
    {
      threshold: 20,
      title: '整理个性化依据',
      description: '正在汇总掌握度、错题记录和学习偏好。',
    },
    {
      threshold: 52,
      title: '生成讲解内容',
      description: '正在组织导入、知识讲解、示例和课堂小结。',
    },
    {
      threshold: 80,
      title: '整理章节返回',
      description: '正在组装课件结构并返回给页面。',
    },
  ],
  exercises: [
    {
      threshold: 0,
      title: '读取课件上下文',
      description: '正在提取当前课件重点和目标知识点。',
    },
    {
      threshold: 20,
      title: '整理薄弱点',
      description: '正在汇总掌握度、错题记录和弱项题型。',
    },
    {
      threshold: 52,
      title: '生成题目与解析',
      description: '正在生成题干、答案和详细解析。',
    },
    {
      threshold: 80,
      title: '组装题组返回',
      description: '正在整理题组顺序并返回给页面。',
    },
  ],
}

function unwrapApiData<T>(payload: EnvelopeLike<T>): T {
  if (
    payload &&
    typeof payload === 'object' &&
    'data' in payload &&
    'code' in payload
  ) {
    return payload.data as T
  }
  return payload as T
}

async function postWithTimeout<T>(
  url: string,
  payload: unknown,
  timeoutMs: number,
): Promise<{ data: T }> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    return await agentApi.post<T>(url, payload, {
      signal: controller.signal,
      timeout: timeoutMs,
    })
  } finally {
    clearTimeout(timer)
  }
}

async function postContentWithTimeout<T>(
  url: string,
  payload: unknown,
  timeoutMs: number,
): Promise<{ data: T }> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    return await contentApi.post<T>(url, payload, {
      signal: controller.signal,
      timeout: timeoutMs,
    })
  } finally {
    clearTimeout(timer)
  }
}

function normalizeResourceResult(payload: EnvelopeLike<ResourceResult> | null | undefined): ResourceResult | null {
  if (!payload) {
    return null
  }
  const result = unwrapApiData(payload)
  if (!result || typeof result !== 'object') {
    return null
  }
  const content = 'content' in result ? result.content : undefined
  if (typeof content !== 'string' || !content.trim()) {
    return null
  }
  return result
}

function normalizeExerciseResponse(
  payload: EnvelopeLike<ExerciseGenerationResponse> | null | undefined,
): ExerciseGenerationResponse | null {
  if (!payload) {
    return null
  }
  const result = unwrapApiData(payload)
  if (!result || typeof result !== 'object' || !('exercises' in result) || !Array.isArray(result.exercises)) {
    return null
  }
  if (result.exercises.length === 0) {
    return null
  }
  return result
}

function parseMarkdownBlocks(body: string): CoursewareBlock[] {
  if (!body) {
    return []
  }

  const blocks: CoursewareBlock[] = []
  const lines = body.split('\n')
  let index = 0

  while (index < lines.length) {
    const line = lines[index].trimEnd()
    const trimmed = line.trim()

    if (!trimmed) {
      index += 1
      continue
    }

    if (trimmed.startsWith('```')) {
      const language = trimmed.slice(3).trim()
      const codeLines: string[] = []
      index += 1
      while (index < lines.length && !lines[index].trim().startsWith('```')) {
        codeLines.push(lines[index])
        index += 1
      }
      if (index < lines.length) {
        index += 1
      }
      blocks.push({
        type: 'code',
        lines: codeLines,
        language,
      })
      continue
    }

    if (/^-\s+/.test(trimmed)) {
      const listLines: string[] = []
      while (index < lines.length && /^-\s+/.test(lines[index].trim())) {
        listLines.push(lines[index].trim().replace(/^-\s+/, ''))
        index += 1
      }
      blocks.push({
        type: 'unordered',
        lines: listLines,
      })
      continue
    }

    if (/^\d+\.\s+/.test(trimmed)) {
      const listLines: string[] = []
      while (index < lines.length && /^\d+\.\s+/.test(lines[index].trim())) {
        listLines.push(lines[index].trim().replace(/^\d+\.\s+/, ''))
        index += 1
      }
      blocks.push({
        type: 'ordered',
        lines: listLines,
      })
      continue
    }

    const paragraphLines: string[] = []
    while (index < lines.length) {
      const current = lines[index].trimEnd()
      const currentTrimmed = current.trim()
      if (!currentTrimmed || currentTrimmed.startsWith('```') || /^-\s+/.test(currentTrimmed) || /^\d+\.\s+/.test(currentTrimmed)) {
        break
      }
      paragraphLines.push(currentTrimmed)
      index += 1
    }
    blocks.push({
      type: 'paragraph',
      lines: paragraphLines,
    })
  }

  return blocks
}

function announceFallback(key: string, message: string) {
  if (fallbackAnnouncements.has(key)) {
    return
  }
  fallbackAnnouncements.add(key)
  ElMessage.warning(message)
}

function syncLearnerFromDashboard(dashboard: LearnerProfileDashboard) {
  profileDashboard.value = dashboard
  learner.mastery = dashboard.mastery_overview
  learner.style = dashboard.learning_style
  learner.habit = dashboard.habit_summary
}

function resetExerciseSession() {
  for (const key of Object.keys(exerciseDrafts)) {
    delete exerciseDrafts[Number(key)]
  }
  for (const key of Object.keys(submittedExercises)) {
    delete submittedExercises[Number(key)]
  }
  currentExerciseIndex.value = 0
  answerStartAt.value = Date.now()
}

function rememberSubmission(payload: PracticeSubmissionPayload, feedback: PracticeFeedback) {
  submittedExercises[payload.exercise_id] = {
    exerciseId: payload.exercise_id,
    userAnswer: payload.user_answer,
    correctAnswer: payload.correct_answer,
    analysis: payload.analysis,
    submittedAt: Date.now(),
    feedback,
  }
  exerciseDrafts[payload.exercise_id] = payload.user_answer
}

function buildFallbackLearningPath(): LearningPathResponse {
  const estimatedDays = pathForm.daily_minutes >= 45 ? 3 : 4
  return {
    user_id: pathForm.user_id,
    subject: pathForm.subject,
    knowledge_point: pathForm.knowledge_point,
    overview: `围绕 ${pathForm.knowledge_point} 的 ${estimatedDays} 天学习路径：先学概念，再练习，最后复盘错题。`,
    estimated_days: estimatedDays,
    stages: [
      {
        stage_id: 'fallback-stage-1',
        title: '阶段一：理解概念',
        description: '先把核心定义、语法结构和常见场景学清楚。',
        tasks: [
          {
            task_id: 'fallback-task-1',
            title: `学习 ${pathForm.knowledge_point} 核心概念`,
            task_type: 'courseware',
            knowledge_point: pathForm.knowledge_point,
            objective: '理解定义、语法和易错点。',
            estimated_minutes: 20,
            difficulty: 'foundation',
            completed: false,
          },
          {
            task_id: 'fallback-task-2',
            title: '查看知识依赖关系',
            task_type: 'graph',
            knowledge_point: pathForm.knowledge_point,
            objective: '弄清楚前置知识点和关联能力。',
            estimated_minutes: 10,
            difficulty: 'foundation',
            completed: false,
          },
        ],
      },
      {
        stage_id: 'fallback-stage-2',
        title: '阶段二：做题巩固',
        description: '通过基础题和进阶题把知识点转成可输出能力。',
        tasks: [
          {
            task_id: 'fallback-task-3',
            title: '完成分层练习题',
            task_type: 'exercise',
            knowledge_point: pathForm.knowledge_point,
            objective: '完成结构化题组并查看标准答案和解析。',
            estimated_minutes: 25,
            difficulty: 'intermediate',
            completed: false,
          },
        ],
      },
      {
        stage_id: 'fallback-stage-3',
        title: '阶段三：错题复盘',
        description: '把错误原因讲清楚，再去做变式重练题。',
        tasks: [
          {
            task_id: 'fallback-task-4',
            title: '错题复盘与变式重练',
            task_type: 'review',
            knowledge_point: pathForm.knowledge_point,
            objective: '整理错误原因，完成变式重练题。',
            estimated_minutes: 20,
            difficulty: 'advanced',
            completed: false,
          },
        ],
      },
    ],
  }
}

function buildFallbackProfileDashboard(userId = exerciseForm.user_id): LearnerProfileDashboard {
  const records = localPracticeRecords.value.filter((item) => item.user_id === userId)
  const total = records.length
  const correct = records.filter((item) => item.is_correct).length
  const mastery = total ? Math.round((correct / total) * 100) : learner.mastery
  const mistakeCount = records.filter((item) => !item.is_correct).length
  const averageTime = total ? Math.round(records.reduce((sum, item) => sum + item.time_spent, 0) / total) : 18

  return {
    user_id: userId,
    learning_style: learner.style || '视觉型',
    mastery_overview: mastery,
    weekly_focus_minutes: Math.max(120, total * 18),
    habit_summary: learner.habit || '最近主要在晚间学习，适合先看案例再做题。',
    radar_metrics: [
      { dimension: '知识掌握', score: mastery },
      { dimension: '逻辑分析', score: Math.min(95, Math.max(45, mastery + 4)) },
      { dimension: '作答稳定性', score: Math.min(92, Math.max(40, 85 - mistakeCount * 6)) },
      { dimension: '完成速度', score: Math.min(90, Math.max(35, 88 - averageTime)) },
      { dimension: '复盘反思', score: Math.min(96, Math.max(42, 76 - mistakeCount * 2 + correct * 3)) },
    ],
    heatmap: [
      { knowledge_point: pathForm.knowledge_point, mastery },
      { knowledge_point: '条件判断', mastery: Math.max(35, mastery - 8) },
      { knowledge_point: '列表与字典', mastery: Math.min(94, mastery + 5) },
      { knowledge_point: '函数封装', mastery: Math.max(32, mastery - 6) },
      { knowledge_point: '综合应用', mastery: Math.max(28, mastery - 12) },
    ],
  }
}

function readStoredQaMistakeRecords(): LocalMistakeRecord[] {
  if (typeof window === 'undefined') {
    return []
  }

  try {
    const raw = window.localStorage.getItem(QA_MISTAKE_STORAGE_KEY)
    if (!raw) {
      return []
    }
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) {
      return []
    }
    return parsed.flatMap((item) => normalizeStoredQaMistakeRecord(item))
  } catch {
    return []
  }
}

function normalizeStoredQaMistakeRecord(value: unknown): LocalMistakeRecord[] {
  if (!value || typeof value !== 'object') {
    return []
  }

  const item = value as Record<string, unknown>
  const userId = Number(item.user_id)
  const exerciseId = Number(item.exercise_id)
  const knowledgePoint = typeof item.knowledge_point === 'string' ? item.knowledge_point.trim() : ''
  const questionType = typeof item.question_type === 'string' ? item.question_type.trim() : ''
  const userAnswer = typeof item.user_answer === 'string' ? item.user_answer.trim() : ''
  const correctAnswer = typeof item.correct_answer === 'string' ? item.correct_answer.trim() : ''
  const analysis = typeof item.analysis === 'string' ? item.analysis.trim() : ''
  const suggestedAction = typeof item.suggested_action === 'string' ? item.suggested_action.trim() : ''
  const source = item.source === 'practice' ? 'practice' : 'qa'

  if (
    !Number.isFinite(userId)
    || !Number.isFinite(exerciseId)
    || !knowledgePoint
    || !questionType
    || !analysis
    || !suggestedAction
  ) {
    return []
  }

  return [{
    user_id: userId,
    exercise_id: exerciseId,
    knowledge_point: knowledgePoint,
    question_type: ['choice', 'blank', 'judge', 'short_answer', 'programming'].includes(questionType)
      ? (questionType as LocalMistakeRecord['question_type'])
      : 'short_answer',
    user_answer: userAnswer,
    correct_answer: correctAnswer,
    analysis,
    suggested_action: suggestedAction,
    source,
  }]
}

function persistQaMistakeRecords() {
  if (typeof window === 'undefined') {
    return
  }
  window.localStorage.setItem(QA_MISTAKE_STORAGE_KEY, JSON.stringify(localQaMistakeRecords.value))
}

function createSyntheticMistakeId(seed: string) {
  let hash = 0
  for (let index = 0; index < seed.length; index += 1) {
    hash = (hash * 31 + seed.charCodeAt(index)) >>> 0
  }
  return 900000000 + (hash % 100000000)
}

function buildMistakeItemKey(item: Pick<MistakeItem, 'exercise_id' | 'knowledge_point' | 'question_type' | 'user_answer' | 'correct_answer' | 'analysis'>) {
  return [
    item.exercise_id,
    item.knowledge_point.trim(),
    item.question_type,
    item.user_answer.trim(),
    item.correct_answer.trim(),
    item.analysis.trim(),
  ].join('::')
}

function collectLocalMistakeItems(userId = exerciseForm.user_id): MistakeItem[] {
  const practiceItems: MistakeItem[] = localPracticeRecords.value
    .filter((item) => item.user_id === userId && !item.is_correct)
    .map((item) => ({
      exercise_id: item.exercise_id,
      knowledge_point: item.knowledge_point,
      question_type: item.question_type,
      user_answer: item.user_answer,
      correct_answer: item.correct_answer,
      analysis: item.analysis,
      suggested_action: '先读懂解析，再去做错题变式重练，不再重复提交原题。',
    }))

  const qaItems: MistakeItem[] = localQaMistakeRecords.value
    .filter((item) => item.user_id === userId)
    .map((item) => ({
      exercise_id: item.exercise_id,
      knowledge_point: item.knowledge_point,
      question_type: item.question_type,
      user_answer: item.user_answer,
      correct_answer: item.correct_answer,
      analysis: item.analysis,
      suggested_action: item.suggested_action,
    }))

  const merged: MistakeItem[] = []
  const seen = new Set<string>()
  ;[...practiceItems, ...qaItems].forEach((item) => {
    const key = buildMistakeItemKey(item)
    if (seen.has(key)) {
      return
    }
    seen.add(key)
    merged.push(item)
  })

  return merged
}

function rebuildMistakeNotebook(userId = exerciseForm.user_id): MistakeNotebook {
  const records = collectLocalMistakeItems(userId)
  return {
    user_id: userId,
    mistake_count: records.length,
    items: records,
  }
}

function mergeMistakeNotebook(base: MistakeNotebook | null, userId = exerciseForm.user_id): MistakeNotebook {
  const merged: MistakeItem[] = []
  const seen = new Set<string>()
  const baseItems = base?.user_id === userId ? base.items : []
  const localItems = collectLocalMistakeItems(userId)

  ;[...baseItems, ...localItems].forEach((item) => {
    const key = buildMistakeItemKey(item)
    if (seen.has(key)) {
      return
    }
    seen.add(key)
    merged.push(item)
  })

  return {
    user_id: userId,
    mistake_count: merged.length,
    items: merged,
  }
}

function buildQaMistakeRecord(result: QAResponsePayload, userId = exerciseForm.user_id): LocalMistakeRecord | null {
  const update = result.structured_analysis.mistake_book_update
  if (!update.should_add) {
    return null
  }

  const questionSummary = update.question_summary.trim() || qaForm.question.trim()
  const wrongReason = update.wrong_reason.trim() || qaForm.wrong_answer?.trim() || qaForm.student_answer?.trim() || '未提供具体错误答案'
  const correctApproach = update.correct_approach.trim() || '先复盘这次错误，再用自己的话重新说一遍正确思路。'
  const knowledgePoint = (
    result.structured_analysis.recommended_next_knowledge_points[0]
    || qaForm.current_knowledge_points[0]
    || pathForm.knowledge_point
    || result.subject
    || '问答复盘'
  ).trim()
  const seed = `${userId}::${knowledgePoint}::${questionSummary}::${wrongReason}::${correctApproach}`

  return {
    user_id: userId,
    exercise_id: createSyntheticMistakeId(seed),
    knowledge_point: knowledgePoint || '问答复盘',
    question_type: 'short_answer',
    user_answer: wrongReason,
    correct_answer: correctApproach,
    analysis: `题目摘要：${questionSummary}\n问题分析：${wrongReason}`,
    suggested_action: correctApproach,
    source: 'qa',
  }
}

function syncQaMistakeRecord(result: QAResponsePayload, userId = exerciseForm.user_id) {
  const record = buildQaMistakeRecord(result, userId)
  if (!record) {
    return false
  }

  const existingIndex = localQaMistakeRecords.value.findIndex((item) => item.exercise_id === record.exercise_id)
  if (existingIndex >= 0) {
    const existing = localQaMistakeRecords.value[existingIndex]
    const existingKey = buildMistakeItemKey(existing)
    const nextKey = buildMistakeItemKey(record)
    if (existingKey === nextKey && existing.suggested_action === record.suggested_action) {
      return false
    }
    localQaMistakeRecords.value.splice(existingIndex, 1, record)
  } else {
    localQaMistakeRecords.value.unshift(record)
  }

  persistQaMistakeRecords()
  mistakeNotebook.value = mergeMistakeNotebook(mistakeNotebook.value, userId)
  persistCurrentMistakeSnapshot()
  return true
}

async function syncQaMistakeRecordToEvaluation(result: QAResponsePayload, userId = exerciseForm.user_id) {
  const record = buildQaMistakeRecord(result, userId)
  if (!record) {
    return false
  }

  const update = result.structured_analysis.mistake_book_update
  const payload: QAMistakeSubmissionPayload = {
    user_id: userId,
    exercise_id: record.exercise_id,
    knowledge_point: record.knowledge_point,
    question_type: record.question_type,
    question_summary: update.question_summary.trim() || qaForm.question.trim(),
    wrong_answer: record.user_answer,
    correct_answer: record.correct_answer,
    analysis: record.analysis,
    suggested_action: record.suggested_action,
    time_spent: 0,
  }

  try {
    await evaluationApi.post('/evaluation/mistakes/qa', payload)
    await Promise.all([
      fetchMistakeNotebook(),
      fetchReports(),
      fetchProfileDashboard(userId),
    ])
    return true
  } catch {
    return false
  }
}

function buildFallbackReport(reportType: 'stage' | 'comprehensive', userId = exerciseForm.user_id): ReportDetail {
  const notebook = rebuildMistakeNotebook(userId)
  const dashboard = buildFallbackProfileDashboard(userId)
  const records = localPracticeRecords.value.filter((item) => item.user_id === userId)
  const total = records.length
  const correct = records.filter((item) => item.is_correct).length
  const averageTime = total
    ? Math.round(records.reduce((sum, item) => sum + item.time_spent, 0) / total)
    : 0
  const wrongTypes = Array.from(new Set(records.filter((item) => !item.is_correct).map((item) => item.question_type)))
  const recentWrong = records.filter((item) => !item.is_correct).slice(-1)[0]
  const strongestQuestionTypes = Array.from(new Set(records.filter((item) => item.is_correct).map((item) => item.question_type)))
  const weakestKnowledgePoint = recentWrong?.knowledge_point ?? null

  return {
    report_type: reportType,
    user_id: userId,
    title: reportType === 'stage' ? '阶段学习报告' : '综合学习报告',
    summary:
      reportType === 'stage'
        ? `当前已完成 ${total} 次作答，答对 ${correct} 次，正确率约为 ${dashboard.mastery_overview}%，平均每题耗时 ${averageTime} 秒。`
        : `当前累计错题 ${notebook.mistake_count} 道，综合掌握度约为 ${dashboard.mastery_overview}%。`,
    strengths: [
      total > 0
        ? `已经完成 ${total} 次真实作答，说明学习流程正在稳定推进。`
        : '完成首轮练习后，这里会显示你已经稳定掌握的能力。',
      correct > 0
        ? `当前至少有 ${correct} 题已经答对，说明部分知识点已经开始形成稳定理解。`
        : '先完成几道题后，这里会更准确显示你的当前优势。',
    ],
    weaknesses: [
      wrongTypes.length > 0
        ? `当前失分更集中的题型是：${wrongTypes.join('、')}。`
        : '当前还没有明显薄弱题型，可以继续做更多题观察趋势。',
      recentWrong
        ? `最近一次错题出现在 ${recentWrong.knowledge_point} / ${recentWrong.question_type}，需要重点复盘这类题。`
        : '如果后续出现错题，这里会指出最具体的薄弱点。',
    ],
    next_actions: [
      recentWrong
        ? `先复盘 ${recentWrong.knowledge_point} 的错题解析，再进入变式重练。`
        : '先完成一轮练习，再根据具体错题安排复盘。',
      wrongTypes.length > 0
        ? `下一轮优先补强 ${wrongTypes.slice(0, 2).join('、')} 题型。`
        : '保持“作答 -> 看标准答案 -> 复述解析”的固定节奏。',
    ],
    evidence: {
      total_answers: total,
      correct_answers: correct,
      accuracy: dashboard.mastery_overview,
      average_time_spent: averageTime,
      average_score: total ? Math.round(records.reduce((sum, item) => sum + item.score, 0) / total) : 0,
      mistake_count: notebook.mistake_count,
      strongest_question_types: strongestQuestionTypes,
      weakest_question_types: wrongTypes,
      weakest_knowledge_point: weakestKnowledgePoint,
      weakest_knowledge_accuracy: weakestKnowledgePoint ? Math.max(0, dashboard.mastery_overview - 10) : null,
      latest_mistake: recentWrong
        ? {
            knowledge_point: recentWrong.knowledge_point,
            question_type: recentWrong.question_type,
            user_answer: recentWrong.user_answer,
            correct_answer: recentWrong.correct_answer,
            analysis: recentWrong.analysis,
          }
        : null,
    },
  }
}

function buildFallbackPracticeFeedback(payload: PracticeSubmissionPayload): PracticeFeedback {
  const normalizedUserAnswer = payload.user_answer.trim().toLowerCase()
  const normalizedCorrectAnswer = payload.correct_answer.trim().toLowerCase()
  const isCorrect =
    normalizedCorrectAnswer === normalizedUserAnswer
    || normalizedCorrectAnswer.includes(normalizedUserAnswer)
    || normalizedUserAnswer.includes(normalizedCorrectAnswer)
  const score = isCorrect ? 100 : payload.user_answer.trim() ? (payload.question_type === 'choice' ? 0 : 60) : 0

  return {
    user_id: payload.user_id,
    exercise_id: payload.exercise_id,
    is_correct: isCorrect,
    score,
    feedback: isCorrect ? '回答正确，当前知识点掌握较稳定。' : '这道题还有提升空间，请先阅读解析。',
    suggested_action: isCorrect ? '保持节奏，继续下一题。' : '不要重复提交原题，先看解析，再去做错题变式重练。',
    analysis: payload.analysis,
  }
}

function applyLocalPracticeState(payload: PracticeSubmissionPayload, feedback: PracticeFeedback) {
  localPracticeRecords.value.push({
    ...payload,
    is_correct: feedback.is_correct,
    score: feedback.score,
  })
  rememberSubmission(payload, feedback)
  mistakeNotebook.value = rebuildMistakeNotebook(payload.user_id)
  stageReport.value = buildFallbackReport('stage', payload.user_id)
  comprehensiveReport.value = buildFallbackReport('comprehensive', payload.user_id)
  syncLearnerFromDashboard(buildFallbackProfileDashboard(payload.user_id))
  persistCurrentMistakeSnapshot()
}

function markTaskCompleted(taskType: string) {
  if (!learningPath.value) {
    return
  }

  learningPath.value = {
    ...learningPath.value,
    stages: learningPath.value.stages.map((stage) => ({
      ...stage,
      tasks: stage.tasks.map((task) => (
        task.task_type === taskType
          ? { ...task, completed: true }
          : task
      )),
    })),
  }
}

function buildCoordinationIntent(subject: string, topic: string, goal: string) {
  const cleanGoal = goal.trim()
  return cleanGoal
    ? `请围绕 ${subject} 中的“${topic}”生成个性化学习路径、学习课件和练习题，学习目标是：${cleanGoal}`
    : `请围绕 ${subject} 中的“${topic}”生成个性化学习路径、学习课件和练习题。`
}

function applyLearningRequestToForms() {
  const subject = learningRequestForm.subject.trim()
  const topic = learningRequestForm.topic.trim()
  const goal = learningRequestForm.goal.trim()

  learningRequestForm.subject = subject
  learningRequestForm.topic = topic

  coordinationForm.knowledge_point = topic
  coordinationForm.intent = buildCoordinationIntent(subject, topic, goal)
  coordinationForm.payload.subject = subject
  coordinationForm.payload.grade = qaForm.grade

  resourceForm.knowledge_point = topic
  pathForm.subject = subject
  pathForm.knowledge_point = topic
  exerciseForm.knowledge_point = topic

  qaForm.subject = subject
  qaForm.current_knowledge_points = [topic]
  if (!qaForm.question.trim() || qaForm.question === DEFAULT_QA_PROMPT) {
    qaForm.question = `我想学习 ${topic}，请先帮我讲清楚核心概念。`
  }
}

function syncFormsWithKnowledgePoint(knowledgePoint: string) {
  coordinationForm.knowledge_point = knowledgePoint
  resourceForm.knowledge_point = knowledgePoint
  pathForm.knowledge_point = knowledgePoint
  exerciseForm.knowledge_point = knowledgePoint
  learningRequestForm.topic = knowledgePoint
  coordinationForm.intent = buildCoordinationIntent(pathForm.subject, knowledgePoint, learningRequestForm.goal)
  qaForm.current_knowledge_points = [knowledgePoint]
}

async function startLearningPlan() {
  if (loading.path || loading.courseware || loading.exercises || loading.coordinate) {
    return
  }
  if (!learningRequestForm.subject.trim() || !learningRequestForm.topic.trim()) {
    ElMessage.warning('请先填写学科和想学习的内容。')
    return
  }

  applyLearningRequestToForms()
  activeTaskId.value = ''
  learningPath.value = null
  resourceResult.value = null
  exerciseSet.value = null
  graphResult.value = null
  graphVisualization.value = null
  selectedCoursewareVariantId.value = ''
  coursewareGenerationError.value = ''
  exerciseGenerationError.value = ''

  await Promise.all([
    generateLearningPath(),
    generateCourseware(),
  ])
}

function scrollToCoursewareSection(anchor: string) {
  const target = document.getElementById(anchor)
  target?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function formatQuestionTypeLabel(value?: string) {
  if (!value) {
    return '未标注题型'
  }
  return questionTypeLabelMap[value] ?? value
}

function formatDifficultyLabel(value?: string) {
  if (!value) {
    return '未标注难度'
  }
  return difficultyLabelMap[value] ?? value
}

function formatDurationLabel(seconds: number) {
  if (seconds < 60) {
    return `${seconds} 秒`
  }
  const minutes = Math.floor(seconds / 60)
  const remain = seconds % 60
  return remain ? `${minutes} 分 ${remain} 秒` : `${minutes} 分钟`
}

function stopAsyncStatus(key: AsyncStatusKey) {
  const timer = asyncStatusTimers[key]
  if (timer) {
    clearInterval(timer)
    delete asyncStatusTimers[key]
  }
}

function resetAsyncStatus(key?: AsyncStatusKey) {
  if (key) {
    stopAsyncStatus(key)
    asyncRequestStatus[key].active = false
    asyncRequestStatus[key].label = ''
    asyncRequestStatus[key].startedAt = null
    asyncRequestStatus[key].elapsedSeconds = 0
    asyncRequestStatus[key].phase = 'idle'
    return
  }

  ;(['profile', 'graph', 'mistakes', 'remedial', 'reports', 'qa', 'path', 'coordinate'] as AsyncStatusKey[]).forEach((item) => {
    stopAsyncStatus(item)
    asyncRequestStatus[item].active = false
    asyncRequestStatus[item].label = ''
    asyncRequestStatus[item].startedAt = null
    asyncRequestStatus[item].elapsedSeconds = 0
    asyncRequestStatus[item].phase = 'idle'
  })
}

function startAsyncStatus(key: AsyncStatusKey, label: string) {
  resetAsyncStatus(key)
  asyncRequestStatus[key].active = true
  asyncRequestStatus[key].label = label
  asyncRequestStatus[key].startedAt = Date.now()
  asyncRequestStatus[key].elapsedSeconds = 0
  asyncRequestStatus[key].phase = 'waiting'
  asyncStatusTimers[key] = setInterval(() => {
    if (!asyncRequestStatus[key].startedAt) {
      return
    }
    const elapsedSeconds = Math.max(
      0,
      Math.floor((Date.now() - asyncRequestStatus[key].startedAt!) / 1000),
    )
    asyncRequestStatus[key].elapsedSeconds = elapsedSeconds
    if (elapsedSeconds >= 18) {
      asyncRequestStatus[key].phase = 'stalled'
    } else if (elapsedSeconds >= 8) {
      asyncRequestStatus[key].phase = 'slow'
    } else {
      asyncRequestStatus[key].phase = 'waiting'
    }
  }, 1000)
}

function buildAsyncStatusView(key: AsyncStatusKey | null): AsyncStatusView | null {
  if (!key) {
    return null
  }
  const state = asyncRequestStatus[key]
  if (!state.active) {
    return null
  }

  if (state.phase === 'stalled') {
    return {
      title: `${state.label}可能卡住了`,
      detail: '如果继续超过 20 秒没有变化，建议重新点击一次。页面当前仍在等待服务返回。',
      elapsedLabel: formatDurationLabel(state.elapsedSeconds),
      tone: 'danger',
    }
  }

  if (state.phase === 'slow') {
    return {
      title: `${state.label}正在等待服务响应`,
      detail: '服务响应比平时慢一些，但请求还在继续处理中。',
      elapsedLabel: formatDurationLabel(state.elapsedSeconds),
      tone: 'warning',
    }
  }

  return {
    title: `${state.label}处理中`,
    detail: '请求已经发出，页面正在等待服务返回。',
    elapsedLabel: formatDurationLabel(state.elapsedSeconds),
    tone: 'info',
  }
}

function buildGenerationStatusView(kind: GenerationKind, label: string): AsyncStatusView | null {
  const state = generationStatus[kind]
  if (!state.startedAt || !state.hint) {
    return null
  }

  if (state.status === 'idle' || state.status === 'done' || state.status === 'fallback') {
    return null
  }

  const progressView = buildGenerationProgressView(kind)

  if (state.status === 'error') {
    return {
      title: `${label}生成失败`,
      detail: `当前停留在“${progressView.title}”阶段。${state.hint}`,
      elapsedLabel: progressView.elapsedLabel,
      tone: 'danger',
    }
  }

  if (state.status === 'background') {
    return {
      title: `${label}已进入后台增强`,
      detail: '页面上已经先展示了一版可用内容，你可以继续学习；系统仍在后台补充更完整的正式结果。',
      elapsedLabel: progressView.elapsedLabel,
      tone: 'warning',
    }
  }

  if (state.elapsedSeconds >= 18) {
    return {
      title: `${label}生成时间偏长`,
      detail: `当前还在“${progressView.title}”阶段等待服务返回。如果继续超过 40 秒没有变化，建议重新点击一次。`,
      elapsedLabel: progressView.elapsedLabel,
      tone: 'danger',
    }
  }

  if (state.elapsedSeconds >= 8) {
    return {
      title: `${label}还在生成`,
      detail: `当前已进入“${progressView.title}”阶段，服务比平时慢一些，但请求仍在处理中。`,
      elapsedLabel: progressView.elapsedLabel,
      tone: 'warning',
    }
  }

  return {
    title: `${label}正在生成`,
    detail: `当前阶段：${progressView.title}。${progressView.remainingLabel}`,
    elapsedLabel: progressView.elapsedLabel,
    tone: 'info',
  }
}

function buildGenerationProgressView(kind: GenerationKind): GenerationProgressView {
  const state = generationStatus[kind]
  const steps = generationStageDefinitions[kind]
  const totalStages = steps.length
  const isCourseware = kind === 'courseware'
  const expectedSeconds = isCourseware ? 35 : 8
  const estimateRangeLabel = isCourseware ? '10-35 秒' : '3-8 秒'
  const currentIndex = steps.reduce((activeIndex, step, index) => {
    return state.progress >= step.threshold ? index : activeIndex
  }, 0)
  const currentStep = steps[currentIndex] ?? steps[0]
  const elapsedLabel = formatDurationLabel(state.elapsedSeconds)

  let remainingLabel = '等待开始'
  let statusLabel = '未开始'
  let detail = currentStep.description

  if (state.status === 'running') {
    statusLabel = `第 ${currentIndex + 1}/${totalStages} 步`
    if (state.elapsedSeconds < 3) {
      remainingLabel = `预计还需 ${estimateRangeLabel}`
    } else if (state.elapsedSeconds < expectedSeconds) {
      remainingLabel = `预计还需 ${Math.max(1, expectedSeconds - state.elapsedSeconds)} 秒`
    } else {
      remainingLabel = '已超过常规时长，仍在继续生成'
    }
  } else if (state.status === 'background') {
    statusLabel = isCourseware ? '仍在继续生成' : '已切到后台增强'
    remainingLabel = isCourseware ? '页面会在生成完成后直接展示正式课件' : '你可以先学习，后台仍在完善正式结果'
    detail = isCourseware
      ? '系统仍在继续等待模型返回完整课件。'
      : '快速版内容已经可用，系统正在继续请求更完整的正式内容。'
  } else if (state.status === 'done') {
    statusLabel = '已完成'
    remainingLabel = '结果已经返回页面'
    detail = isCourseware ? '正式学习课件已经返回，可以直接开始学习。' : '课后自测已经生成完成，可以直接继续练习。'
  } else if (state.status === 'fallback') {
    statusLabel = isCourseware ? '本轮未完成' : '已切换快速版'
    remainingLabel = isCourseware ? '当前没有可展示的课件内容' : '当前先使用快速版结果'
    detail = isCourseware ? '模型未返回可展示课件，请重试。' : '远程生成较慢或失败，页面已切换为可直接使用的快速版。'
  } else if (state.status === 'error') {
    statusLabel = '生成失败'
    remainingLabel = isCourseware ? '当前未返回正式课件' : '当前未返回可展示题组'
    detail = isCourseware
      ? '本次不会切换为本地快速课件，请调整需求后重新生成。'
      : '本次题组生成失败，请稍后重试。'
  }

  return {
    title: currentStep.title,
    detail,
    stageIndex: currentIndex + 1,
    totalStages,
    elapsedLabel,
    remainingLabel,
    statusLabel,
    steps: steps.map((step, index) => ({
      index: index + 1,
      title: step.title,
      description: step.description,
      state: index < currentIndex ? 'completed' : index === currentIndex ? 'current' : 'pending',
    })),
  }
}

function scrollToExerciseResult() {
  exerciseResultAnchor.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function scrollToQaResult() {
  qaResultAnchor.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

async function checkHealth() {
  try {
    await userApi.get('/health')
    serviceStatus.user = 'online'
  } catch {
    serviceStatus.user = 'offline'
  }

  try {
    await agentApi.get('/health')
    serviceStatus.agent = 'online'
  } catch {
    serviceStatus.agent = 'offline'
  }

  try {
    await evaluationApi.get('/health')
    serviceStatus.evaluation = 'online'
  } catch {
    serviceStatus.evaluation = 'offline'
  }
}

async function fetchCurrentUser() {
  try {
    const { data } = await userApi.get('/users/me')
    coordinationForm.user_id = data.id
    resourceForm.user_id = data.id
    pathForm.user_id = data.id
    exerciseForm.user_id = data.id
    qaForm.student_id = String(data.id)
    await fetchProfileDashboard(data.id)
  } catch {
    authStore.clear()
    await router.push({ name: 'login' })
  }
}

async function fetchProfileDashboard(userId = exerciseForm.user_id) {
  startAsyncStatus('profile', '学习画像')
  try {
    const [{ data: dashboard }, { data: profile }] = await Promise.all([
      userApi.get<LearnerProfileDashboard>(`/users/${userId}/profile/dashboard`),
      userApi.get<UserProfileRead>(`/users/${userId}/profile`),
    ])
    syncLearnerFromDashboard(dashboard)
    profileRecord.value = profile
  } catch {
    syncLearnerFromDashboard(buildFallbackProfileDashboard(userId))
    profileRecord.value = null
    announceFallback('profile-dashboard', '学习画像服务暂不可用，已切换到本地画像模式。')
  } finally {
    resetAsyncStatus('profile')
  }
}

async function submitProfileChat() {
  const message = profileChatMessage.value.trim()
  if (!message) {
    ElMessage.warning('请先输入一段你当前的学习情况或目标。')
    return
  }

  loading.profileChat = true
  profileChatError.value = ''
  try {
    const userId = authStore.user?.userId ?? exerciseForm.user_id
    const { data } = await userApi.post<ProfileChatResponsePayload>(`/users/${userId}/profile/chat`, {
      message,
    })
    profileChatResult.value = data
    profileChatMessage.value = ''
    await fetchProfileDashboard(userId)
    ElMessage.success('画像对话已更新。')
  } catch {
    profileChatError.value = '画像对话提交失败，请稍后再试。'
    ElMessage.error('画像对话提交失败。')
  } finally {
    loading.profileChat = false
  }
}

async function runCoordination() {
  loading.coordinate = true
  startAsyncStatus('coordinate', '协同计划')
  try {
    applyLearningRequestToForms()
    const { data } = await agentApi.post('/agents/coordinate', coordinationForm)
    coordinationResult.value = data as CoordinationResult
    ElMessage.success('学习协同计划已生成。')
  } catch {
    ElMessage.error('协调调度失败。')
  } finally {
    loading.coordinate = false
    resetAsyncStatus('coordinate')
  }
}

async function generateLearningPath() {
  loading.path = true
  startAsyncStatus('path', '学习路径')
  try {
    applyLearningRequestToForms()
    const { data } = await agentApi.post<LearningPathResponse>('/paths/generate', pathForm)
    learningPath.value = data
    activeTaskId.value = data.stages[0]?.tasks[0]?.task_id ?? ''
    ElMessage.success('学习路径已生成。')
  } catch {
    const fallback = buildFallbackLearningPath()
    learningPath.value = fallback
    activeTaskId.value = fallback.stages[0]?.tasks[0]?.task_id ?? ''
    announceFallback('learning-path', '学习路径服务暂不可用，已切换到本地学习路径。')
  } finally {
    loading.path = false
    resetAsyncStatus('path')
  }
}

function buildFallbackCoursewareContent(knowledgePoint: string) {
  if (knowledgePoint.includes('循环')) {
    return [
      `# ${knowledgePoint} 学习课件`,
      '',
      '## 课程导入',
      '想象一下，如果你要把 1 到 100 的数字全部打印出来，或者要逐个检查一组成绩是否及格，你会怎么做？',
      '如果没有循环，我们只能把相同的代码一遍遍重复写出来，不但效率低，而且特别容易出错。',
      `所以学习 ${knowledgePoint}，本质上不是只背一个语法，而是学会把“重复任务”交给程序自动完成。`,
      '',
      '## 学习目标',
      `- 能说清 ${knowledgePoint} 解决的核心问题是什么`,
      '- 能区分 `for` 循环和 `while` 循环的适用场景',
      '- 能读懂基础循环代码，并解释每一行在做什么',
      '- 能主动检查循环中的边界、条件和更新步骤，避免死循环',
      '',
      '## 知识讲解',
      '循环就是让程序按照一定规则重复执行同一类操作。',
      '学习循环时，必须盯住三个问题：',
      '1. 重复的对象是谁，比如列表里的每个元素，或者不断变化的计数值。',
      '2. 每一轮要做什么，比如输出、统计、判断或者筛选。',
      '3. 什么时候停下来，如果停不下来，就可能变成死循环。',
      '',
      '通常来说：',
      '- `for` 更适合遍历固定范围、固定序列或已知集合。',
      '- `while` 更适合“只要条件成立就继续执行”的场景。',
      '- 循环常常会和条件判断一起使用，因为真实任务通常既要重复，也要判断。',
      '',
      '## 重难点突破',
      '很多同学写循环时，不是语法不会，而是思路不清。',
      '最常见的三个问题是：',
      '- 把 `for` 和 `while` 的场景混用，本来遍历列表就能解决的问题，非要写成复杂的 `while`。',
      '- 没有意识到 `range(5)` 得到的是 `0, 1, 2, 3, 4`，不包含 5。',
      '- 在 `while` 循环里忘记更新控制变量，比如忘记写 `count += 1`，结果程序一直停不下来。',
      '',
      '你可以把循环想成“程序在按规则做一轮一轮的工作”，每做完一轮都要问自己：',
      '- 这轮做了什么？',
      '- 变量变了吗？',
      '- 下一轮为什么还能继续，或者为什么应该结束？',
      '',
      '## 关键语法',
      '```python',
      'for item in items:',
      '    print(item)',
      '```',
      '',
      '上面这段代码表示：从 `items` 中每次取出一个元素，放到 `item` 里，再执行循环体。',
      '',
      '```python',
      'count = 0',
      'while count < 3:',
      '    print(count)',
      '    count += 1',
      '```',
      '',
      '这段代码表示：只要 `count < 3` 这个条件成立，就继续执行循环体。每执行一轮后，`count` 都会加 1，所以它最终会停下来。',
      '',
      '## 示例讲解',
      '下面看一个更贴近真实任务的例子：',
      '',
      '```python',
      'scores = [78, 91, 59, 84]',
      'for score in scores:',
      '    if score >= 60:',
      "        print(score, '及格')",
      '    else:',
      "        print(score, '不及格')",
      '```',
      '',
      '这段代码的理解顺序应该是：',
      '- `scores` 是要处理的数据。',
      '- `for score in scores` 表示把每个成绩依次取出来。',
      '- `if score >= 60` 表示对当前这一个成绩进行判断。',
      "- 如果条件成立，就输出“及格”；否则输出“不及格”。",
      '',
      '这个例子说明，循环真正的价值不是“重复写代码”，而是“自动处理一批相似任务”。',
      '',
      '## 课堂小结',
      `- ${knowledgePoint} 的核心价值，是让程序自动完成重复性的处理工作。`,
      '- `for` 偏向遍历型任务，`while` 偏向条件型任务。',
      '- 做循环题时，要重点检查：循环对象、循环条件、变量更新、缩进层级。',
      '- 一旦程序停不下来，优先排查 `while` 条件和控制变量是否发生了变化。',
      '',
      '## 学完后自测',
      '- 我能不能解释 `for` 和 `while` 各自适合什么场景？',
      '- 我能不能说出 `range(5)` 实际会产生哪些数字？',
      '- 我能不能分析一个 `while` 循环为什么会死循环？',
      '- 我能不能写出一段遍历列表并做条件判断的代码？',
      '',
      '## 拓展延伸',
      '下一步可以尝试把循环和条件判断、列表、函数结合起来，完成统计、筛选、查找等小任务。',
      `真正掌握 ${knowledgePoint}，不是看到代码会点头，而是自己写题时知道什么时候该用它、为什么这样用、出错后怎么检查。`,
    ].join('\n')
  }

  if (knowledgePoint.includes('条件判断')) {
    return [
      `# ${knowledgePoint} 学习课件`,
      '',
      '## 课程导入',
      '程序并不是只会机械执行命令，它还可以根据不同情况作出不同选择。',
      `学习 ${knowledgePoint}，就是学习如何让程序“看情况办事”。`,
      '',
      '## 学习目标',
      `- 理解 ${knowledgePoint} 的基本作用`,
      '- 能读懂并写出 `if / elif / else` 结构',
      '- 能分析条件顺序、边界值和比较逻辑是否正确',
      '',
      '## 知识讲解',
      '- `if` 表示当条件成立时执行。',
      '- `elif` 表示当前面条件不满足时，再检查新的条件。',
      '- `else` 表示当前面条件都不成立时的兜底处理。',
      '- 写条件判断时，要特别关注边界值，比如“是否包含等于号”。',
      '',
      '## 重难点突破',
      '- 很多错误不是语法错，而是条件顺序错。',
      '- 如果宽范围条件写在前面，后面更精细的条件可能永远不会被执行。',
      '- `=` 是赋值，`==` 才是比较，这也是初学者常见错误。',
      '',
      '## 示例讲解',
      '```python',
      'score = 85',
      'if score >= 90:',
      "    print('A')",
      'elif score >= 80:',
      "    print('B')",
      'else:',
      "    print('C')",
      '```',
      '',
      '这段代码会先判断是否大于等于 90；如果不是，再判断是否大于等于 80；最后再进入兜底分支。',
      '',
      '## 课堂小结',
      `- ${knowledgePoint} 的本质是根据条件选择不同执行路径。`,
      '- 写题时要检查条件顺序、边界和比较符号是否准确。',
      '',
      '## 学完后自测',
      '- 我能不能解释 `if / elif / else` 的执行顺序？',
      '- 我能不能判断条件区间是否有重叠或遗漏？',
      '',
      '## 拓展延伸',
      '条件判断通常会和循环一起出现。学完这一节后，可以继续做“循环 + 判断”的综合练习。',
    ].join('\n')
  }

  return [
    `# ${knowledgePoint} 学习课件`,
    '',
    '## 课程导入',
    `学习 ${knowledgePoint} 时，先不要急着记语法或结论，而要先想清楚：这个知识点到底解决什么问题。`,
    '',
    '## 学习目标',
    `- 理解 ${knowledgePoint} 的核心概念`,
    '- 知道它的典型使用场景',
    '- 能结合一个具体例子说明它的作用',
    '',
    '## 知识讲解',
    `${knowledgePoint} 建议从“定义是什么、为什么要学、容易错在哪里、怎么用在题目里”四个角度去理解。`,
    '',
    '## 重难点突破',
    '如果一个知识点总是学了就忘，通常不是记忆力问题，而是没有把概念、场景和步骤连起来。',
    '学习时要不断追问自己：为什么这样做？如果换个题目还能不能用？',
    '',
    '## 示例讲解',
    `请尝试围绕 ${knowledgePoint} 自己举一个最小例子，再对照课件检查自己是否真的理解。`,
    '',
    '## 课堂小结',
    `- 先理解 ${knowledgePoint} 为什么存在`,
    `- 再掌握 ${knowledgePoint} 怎么使用`,
    `- 最后通过做题把 ${knowledgePoint} 变成真正会用的能力`,
    '',
    '## 学完后自测',
    `- 我能不能用自己的话解释 ${knowledgePoint}？`,
    `- 我能不能说出它适合解决什么问题？`,
    `- 我能不能指出它最容易出错的地方？`,
    '',
    '## 拓展延伸',
    `建议继续生成围绕 ${knowledgePoint} 的课后自测题，把“看懂”进一步变成“会做”。`,
  ].join('\n')
}

function buildQuickExerciseSet(): ExerciseGenerationResponse {
  return {
    user_id: exerciseForm.user_id,
    knowledge_point: exerciseForm.knowledge_point,
    summary: `已为 ${exerciseForm.knowledge_point} 先生成一组快速版自测题，你可以先开始作答，后台会继续尝试升级为更完整的正式题组。`,
    exercises: [
      {
        exercise_id: 1,
        knowledge_point: exerciseForm.knowledge_point,
        question_type: 'choice',
        difficulty: 'foundation',
        prompt: `关于 ${exerciseForm.knowledge_point}，下面哪一项理解最准确？`,
        options: [
          'A. 它只能背语法，不能解决实际问题',
          'B. 它主要用于按照一定规则重复处理任务',
          'C. 它只能和一种固定数据类型一起使用',
          'D. 一旦使用就不能再配合条件判断',
        ],
        answer: 'B',
        analysis: `${exerciseForm.knowledge_point} 的核心作用是让程序按照规则重复执行操作。A、C、D 都把它理解得过于狭窄或错误。`,
      },
      {
        exercise_id: 2,
        knowledge_point: exerciseForm.knowledge_point,
        question_type: 'blank',
        difficulty: 'foundation',
        prompt: '如果循环条件一直成立，而循环内部又没有让条件发生变化，程序就可能出现 ______。',
        options: [],
        answer: '死循环',
        analysis: '这道题考查你是否理解循环结束依赖于条件变化。如果条件始终不变，程序就会不停执行下去。',
      },
      {
        exercise_id: 3,
        knowledge_point: exerciseForm.knowledge_point,
        question_type: 'judge',
        difficulty: 'intermediate',
        prompt: '判断正误：循环结构和条件判断结构在实际做题时经常需要配合使用。',
        options: [],
        answer: '正确',
        analysis: '很多真实任务都需要“重复 + 判断”同时出现，例如筛选、统计、查找等，所以这句话是正确的。',
      },
      {
        exercise_id: 4,
        knowledge_point: exerciseForm.knowledge_point,
        question_type: 'short_answer',
        difficulty: 'intermediate',
        prompt: `请用自己的话说明 ${exerciseForm.knowledge_point} 在实际编程中能解决什么问题。`,
        options: [],
        answer: '答案示例：它可以帮助我们把需要重复执行的操作按规则自动完成，比如遍历数据、统计结果、筛选信息等。',
        analysis: '这道题重点不是背定义，而是说清它在真实任务中的作用。',
      },
      {
        exercise_id: 5,
        knowledge_point: exerciseForm.knowledge_point,
        question_type: 'programming',
        difficulty: 'advanced',
        prompt: `编写一段简单代码，展示如何使用 ${exerciseForm.knowledge_point} 处理一组数据。`,
        options: [],
        answer: '参考答案：使用循环遍历一组数据，并在循环体内完成输出、统计或筛选操作。',
        analysis: '编程题重点看你是否能把知识点转换成具体步骤，而不是只会写出一个关键词。',
      },
    ],
  }
}

function buildQaLearningHistory() {
  const records = localPracticeRecords.value.slice(-5).map((item) => ({
    knowledge_point: item.knowledge_point,
    question_type: item.question_type,
    is_correct: item.is_correct,
    score: item.score,
    time_spent: item.time_spent,
  }))
  return {
    last_7_days: records,
    mastery: learner.mastery,
    learning_style: learner.style,
  }
}

function isLikelyLearningQuestion(question: string) {
  const trimmed = question.trim()
  if (!trimmed) {
    return false
  }

  const lower = trimmed.toLowerCase()
  return /python|java|c\+\+|循环|for|while|if|代码|编程|函数|算法|题目|错题|作业|考试|学习|知识点|数学|物理|化学|英语|讲解|解析|证明|推导/.test(
    lower,
  )
}

function buildFallbackQaResponse(): QAResponsePayload {
  const question = qaForm.question.trim()
  const knowledgePoint =
    qaForm.current_knowledge_points[0] ||
    pathForm.knowledge_point ||
    exerciseForm.knowledge_point ||
    '当前问题'
  const lowerQuestion = question.toLowerCase()
  const hasLearningContext = isLikelyLearningQuestion(question)
  const hasWrongContext = Boolean(qaForm.student_answer?.trim() || qaForm.wrong_answer?.trim())
  const shouldAddMistake = hasWrongContext && /题|错|答案|作业|解析|复盘/.test(question)

  let studentResponse = hasLearningContext
    ? `你提到的问题目前更像一个学习问题，我会先围绕问题本身讲解；如果你愿意继续做学习分析，可以再补充题目背景、你的思路或者错误答案。`
    : `你刚刚问的是：“${question}”。这个问题本身不一定属于错题复盘或知识漏洞诊断场景，所以我不会强行把它归到当前课件知识点上。若你想继续做学习分析，可以补充题目或作答过程。`
  let knowledgeGaps = hasLearningContext ? [knowledgePoint] : []
  let misconceptions = hasLearningContext ? ['当前理解还需要把概念、条件和执行过程连起来。'] : []
  let nextActions = hasLearningContext
    ? ['先听讲解，再根据是否有错误作答决定要不要继续复盘。']
    : ['如果你希望继续做学习分析，可以补充题目背景、作答思路或错误答案。']
  let routeAction = hasLearningContext ? '先完成问题讲解，再决定是否进入专项复盘。' : '当前不强制调整学习路线。'
  let routeReason = hasLearningContext ? '当前提问有学习语境，但是否属于明确错题还需要更多上下文。' : '当前更像一般提问。'
  let wrongReason = '当前没有提供完整错误作答过程，无法进一步定位到某一步骤。'
  let correctApproach = shouldAddMistake
    ? '结合错误答案和正确思路逐步对照，提炼成可复用的改错规则。'
    : '如果这是错题复盘，请补充错误答案或完整思路，再定位具体错因。'

  if (lowerQuestion.includes('while') || lowerQuestion.includes('死循环')) {
    studentResponse = [
      '你这个问题很典型，很多同学第一次学 `while` 时都会卡在这里。',
      '',
      '先抓住一句话：`while` 的意思是“只要条件成立，就一直重复执行”。',
      '所以它会不会变成死循环，关键不在于写了 `while`，而在于循环体里有没有让条件发生变化。',
      '',
      '看一个最常见的例子：',
      '',
      '```python',
      'count = 0',
      'while count < 3:',
      '    print(count)',
      '```',
      '',
      '这段代码的问题是：`count` 一开始等于 0，而且循环里没有修改 `count`。',
      '于是程序每一轮判断时都会发现 `count < 3` 仍然成立，就会一直重复执行下去，这就是死循环。',
      '',
      '正确写法应该是：',
      '',
      '```python',
      'count = 0',
      'while count < 3:',
      '    print(count)',
      '    count += 1',
      '```',
      '',
      '现在每执行一轮，`count` 都会加 1：',
      '- 第 1 轮后，`count = 1`',
      '- 第 2 轮后，`count = 2`',
      '- 第 3 轮后，`count = 3`',
      '这时条件 `count < 3` 不再成立，循环自然结束。',
      '',
      '你可以把 `while` 理解成“门口保安不断检查条件”，只要条件还满足，就放程序继续执行；一旦条件不满足，程序才会停下来。',
      '',
      '以后检查 `while` 题目时，重点看三件事：',
      '- 循环开始前，条件是不是成立',
      '- 每执行一轮，控制变量有没有变化',
      '- 这种变化会不会最终让条件不成立',
    ].join('\n')
    knowledgeGaps = ['while 循环结束条件', '控制变量更新', '死循环成因']
    misconceptions = [
      '容易把“写了 while”误认为“程序会自动结束”。',
      '容易忽略循环体里必须让控制变量发生变化这一点。',
    ]
    nextActions = [
      '先自己口述一遍：while 循环为什么会停下来。',
      '再手动模拟一段简单 while 代码的每一轮变量变化。',
      '最后做 2 道“找死循环原因”的小题巩固。',
    ]
    routeAction = '补强 while 循环结束条件与变量更新逻辑，再做死循环诊断题。'
    routeReason = '当前问题直接暴露出对 while 执行机制和退出条件的理解不稳定。'
    wrongReason = '容易忽略循环体内部是否真正改变了控制变量。'
    correctApproach = '先检查条件，再逐轮追踪变量变化，确认条件是否会最终失效。'
  }

  return {
    student_id: String(authStore.user?.userId ?? exerciseForm.user_id),
    subject: pathForm.subject,
    grade: qaForm.grade,
    student_response: studentResponse,
    structured_analysis: {
      identified_knowledge_gaps: knowledgeGaps,
      misconceptions,
      difficulty_level: hasLearningContext ? 'intermediate' : 'foundation',
      learning_state: hasLearningContext
        ? '当前处于“已经接触概念，但执行过程还没有真正想透”的阶段，适合通过讲解加少量诊断题快速补牢。'
        : '本轮问题属于通用问答，未触发学习分析。',
      recommended_next_knowledge_points: hasLearningContext ? [knowledgePoint] : [],
      learning_route_updates: hasLearningContext
        ? [
            {
              knowledge_point: knowledgePoint,
              priority: 'high',
              action: routeAction,
              reason: routeReason,
            },
          ]
        : [],
      resource_recommendations: hasLearningContext
        ? [
            {
              resource_type: 'courseware',
              title: `${knowledgePoint} 精讲课件`,
              reason: '先把概念、条件和执行步骤重新讲透，再做题效果更好。',
            },
            {
              resource_type: 'exercise',
              title: `${knowledgePoint} 基础诊断题`,
              reason: '通过少量题目确认是否真的理解了关键逻辑。',
            },
          ]
        : [],
      study_suggestions: hasLearningContext ? nextActions : [],
      mistake_book_update: {
        should_add: shouldAddMistake,
        question_summary: question || `关于 ${knowledgePoint} 的提问`,
        wrong_reason: shouldAddMistake ? wrongReason : '',
        correct_approach: shouldAddMistake ? correctApproach : '',
      },
    },
  }
}

function stopGenerationProgress(kind: GenerationKind) {
  const timer = generationProgressTimers[kind]
  if (timer) {
    clearInterval(timer)
    delete generationProgressTimers[kind]
  }
}

function startGenerationProgress(kind: GenerationKind, message: string) {
  stopGenerationProgress(kind)
  generationStatus[kind].hint = message
  generationStatus[kind].progress = 8
  generationStatus[kind].startedAt = Date.now()
  generationStatus[kind].elapsedSeconds = 0
  generationStatus[kind].status = 'running'
  generationProgressTimers[kind] = setInterval(() => {
    if (generationStatus[kind].startedAt) {
      generationStatus[kind].elapsedSeconds = Math.max(
        0,
        Math.floor((Date.now() - generationStatus[kind].startedAt) / 1000),
      )
    }
    if (generationStatus[kind].progress < 45) {
      generationStatus[kind].progress += 7
      return
    }
    if (generationStatus[kind].progress < 75) {
      generationStatus[kind].progress += 4
      return
    }
    if (generationStatus[kind].progress < 94) {
      generationStatus[kind].progress += 1
    }
  }, 450)
}

function setGenerationProgressBackground(kind: GenerationKind, message: string) {
  generationStatus[kind].hint = message
  generationStatus[kind].status = 'background'
  generationStatus[kind].progress = Math.max(generationStatus[kind].progress, 82)
}

function finishGenerationProgress(
  kind: GenerationKind,
  message: string,
  status: Extract<GenerationPhaseStatus, 'done' | 'fallback' | 'error'> = 'done',
) {
  stopGenerationProgress(kind)
  generationStatus[kind].progress = 100
  generationStatus[kind].hint = message
  if (generationStatus[kind].startedAt) {
    generationStatus[kind].elapsedSeconds = Math.max(
      generationStatus[kind].elapsedSeconds,
      Math.floor((Date.now() - generationStatus[kind].startedAt) / 1000),
    )
  }
  generationStatus[kind].status = status
}

function resetGenerationProgress(kind?: GenerationKind) {
  if (kind) {
    stopGenerationProgress(kind)
    generationStatus[kind].hint = ''
    generationStatus[kind].progress = 0
    generationStatus[kind].startedAt = null
    generationStatus[kind].elapsedSeconds = 0
    generationStatus[kind].status = 'idle'
    return
  }

  ;(['courseware', 'exercises'] as GenerationKind[]).forEach((item) => {
    stopGenerationProgress(item)
    generationStatus[item].hint = ''
    generationStatus[item].progress = 0
    generationStatus[item].startedAt = null
    generationStatus[item].elapsedSeconds = 0
    generationStatus[item].status = 'idle'
  })
}

async function generateCourseware() {
  const requestVersion = ++coursewareRequestVersion
  applyLearningRequestToForms()
  loading.courseware = true
  startGenerationProgress('courseware', '正在调用模型生成正式学习课件，预计等待 10-35 秒。')
  coursewareGenerationError.value = ''
  resourceResult.value = null
  selectedCoursewareVariantId.value = ''
  exerciseForm.courseware_content = ''
  try {
    resourceForm.resource_type = 'courseware'
    resourceForm.request_text = `${learningRequestForm.goal}，知识点：${resourceForm.knowledge_point}`
    lastCoursewareRequest.value = {
      ...resourceForm,
    }
    const { data } = await postContentWithTimeout<EnvelopeLike<ResourceResult>>('/resources/generate', resourceForm, 60000)
    if (requestVersion !== coursewareRequestVersion) {
      return
    }
    lastCoursewareRawResponse.value = data
    const normalized = normalizeResourceResult(data)
    if (!normalized) {
      throw new Error('resource payload is empty')
    }
    resourceResult.value = normalized
    selectedCoursewareVariantId.value =
      normalized.variants?.find((item) => item.is_recommended)?.variant_id ??
      normalized.variants?.[0]?.variant_id ??
      ''
    exerciseForm.courseware_content =
      normalized.variants?.find((item) => item.variant_id === selectedCoursewareVariantId.value)?.content ??
      resourceResult.value.content ??
      ''
    persistCurrentCoursewareSnapshot()
    coursewareGenerationError.value = ''
    markTaskCompleted('courseware')
    finishGenerationProgress('courseware', '模型学习课件已生成完成。')
    ElMessage.success('模型学习课件已生成')
  } catch {
    if (requestVersion !== coursewareRequestVersion) {
      return
    }
    resourceResult.value = null
    selectedCoursewareVariantId.value = ''
    exerciseForm.courseware_content = ''
    coursewareGenerationError.value = '模型课件生成失败或超时，请重试，当前不会再切换为本地快速课件。'
    finishGenerationProgress('courseware', '模型课件生成失败，请重试。', 'error')
    ElMessage.error('模型课件生成失败，请重试')
  } finally {
    if (requestVersion === coursewareRequestVersion) {
      loading.courseware = false
    }
  }
}

function selectCoursewareVariant(variantId: string) {
  selectedCoursewareVariantId.value = variantId
  const variant = coursewareVariants.value.find((item) => item.variant_id === variantId)
  if (variant) {
    exerciseForm.courseware_content = variant.content
  }
  persistCurrentCoursewareSnapshot()
}

function persistCurrentCoursewareSnapshot() {
  if (typeof window === 'undefined' || !resourceResult.value) {
    return
  }

  const snapshot: StoredCoursewareSnapshot = {
    subject: learningRequestForm.subject.trim(),
    topic: learningRequestForm.topic.trim(),
    goal: learningRequestForm.goal.trim(),
    selectedVariantId: selectedCoursewareVariantId.value,
    generatedAt: Date.now(),
    resourceResult: resourceResult.value,
  }

  window.sessionStorage.setItem(COURSEWARE_STORAGE_KEY, JSON.stringify(snapshot))
}

function openCoursewarePage() {
  if (!resourceResult.value) {
    ElMessage.warning('请先生成正式课件，再进入独立课件页。')
    return
  }

  persistCurrentCoursewareSnapshot()
  void router.push({ name: 'student-courseware' })
}

function persistCurrentMistakeSnapshot() {
  if (typeof window === 'undefined') {
    return
  }

  const snapshot: StoredMistakeSnapshot = {
    userId: exerciseForm.user_id,
    generatedAt: Date.now(),
    mistakeNotebook: mistakeNotebook.value,
    remedialExerciseSet: remedialExerciseSet.value,
  }

  window.sessionStorage.setItem(MISTAKE_NOTEBOOK_STORAGE_KEY, JSON.stringify(snapshot))
}

function openMistakeNotebookPage() {
  if (!mistakeNotebook.value && !remedialExerciseSet.value) {
    ElMessage.warning('请先刷新错题本或生成重练题，再进入独立错题页。')
    return
  }

  persistCurrentMistakeSnapshot()
  void router.push({ name: 'student-mistakes' })
}

function buildExerciseContext(content?: string) {
  if (!content) {
    return ''
  }
  const lines = content
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
  const picked = lines.filter((line) =>
    line.startsWith('## ') ||
    line.startsWith('- ') ||
    line.includes('常见错误') ||
    line.includes('学完后自测') ||
    line.includes('关键语法'),
  )
  const compact = (picked.length ? picked : lines).slice(0, 24).join('\n')
  return compact.slice(0, 900)
}

async function generateExercises() {
  const requestVersion = ++exerciseRequestVersion
  applyLearningRequestToForms()
  loading.exercises = true
  startGenerationProgress('exercises', '正在生成课后自测，预计等待 3-8 秒。')
  exerciseGenerationError.value = ''
  exerciseSet.value = buildQuickExerciseSet()
  resetExerciseSession()
  exerciseDeliveryMode.value = 'upgrading'
  await nextTick()
  scrollToExerciseResult()
  let fallbackTakeoverTriggered = false
  const takeoverTimer = setTimeout(() => {
    if (requestVersion !== exerciseRequestVersion) {
      return
    }
    fallbackTakeoverTriggered = true
    loading.exercises = false
    setGenerationProgressBackground('exercises', '已先展示快速版题组，后台正在继续增强正式题组。')
    ElMessage.info('已先展示快速版题组，可先开始作答。')
  }, 2200)
  try {
    exerciseForm.generation_mode = 'self_test'
    exerciseForm.courseware_content = buildExerciseContext(resourceResult.value?.content)
    lastExerciseRequest.value = {
      user_id: exerciseForm.user_id,
      knowledge_point: exerciseForm.knowledge_point,
      resource_style: exerciseForm.resource_style,
      learner_profile: exerciseForm.learner_profile,
      exercise_count: exerciseForm.exercise_count,
      generation_mode: exerciseForm.generation_mode,
      courseware_content_preview: exerciseForm.courseware_content.slice(0, 500),
    }
    const { data } = await postContentWithTimeout<EnvelopeLike<ExerciseGenerationResponse>>('/exercises/generate', exerciseForm, 12000)
    if (requestVersion !== exerciseRequestVersion) {
      return
    }
    lastExerciseRawResponse.value = data
    const normalized = normalizeExerciseResponse(data)
    if (!normalized) {
      throw new Error('exercise payload is empty')
    }
    exerciseSet.value = normalized
    resetExerciseSession()
    exerciseGenerationError.value = ''
    exerciseDeliveryMode.value = 'remote'
    await nextTick()
    scrollToExerciseResult()
    markTaskCompleted('exercise')
    finishGenerationProgress(
      'exercises',
      fallbackTakeoverTriggered ? '正式题组已更新完成。' : '课后自测已生成完成。',
    )
    ElMessage.success(fallbackTakeoverTriggered ? '正式题组已更新' : '课后自测已生成')
  } catch {
    if (requestVersion !== exerciseRequestVersion) {
      return
    }
    exerciseDeliveryMode.value = 'fallback'
    exerciseGenerationError.value = '远程题目生成失败或超时，当前已保留快速版题组，你可以先继续作答。'
    finishGenerationProgress('exercises', '远程生成较慢，当前先使用快速版题组。', 'fallback')
    ElMessage.warning('远程题目生成较慢，当前先使用快速版题组')
  } finally {
    clearTimeout(takeoverTimer)
    if (requestVersion === exerciseRequestVersion) {
      loading.exercises = false
    }
  }
}

async function queryGraph() {
  loading.graph = true
  startAsyncStatus('graph', '知识图谱查询')
  try {
    applyLearningRequestToForms()
    const payload = {
      knowledge_point: pathForm.knowledge_point,
      max_depth: 3,
    }
    const [dependencyResponse, visualizationResponse] = await Promise.all([
      agentApi.post('/graph/dependencies', payload),
      agentApi.post<GraphVisualizationResponse>('/graph/visualization', payload),
    ])
    graphResult.value = dependencyResponse.data as GraphResult
    graphVisualization.value = visualizationResponse.data
    await renderGraph()
    markTaskCompleted('graph')
    ElMessage.success('知识图谱依赖路径已返回。')
  } catch {
    ElMessage.error('知识图谱查询失败。')
  } finally {
    loading.graph = false
    resetAsyncStatus('graph')
  }
}

async function renderGraph() {
  await nextTick()
  if (!graphCanvas.value || !graphVisualization.value) {
    return
  }

  graphNetwork?.destroy()

  const nodes = new DataSet(
    graphVisualization.value.nodes.map((node) => ({
      id: node.id,
      label: node.label,
      shape: 'dot',
      size: node.category === 'current' ? 24 : 18,
      color:
        node.category === 'current'
          ? '#b5542f'
          : node.category === 'recommended'
            ? '#2f7d59'
            : node.category === 'resource'
              ? '#6b5cff'
              : '#d6a55f',
      font: {
        color: '#2e2117',
        size: 14,
      },
    })),
  )

  const edges = new DataSet(
    graphVisualization.value.edges.map((edge) => ({
      from: edge.source,
      to: edge.target,
      label: edge.label,
      color: '#bda68f',
      font: {
        color: '#6b5848',
        size: 12,
      },
      arrows: 'to',
      smooth: {
        type: 'curvedCW',
        roundness: 0.15,
      },
    })),
  )

  graphNetwork = new Network(
    graphCanvas.value,
    { nodes, edges },
    {
      autoResize: true,
      physics: {
        stabilization: true,
        barnesHut: {
          springLength: 140,
        },
      },
      interaction: {
        dragNodes: true,
        zoomView: true,
      },
    },
  )
}

async function submitPractice() {
  if (!currentExercise.value) {
    return
  }
  if (currentSubmission.value) {
    ElMessage.warning('这道题已经提交过，不能再次作答。')
    return
  }
  if (!currentAnswerDraft.value.trim()) {
    ElMessage.warning('请先填写答案。')
    return
  }

  loading.submit = true
  const payload: PracticeSubmissionPayload = {
    user_id: exerciseForm.user_id,
    exercise_id: currentExercise.value.exercise_id,
    knowledge_point: currentExercise.value.knowledge_point,
    question_type: currentExercise.value.question_type,
    user_answer: currentAnswerDraft.value.trim(),
    correct_answer: currentExercise.value.answer,
    analysis: currentExercise.value.analysis,
    time_spent: answerStartAt.value ? Math.max(1, Math.round((Date.now() - answerStartAt.value) / 1000)) : 0,
  }

  try {
    const { data } = await evaluationApi.post<ApiEnvelope<PracticeFeedback>>('/evaluation/practice/submit', payload)
    const feedback = data.data
    localPracticeRecords.value.push({
      ...payload,
      is_correct: feedback.is_correct,
      score: feedback.score,
    })
    rememberSubmission(payload, feedback)
    learner.mastery = Math.min(100, Math.max(0, learner.mastery + (feedback.is_correct ? 4 : -2)))
    await Promise.all([fetchMistakeNotebook(), fetchReports(), fetchProfileDashboard(payload.user_id)])
    ElMessage.success(feedback.is_correct ? '回答正确。' : '已返回标准答案与解析。')
    scheduleNextExerciseAutoAdvance()
  } catch {
    const fallback = buildFallbackPracticeFeedback(payload)
    applyLocalPracticeState(payload, fallback)
    ElMessage.success(fallback.is_correct ? '回答正确。' : '已返回标准答案与解析。')
    announceFallback('practice-submit', '评估服务暂不可用，已切换到本地判分模式。')
    scheduleNextExerciseAutoAdvance()
  } finally {
    loading.submit = false
  }
}

function scheduleNextExerciseAutoAdvance() {
  if (!exerciseSet.value || !currentSubmission.value) {
    return
  }
  if (autoAdvanceExerciseTimer) {
    clearTimeout(autoAdvanceExerciseTimer)
  }
  autoAdvanceExerciseTimer = setTimeout(() => {
    autoAdvanceExerciseTimer = null
    goToNextExercise()
  }, 1200)
}

function goToNextExercise() {
  if (autoAdvanceExerciseTimer) {
    clearTimeout(autoAdvanceExerciseTimer)
    autoAdvanceExerciseTimer = null
  }
  if (!exerciseSet.value) {
    return
  }
  if (!currentSubmission.value) {
    ElMessage.warning('请先提交当前题目。')
    return
  }
  if (currentExerciseIndex.value < exerciseSet.value.exercises.length - 1) {
    currentExerciseIndex.value += 1
    if (!currentSubmission.value) {
      answerStartAt.value = Date.now()
    }
    return
  }
  markTaskCompleted('review')
  ElMessage.success('本组练习已完成，可以开始错题复盘。')
}

async function fetchMistakeNotebook() {
  loading.mistakes = true
  startAsyncStatus('mistakes', '错题本刷新')
  try {
    const userId = exerciseForm.user_id
    const { data } = await evaluationApi.get<ApiEnvelope<MistakeNotebook>>(`/evaluation/mistakes/${userId}/detail`)
    mistakeNotebook.value = mergeMistakeNotebook(data.data, userId)
  } catch {
    mistakeNotebook.value = rebuildMistakeNotebook()
    announceFallback('mistake-notebook', '错题本服务暂不可用，已切换到本地错题记录。')
  } finally {
    persistCurrentMistakeSnapshot()
    loading.mistakes = false
    resetAsyncStatus('mistakes')
  }
}

async function fetchRemedialExercises() {
  loading.remedial = true
  startAsyncStatus('remedial', '重练题生成')
  try {
    const userId = exerciseForm.user_id
    const { data } = await evaluationApi.get<ApiEnvelope<RemedialExerciseSet>>(`/evaluation/mistakes/${userId}/remedial`)
    remedialExerciseSet.value = data.data
    if (data.data.exercises.length > 0) {
      exerciseSet.value = {
        user_id: userId,
        knowledge_point: exerciseForm.knowledge_point,
        summary: data.data.summary,
        exercises: data.data.exercises.map((item) => ({
          exercise_id: item.exercise_id,
          knowledge_point: item.knowledge_point,
          question_type: item.question_type,
          difficulty: 'advanced',
          prompt: item.prompt,
          options: item.options,
          answer: item.answer,
          analysis: item.analysis,
        })),
      }
      resetExerciseSession()
      ElMessage.success('错题变式重练题已生成。')
    } else {
      ElMessage.info('当前还没有可生成的错题重练题。')
    }
  } catch {
    const notebook = rebuildMistakeNotebook(exerciseForm.user_id)
    const localExercises = notebook.items.map((item, index) => ({
      exercise_id: 9500 + index,
      knowledge_point: item.knowledge_point,
      question_type: item.question_type,
      prompt: `变式题 ${index + 1}：围绕 ${item.knowledge_point} 重新完成一道题，重点避免上次错误。`,
      options: item.question_type === 'choice'
        ? ['A. 关注边界条件', 'B. 按步骤拆解逻辑', 'C. 检查循环或判断条件', 'D. 对照示例验证结果']
        : [],
      answer: item.correct_answer,
      analysis: `本题用于针对性复练 ${item.knowledge_point}，帮助你修正同类错误。`,
      source_exercise_id: item.exercise_id,
    }))
    remedialExerciseSet.value = {
      user_id: exerciseForm.user_id,
      generated_from_mistakes: notebook.items.length,
      summary: '已根据本地错题记录生成变式重练题。',
      exercises: localExercises,
    }
    if (localExercises.length > 0) {
      exerciseSet.value = {
        user_id: exerciseForm.user_id,
        knowledge_point: exerciseForm.knowledge_point,
        summary: remedialExerciseSet.value.summary,
        exercises: localExercises.map((item) => ({
          exercise_id: item.exercise_id,
          knowledge_point: item.knowledge_point,
          question_type: item.question_type,
          difficulty: 'advanced',
          prompt: item.prompt,
          options: item.options,
          answer: item.answer,
          analysis: item.analysis,
        })),
      }
      resetExerciseSession()
      ElMessage.success('本地错题变式重练题已生成。')
    } else {
      ElMessage.info('当前还没有错题，暂时不能生成重练题。')
    }
    announceFallback('remedial-exercises', '错题重练服务暂不可用，已切换到本地变式题模式。')
  } finally {
    persistCurrentMistakeSnapshot()
    loading.remedial = false
    resetAsyncStatus('remedial')
  }
}

async function fetchReports() {
  loading.reports = true
  startAsyncStatus('reports', '学习报告刷新')
  try {
    const userId = exerciseForm.user_id
    const [stageResponse, comprehensiveResponse] = await Promise.all([
      evaluationApi.get<ApiEnvelope<ReportDetail>>(`/evaluation/reports/stage/${userId}/detail`),
      evaluationApi.get<ApiEnvelope<ReportDetail>>(`/evaluation/reports/comprehensive/${userId}/detail`),
    ])
    stageReport.value = stageResponse.data.data
    comprehensiveReport.value = comprehensiveResponse.data.data
  } catch {
    stageReport.value = buildFallbackReport('stage')
    comprehensiveReport.value = buildFallbackReport('comprehensive')
    announceFallback('learning-reports', '学习报告服务暂不可用，已切换到本地报告模式。')
  } finally {
    loading.reports = false
    resetAsyncStatus('reports')
  }
}

async function askQaAgent() {
  if (loading.qa) {
    return
  }
  applyLearningRequestToForms()
  if (!qaForm.question.trim()) {
    qaError.value = '请先输入你的问题，再开始智能回答。'
    return
  }
  loading.qa = true
  startAsyncStatus('qa', '智能回答')
  qaError.value = ''
  qaResult.value = null
  await nextTick()
  scrollToQaResult()
  try {
    qaForm.student_id = String(authStore.user?.userId ?? exerciseForm.user_id)
    qaForm.subject = pathForm.subject
    const learningQuestion = isLikelyLearningQuestion(qaForm.question)
    qaForm.current_knowledge_points = learningQuestion
      ? [pathForm.knowledge_point, exerciseForm.knowledge_point, resourceResult.value?.knowledge_point].filter(
          (item): item is string => Boolean(item && item.trim()),
        )
      : []
    qaForm.learning_route = learningQuestion ? (learningPath.value ?? {}) : {}
    qaForm.error_book = learningQuestion ? (mistakeNotebook.value ?? {}) : {}
    qaForm.learning_history = learningQuestion ? buildQaLearningHistory() : {}

    lastQaRequest.value = {
      ...qaForm,
      question: qaForm.question,
    }
    const { data } = await qaApi.post<EnvelopeLike<QAResponsePayload>>('/qa/analyze', qaForm)
    lastQaRawResponse.value = data
    qaResult.value = unwrapApiData(data)
    const addedToMistakeNotebook = syncQaMistakeRecord(qaResult.value, Number(qaForm.student_id) || exerciseForm.user_id)
    const syncedQaMistakeRemotely = addedToMistakeNotebook
      ? await syncQaMistakeRecordToEvaluation(qaResult.value, Number(qaForm.student_id) || exerciseForm.user_id)
      : false
    await nextTick()
    scrollToQaResult()
    ElMessage.success(
      syncedQaMistakeRemotely
        ? '智能回答结果已生成，并已同步到错题本和学习报告。'
        : addedToMistakeNotebook
          ? '智能回答结果已生成，并已同步到错题本。'
          : '智能回答结果已生成',
    )
  } catch (error) {
    const message =
      typeof error === 'object' &&
      error !== null &&
      'response' in error &&
      typeof (error as { response?: { data?: { detail?: string } } }).response?.data?.detail === 'string'
        ? (error as { response?: { data?: { detail?: string } } }).response?.data?.detail
        : ''
    qaResult.value = buildFallbackQaResponse()
    const addedToMistakeNotebook = syncQaMistakeRecord(qaResult.value, Number(qaForm.student_id) || exerciseForm.user_id)
    const syncedQaMistakeRemotely = addedToMistakeNotebook
      ? await syncQaMistakeRecordToEvaluation(qaResult.value, Number(qaForm.student_id) || exerciseForm.user_id)
      : false
    qaError.value = message
      ? `远程问答暂时不可用，当前已切换为本地回答模式：${message}`
      : '远程问答暂时不可用，当前已切换为本地回答模式。'
    lastQaRawResponse.value = error
    await nextTick()
    scrollToQaResult()
    if (syncedQaMistakeRemotely) {
      ElMessage.success('已根据本地问答结果同步更新错题本和学习报告。')
    } else if (addedToMistakeNotebook) {
      ElMessage.success('已根据本地问答结果同步更新错题本。')
    }
    announceFallback('qa-agent', '智能问答远程服务暂不可用，已切换为本地回答模式。')
  } finally {
    loading.qa = false
    resetAsyncStatus('qa')
  }
}

async function startRemedialFromMistake(knowledgePoint: string) {
  syncFormsWithKnowledgePoint(knowledgePoint)
  await fetchRemedialExercises()
}

async function logout() {
  authStore.clear()
  ElMessage.success('已退出登录。')
  await router.push({ name: 'login' })
}

onMounted(async () => {
  void checkHealth()
  await fetchCurrentUser()
  applyLearningRequestToForms()
  await Promise.all([
    generateLearningPath(),
    generateCourseware(),
    fetchMistakeNotebook(),
    fetchReports(),
  ])
})

onUnmounted(() => {
  if (autoAdvanceExerciseTimer) {
    clearTimeout(autoAdvanceExerciseTimer)
    autoAdvanceExerciseTimer = null
  }
  resetGenerationProgress()
  resetAsyncStatus()
})
</script>

<template>
  <div class="dashboard-shell student-workspace-shell">
    <div class="aurora aurora-a" />
    <div class="aurora aurora-b" />

    <header class="hero-panel">
      <div class="hero-copy">
        <div class="eyebrow">Student Workspace</div>
        <h1>个性化学习工作台</h1>
        <p>
          这里不再只是接口结果展示页。你可以直接查看学习路径、阅读课件、完成练习题、
          获取标准答案和解析，再进入错题复盘与阶段报告。
        </p>

        <div class="status-row">
          <div class="status-chip" :class="serviceStatus.user">
            <School class="chip-icon" />
            user-service: {{ serviceStatus.user }}
          </div>
          <div class="status-chip" :class="serviceStatus.agent">
            <Connection class="chip-icon" />
            agent-service: {{ serviceStatus.agent }}
          </div>
          <div class="status-chip" :class="serviceStatus.evaluation">
            <CircleCheck class="chip-icon" />
            evaluation-service: {{ serviceStatus.evaluation }}
          </div>
          <div class="status-chip checking">
            <Lock class="chip-icon" />
            {{ authStore.user?.username }} / {{ authStore.user?.role }}
          </div>
        </div>
      </div>

      <div class="hero-aside">
        <div class="signal-card">
          <div class="signal-title">当前掌握度</div>
          <div class="signal-metric">{{ learner.mastery }}</div>
          <div class="signal-caption">基于作答表现和画像得到的实时估计值</div>
        </div>
        <div class="signal-card">
          <div class="signal-title">任务完成度</div>
          <div class="signal-metric accent">{{ completionStats.completed }}/{{ completionStats.total || 4 }}</div>
          <div class="signal-caption">已完成任务 / 总任务数</div>
        </div>
      </div>
    </header>

    <section class="card-grid">
      <article v-for="card in systemCards" :key="card.title" class="metric-card">
        <component :is="card.icon" class="metric-icon" />
        <div class="metric-title">{{ card.title }}</div>
        <div class="metric-value">{{ card.value }}</div>
        <div class="metric-subtitle">{{ card.subtitle }}</div>
      </article>
    </section>

    <div v-if="globalStatusView" class="request-status-card global-status-banner" :class="globalStatusView.tone">
      <div class="global-status-layout">
        <div class="global-status-copy">
          <strong>{{ globalStatusView.title }}</strong>
          <p>{{ globalStatusView.detail }}</p>
        </div>
        <div class="global-status-side">
          <span>已等待 {{ globalStatusView.elapsedLabel }}</span>
          <div v-if="globalGenerationBannerView" class="global-progress-value">
            {{ globalGenerationBannerView.progress }}%
          </div>
        </div>
      </div>
      <div v-if="globalGenerationBannerView" class="global-progress-block">
        <div class="global-progress-meta">
          <span>{{ globalGenerationBannerView.label }} · {{ globalGenerationBannerView.statusLabel }}</span>
          <span>当前阶段：{{ globalGenerationBannerView.stageLabel }}</span>
        </div>
        <el-progress
          :percentage="globalGenerationBannerView.progress"
          :stroke-width="8"
          :show-text="false"
          striped
          striped-flow
          :duration="8"
        />
      </div>
    </div>

    <main class="workspace-grid student-grid">

      <section class="workspace-panel wide learning-request-panel">
        <div class="panel-heading">
          <div>
            <div class="panel-kicker">学习入口</div>
            <h2>先告诉系统你想学什么</h2>
          </div>
          <School class="panel-icon" />
        </div>
        <p class="panel-text">
          这里不再只固定围绕 Python 课件。你可以自由输入学科、想学习的内容和学习目标，再生成对应的学习路径、课件和练习题。
        </p>
        <div class="learning-request-grid">
          <el-input v-model="learningRequestForm.subject" placeholder="例如：Python 程序设计 / 高等数学 / 英语阅读" />
          <el-input v-model="learningRequestForm.topic" placeholder="例如：递归、极限、虚拟语气、牛顿第二定律" />
        </div>
        <el-input
          v-model="learningRequestForm.goal"
          type="textarea"
          :rows="3"
          placeholder="可选：填写你的学习目标，例如准备考试、先学基础、需要更多例题。"
        />
        <div class="action-row">
          <el-button type="primary" :loading="loading.path || loading.courseware" @click="startLearningPlan">
            开始生成学习内容
          </el-button>
          <el-button :loading="loading.coordinate" @click="runCoordination">生成协同计划</el-button>
        </div>
      </section>

      <section class="workspace-panel wide">
        <div class="panel-heading">
          <div>
            <div class="panel-kicker">学习路径</div>
            <h2>今日学习路线</h2>
          </div>
          <Promotion class="panel-icon" />
        </div>
        <p class="panel-text">{{ learningPath?.overview ?? '正在为你生成个性化学习路径。' }}</p>
        <div class="action-row">
          <el-button type="primary" :loading="loading.path" @click="generateLearningPath">刷新学习路径</el-button>
          <el-button type="success" :loading="loading.coordinate" @click="runCoordination">生成协同计划</el-button>
          <el-button plain @click="logout">退出登录</el-button>
        </div>

        <div v-if="pathStatusView" class="request-status-card" :class="pathStatusView.tone">
          <strong>{{ pathStatusView.title }}</strong>
          <p>{{ pathStatusView.detail }}</p>
          <span>已等待 {{ pathStatusView.elapsedLabel }}</span>
        </div>
        <div v-if="coordinationStatusView" class="request-status-card" :class="coordinationStatusView.tone">
          <strong>{{ coordinationStatusView.title }}</strong>
          <p>{{ coordinationStatusView.detail }}</p>
          <span>已等待 {{ coordinationStatusView.elapsedLabel }}</span>
        </div>
        <div v-if="learningPath" class="path-stage-list">
          <article v-for="stage in learningPath.stages" :key="stage.stage_id" class="stage-card">
            <div class="stage-header">
              <div>
                <div class="insight-label">{{ stage.title }}</div>
                <h3>{{ stage.description }}</h3>
              </div>
            </div>
            <div class="task-list">
              <button
                v-for="task in stage.tasks"
                :key="task.task_id"
                type="button"
                class="task-card"
                :class="{ active: activeTaskId === task.task_id, completed: task.completed }"
                @click="activeTaskId = task.task_id; syncFormsWithKnowledgePoint(task.knowledge_point)"
              >
                <div class="task-topline">
                  <strong>{{ task.title }}</strong>
                  <span>{{ task.estimated_minutes }} 分钟</span>
                </div>
                <p>{{ task.objective }}</p>
              </button>
            </div>
          </article>
        </div>
      </section>

      <div class="student-column student-column-main">
        <section class="workspace-panel">
          <div class="panel-heading">
            <div>
              <div class="panel-kicker">当前任务</div>
              <h2>{{ activeTask?.title ?? '等待任务' }}</h2>
            </div>
            <TrendCharts class="panel-icon" />
          </div>
          <div v-if="activeTask" class="insight-card">
            <div class="insight-label">任务目标</div>
            <div class="insight-value">{{ activeTask.objective }}</div>
            <p class="panel-text">
              难度：{{ activeTask.difficulty }} / 预计时长：{{ activeTask.estimated_minutes }} 分钟
            </p>
          </div>
          <div class="action-row">
            <el-button type="warning" :loading="loading.courseware" @click="generateCourseware()">生成学习课件</el-button>
            <el-button plain :disabled="loading.courseware" @click="generateCourseware()">重新生成课件</el-button>
            <el-button v-if="resourceResult" type="primary" plain @click="openCoursewarePage()">打开独立课件页</el-button>
            <el-button type="success" :loading="loading.exercises" @click="generateExercises()">生成课后自测</el-button>
            <el-button plain :disabled="loading.exercises" @click="generateExercises()">重新生成自测</el-button>
            <el-button type="danger" :loading="loading.remedial" @click="fetchRemedialExercises">错题变式重练</el-button>
            <el-button :loading="loading.graph" @click="queryGraph">查询知识图谱</el-button>
          </div>
        </section>

        <section class="workspace-panel">
          <div class="panel-heading">
            <div>
              <div class="panel-kicker">课件学习</div>
              <h2>{{ coursewareTitle }}</h2>
            </div>
            <Document class="panel-icon" />
          </div>
          <div v-if="generationStatus.courseware.hint" class="generation-hint courseware-progress-panel">
            <div class="courseware-progress-header">
              <div>
                <div class="generation-hint-title">课件生成进度</div>
                <p class="courseware-progress-meta">模型会根据当前学习目标和知识点直接生成正式课件内容。</p>
              </div>
              <strong class="courseware-progress-percentage">{{ generationStatus.courseware.progress }}%</strong>
            </div>
            <div class="generation-status-row">
              <span class="generation-status-pill">{{ coursewareProgressView.statusLabel }}</span>
              <span class="generation-status-pill">已耗时 {{ coursewareProgressView.elapsedLabel }}</span>
              <span class="generation-status-pill">{{ coursewareProgressView.remainingLabel }}</span>
            </div>
            <div class="generation-hint-line">
              <span class="generation-hint-dot" :class="{ running: loading.courseware }"></span>
              <span>{{ coursewareProgressView.title }}</span>
              <strong>阶段 {{ coursewareProgressView.stageIndex }}/{{ coursewareProgressView.totalStages }}</strong>
            </div>
            <p class="generation-stage-detail">{{ generationStatus.courseware.hint }}</p>
            <p class="generation-stage-note">{{ coursewareProgressView.detail }}</p>
            <el-progress
              :percentage="generationStatus.courseware.progress"
              :stroke-width="12"
              :show-text="false"
              striped
              striped-flow
              :duration="8"
            />
            <div class="generation-step-list">
              <div
                v-for="step in coursewareProgressView.steps"
                :key="`courseware-step-${step.index}`"
                class="generation-step-card"
                :class="step.state"
              >
                <span class="generation-step-index">{{ step.index }}</span>
                <div class="generation-step-copy">
                  <strong>{{ step.title }}</strong>
                  <p>{{ step.description }}</p>
                </div>
              </div>
            </div>
          </div>
          <div v-if="coursewareGenerationError" class="feedback-card wrong">
            <div class="insight-label">课件生成状态</div>
            <div class="insight-value">本次生成失败</div>
            <p class="panel-text">{{ coursewareGenerationError }}</p>
          </div>
          <div v-if="resourceResult" class="courseware-entry-layout">
            <aside class="reader-outline">
              <div class="insight-label">课件目录预览</div>
              <div class="outline-list">
                <button
                  v-for="heading in coursewareOutline"
                  :key="heading"
                  type="button"
                  class="outline-item static"
                >
                  {{ heading }}
                </button>
              </div>
            </aside>

            <div class="learning-content reader-content">
              <article class="learning-section courseware-entry-card">
                <h3>课件已移至独立页面</h3>
                <div class="tag-row">
                  <span class="agent-tag">正式课件</span>
                  <span class="agent-tag">独立阅读</span>
                  <span class="agent-tag">{{ resourceSections.length }} 个章节</span>
                </div>
                <p class="learning-line">
                  当前工作台只保留课件生成状态和目录预览，完整课件正文已经放到单独网页里，便于专注阅读和后续继续生成练习题。
                </p>
                <div class="action-row">
                  <el-button type="primary" @click="openCoursewarePage()">进入独立课件页</el-button>
                  <el-button plain @click="generateExercises()">基于当前课件生成练习题</el-button>
                </div>
              </article>

              <article v-if="coursewareVariants.length > 1" class="learning-section">
                <h3>可选课件版本</h3>
                <div class="reference-list">
                  <article
                    v-for="variant in coursewareVariants"
                    :key="variant.variant_id"
                    class="reference-card clickable-card"
                    :class="{ active: activeCoursewareVariant?.variant_id === variant.variant_id }"
                    @click="selectCoursewareVariant(variant.variant_id)"
                  >
                    <strong>{{ variant.title }}</strong>
                    <p>{{ variant.summary }}</p>
                    <span class="reference-meta">
                      风格：{{ variant.resource_style }}
                      <template v-if="variant.is_recommended"> · 推荐</template>
                    </span>
                  </article>
                </div>
              </article>

              <article v-if="coursewarePersonalization" class="learning-section">
                <h3>本次个性化依据</h3>
                <div class="report-evidence-grid">
                  <div class="report-evidence-card">
                    <span>当前掌握度</span>
                    <strong>{{ coursewarePersonalization.mastery_score }}/100</strong>
                  </div>
                  <div class="report-evidence-card">
                    <span>近期正确率</span>
                    <strong>{{ coursewarePersonalization.correct_rate }}%</strong>
                  </div>
                  <div class="report-evidence-card">
                    <span>真实作答次数</span>
                    <strong>{{ coursewarePersonalization.answered_count }}</strong>
                  </div>
                  <div class="report-evidence-card">
                    <span>近期弱项题型</span>
                    <strong>{{ coursewarePersonalization.weak_question_types.length || 0 }}</strong>
                  </div>
                </div>
                <ul class="markdown-list">
                  <li v-for="item in coursewarePersonalization.basis" :key="item">{{ item }}</li>
                </ul>
              </article>
            </div>
          </div>
          <div v-else class="empty-state">点击“生成学习课件”后，这里会出现可直接阅读的学习内容。</div>
        </section>

        <section class="workspace-panel">
          <div class="panel-heading">
            <div>
              <div class="panel-kicker">在线练习</div>
              <h2>刷题与作答</h2>
            </div>
            <EditPen class="panel-icon" />
          </div>
          <div class="practice-toolbar">
            <el-button type="success" :loading="loading.exercises" @click="generateExercises()">生成课后自测</el-button>
            <el-button plain :disabled="loading.exercises" @click="generateExercises()">重新生成本轮题目</el-button>
            <span class="practice-toolbar-tip">先生成学习课件，再在这里直接生成围绕当前课件内容的自测题。每次点击都会重新请求后端生成。</span>
          </div>
          <div v-if="generationStatus.exercises.hint" class="generation-hint compact">
            <div class="generation-hint-title">自测题生成进度</div>
            <div class="generation-status-row">
              <span class="generation-status-pill">{{ exerciseProgressView.statusLabel }}</span>
              <span class="generation-status-pill">已耗时 {{ exerciseProgressView.elapsedLabel }}</span>
              <span class="generation-status-pill">{{ exerciseProgressView.remainingLabel }}</span>
            </div>
            <div class="generation-hint-line">
              <span class="generation-hint-dot" :class="{ running: loading.exercises }"></span>
              <span>{{ exerciseProgressView.title }}</span>
              <strong>{{ generationStatus.exercises.progress }}%</strong>
            </div>
            <p class="generation-stage-detail">{{ generationStatus.exercises.hint }}</p>
            <p class="generation-stage-note">{{ exerciseProgressView.detail }}</p>
            <el-progress
              :percentage="generationStatus.exercises.progress"
              :stroke-width="10"
              :show-text="false"
              striped
              striped-flow
              :duration="8"
            />
            <div class="generation-step-list">
              <div
                v-for="step in exerciseProgressView.steps"
                :key="`exercise-step-${step.index}`"
                class="generation-step-card"
                :class="step.state"
              >
                <span class="generation-step-index">{{ step.index }}</span>
                <div class="generation-step-copy">
                  <strong>{{ step.title }}</strong>
                  <p>{{ step.description }}</p>
                </div>
              </div>
            </div>
          </div>
          <div ref="exerciseResultAnchor" />
          <div v-if="loading.exercises && exerciseSet?.exercises?.length" class="insight-card">
            <div class="insight-label">题组生成状态</div>
            <div class="insight-value">正在准备题目</div>
            <p class="panel-text">已经先为你展示一版可作答题组，页面正在继续等待更完整的正式结果。</p>
          </div>
          <div v-if="exerciseSet?.exercises?.length" class="insight-card">
            <div class="insight-label">本轮题组</div>
            <div class="insight-value">已生成 {{ exerciseSet.exercises.length }} 道题</div>
            <p class="panel-text">{{ exerciseSet.summary }}</p>
            <p v-if="exerciseDeliveryMode === 'upgrading'" class="panel-text">当前先展示快速版题组，后台仍在继续请求正式版题目。</p>
          </div>
          <div v-else-if="exerciseGenerationError" class="feedback-card wrong">
            <div class="insight-label">题目生成结果</div>
            <div class="insight-value">没有拿到可展示的题目</div>
            <p class="panel-text">{{ exerciseGenerationError }}</p>
          </div>
          <article v-if="exercisePersonalization" class="learning-section">
            <h3>本次题组依据</h3>
            <div class="report-evidence-grid">
              <div class="report-evidence-card"><span>当前掌握度</span><strong>{{ exercisePersonalization.mastery_score }}/100</strong></div>
              <div class="report-evidence-card"><span>近期正确率</span><strong>{{ exercisePersonalization.correct_rate }}%</strong></div>
              <div class="report-evidence-card"><span>真实作答次数</span><strong>{{ exercisePersonalization.answered_count }}</strong></div>
              <div class="report-evidence-card"><span>最近错题数</span><strong>{{ exercisePersonalization.recent_mistakes.length }}</strong></div>
            </div>
            <ul class="markdown-list">
              <li v-for="item in exercisePersonalization.basis" :key="item">{{ item }}</li>
            </ul>
            <div v-if="exercisePersonalization.weak_question_types.length" class="tag-row">
              <span v-for="item in exercisePersonalization.weak_question_types" :key="`exercise-weak-${item}`" class="agent-tag">
                {{ formatQuestionTypeLabel(item) }}
              </span>
            </div>
            <div v-if="exercisePersonalization.recent_mistakes.length" class="reference-list">
              <article v-for="mistake in exercisePersonalization.recent_mistakes" :key="`exercise-mistake-${mistake.exercise_id}`" class="reference-card">
                <strong>{{ formatQuestionTypeLabel(mistake.question_type) }} / {{ formatDifficultyLabel(mistake.difficulty) }}</strong>
                <p>{{ mistake.prompt }}</p>
                <p>错因依据：{{ mistake.analysis }}</p>
              </article>
            </div>
          </article>
          <template v-if="currentExercise">
            <div class="exercise-head">
              <div class="agent-tag">{{ currentExercise.question_type }}</div>
              <div class="agent-tag">{{ currentExercise.difficulty }}</div>
              <div class="agent-tag">第 {{ currentExerciseIndex + 1 }} / {{ exerciseSet?.exercises.length }}</div>
              <div class="agent-tag">已提交 {{ answeredCount }} 题</div>
            </div>
            <div v-if="currentSubmission" class="insight-card">
              <div class="insight-label">作答状态</div>
              <div class="insight-value">本题已提交，不能再次作答</div>
              <p class="panel-text">你的答案已经锁定。系统会自动进入下一题，你也可以先查看标准答案与解析。</p>
            </div>
            <div class="exercise-card">
              <h3>{{ currentExercise.prompt }}</h3>
              <div v-if="currentExercise.options.length" class="option-list">
                <label v-for="option in currentExercise.options" :key="option" class="option-item">
                  <input v-model="currentAnswerDraft" type="radio" :value="option.charAt(0)" :disabled="Boolean(currentSubmission)" />
                  <span>{{ option }}</span>
                </label>
              </div>
              <el-input v-else v-model="currentAnswerDraft" type="textarea" :rows="5" :disabled="Boolean(currentSubmission)" placeholder="请输入你的答案" />
            </div>
            <div class="action-row">
              <el-button type="primary" :loading="loading.submit" :disabled="Boolean(currentSubmission)" @click="submitPractice">提交答案</el-button>
              <el-button :disabled="!currentSubmission" @click="goToNextExercise">下一题</el-button>
            </div>
            <div v-if="currentSubmission" class="feedback-card" :class="{ correct: currentSubmission.feedback.is_correct, wrong: !currentSubmission.feedback.is_correct }">
              <div class="insight-label">即时反馈</div>
              <div class="insight-value">{{ currentSubmission.feedback.is_correct ? '回答正确' : '需要继续巩固' }}</div>
              <p class="panel-text">得分：{{ currentSubmission.feedback.score }}</p>
              <p class="panel-text">反馈：{{ currentSubmission.feedback.feedback }}</p>
              <p class="panel-text">建议：{{ currentSubmission.feedback.suggested_action }}</p>
              <p v-if="currentSubmission.feedback.mastery_after_update !== null" class="panel-text">提交后掌握度更新为：{{ currentSubmission.feedback.mastery_after_update }}/100</p>
              <p class="panel-text"><strong>你的答案：</strong>{{ currentSubmission.userAnswer }}</p>
              <p class="panel-text"><strong>标准答案：</strong>{{ currentSubmission.correctAnswer }}</p>
              <p class="panel-text"><strong>解析：</strong>{{ currentSubmission.analysis }}</p>
            </div>
          </template>
          <div v-else class="empty-state">点击“生成课后自测”后，这里会出现围绕当前课件内容生成的结构化题目与答题入口。</div>
        </section>

        <section class="workspace-panel mistake-entry-panel">
          <div class="panel-heading">
            <div>
              <div class="panel-kicker">错题本</div>
              <h2>复盘与重练入口</h2>
            </div>
            <CircleCheck class="panel-icon" />
          </div>
          <div class="action-row">
            <el-button :loading="loading.mistakes" @click="fetchMistakeNotebook">刷新错题本</el-button>
            <el-button type="danger" :loading="loading.remedial" @click="fetchRemedialExercises">生成变式重练题</el-button>
            <el-button
              v-if="mistakeNotebook || remedialExerciseSet"
              type="primary"
              plain
              @click="openMistakeNotebookPage()"
            >
              打开独立错题页
            </el-button>
          </div>
          <div v-if="mistakeStatusView" class="request-status-card" :class="mistakeStatusView.tone">
            <strong>{{ mistakeStatusView.title }}</strong>
            <p>{{ mistakeStatusView.detail }}</p>
            <span>已等待 {{ mistakeStatusView.elapsedLabel }}</span>
          </div>
          <div v-if="mistakeNotebook || remedialExerciseSet" class="courseware-entry-layout mistake-entry-layout">
            <aside class="reader-outline">
              <div class="insight-label">错题预览</div>
              <div class="outline-list">
                <button
                  v-for="(item, index) in mistakeNotebook?.items.slice(0, 6) ?? []"
                  :key="`${item.exercise_id}-${index}`"
                  type="button"
                  class="outline-item static"
                >
                  {{ item.knowledge_point }} / {{ formatQuestionTypeLabel(item.question_type) }}
                </button>
              </div>
            </aside>

            <div class="learning-content reader-content">
              <article class="learning-section courseware-entry-card">
                <h3>错题复盘与重练已移至独立页面</h3>
                <div class="tag-row">
                  <span class="agent-tag">错题 {{ mistakeNotebook?.mistake_count ?? 0 }} 条</span>
                  <span class="agent-tag">重练 {{ remedialCount }} 题</span>
                  <span class="agent-tag">独立复盘</span>
                </div>
                <p class="learning-line">
                  当前工作台只保留错题概览和进入入口，完整错题内容、标准答案、解析建议和变式重练结果已经放到独立网页里，便于集中复盘。
                </p>
                <div class="action-row">
                  <el-button type="primary" @click="openMistakeNotebookPage()">进入独立错题页</el-button>
                  <el-button plain @click="fetchRemedialExercises">继续生成变式重练题</el-button>
                </div>
              </article>

              <article v-if="mistakeNotebook?.items.length" class="learning-section">
                <h3>当前优先复盘</h3>
                <div class="reference-list">
                  <article class="reference-card">
                    <strong>
                      {{ mistakeNotebook.items[0].knowledge_point }} /
                      {{ formatQuestionTypeLabel(mistakeNotebook.items[0].question_type) }}
                    </strong>
                    <p>你的答案：{{ mistakeNotebook.items[0].user_answer }}</p>
                    <p>标准答案：{{ mistakeNotebook.items[0].correct_answer }}</p>
                    <p>错因分析：{{ mistakeNotebook.items[0].analysis }}</p>
                    <p>建议动作：{{ mistakeNotebook.items[0].suggested_action }}</p>
                  </article>
                </div>
              </article>

              <article v-if="remedialCount" class="learning-section">
                <h3>最近一轮重练摘要</h3>
                <div class="report-evidence-grid compact">
                  <div class="report-evidence-card">
                    <span>已生成题目</span>
                    <strong>{{ remedialCount }}</strong>
                  </div>
                  <div class="report-evidence-card">
                    <span>来源错题</span>
                    <strong>{{ remedialExerciseSet?.generated_from_mistakes ?? 0 }}</strong>
                  </div>
                </div>
                <p class="learning-line">{{ remedialExerciseSet?.summary }}</p>
              </article>

              <article v-if="remedialExerciseSet?.exercises.length" class="learning-section">
                <h3>最近生成的变式题预览</h3>
                <div class="reference-list">
                  <article
                    v-for="exercise in remedialExerciseSet.exercises.slice(0, 3)"
                    :key="`student-remedial-preview-${exercise.exercise_id}`"
                    class="reference-card"
                  >
                    <strong>{{ exercise.knowledge_point }} / {{ formatQuestionTypeLabel(exercise.question_type) }}</strong>
                    <p>{{ exercise.prompt }}</p>
                    <span class="reference-meta">进入独立错题页后可直接作答，提交后再显示答案与解析</span>
                  </article>
                </div>
              </article>
            </div>
          </div>
          <div v-else class="empty-state">当前还没有错题记录，继续保持。</div>
        </section>
      </div>

      <div class="student-column student-column-side">
        <section class="workspace-panel">
          <div class="panel-heading">
            <div>
              <div class="panel-kicker">学习画像</div>
              <h2>能力雷达与掌握热力图</h2>
            </div>
            <TrendCharts class="panel-icon" />
          </div>
          <div class="action-row">
            <el-button @click="fetchProfileDashboard()">刷新画像</el-button>
          </div>
          <article class="learning-section profile-chat-section">
            <h3>画像对话构建</h3>
            <p class="learning-line">用自然语言告诉系统你学过什么、怎么学得更顺、最近想达成什么目标，系统会自动补全学习画像。</p>
            <el-input v-model="profileChatMessage" type="textarea" :rows="4" placeholder="例如：我学过 Python 基础，喜欢边写边学，最近想冲刺后端实习。" />
            <div class="action-row">
              <el-button type="primary" :loading="loading.profileChat" @click="submitProfileChat">提交画像对话</el-button>
            </div>
            <p v-if="profileChatError" class="feedback-inline danger">{{ profileChatError }}</p>
          </article>
          <div v-if="profileStatusView" class="request-status-card" :class="profileStatusView.tone">
            <strong>{{ profileStatusView.title }}</strong>
            <p>{{ profileStatusView.detail }}</p>
            <span>已等待 {{ profileStatusView.elapsedLabel }}</span>
          </div>
          <div v-if="profileDashboard" class="learning-content">
            <article v-if="profileChatResult" class="learning-section">
              <h3>本轮画像提取结果</h3>
              <p class="learning-line preserve-linebreaks">{{ profileChatResult.reply }}</p>
              <div v-if="Object.keys(profileChatResult.profile_updates).length" class="tag-row">
                <span v-for="(value, key) in profileChatResult.profile_updates" :key="key" class="agent-tag">{{ key }}: {{ value }}</span>
              </div>
              <p class="learning-line">预计还需 {{ profileChatResult.estimated_remaining_rounds }} 轮可基本补全画像。</p>
            </article>
            <article class="learning-section">
              <h3>画像摘要</h3>
              <p class="learning-line">学习风格：{{ profileDashboard.learning_style }}</p>
              <p class="learning-line">近期学习习惯：{{ profileDashboard.habit_summary }}</p>
              <p class="learning-line">本周专注时长：{{ profileDashboard.weekly_focus_minutes }} 分钟</p>
            </article>
            <article class="learning-section">
              <h3>能力雷达</h3>
              <div class="metric-stack">
                <div v-for="item in radarMetrics" :key="item.dimension" class="progress-row">
                  <div class="progress-label">
                    <span>{{ item.dimension }}</span>
                    <strong>{{ item.score }}</strong>
                  </div>
                  <el-progress :percentage="item.score" :stroke-width="12" :show-text="false" />
                </div>
              </div>
            </article>
            <article class="learning-section">
              <h3>知识点热力图</h3>
              <div class="heatmap-grid">
                <div v-for="item in heatmapMetrics" :key="item.knowledge_point" class="heatmap-cell" :style="{ opacity: `${Math.max(0.38, item.mastery / 100)}` }">
                  <strong>{{ item.knowledge_point }}</strong>
                  <span>{{ item.mastery }}%</span>
                </div>
              </div>
            </article>
          </div>
          <div v-else class="empty-state">正在加载学习画像。</div>
        </section>

        <section class="workspace-panel">
          <div class="panel-heading">
            <div>
              <div class="panel-kicker">知识图谱</div>
              <h2>前置依赖</h2>
            </div>
            <Connection class="panel-icon" />
          </div>
          <div v-if="graphStatusView" class="request-status-card" :class="graphStatusView.tone">
            <strong>{{ graphStatusView.title }}</strong>
            <p>{{ graphStatusView.detail }}</p>
            <span>已等待 {{ graphStatusView.elapsedLabel }}</span>
          </div>
          <template v-if="dependencyPaths.length || graphVisualization?.nodes.length">
            <div v-if="dependencyPaths.length" class="dependency-list">
              <article v-for="(path, index) in dependencyPaths" :key="`path-${index}`" class="dependency-card">
                <div class="insight-label">依赖链 {{ index + 1 }}</div>
                <div class="dependency-flow">
                  <span v-for="(node, nodeIndex) in path" :key="`${node}-${nodeIndex}`" class="dependency-node">{{ node }}</span>
                </div>
              </article>
            </div>
            <div ref="graphCanvas" class="graph-canvas" />
          </template>
          <div v-else class="empty-state">点击“查询知识图谱”后，这里会展示当前知识点的依赖链。</div>
        </section>

        <section class="workspace-panel sidebar-briefing-panel">
          <div class="panel-heading">
            <div>
              <div class="panel-kicker">学习总览</div>
              <h2>本轮状态</h2>
            </div>
            <CircleCheck class="panel-icon" />
          </div>
          <div class="sidebar-metric-grid">
            <article v-for="item in sidebarOverviewMetrics" :key="item.label" class="sidebar-metric-card">
              <span>{{ item.label }}</span>
              <strong>{{ item.value }}</strong>
              <p>{{ item.hint }}</p>
            </article>
          </div>

          <article class="learning-section">
            <h3>生成进度</h3>
            <div v-if="sidebarGenerationItems.length" class="sidebar-progress-list">
              <div v-for="item in sidebarGenerationItems" :key="item.label" class="sidebar-progress-card">
                <div class="sidebar-progress-topline">
                  <strong>{{ item.label }}</strong>
                  <span>{{ item.status }}</span>
                </div>
                <p>{{ item.detail }}</p>
                <el-progress :percentage="item.progress" :stroke-width="10" :show-text="false" />
              </div>
            </div>
            <div v-else class="empty-state compact">开始生成课件或练习后，这里会实时显示进度。</div>
          </article>

          <article class="learning-section">
            <h3>接下来建议</h3>
            <ul class="markdown-list">
              <li v-for="item in sidebarActionItems" :key="item">{{ item }}</li>
            </ul>
          </article>

          <article v-if="stageReport" class="learning-section">
            <h3>阶段速览</h3>
            <p class="learning-line">{{ stageReport.summary }}</p>
            <div class="report-evidence-grid compact">
              <div class="report-evidence-card">
                <span>正确率</span>
                <strong>{{ stageReport.evidence.accuracy }}%</strong>
              </div>
              <div class="report-evidence-card">
                <span>作答</span>
                <strong>{{ stageReport.evidence.total_answers }}</strong>
              </div>
              <div class="report-evidence-card">
                <span>平均耗时</span>
                <strong>{{ stageReport.evidence.average_time_spent }} 秒</strong>
              </div>
              <div class="report-evidence-card">
                <span>错题</span>
                <strong>{{ stageReport.evidence.mistake_count }}</strong>
              </div>
            </div>
            <p v-if="stageReport.evidence.weakest_knowledge_point" class="learning-line">
              当前薄弱点：{{ stageReport.evidence.weakest_knowledge_point }}
            </p>
          </article>
        </section>
      </div>

      <section class="workspace-panel wide">
        <div class="panel-heading">
          <div>
            <div class="panel-kicker">智能问答</div>
            <h2>提问、回答与按需分析</h2>
          </div>
          <MagicStick class="panel-icon" />
        </div>
        <div class="learning-content">
          <article class="learning-section">
            <h3>提问输入</h3>
            <el-input
              v-model="qaForm.question"
              type="textarea"
              :rows="4"
              placeholder="请输入任何你想问的问题；学习类问题会附带分析，通用问题会直接回答。"
            />
            <div class="action-row">
              <el-input
                v-model="qaForm.student_answer"
                placeholder="可选：填写你自己的答案或思路"
              />
              <el-input
                v-model="qaForm.wrong_answer"
                placeholder="可选：填写你的错误答案"
              />
            </div>
            <div class="action-row">
              <el-button type="primary" :loading="loading.qa" @click="askQaAgent">开始智能回答</el-button>
            </div>
          </article>

          <article v-if="qaStatusView" class="learning-section">
            <h3>{{ qaStatusView.title }}</h3>
            <p class="learning-line">{{ qaStatusView.detail }}</p>
            <p class="panel-text">已等待 {{ qaStatusView.elapsedLabel }}</p>
          </article>

          <article v-if="loading.qa" ref="qaResultAnchor" class="learning-section">
            <h3>问答处理中</h3>
            <p class="learning-line">正在生成回答；如果问题需要联网信息，系统会优先检索参考结果后再作答。若远程服务较慢，页面会自动切换到本地回答模式。</p>
          </article>

          <article v-if="qaResult" ref="qaResultAnchor" class="learning-section">
            <h3>智能回答</h3>
            <p class="learning-line preserve-linebreaks">{{ qaResult.student_response }}</p>
          </article>

          <article v-else-if="qaError" ref="qaResultAnchor" class="learning-section">
            <h3>答疑状态</h3>
            <p class="learning-line">{{ qaError }}</p>
          </article>

          <template v-if="qaResult && showQaLearningAnalysis">
            <article class="learning-section">
              <h3>系统识别出的知识漏洞</h3>
              <div class="tag-row">
                <span v-for="item in qaKnowledgeGaps" :key="item" class="agent-tag">{{ item }}</span>
              </div>
              <p class="learning-line">{{ qaResult.structured_analysis.learning_state }}</p>
            </article>

            <article class="learning-section">
              <h3>可能存在的思维误区</h3>
              <ul class="markdown-list">
                <li v-for="item in qaMisconceptions" :key="item">{{ item }}</li>
              </ul>
            </article>

            <article class="learning-section">
              <h3>学习路线更新建议</h3>
              <div v-if="qaRouteUpdates.length" class="reference-list">
                <article v-for="item in qaRouteUpdates" :key="`${item.knowledge_point}-${item.priority}`" class="reference-card">
                  <strong>{{ item.knowledge_point }} / {{ item.priority }}</strong>
                  <p>建议动作：{{ item.action }}</p>
                  <p>原因：{{ item.reason }}</p>
                </article>
              </div>
              <div v-else class="empty-state compact">当前没有额外的路线调整建议。</div>
            </article>

            <article class="learning-section">
              <h3>个性化推荐</h3>
              <div class="reference-list">
                <article v-for="item in qaRecommendations" :key="`${item.resource_type}-${item.title}`" class="reference-card">
                  <strong>{{ item.title }}</strong>
                  <p>类型：{{ item.resource_type }}</p>
                  <p>推荐理由：{{ item.reason }}</p>
                </article>
              </div>
            </article>

            <article class="learning-section">
              <h3>学习建议</h3>
              <ul class="markdown-list">
                <li v-for="item in qaStudySuggestions" :key="item">{{ item }}</li>
              </ul>
              <div v-if="qaResult.structured_analysis.mistake_book_update.should_add" class="insight-card">
                <div class="insight-label">错题本更新建议</div>
                <div class="insight-value">
                  建议加入错题本
                </div>
                <p class="panel-text">题目摘要：{{ qaResult.structured_analysis.mistake_book_update.question_summary }}</p>
                <p class="panel-text">错误原因：{{ qaResult.structured_analysis.mistake_book_update.wrong_reason }}</p>
                <p class="panel-text">正确思路：{{ qaResult.structured_analysis.mistake_book_update.correct_approach }}</p>
              </div>
            </article>
          </template>
        </div>
      </section>

      <section class="workspace-panel wide">
        <div class="panel-heading">
          <div>
            <div class="panel-kicker">学习报告</div>
            <h2>阶段与综合反馈</h2>
          </div>
          <TrendCharts class="panel-icon" />
        </div>
        <div class="action-row">
          <el-button :loading="loading.reports" @click="fetchReports">刷新报告</el-button>
        </div>
        <div v-if="reportStatusView" class="request-status-card" :class="reportStatusView.tone">
          <strong>{{ reportStatusView.title }}</strong>
          <p>{{ reportStatusView.detail }}</p>
          <span>已等待 {{ reportStatusView.elapsedLabel }}</span>
        </div>

        <div class="report-grid">
          <article v-if="stageReport" class="learning-section">
            <h3>{{ stageReport.title }}</h3>
            <p class="learning-line">{{ stageReport.summary }}</p>
            <div class="report-evidence-grid">
              <div class="report-evidence-card">
                <span>作答次数</span>
                <strong>{{ stageReport.evidence.total_answers }}</strong>
              </div>
              <div class="report-evidence-card">
                <span>正确率</span>
                <strong>{{ stageReport.evidence.accuracy }}%</strong>
              </div>
              <div class="report-evidence-card">
                <span>平均耗时</span>
                <strong>{{ stageReport.evidence.average_time_spent }} 秒</strong>
              </div>
              <div class="report-evidence-card">
                <span>错题数量</span>
                <strong>{{ stageReport.evidence.mistake_count }}</strong>
              </div>
            </div>
            <div
              v-if="stageReport.evidence.weakest_knowledge_point || stageReport.evidence.weakest_question_types.length"
              class="report-block evidence-block"
            >
              <strong>报告依据</strong>
              <p v-if="stageReport.evidence.weakest_knowledge_point" class="learning-line">
                当前最薄弱知识点：{{ stageReport.evidence.weakest_knowledge_point }}
                <span v-if="stageReport.evidence.weakest_knowledge_accuracy !== null">
                  （正确率 {{ stageReport.evidence.weakest_knowledge_accuracy }}%）
                </span>
              </p>
              <p v-if="stageReport.evidence.weakest_question_types.length" class="learning-line">
                当前更容易失分的题型：{{ stageReport.evidence.weakest_question_types.join('、') }}
              </p>
              <p v-if="stageReport.evidence.strongest_question_types.length" class="learning-line">
                当前相对稳定的题型：{{ stageReport.evidence.strongest_question_types.join('、') }}
              </p>
            </div>
            <div v-if="stageReport.evidence.latest_mistake" class="report-block evidence-block">
              <strong>最近一次错题</strong>
              <p class="learning-line">
                {{ stageReport.evidence.latest_mistake.knowledge_point }} /
                {{ stageReport.evidence.latest_mistake.question_type }}
              </p>
              <p class="learning-line">你的答案：{{ stageReport.evidence.latest_mistake.user_answer }}</p>
              <p class="learning-line">标准答案：{{ stageReport.evidence.latest_mistake.correct_answer }}</p>
              <p class="learning-line">问题分析：{{ stageReport.evidence.latest_mistake.analysis }}</p>
            </div>
            <div class="report-block">
              <strong>当前优势</strong>
              <p v-for="item in stageReport.strengths" :key="item" class="learning-line">{{ item }}</p>
            </div>
            <div class="report-block">
              <strong>当前薄弱点</strong>
              <p v-for="item in stageReport.weaknesses" :key="item" class="learning-line">{{ item }}</p>
            </div>
            <div class="report-block">
              <strong>下一步建议</strong>
              <p v-for="item in stageReport.next_actions" :key="item" class="learning-line">{{ item }}</p>
            </div>
          </article>

          <article v-if="comprehensiveReport" class="learning-section">
            <h3>{{ comprehensiveReport.title }}</h3>
            <p class="learning-line">{{ comprehensiveReport.summary }}</p>
            <div class="report-evidence-grid">
              <div class="report-evidence-card">
                <span>累计作答</span>
                <strong>{{ comprehensiveReport.evidence.total_answers }}</strong>
              </div>
              <div class="report-evidence-card">
                <span>综合正确率</span>
                <strong>{{ comprehensiveReport.evidence.accuracy }}%</strong>
              </div>
              <div class="report-evidence-card">
                <span>平均得分</span>
                <strong>{{ comprehensiveReport.evidence.average_score }}</strong>
              </div>
              <div class="report-evidence-card">
                <span>累计错题</span>
                <strong>{{ comprehensiveReport.evidence.mistake_count }}</strong>
              </div>
            </div>
            <div
              v-if="comprehensiveReport.evidence.weakest_knowledge_point || comprehensiveReport.evidence.weakest_question_types.length"
              class="report-block evidence-block"
            >
              <strong>综合趋势依据</strong>
              <p v-if="comprehensiveReport.evidence.weakest_knowledge_point" class="learning-line">
                当前最需要补强的知识点：{{ comprehensiveReport.evidence.weakest_knowledge_point }}
                <span v-if="comprehensiveReport.evidence.weakest_knowledge_accuracy !== null">
                  （正确率 {{ comprehensiveReport.evidence.weakest_knowledge_accuracy }}%）
                </span>
              </p>
              <p v-if="comprehensiveReport.evidence.weakest_question_types.length" class="learning-line">
                当前需要重点训练的题型：{{ comprehensiveReport.evidence.weakest_question_types.join('、') }}
              </p>
              <p v-if="comprehensiveReport.evidence.strongest_question_types.length" class="learning-line">
                当前表现最稳定的题型：{{ comprehensiveReport.evidence.strongest_question_types.join('、') }}
              </p>
            </div>
            <div class="report-block">
              <strong>综合优势</strong>
              <p v-for="item in comprehensiveReport.strengths" :key="item" class="learning-line">{{ item }}</p>
            </div>
            <div class="report-block">
              <strong>综合薄弱点</strong>
              <p v-for="item in comprehensiveReport.weaknesses" :key="item" class="learning-line">{{ item }}</p>
            </div>
            <div class="report-block">
              <strong>综合建议</strong>
              <p v-for="item in comprehensiveReport.next_actions" :key="item" class="learning-line">{{ item }}</p>
            </div>
          </article>
        </div>
      </section>

      <section class="workspace-panel wide">
        <div class="panel-heading">
          <div>
            <div class="panel-kicker">调试详情</div>
            <h2>服务原始响应</h2>
          </div>
          <MagicStick class="panel-icon" />
        </div>
        <details class="debug-panel">
          <summary>查看协调调度响应</summary>
          <pre class="result-box">{{ JSON.stringify(coordinationResult, null, 2) }}</pre>
        </details>
        <details class="debug-panel">
          <summary>查看资源生成响应</summary>
          <pre class="result-box">{{ JSON.stringify(resourceResult, null, 2) }}</pre>
        </details>
        <details class="debug-panel">
          <summary>查看课件生成请求</summary>
          <pre class="result-box">{{ JSON.stringify(lastCoursewareRequest, null, 2) }}</pre>
        </details>
        <details class="debug-panel">
          <summary>查看课件生成原始响应</summary>
          <pre class="result-box">{{ JSON.stringify(lastCoursewareRawResponse, null, 2) }}</pre>
        </details>
        <details class="debug-panel">
          <summary>查看知识图谱响应</summary>
          <pre class="result-box">{{ JSON.stringify(graphResult, null, 2) }}</pre>
        </details>
        <details class="debug-panel">
          <summary>查看习题生成请求</summary>
          <pre class="result-box">{{ JSON.stringify(lastExerciseRequest, null, 2) }}</pre>
        </details>
        <details class="debug-panel">
          <summary>查看习题生成响应</summary>
          <pre class="result-box">{{ JSON.stringify(lastExerciseRawResponse, null, 2) }}</pre>
        </details>
        <details class="debug-panel">
          <summary>查看答疑分析请求</summary>
          <pre class="result-box">{{ JSON.stringify(lastQaRequest, null, 2) }}</pre>
        </details>
        <details class="debug-panel">
          <summary>查看答疑分析响应</summary>
          <pre class="result-box">{{ JSON.stringify(lastQaRawResponse, null, 2) }}</pre>
        </details>
      </section>
    </main>
  </div>
</template>

<style scoped>
.profile-chat-section {
  margin-bottom: 12px;
}

.feedback-inline {
  margin: 10px 0 0;
  font-size: 13px;
}

.feedback-inline.danger {
  color: #9b3b26;
}

.global-status-banner {
  position: sticky;
  top: 12px;
  z-index: 12;
  margin: 18px 0 4px;
}

.global-status-layout {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
}

.global-status-copy {
  min-width: 0;
}

.global-status-copy strong {
  display: block;
  margin: 0 0 6px;
}

.global-status-copy p {
  margin: 0;
}

.global-status-side {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 8px;
  flex: 0 0 auto;
}

.global-status-side span {
  font-size: 12px;
  color: inherit;
  opacity: 0.78;
  white-space: nowrap;
}

.global-progress-block {
  margin-top: 12px;
}

.global-progress-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 8px;
  color: inherit;
}

.global-progress-meta span {
  margin: 0;
  font-size: 13px;
  opacity: 0.86;
}

.global-progress-value {
  font-size: 24px;
  line-height: 1;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
}

.global-progress-block .el-progress {
  width: 100%;
}

@media (max-width: 760px) {
  .global-status-layout {
    flex-direction: column;
  }

  .global-status-side {
    align-items: flex-start;
  }
}

.request-status-card {
  margin-top: 12px;
  padding: 14px 16px;
  border-radius: 16px;
  border: 1px solid rgba(191, 116, 63, 0.18);
  background: rgba(255, 249, 242, 0.94);
  box-shadow: 0 10px 28px rgba(120, 72, 40, 0.08);
}

.request-status-card strong {
  display: block;
  color: #5e2e12;
  font-size: 15px;
  margin-bottom: 6px;
}

.request-status-card p {
  margin: 0;
  color: #7a533b;
  font-size: 13px;
  line-height: 1.7;
}

.request-status-card span {
  display: inline-block;
  margin-top: 8px;
  font-size: 12px;
  color: #8e684f;
}

.request-status-card.info {
  border-color: rgba(191, 116, 63, 0.22);
  background: linear-gradient(135deg, rgba(255, 248, 238, 0.98), rgba(255, 255, 255, 0.96));
}

.request-status-card.warning {
  border-color: rgba(214, 143, 31, 0.28);
  background: linear-gradient(135deg, rgba(255, 247, 229, 0.98), rgba(255, 252, 244, 0.96));
}

.request-status-card.warning strong,
.request-status-card.warning span {
  color: #94610d;
}

.request-status-card.warning p {
  color: #815b1b;
}

.request-status-card.danger {
  border-color: rgba(198, 84, 57, 0.3);
  background: linear-gradient(135deg, rgba(255, 240, 236, 0.98), rgba(255, 248, 246, 0.96));
}

.request-status-card.danger strong,
.request-status-card.danger span {
  color: #9b3b26;
}

.request-status-card.danger p {
  color: #884333;
}

.generation-status-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 10px;
}

.generation-status-pill {
  padding: 5px 10px;
  border-radius: 999px;
  background: rgba(191, 116, 63, 0.12);
  color: #8b4b24;
  font-size: 12px;
  line-height: 1.2;
}

.generation-stage-detail {
  margin: 10px 0 4px;
  color: #7b3f1f;
  font-size: 14px;
}

.generation-stage-note {
  margin: 0 0 12px;
  color: #8e684f;
  font-size: 13px;
  line-height: 1.6;
}

.generation-step-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 10px;
  margin-top: 12px;
}

.generation-step-card {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding: 12px;
  border-radius: 14px;
  border: 1px solid rgba(191, 116, 63, 0.18);
  background: rgba(255, 255, 255, 0.72);
}

.generation-step-card.completed {
  border-color: rgba(66, 159, 96, 0.3);
  background: rgba(232, 247, 237, 0.92);
}

.generation-step-card.current {
  border-color: rgba(191, 116, 63, 0.36);
  background: rgba(255, 244, 232, 0.96);
  box-shadow: 0 8px 20px rgba(191, 116, 63, 0.12);
}

.generation-step-index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 999px;
  background: rgba(191, 116, 63, 0.12);
  color: #8b4b24;
  font-weight: 700;
  font-size: 13px;
  flex: none;
}

.generation-step-card.completed .generation-step-index {
  background: rgba(66, 159, 96, 0.18);
  color: #2f7b4b;
}

.generation-step-card.current .generation-step-index {
  background: #bf743f;
  color: #fff;
}

.generation-step-copy {
  min-width: 0;
}

.generation-step-copy strong {
  display: block;
  color: #5e2e12;
  font-size: 14px;
  margin-bottom: 4px;
}

.generation-step-copy p {
  margin: 0;
  color: #8e684f;
  font-size: 12px;
  line-height: 1.5;
}

.clickable-card {
  cursor: pointer;
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}

.clickable-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 10px 24px rgba(120, 72, 40, 0.1);
}

.clickable-card.active {
  border-color: rgba(191, 116, 63, 0.42);
  background: rgba(255, 246, 236, 0.96);
  box-shadow: 0 12px 28px rgba(191, 116, 63, 0.12);
}

.student-workspace-shell .global-status-banner {
  top: 16px;
}

.student-workspace-shell .request-status-card {
  border-color: rgba(94, 131, 183, 0.18);
  background: linear-gradient(135deg, rgba(242, 247, 255, 0.96), rgba(234, 242, 252, 0.94));
  box-shadow: 0 16px 36px rgba(10, 26, 46, 0.08);
}

.student-workspace-shell .request-status-card strong {
  color: #163152;
}

.student-workspace-shell .request-status-card p {
  color: #536887;
}

.student-workspace-shell .request-status-card span {
  color: #6e819d;
}

.student-workspace-shell .request-status-card.warning {
  border-color: rgba(255, 157, 92, 0.26);
  background: linear-gradient(135deg, rgba(255, 247, 235, 0.98), rgba(255, 239, 221, 0.94));
}

.student-workspace-shell .request-status-card.warning strong,
.student-workspace-shell .request-status-card.warning span {
  color: #9d5816;
}

.student-workspace-shell .request-status-card.warning p {
  color: #8a683d;
}

.student-workspace-shell .request-status-card.danger {
  border-color: rgba(224, 108, 77, 0.24);
  background: linear-gradient(135deg, rgba(255, 241, 238, 0.98), rgba(255, 233, 227, 0.94));
}

.student-workspace-shell .request-status-card.danger strong,
.student-workspace-shell .request-status-card.danger span {
  color: #9a3d2d;
}

.student-workspace-shell .request-status-card.danger p {
  color: #825350;
}

.student-workspace-shell .generation-status-pill {
  background: rgba(36, 201, 184, 0.12);
  color: #0c756d;
}

.student-workspace-shell .generation-stage-detail {
  color: #173459;
}

.student-workspace-shell .generation-stage-note {
  color: #617795;
}

.student-workspace-shell .generation-step-card {
  border-color: rgba(94, 131, 183, 0.16);
  background: rgba(255, 255, 255, 0.82);
}

.student-workspace-shell .generation-step-card.completed {
  border-color: rgba(56, 176, 135, 0.28);
  background: rgba(235, 251, 245, 0.96);
}

.student-workspace-shell .generation-step-card.current {
  border-color: rgba(255, 139, 82, 0.28);
  background: rgba(255, 247, 240, 0.98);
  box-shadow: 0 12px 26px rgba(255, 139, 82, 0.14);
}

.student-workspace-shell .generation-step-index {
  background: rgba(36, 201, 184, 0.14);
  color: #0f7f79;
}

.student-workspace-shell .generation-step-card.current .generation-step-index {
  background: linear-gradient(135deg, #ff8b52, #ffb36e);
}

.student-workspace-shell .generation-step-copy strong {
  color: #173459;
}

.student-workspace-shell .generation-step-copy p {
  color: #687b96;
}

.student-workspace-shell .clickable-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 16px 34px rgba(15, 42, 74, 0.14);
}

.student-workspace-shell .clickable-card.active {
  border-color: rgba(36, 201, 184, 0.32);
  background: linear-gradient(180deg, rgba(240, 253, 250, 0.98), rgba(230, 247, 244, 0.96));
  box-shadow: 0 16px 36px rgba(36, 201, 184, 0.12);
}

.learning-request-panel {
  background:
    radial-gradient(circle at top right, rgba(191, 116, 63, 0.14), transparent 34%),
    linear-gradient(135deg, rgba(255, 250, 244, 0.98), rgba(255, 255, 255, 0.94));
}

.student-workspace-shell .learning-request-panel {
  background:
    radial-gradient(circle at top right, rgba(36, 201, 184, 0.18), transparent 32%),
    radial-gradient(circle at left bottom, rgba(255, 139, 82, 0.12), transparent 30%),
    linear-gradient(135deg, rgba(245, 250, 255, 0.98), rgba(236, 243, 252, 0.96));
}

.student-workspace-shell :deep(.el-input__wrapper),
.student-workspace-shell :deep(.el-textarea__inner) {
  background: rgba(255, 255, 255, 0.84);
  border-radius: 16px;
  box-shadow: inset 0 0 0 1px rgba(94, 131, 183, 0.14);
}

.student-workspace-shell :deep(.el-input__wrapper.is-focus),
.student-workspace-shell :deep(.el-textarea__inner:focus) {
  box-shadow:
    inset 0 0 0 1px rgba(36, 201, 184, 0.42),
    0 0 0 4px rgba(36, 201, 184, 0.08);
}

.student-workspace-shell :deep(.el-input__inner),
.student-workspace-shell :deep(.el-textarea__inner) {
  color: #163152;
}

.student-workspace-shell :deep(.el-button) {
  border-radius: 14px !important;
  font-weight: 600;
  border-color: rgba(94, 131, 183, 0.18);
}

.student-workspace-shell :deep(.el-button--default) {
  background: rgba(255, 255, 255, 0.8);
  color: #173459;
}

.student-workspace-shell :deep(.el-button--primary) {
  color: #071321;
  border-color: transparent;
  background: linear-gradient(135deg, #22d1bf, #ff975d);
  box-shadow: 0 12px 24px rgba(36, 201, 184, 0.18);
}

.student-workspace-shell :deep(.el-progress-bar__outer) {
  background: rgba(18, 35, 58, 0.08);
}

.student-workspace-shell :deep(.el-progress-bar__inner) {
  background: linear-gradient(90deg, #22d1bf, #ff975d);
}

.learning-request-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin: 16px 0 12px;
}

@media (max-width: 760px) {
  .learning-request-grid {
    grid-template-columns: 1fr;
  }
}
</style>
