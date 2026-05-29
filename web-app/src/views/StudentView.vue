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
  evaluationApi,
  userApi,
  type ApiEnvelope,
  type CoordinationPayload,
  type ExerciseGenerationPayload,
  type ExerciseGenerationResponse,
  type GraphVisualizationResponse,
  type LearnerProfileDashboard,
  type LearningPathPayload,
  type LearningPathResponse,
  type MistakeNotebook,
  type PracticeFeedback,
  type PracticeSubmissionPayload,
  type QARequestPayload,
  type QAResponsePayload,
  type RemedialExerciseSet,
  type ReportDetail,
  type ResourcePayload,
} from '../api'
import { useAuthStore } from '../stores/auth'

type CoordinationResult = {
  status?: string
  selected_agents?: string[]
  route_reason?: string
  outputs?: Record<string, { queue?: string; message?: string }>
}

type ResourceReference = {
  id?: string
  content?: string
  metadata?: Record<string, unknown>
}

type ResourceResult = {
  user_id?: number
  knowledge_point?: string
  resource_type?: string
  resource_style?: string
  references?: ResourceReference[]
  content?: string
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

type GenerationProgressState = {
  hint: string
  progress: number
}

const router = useRouter()
const authStore = useAuthStore()
const fallbackAnnouncements = new Set<string>()

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
const coursewareDeliveryMode = ref<'remote' | 'fallback' | 'upgrading'>('remote')
const exerciseDeliveryMode = ref<'remote' | 'fallback' | 'upgrading'>('remote')
const generationStatus = reactive<Record<GenerationKind, GenerationProgressState>>({
  courseware: {
    hint: '',
    progress: 0,
  },
  exercises: {
    hint: '',
    progress: 0,
  },
})

const activeTaskId = ref('')
const currentExerciseIndex = ref(0)
const localPracticeRecords = ref<LocalPracticeRecord[]>([])

const exerciseDrafts = reactive<Record<number, string>>({})
const submittedExercises = reactive<Record<number, SubmittedExerciseState>>({})

const loading = reactive({
  coordinate: false,
  courseware: false,
  graph: false,
  path: false,
  exercises: false,
  mistakes: false,
  remedial: false,
  reports: false,
  submit: false,
  qa: false,
})

const answerStartAt = ref<number | null>(null)
const graphCanvas = ref<HTMLDivElement | null>(null)
let graphNetwork: Network | null = null
const generationProgressTimers: Partial<Record<GenerationKind, ReturnType<typeof setInterval>>> = {}
let coursewareRequestVersion = 0
let exerciseRequestVersion = 0

const coordinationForm = reactive<CoordinationPayload>({
  user_id: authStore.user?.userId ?? 1,
  intent: '请生成 Python 循环的个性化课件、练习题和学习路径建议。',
  knowledge_point: 'Python 循环',
  payload: {
    subject: 'Python 程序设计',
    grade: '大一',
  },
})

const resourceForm = reactive<ResourcePayload>({
  user_id: authStore.user?.userId ?? 1,
  knowledge_point: 'Python 循环',
  resource_style: 'interactive',
  resource_type: 'courseware',
  learner_profile: {
    learning_style: 'visual',
    mastery: 62,
    habits: ['晚间学习', '偏好案例'],
  },
})

const pathForm = reactive<LearningPathPayload>({
  user_id: authStore.user?.userId ?? 1,
  subject: 'Python 程序设计',
  knowledge_point: 'Python 循环',
  daily_minutes: 45,
  learner_profile: {
    learning_style: 'visual',
    mastery: 62,
  },
})

const exerciseForm = reactive<ExerciseGenerationPayload>({
  user_id: authStore.user?.userId ?? 1,
  knowledge_point: 'Python 循环',
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
  subject: 'Python 程序设计',
  grade: '大一',
  question: '我不太明白 while 循环为什么会死循环，能不能结合一个例子讲一下？',
  student_answer: '',
  wrong_answer: '',
  current_knowledge_points: ['Python 循环'],
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
const dependencyPaths = computed(() => {
  const dependencies = graphResult.value?.dependencies ?? []
  return dependencies.map((item) => item.path ?? []).filter((path) => path.length > 0)
})
const radarMetrics = computed(() => profileDashboard.value?.radar_metrics ?? [])
const heatmapMetrics = computed(() => profileDashboard.value?.heatmap ?? [])
const qaRecommendations = computed(() => qaResult.value?.structured_analysis.resource_recommendations ?? [])
const qaRouteUpdates = computed(() => qaResult.value?.structured_analysis.learning_route_updates ?? [])
const qaKnowledgeGaps = computed(() => qaResult.value?.structured_analysis.identified_knowledge_gaps ?? [])
const qaMisconceptions = computed(() => qaResult.value?.structured_analysis.misconceptions ?? [])
const qaStudySuggestions = computed(() => qaResult.value?.structured_analysis.study_suggestions ?? [])

const coursewareTitle = computed(() => {
  const raw = resourceResult.value?.content?.trim()
  const firstLine = raw?.split(/\r?\n/)[0] ?? ''
  return firstLine.startsWith('# ') ? firstLine.replace(/^#\s+/, '') : '学习课件'
})

const resourceSections = computed<CoursewareSection[]>(() => {
  const content = resourceResult.value?.content?.trim()
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

function rebuildMistakeNotebook(userId = exerciseForm.user_id): MistakeNotebook {
  const records = localPracticeRecords.value.filter((item) => item.user_id === userId && !item.is_correct)
  return {
    user_id: userId,
    mistake_count: records.length,
    items: records.map((item) => ({
      exercise_id: item.exercise_id,
      knowledge_point: item.knowledge_point,
      question_type: item.question_type,
      user_answer: item.user_answer,
      correct_answer: item.correct_answer,
      analysis: item.analysis,
      suggested_action: '先读懂解析，再去做错题变式重练，不再重复提交原题。',
    })),
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

function syncFormsWithKnowledgePoint(knowledgePoint: string) {
  coordinationForm.knowledge_point = knowledgePoint
  resourceForm.knowledge_point = knowledgePoint
  pathForm.knowledge_point = knowledgePoint
  exerciseForm.knowledge_point = knowledgePoint
}

function scrollToCoursewareSection(anchor: string) {
  const target = document.getElementById(anchor)
  target?.scrollIntoView({ behavior: 'smooth', block: 'start' })
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
    await fetchProfileDashboard(data.id)
  } catch {
    authStore.clear()
    await router.push({ name: 'login' })
  }
}

async function fetchProfileDashboard(userId = exerciseForm.user_id) {
  try {
    const { data } = await userApi.get<LearnerProfileDashboard>(`/users/${userId}/profile/dashboard`)
    syncLearnerFromDashboard(data)
  } catch {
    syncLearnerFromDashboard(buildFallbackProfileDashboard(userId))
    announceFallback('profile-dashboard', '学习画像服务暂不可用，已切换到本地画像模式。')
  }
}

async function runCoordination() {
  loading.coordinate = true
  try {
    const { data } = await agentApi.post('/agents/coordinate', coordinationForm)
    coordinationResult.value = data as CoordinationResult
    ElMessage.success('学习协同计划已生成。')
  } catch {
    ElMessage.error('协调调度失败。')
  } finally {
    loading.coordinate = false
  }
}

async function generateLearningPath() {
  loading.path = true
  try {
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
  }
}

function buildFallbackCoursewareContent(knowledgePoint: string) {
  return `# ${knowledgePoint} 学习课件

## 课程导入
很多同学刚接触 ${knowledgePoint} 时，会觉得它只是一个语法点，但真正重要的是理解它在什么场景下帮助我们更高效地解决问题。

## 学习目标
- 先理解 ${knowledgePoint} 的核心作用
- 再弄清它常见的使用场景
- 最后结合一个小例子把概念落到实际

## 知识讲解
${knowledgePoint} 的本质，是帮助我们按照一定规则重复执行一段操作。学习时不要只盯着写法，更要关注“为什么要这样写”和“什么时候应该停止”。

## 重难点突破
初学时最容易出错的地方通常有两个：一是没有真正看懂条件或范围，二是步骤顺序写对了表面形式，却没理解运行过程。

## 示例讲解
\`\`\`python
count = 0
while count < 3:
    print(count)
    count += 1
\`\`\`

这段代码里，\`count < 3\` 是继续执行的条件，\`count += 1\` 是防止循环一直不结束的关键。

## 课堂小结
- 先理解作用，再记语法
- 先判断场景，再选择写法
- 做题时一定检查条件、范围和更新步骤

## 学完后自测
- 我能不能说清这个知识点在解决什么问题？
- 我能不能指出最容易出错的地方？
- 我能不能写出一个最基础的小例子？

## 拓展延伸
建议你先完成一轮自测题，再回头看解析，这样更容易发现自己是真懂了还是只“看懂了”。`
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
  generationProgressTimers[kind] = setInterval(() => {
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

function finishGenerationProgress(kind: GenerationKind, message: string) {
  stopGenerationProgress(kind)
  generationStatus[kind].progress = 100
  generationStatus[kind].hint = message
}

function resetGenerationProgress(kind?: GenerationKind) {
  if (kind) {
    stopGenerationProgress(kind)
    generationStatus[kind].hint = ''
    generationStatus[kind].progress = 0
    return
  }

  ;(['courseware', 'exercises'] as GenerationKind[]).forEach((item) => {
    stopGenerationProgress(item)
    generationStatus[item].hint = ''
    generationStatus[item].progress = 0
  })
}

async function generateCourseware() {
  const requestVersion = ++coursewareRequestVersion
  loading.courseware = true
  startGenerationProgress('courseware', '正在生成学习课件，预计等待 3-8 秒。')
  coursewareGenerationError.value = ''
  const fallbackContent = buildFallbackCoursewareContent(resourceForm.knowledge_point)
  resourceResult.value = {
    user_id: resourceForm.user_id,
    knowledge_point: resourceForm.knowledge_point,
    resource_type: resourceForm.resource_type,
    resource_style: resourceForm.resource_style,
    references: [],
    content: fallbackContent,
  }
  exerciseForm.courseware_content = fallbackContent
  coursewareDeliveryMode.value = 'upgrading'
  try {
    resourceForm.resource_type = 'courseware'
    lastCoursewareRequest.value = {
      ...resourceForm,
    }
    const { data } = await postWithTimeout<EnvelopeLike<ResourceResult>>('/resources/generate', resourceForm, 12000)
    if (requestVersion !== coursewareRequestVersion) {
      return
    }
    lastCoursewareRawResponse.value = data
    const normalized = normalizeResourceResult(data)
    if (!normalized) {
      throw new Error('resource payload is empty')
    }
    resourceResult.value = normalized
    exerciseForm.courseware_content = resourceResult.value.content ?? ''
    coursewareDeliveryMode.value = 'remote'
    markTaskCompleted('courseware')
    finishGenerationProgress('courseware', '学习课件已生成完成。')
    ElMessage.success('学习课件已生成')
  } catch {
    if (requestVersion !== coursewareRequestVersion) {
      return
    }
    resourceResult.value = {
      user_id: resourceForm.user_id,
      knowledge_point: resourceForm.knowledge_point,
      resource_type: resourceForm.resource_type,
      resource_style: resourceForm.resource_style,
      references: [],
      content: fallbackContent,
    }
    exerciseForm.courseware_content = fallbackContent
    coursewareDeliveryMode.value = 'fallback'
    coursewareGenerationError.value = '远程课件生成超时或失败，当前已切换为快速版本地课件，页面不会卡住。'
    finishGenerationProgress('courseware', '远程生成较慢，已切换为快速版课件。')
    ElMessage.warning('远程课件生成较慢，已切换为快速版课件')
  } finally {
    if (requestVersion === coursewareRequestVersion) {
      loading.courseware = false
    }
  }
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
  loading.exercises = true
  startGenerationProgress('exercises', '正在生成课后自测，预计等待 3-8 秒。')
  exerciseGenerationError.value = ''
  exerciseSet.value = buildQuickExerciseSet()
  resetExerciseSession()
  exerciseDeliveryMode.value = 'upgrading'
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
    const { data } = await postWithTimeout<EnvelopeLike<ExerciseGenerationResponse>>('/exercises/generate', exerciseForm, 12000)
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
    exerciseDeliveryMode.value = 'remote'
    markTaskCompleted('exercise')
    finishGenerationProgress('exercises', '课后自测已生成完成。')
    ElMessage.success('课后自测已生成')
  } catch {
    if (requestVersion !== exerciseRequestVersion) {
      return
    }
    exerciseDeliveryMode.value = 'fallback'
    exerciseGenerationError.value = '远程题目生成失败或超时，当前已保留快速版题组，你可以先继续作答。'
    finishGenerationProgress('exercises', '远程生成较慢，当前先使用快速版题组。')
    ElMessage.warning('远程题目生成较慢，当前先使用快速版题组')
  } finally {
    if (requestVersion === exerciseRequestVersion) {
      loading.exercises = false
    }
  }
}

async function queryGraph() {
  loading.graph = true
  try {
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
  } catch {
    const fallback = buildFallbackPracticeFeedback(payload)
    applyLocalPracticeState(payload, fallback)
    ElMessage.success(fallback.is_correct ? '回答正确。' : '已返回标准答案与解析。')
    announceFallback('practice-submit', '评估服务暂不可用，已切换到本地判分模式。')
  } finally {
    loading.submit = false
  }
}

function goToNextExercise() {
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
  try {
    const userId = exerciseForm.user_id
    const { data } = await evaluationApi.get<ApiEnvelope<MistakeNotebook>>(`/evaluation/mistakes/${userId}/detail`)
    mistakeNotebook.value = data.data
  } catch {
    mistakeNotebook.value = rebuildMistakeNotebook()
    announceFallback('mistake-notebook', '错题本服务暂不可用，已切换到本地错题记录。')
  } finally {
    loading.mistakes = false
  }
}

async function fetchRemedialExercises() {
  loading.remedial = true
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
    loading.remedial = false
  }
}

async function fetchReports() {
  loading.reports = true
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
  }
}

async function askQaAgent() {
  loading.qa = true
  qaError.value = ''
  try {
    qaForm.student_id = String(authStore.user?.userId ?? exerciseForm.user_id)
    qaForm.subject = pathForm.subject
    qaForm.current_knowledge_points = [pathForm.knowledge_point]
    qaForm.learning_route = learningPath.value ?? {}
    qaForm.error_book = mistakeNotebook.value ?? {}
    qaForm.learning_history = buildQaLearningHistory()

    lastQaRequest.value = {
      ...qaForm,
      question: qaForm.question,
    }
    const { data } = await agentApi.post<EnvelopeLike<QAResponsePayload>>('/qa/analyze', qaForm)
    lastQaRawResponse.value = data
    qaResult.value = unwrapApiData(data)
    ElMessage.success('智能答疑结果已生成')
  } catch {
    qaResult.value = null
    qaError.value = '答疑分析失败，请查看下方调试详情中的原始响应。'
    ElMessage.error('智能答疑失败')
  } finally {
    loading.qa = false
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
  await Promise.all([
    generateLearningPath(),
    generateCourseware(),
    fetchMistakeNotebook(),
    fetchReports(),
  ])
})

onUnmounted(() => {
  resetGenerationProgress()
})
</script>

<template>
  <div class="dashboard-shell">
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

    <main class="workspace-grid student-grid">
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
        <div v-if="generationStatus.courseware.hint" class="generation-hint">
          <div class="generation-hint-title">课件生成进度</div>
          <div class="generation-hint-line">
            <span class="generation-hint-dot" :class="{ running: loading.courseware }"></span>
            <span>{{ generationStatus.courseware.hint }}</span>
            <strong>{{ generationStatus.courseware.progress }}%</strong>
          </div>
          <el-progress
            :percentage="generationStatus.courseware.progress"
            :stroke-width="10"
            :show-text="false"
            striped
            striped-flow
            :duration="8"
          />
        </div>
      </section>

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
          <el-button type="success" :loading="loading.exercises" @click="generateExercises()">生成课后自测</el-button>
          <el-button plain :disabled="loading.exercises" @click="generateExercises()">重新生成自测</el-button>
          <el-button type="danger" :loading="loading.remedial" @click="fetchRemedialExercises">错题变式重练</el-button>
          <el-button :loading="loading.graph" @click="queryGraph">查询知识图谱</el-button>
        </div>
      </section>

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
        <div v-if="profileDashboard" class="learning-content">
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
              <div
                v-for="item in heatmapMetrics"
                :key="item.knowledge_point"
                class="heatmap-cell"
                :style="{ opacity: `${Math.max(0.38, item.mastery / 100)}` }"
              >
                <strong>{{ item.knowledge_point }}</strong>
                <span>{{ item.mastery }}%</span>
              </div>
            </div>
          </article>
        </div>
        <div v-else class="empty-state">正在加载学习画像。</div>
      </section>

      <section class="workspace-panel wide">
        <div class="panel-heading">
          <div>
            <div class="panel-kicker">课件学习</div>
            <h2>{{ coursewareTitle }}</h2>
          </div>
          <Document class="panel-icon" />
        </div>
        <div v-if="coursewareGenerationError" class="feedback-card wrong">
          <div class="insight-label">课件生成状态</div>
          <div class="insight-value">已自动脱困</div>
          <p class="panel-text">{{ coursewareGenerationError }}</p>
        </div>
        <div v-else-if="coursewareDeliveryMode === 'upgrading'" class="insight-card">
          <div class="insight-label">课件生成状态</div>
          <div class="insight-value">已先展示快速版课件</div>
          <p class="panel-text">你可以先开始学习，后台正在继续尝试生成更完整的远程正式版内容。</p>
        </div>
        <div v-if="resourceResult" class="reader-layout">
          <aside class="reader-outline">
            <div class="insight-label">课件目录</div>
            <div class="outline-list">
              <button
                v-for="section in resourceSections"
                :key="section.anchor"
                type="button"
                class="outline-item"
                @click="scrollToCoursewareSection(section.anchor)"
              >
                {{ section.heading }}
              </button>
            </div>
          </aside>

          <div class="learning-content reader-content">
            <article class="learning-section">
              <h3>学习建议</h3>
              <div class="tag-row">
                <span class="agent-tag">先看概念</span>
                <span class="agent-tag">再读示例</span>
                <span class="agent-tag">最后做题</span>
              </div>
              <p class="learning-line">
                这份课件已经按章节拆开。建议先顺着目录学习，再回到练习区做题，提交后查看标准答案和解析。
              </p>
            </article>

            <section
              v-for="section in resourceSections"
              :id="section.anchor"
              :key="section.anchor"
              class="learning-section"
            >
              <h3>{{ section.heading }}</h3>
              <template v-for="block in section.blocks" :key="`${section.anchor}-${block.type}-${block.lines.join('-')}`">
                <p v-if="block.type === 'paragraph'" class="learning-line">
                  {{ block.lines.join(' ') }}
                </p>
                <ul v-else-if="block.type === 'unordered'" class="markdown-list">
                  <li v-for="line in block.lines" :key="line">{{ line }}</li>
                </ul>
                <ol v-else-if="block.type === 'ordered'" class="markdown-list markdown-list-ordered">
                  <li v-for="line in block.lines" :key="line">{{ line }}</li>
                </ol>
                <div v-else class="code-block">
                  <div v-if="block.language" class="code-block-label">{{ block.language }}</div>
                  <pre><code>{{ block.lines.join('\n') }}</code></pre>
                </div>
              </template>
            </section>

            <article v-if="resourceResult.references?.length" class="learning-section">
              <h3>参考材料</h3>
              <div class="reference-list">
                <article
                  v-for="reference in resourceResult.references"
                  :key="reference.id ?? reference.content"
                  class="reference-card"
                >
                  <strong>{{ reference.id ?? '参考片段' }}</strong>
                  <p>{{ reference.content }}</p>
                  <span class="reference-meta">
                    来源：{{ String(reference.metadata?.source ?? 'RAG 检索') }}
                  </span>
                </article>
              </div>
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
          <el-button type="success" :loading="loading.exercises" @click="generateExercises()">
            生成课后自测
          </el-button>
          <el-button plain :disabled="loading.exercises" @click="generateExercises()">
            重新生成本轮题目
          </el-button>
          <span class="practice-toolbar-tip">
            先生成学习课件，再在这里直接生成围绕当前课件内容的自测题。每次点击都会重新请求后端生成。
          </span>
        </div>
        <div v-if="generationStatus.exercises.hint" class="generation-hint compact">
          <div class="generation-hint-title">自测题生成进度</div>
          <div class="generation-hint-line">
            <span class="generation-hint-dot" :class="{ running: loading.exercises }"></span>
            <span>{{ generationStatus.exercises.hint }}</span>
            <strong>{{ generationStatus.exercises.progress }}%</strong>
          </div>
          <el-progress
            :percentage="generationStatus.exercises.progress"
            :stroke-width="10"
            :show-text="false"
            striped
            striped-flow
            :duration="8"
          />
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
            <p class="panel-text">
              你的答案已经锁定。现在可以查看标准答案与解析，或进入下一题。
            </p>
          </div>

          <div class="exercise-card">
            <h3>{{ currentExercise.prompt }}</h3>

            <div v-if="currentExercise.options.length" class="option-list">
              <label v-for="option in currentExercise.options" :key="option" class="option-item">
                <input
                  v-model="currentAnswerDraft"
                  type="radio"
                  :value="option.charAt(0)"
                  :disabled="Boolean(currentSubmission)"
                />
                <span>{{ option }}</span>
              </label>
            </div>

            <el-input
              v-else
              v-model="currentAnswerDraft"
              type="textarea"
              :rows="5"
              :disabled="Boolean(currentSubmission)"
              placeholder="请输入你的答案"
            />
          </div>

          <div class="action-row">
            <el-button
              type="primary"
              :loading="loading.submit"
              :disabled="Boolean(currentSubmission)"
              @click="submitPractice"
            >
              提交答案
            </el-button>
            <el-button :disabled="!currentSubmission" @click="goToNextExercise">下一题</el-button>
          </div>

          <div v-if="currentSubmission" class="feedback-card" :class="{ correct: currentSubmission.feedback.is_correct, wrong: !currentSubmission.feedback.is_correct }">
            <div class="insight-label">即时反馈</div>
            <div class="insight-value">{{ currentSubmission.feedback.is_correct ? '回答正确' : '需要继续巩固' }}</div>
            <p class="panel-text">得分：{{ currentSubmission.feedback.score }}</p>
            <p class="panel-text">反馈：{{ currentSubmission.feedback.feedback }}</p>
            <p class="panel-text">建议：{{ currentSubmission.feedback.suggested_action }}</p>
            <p class="panel-text"><strong>你的答案：</strong>{{ currentSubmission.userAnswer }}</p>
            <p class="panel-text"><strong>标准答案：</strong>{{ currentSubmission.correctAnswer }}</p>
            <p class="panel-text"><strong>解析：</strong>{{ currentSubmission.analysis }}</p>
          </div>
        </template>

        <div v-else class="empty-state">点击“生成课后自测”后，这里会出现围绕当前课件内容生成的结构化题目与答题入口。</div>
      </section>

      <section class="workspace-panel">
        <div class="panel-heading">
          <div>
            <div class="panel-kicker">知识图谱</div>
            <h2>前置依赖</h2>
          </div>
          <Connection class="panel-icon" />
        </div>
        <template v-if="dependencyPaths.length || graphVisualization?.nodes.length">
          <div v-if="dependencyPaths.length" class="dependency-list">
            <article v-for="(path, index) in dependencyPaths" :key="`path-${index}`" class="dependency-card">
              <div class="insight-label">依赖链 {{ index + 1 }}</div>
              <div class="dependency-flow">
                <span v-for="(node, nodeIndex) in path" :key="`${node}-${nodeIndex}`" class="dependency-node">
                  {{ node }}
                </span>
              </div>
            </article>
          </div>
          <div ref="graphCanvas" class="graph-canvas" />
        </template>
        <div v-else class="empty-state">点击“查询知识图谱”后，这里会展示当前知识点的依赖链。</div>
      </section>

      <section class="workspace-panel">
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
        </div>

        <div v-if="hasMistakes" class="reference-list">
          <article
            v-for="(item, index) in mistakeNotebook?.items"
            :key="`${item.exercise_id}-${index}`"
            class="reference-card"
          >
            <strong>{{ item.knowledge_point }} / {{ item.question_type }}</strong>
            <p>你的答案：{{ item.user_answer }}</p>
            <p>标准答案：{{ item.correct_answer }}</p>
            <p>解析：{{ item.analysis }}</p>
            <p>建议：{{ item.suggested_action }}</p>
            <div class="action-row">
              <el-button size="small" type="warning" @click="startRemedialFromMistake(item.knowledge_point)">
                生成同类重练题
              </el-button>
            </div>
          </article>
        </div>

        <div v-else class="empty-state">当前还没有错题记录，继续保持。</div>

        <div v-if="remedialCount" class="insight-card">
          <div class="insight-label">变式重练</div>
          <div class="insight-value">{{ remedialCount }} 题</div>
          <p class="panel-text">{{ remedialExerciseSet?.summary }}</p>
        </div>
      </section>

      <section class="workspace-panel wide">
        <div class="panel-heading">
          <div>
            <div class="panel-kicker">智能答疑</div>
            <h2>提问、讲解与学习分析</h2>
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
              placeholder="请输入你当前不会的知识点、题目疑问，或者为什么做错。"
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
              <el-button type="primary" :loading="loading.qa" @click="askQaAgent">开始答疑分析</el-button>
            </div>
          </article>

          <article v-if="qaResult" class="learning-section">
            <h3>老师讲解</h3>
            <p class="learning-line preserve-linebreaks">{{ qaResult.student_response }}</p>
          </article>

          <article v-else-if="qaError" class="learning-section">
            <h3>答疑状态</h3>
            <p class="learning-line">{{ qaError }}</p>
          </article>

          <template v-if="qaResult">
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
              <div class="insight-card">
                <div class="insight-label">错题本更新建议</div>
                <div class="insight-value">
                  {{ qaResult.structured_analysis.mistake_book_update.should_add ? '建议加入错题本' : '暂不加入错题本' }}
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
