<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ChatDotRound, Delete, Expand, Fold, Plus, Promotion, Search, Setting } from '@element-plus/icons-vue'
import { useAuthStore } from '../../stores/auth'
import {
  evaluationApi,
  createChatSession,
  deleteChatSession,
  getChatSession,
  listChatSessions,
  qaApi,
  type ApiEnvelope,
  type ChatMessageItem,
  type ChatSessionDetail,
  type ChatSessionSummary,
  type ExerciseGenerationResponse,
  type MistakeItem,
  type QAAnalysisPayload,
  type QARequestPayload,
  type QAResponsePayload,
  type QAMistakeSubmissionPayload,
  type ResourceResult,
} from '../../api'
import {
  EXERCISE_STORAGE_KEY,
  readStudentWorkspaceContext,
  type StudentWorkspaceContext,
} from '../../utils/studentWorkspace'

type UiMessage = {
  id: string
  role: 'user' | 'assistant'
  content: string
  created_at: string
  model_used?: string
  analysis?: QAAnalysisPayload | null
  confidence?: number | null
  generatedExercises?: ExerciseGenerationResponse | null
  generatedResource?: ResourceResult | null
}

type SessionGroup = {
  label: string
  items: Array<{
    id: number
    title: string
    updatedAt: string
    messageCount: number
  }>
}

type UiSession = {
  id: number
  title: string
  subject: string
  topicHint: string
  updatedAt: string
  messageCount: number
  messages: UiMessage[]
  persisted: boolean
  loaded: boolean
}

type QaErrorState = {
  code: string
  title: string
  message: string
  retryable: boolean
}

const authStore = useAuthStore()
const user = authStore.user!
const router = useRouter()
const workspaceContext = ref<StudentWorkspaceContext | null>(null)
const useWorkspaceContext = ref(false)

const qaForm = reactive<QARequestPayload>({
  student_id: String(user.userId),
  subject: '',
  grade: '大学',
  question: '',
  session_id: null,
  session_title: '',
  student_answer: '',
  wrong_answer: '',
  current_knowledge_points: [],
  learning_route: {},
  error_book: {},
  learning_history: {},
})

const sessions = ref<UiSession[]>([])
const searchedSessions = ref<UiSession[] | null>(null)
const activeSessionId = ref<number | null>(null)
const sending = ref(false)
const loadingSessions = ref(false)
const qaError = ref<QaErrorState | null>(null)
const sideCollapsed = ref(false)
const sessionSearch = ref('')
const messagesRef = ref<HTMLDivElement | null>(null)
const lastFailedQuestion = ref('')
let sessionSearchTimer: ReturnType<typeof setTimeout> | undefined

const activeSession = computed(() => sessions.value.find((item) => item.id === activeSessionId.value) ?? null)
const activeMessages = computed(() => activeSession.value?.messages ?? [])
const sessionTitle = computed(() => activeSession.value?.title || '新对话')
const activeSubject = computed(() => useWorkspaceContext.value && workspaceContext.value?.topic
  ? `聚焦：${workspaceContext.value.topic}`
  : qaForm.subject.trim() || '自由提问')
const visibleSessions = computed(() => searchedSessions.value ?? sessions.value)
const suggestionQuestions = [
  '用通俗的例子解释相对论',
  '帮我规划 Python 入门学习路线',
  '通货膨胀为什么会影响日常生活？',
]

function resolveQaError(error: any, fallback = '请求暂时未完成', retryable = true): QaErrorState {
  const status = Number(error?.response?.status ?? 0)
  const detail = error?.response?.data?.detail
  const detailObject = detail && typeof detail === 'object' ? detail : null
  const code = String(detailObject?.code ?? '')
  const rawMessage = typeof detail === 'string' ? detail : String(error?.message ?? '')

  if (code === 'AI_MODEL_INITIALIZATION_TIMEOUT' || (status === 503 && rawMessage.includes('model initialization'))) {
    return {
      code: 'AI_MODEL_INITIALIZATION_TIMEOUT',
      title: 'AI 助教正在加载',
      message: '模型正在准备中，请稍后重试。你的问题已保留在输入框里。',
      retryable: true,
    }
  }
  if (code === 'AI_INFERENCE_TIMEOUT' || status === 504 || error?.code === 'ECONNABORTED') {
    return {
      code: 'AI_INFERENCE_TIMEOUT',
      title: 'AI 助教响应超时',
      message: '本次回答耗时较长，网络没有断开，请稍后再次发送。',
      retryable: true,
    }
  }
  if (!error?.response || error?.code === 'ERR_NETWORK') {
    return {
      code: 'NETWORK_ERROR',
      title: '网络连接异常',
      message: '暂时无法连接学习服务，请检查网络后重试。',
      retryable,
    }
  }
  if (status === 429) {
    return {
      code: code || 'RATE_LIMITED',
      title: '当前提问较多',
      message: '服务正在处理其他问题，请稍等片刻再重试。',
      retryable,
    }
  }
  return {
    code: code || `HTTP_${status || 'UNKNOWN'}`,
    title: '服务暂时不可用',
    message: detailObject?.message || (status >= 500
      ? 'AI助教暂时无法生成回答，请稍后重试。你的问题仍保留在输入框里。'
      : fallback),
    retryable,
  }
}

function setQaError(error: any, fallback: string, retryable = true) {
  qaError.value = resolveQaError(error, fallback, retryable)
}

function clearQaError() {
  qaError.value = null
}

function useSuggestion(question: string) {
  qaForm.question = question
}

function formatModelUsed(modelUsed?: string) {
  const normalized = modelUsed?.trim()
  if (!normalized) {
    return ''
  }
  const labelMap: Record<string, string> = {
    qa_learning_llm: '学习助教',
    qa_general_llm: '通用助手',
    qa_realtime: '实时信息',
    large_model: '深度回答',
    small_model: '快速回答',
  }
  return labelMap[normalized] ?? 'AI 助手'
}

function isBrokenSessionTitle(value: string | null | undefined) {
  const normalized = value?.trim() ?? ''
  if (!normalized) {
    return true
  }
  const lowered = normalized.toLowerCase()
  if (['new chat', '新对话', '智能问答'].includes(lowered)) {
    return false
  }
  if (normalized.includes('�')) {
    return true
  }
  const questionMarkCount = (normalized.match(/[?？]/g) ?? []).length
  const hasMeaningfulChar = /[\p{L}\p{N}]/u.test(normalized)
  return !hasMeaningfulChar || questionMarkCount >= Math.max(2, Math.floor(normalized.length / 2))
}

function resolveSessionTitle(title: string | null | undefined, fallback = '新对话') {
  const normalized = title?.trim() ?? ''
  if (!normalized || isBrokenSessionTitle(normalized)) {
    return fallback
  }
  return normalized
}

const filteredSessionGroups = computed<SessionGroup[]>(() => {
  const keyword = sessionSearch.value.trim().toLowerCase()
  const source = visibleSessions.value
  const filtered = searchedSessions.value || !keyword
    ? source
    : source.filter((item) => {
        const title = item.title.toLowerCase()
        const hasMessage = item.messages.some((msg) => msg.content.toLowerCase().includes(keyword))
        return title.includes(keyword) || hasMessage
      })

  const groups = new Map<string, SessionGroup['items']>()
  for (const session of filtered) {
    const label = formatSessionGroup(session.updatedAt)
    const bucket = groups.get(label) ?? []
    bucket.push({
      id: session.id,
      title: session.title,
      updatedAt: session.updatedAt,
      messageCount: session.messageCount,
    })
    groups.set(label, bucket)
  }

  return Array.from(groups.entries()).map(([label, items]) => ({ label, items }))
})

function formatSessionTime(value: string) {
  try {
    return new Date(value).toLocaleString('zh-CN', {
      hour12: false,
      timeZone: 'Asia/Shanghai',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return value
  }
}

function formatSessionGroup(value: string) {
  try {
    const date = new Date(value)
    const today = new Date()
    const startOfToday = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime()
    const startOfTarget = new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime()
    const diffDays = Math.floor((startOfToday - startOfTarget) / 86400000)
    if (diffDays === 0) return '今天'
    if (diffDays === 1) return '昨天'
    if (diffDays < 7) return '最近 7 天'
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
  } catch {
    return '更早'
  }
}

function createLocalDraftSession(resetContext = true) {
  const draftTitle = '新对话'
  const id = Date.now()
  const session: UiSession = {
    id,
    title: draftTitle,
    subject: '',
    topicHint: '',
    updatedAt: new Date().toISOString(),
    messageCount: 0,
    messages: [],
    persisted: false,
    loaded: true,
  }
  sessions.value = [session, ...sessions.value.filter((item) => item.persisted || item.messageCount > 0)]
  searchedSessions.value = null
  activeSessionId.value = id
  qaForm.session_id = null
  qaForm.session_title = draftTitle
  if (resetContext) {
    qaForm.subject = ''
    qaForm.current_knowledge_points = []
    qaForm.learning_route = {}
    useWorkspaceContext.value = false
  }
  clearQaError()
}

async function createEmptySession(persist = true) {
  if (!persist) {
    createLocalDraftSession()
    return
  }
  try {
    const detail = await createChatSession({
      user_id: user.userId,
      title: '新对话',
      subject: '',
    })
    const session = mapSessionDetail(detail)
    sessions.value = [session, ...sessions.value.filter((item) => item.persisted || item.messageCount > 0)]
    searchedSessions.value = null
    activeSessionId.value = session.id
    qaForm.session_id = session.id
    qaForm.session_title = session.title
    qaForm.subject = ''
    qaForm.current_knowledge_points = []
    qaForm.learning_route = {}
    useWorkspaceContext.value = false
    clearQaError()
    await scrollToBottom()
  } catch (error: any) {
    const state = resolveQaError(error, '新建会话失败，已切换到临时会话', false)
    ElMessage.error(state.message)
    createLocalDraftSession()
  }
}

async function loadPersistedSessions(keyword = '') {
  loadingSessions.value = true
  if (!keyword) {
    clearQaError()
  }
  try {
    applyWorkspaceContext()
    const rows = await listChatSessions(user.userId, 50, keyword)
    const mapped = rows.map(mapSessionSummary)
    if (keyword) {
      searchedSessions.value = mapped
      return
    }
    searchedSessions.value = null
    sessions.value = mapped
    if (sessions.value.length) {
      await selectSession(sessions.value[0].id)
    } else {
      createLocalDraftSession()
    }
  } catch (error: any) {
    const state = resolveQaError(error, keyword ? '搜索历史会话失败' : '加载历史会话失败', false)
    if (keyword) {
      ElMessage.error(state.message)
    } else {
      qaError.value = state
      ElMessage.error(state.message)
      createLocalDraftSession()
    }
  } finally {
    loadingSessions.value = false
  }
}

function scheduleSessionSearch(keyword: string) {
  if (sessionSearchTimer) {
    clearTimeout(sessionSearchTimer)
  }
  if (!keyword.trim()) {
    searchedSessions.value = null
    void loadPersistedSessions()
    return
  }
  sessionSearchTimer = setTimeout(() => {
    void loadPersistedSessions(keyword.trim())
  }, 260)
}

function mapSessionSummary(row: ChatSessionSummary): UiSession {
  return {
    id: row.id,
    title: resolveSessionTitle(row.title),
    subject: row.subject ?? '',
    topicHint: inferSessionTopic([], row.subject ?? '', resolveSessionTitle(row.title)),
    updatedAt: row.last_message_at || row.created_at,
    messageCount: row.message_count,
    messages: [],
    persisted: true,
    loaded: false,
  }
}

function mapSessionDetail(row: ChatSessionDetail): UiSession {
  const normalizedMessages = normalizeChatMessages(row.messages)
  return {
    id: row.id,
    title: resolveSessionTitle(row.title),
    subject: row.subject ?? '',
    topicHint: inferSessionTopic(normalizedMessages, row.subject ?? '', resolveSessionTitle(row.title)),
    updatedAt: row.last_message_at || row.created_at,
    messageCount: row.message_count,
    messages: normalizedMessages,
    persisted: true,
    loaded: true,
  }
}

async function selectSession(sessionId: number) {
  activeSessionId.value = sessionId
  let session = sessions.value.find((item) => item.id === sessionId)
  if (!session) {
    session = searchedSessions.value?.find((item) => item.id === sessionId)
    if (session) {
      sessions.value = [session, ...sessions.value.filter((item) => item.id !== sessionId)]
    }
  }
  if (!session) {
    return
  }
  if (session.persisted && !session.loaded) {
    try {
      const detail = await getChatSession(sessionId, user.userId)
      const hydrated = mapSessionDetail(detail)
      sessions.value = sessions.value.map((item) => item.id === sessionId ? hydrated : item)
    } catch (error: any) {
      const state = resolveQaError(error, '加载会话失败', false)
      qaError.value = state
      ElMessage.error(state.message)
      return
    }
  }
  const selected = sessions.value.find((item) => item.id === sessionId)
  qaForm.session_id = selected?.persisted ? selected.id : null
  qaForm.session_title = selected?.title ?? session.title
  qaForm.subject = ''
  qaForm.current_knowledge_points = []
  qaForm.learning_route = {}
  useWorkspaceContext.value = false
  clearQaError()
  await scrollToBottom()
}

async function removeSession(sessionId: number) {
  const target = sessions.value.find((item) => item.id === sessionId)
  if (target?.persisted) {
    try {
      await deleteChatSession(sessionId, user.userId)
    } catch (error: any) {
      const state = resolveQaError(error, '删除会话失败', false)
      ElMessage.error(state.message)
      return
    }
  }
  sessions.value = sessions.value.filter((item) => item.id !== sessionId)
  if (activeSessionId.value === sessionId) {
    const nextId = sessions.value[0]?.id ?? null
    if (nextId) {
      await selectSession(nextId)
    } else {
      await createEmptySession()
    }
  }
}

function normalizeGeneratedExercises(value: unknown): ExerciseGenerationResponse | null {
  if (!value || typeof value !== 'object') {
    return null
  }
  return value as ExerciseGenerationResponse
}

function normalizeGeneratedResource(value: unknown): ResourceResult | null {
  if (!value || typeof value !== 'object') {
    return null
  }
  return value as ResourceResult
}

function normalizeChatMessages(messages: ChatMessageItem[]) {
  return messages
    .filter((item) => item.role === 'user' || item.role === 'assistant')
    .map((item) => {
      const analysis = item.role === 'assistant'
        ? (item.metadata?.structured_analysis as QAAnalysisPayload | undefined) ?? null
        : null
      const confidence = item.role === 'assistant' && typeof item.metadata?.confidence === 'number'
        ? item.metadata.confidence
        : null
      const generatedExercises = item.role === 'assistant'
        ? normalizeGeneratedExercises(item.metadata?.generated_exercises)
        : null
      const generatedResource = item.role === 'assistant'
        ? normalizeGeneratedResource(item.metadata?.generated_resource)
        : null
      return {
        id: `${item.role}-${item.id}`,
        role: item.role,
        content: item.content,
        created_at: item.created_at,
        model_used: item.model_used,
        analysis,
        confidence,
        generatedExercises,
        generatedResource,
      } satisfies UiMessage
    })
}

function upsertSessionFromResponse(data: QAResponsePayload, question: string) {
  const normalizedMessages = normalizeQaMessages(
    data.message_history ?? [],
    data.structured_analysis,
    data.confidence,
    data.generated_exercises ?? null,
    data.generated_resource ?? null,
  )
  const updatedAt = normalizedMessages[normalizedMessages.length - 1]?.created_at ?? new Date().toISOString()
  const persistentId = data.session_id ?? activeSessionId.value ?? Date.now()
  const title = resolveSessionTitle(data.session_title, question.slice(0, 24) || '智能问答')

  const nextSession = {
    id: persistentId,
    title,
    subject: data.subject ?? qaForm.subject,
    topicHint: inferSessionTopic(normalizedMessages, data.subject ?? qaForm.subject, title),
    updatedAt,
    messageCount: normalizedMessages.length,
    messages: normalizedMessages,
    persisted: Boolean(data.session_id),
    loaded: true,
  }

  sessions.value = [nextSession, ...sessions.value.filter((item) => item.id !== activeSessionId.value && item.id !== persistentId)]
  activeSessionId.value = persistentId
  qaForm.session_id = data.session_id ?? persistentId
  qaForm.session_title = title
}

function applyWorkspaceContext() {
  workspaceContext.value = readStudentWorkspaceContext(user.userId)
}

function inferSessionTopic(messages: UiMessage[], subject: string, title: string) {
  for (const message of [...messages].reverse()) {
    const resourceTopic = message.generatedResource?.knowledge_point?.trim()
    if (resourceTopic) {
      return resourceTopic
    }
    const exerciseTopic = message.generatedExercises?.knowledge_point?.trim()
    if (exerciseTopic) {
      return exerciseTopic
    }
    const analysisTopic = message.analysis?.identified_knowledge_gaps?.find((item) => item.trim())
    if (analysisTopic) {
      return analysisTopic.trim()
    }
  }
  if (title.endsWith(' 问答')) {
    return title.slice(0, -3).trim()
  }
  return subject.trim()
}

function normalizeQaMessages(
  history: QAResponsePayload['message_history'],
  latestAnalysis: QAAnalysisPayload,
  confidence: number | null,
  generatedExercises: ExerciseGenerationResponse | null,
  generatedResource: ResourceResult | null,
) {
  const lastAssistantIndex = history.map((entry) => entry.role).lastIndexOf('assistant')
  return history
    .filter((item) => item.role === 'user' || item.role === 'assistant')
    .map((item, index) => {
      const isLatestAssistant = item.role === 'assistant' && index === lastAssistantIndex
      const metadataExercises = normalizeGeneratedExercises(item.metadata?.generated_exercises)
      const metadataResource = normalizeGeneratedResource(item.metadata?.generated_resource)
      return {
        id: `${item.role}-${item.id ?? index}`,
        role: item.role,
        content: item.content,
        created_at: item.created_at,
        model_used: item.model_used,
        analysis: isLatestAssistant ? latestAnalysis : (item.metadata?.structured_analysis as QAAnalysisPayload | undefined) ?? null,
        confidence: isLatestAssistant ? confidence : null,
        generatedExercises: isLatestAssistant ? generatedExercises : metadataExercises,
        generatedResource: isLatestAssistant ? generatedResource : metadataResource,
      } satisfies UiMessage
    })
}

function resourcePreview(content: string, maxLength = 320) {
  const trimmed = content.trim()
  if (!trimmed) {
    return ''
  }
  return trimmed.length > maxLength ? `${trimmed.slice(0, maxLength)}...` : trimmed
}

function buildQaMistakeExerciseId(sessionId: number | null | undefined) {
  const seed = sessionId ? sessionId * 100000 : Date.now()
  return 700000000 + (seed % 100000000)
}

function resolveQaSubject(data: QAResponsePayload) {
  return (
    data.subject?.trim()
    || qaForm.subject.trim()
    || (useWorkspaceContext.value ? workspaceContext.value?.subject?.trim() : '')
    || (useWorkspaceContext.value ? workspaceContext.value?.topic?.trim() : '')
    || '未分类科目'
  )
}

function resolveQaKnowledgePoint(data: QAResponsePayload) {
  return (
    data.structured_analysis.identified_knowledge_gaps?.find((item) => item.trim())?.trim()
    || qaForm.current_knowledge_points?.find((item) => item.trim())?.trim()
    || (useWorkspaceContext.value ? workspaceContext.value?.topic?.trim() : '')
    || resolveQaSubject(data)
  )
}

function buildQaMistakePayload(data: QAResponsePayload, question: string): QAMistakeSubmissionPayload | null {
  const update = data.structured_analysis.mistake_book_update
  const hasQaMistakeSignal = Boolean(
    update?.should_add
    || update?.wrong_reason?.trim()
    || data.structured_analysis.misconceptions.some((item) => item.trim())
    || data.structured_analysis.identified_knowledge_gaps.some((item) => item.trim()),
  )
  if (!hasQaMistakeSignal) {
    return null
  }

  const wrongAnswer = (
    qaForm.wrong_answer.trim()
    || qaForm.student_answer.trim()
    || update?.wrong_reason?.trim()
    || `本轮问答暴露的疑问：${question}`
  )
  if (!wrongAnswer) {
    return null
  }

  const correctApproach = update?.correct_approach?.trim() || data.student_response.trim()
  const analysis = [
    update?.wrong_reason?.trim() ?? '',
    ...data.structured_analysis.misconceptions.filter((item) => item.trim()),
    correctApproach ? `订正思路：${correctApproach}` : '',
  ].filter(Boolean).join('\n')

  return {
    user_id: user.userId,
    exercise_id: buildQaMistakeExerciseId(data.session_id ?? qaForm.session_id),
    subject: resolveQaSubject(data),
    knowledge_point: resolveQaKnowledgePoint(data),
    question_type: 'short_answer',
    question_summary: update?.question_summary?.trim() || question,
    wrong_answer: wrongAnswer,
    correct_answer: correctApproach || data.student_response,
    analysis: analysis || data.structured_analysis.learning_state,
    suggested_action: data.structured_analysis.study_suggestions[0] || correctApproach || '回看本轮问答解析后再做同类题。',
    time_spent: 0,
    difficulty: data.structured_analysis.difficulty_level === 'foundation' ? 'basic' : data.structured_analysis.difficulty_level,
  }
}

async function syncQaMistakeToNotebook(data: QAResponsePayload, question: string) {
  const payload = buildQaMistakePayload(data, question)
  if (!payload) {
    return
  }

  try {
    await evaluationApi.post<ApiEnvelope<MistakeItem>>('/evaluation/mistakes/qa', payload)
    ElMessage.success('已同步到对应科目的错题本。')
  } catch (error: any) {
    ElMessage.warning(error?.response?.data?.detail ?? error?.message ?? '问答错题同步失败，可稍后刷新错题本。')
  }
}

async function openExercisesInPractice(exerciseSet: ExerciseGenerationResponse) {
  if (typeof window !== 'undefined') {
    window.sessionStorage.setItem(EXERCISE_STORAGE_KEY, JSON.stringify({
      generatedAt: Date.now(),
      source: 'qa',
      exerciseSet,
    }))
  }
  ElMessage.success('已将生成习题带入练习测评')
  await router.push({ name: 'student-exercise' })
}

async function askQaAgent() {
  const question = qaForm.question.trim()
  if (!question || sending.value) {
    return
  }

  const currentSession = activeSession.value
  if (!currentSession) {
    createLocalDraftSession(false)
  }

  sending.value = true
  clearQaError()
  try {
    const focusedTopic = useWorkspaceContext.value ? workspaceContext.value?.topic.trim() : ''
    const { data } = await qaApi.post<QAResponsePayload>('/qa/analyze', {
      ...qaForm,
      student_id: String(user.userId),
      subject: qaForm.subject.trim() || (focusedTopic ? workspaceContext.value?.subject || '' : ''),
      current_knowledge_points: focusedTopic ? [focusedTopic] : [],
      use_knowledge_base: Boolean(focusedTopic),
      learning_route: focusedTopic ? {
        subject: workspaceContext.value?.subject || '',
        knowledge_point: focusedTopic,
        overview: workspaceContext.value?.goal ?? '',
      } : {},
      question,
      session_id: qaForm.session_id,
      session_title: qaForm.session_title || currentSession?.title || question.slice(0, 24),
    })

    upsertSessionFromResponse(data, question)
    await syncQaMistakeToNotebook(data, question)
    qaForm.question = ''
    qaForm.student_answer = ''
    qaForm.wrong_answer = ''
    lastFailedQuestion.value = ''
    await scrollToBottom()
  } catch (error: any) {
    lastFailedQuestion.value = question
    const state = resolveQaError(error, '发送失败，请稍后重试')
    qaError.value = state
    ElMessage.error(state.message)
  } finally {
    sending.value = false
  }
}

async function retryLastQuestion() {
  if (!lastFailedQuestion.value || sending.value) {
    return
  }
  qaForm.question = lastFailedQuestion.value
  await askQaAgent()
}

async function scrollToBottom() {
  await nextTick()
  const el = messagesRef.value
  if (!el) {
    return
  }
  el.scrollTop = el.scrollHeight
}

watch(activeMessages, () => {
  void scrollToBottom()
})

watch(sessionSearch, (value) => {
  scheduleSessionSearch(value)
})

onMounted(() => {
  void loadPersistedSessions()
})
</script>

<template>
  <div class="qa-shell" :class="{ 'history-collapsed': sideCollapsed }">
    <aside class="qa-sidebar" :class="{ collapsed: sideCollapsed }">
      <div class="qa-sidebar-head">
        <div v-if="!sideCollapsed">
          <div class="qa-sidebar-kicker">对话记录</div>
          <h3>历史会话</h3>
        </div>
        <button
          class="icon-btn collapse-icon"
          type="button"
          :aria-label="sideCollapsed ? '展开会话列表' : '收起会话列表'"
          :title="sideCollapsed ? '展开会话列表' : '收起会话列表'"
          @click="sideCollapsed = !sideCollapsed"
        >
          <el-icon><Expand v-if="sideCollapsed" /><Fold v-else /></el-icon>
        </button>
      </div>

      <div v-if="!sideCollapsed" class="qa-side-body">
        <button class="new-chat-btn" type="button" @click="() => createEmptySession()">
          <el-icon><Plus /></el-icon>
          <span>新建对话</span>
        </button>

        <label class="qa-search-wrap">
          <el-icon><Search /></el-icon>
          <input v-model="sessionSearch" class="qa-search-input" placeholder="搜索历史会话" />
        </label>

        <div class="qa-session-list">
          <section v-for="group in filteredSessionGroups" :key="group.label" class="qa-session-group">
            <div class="qa-session-group-title">{{ group.label }}</div>
            <div
              v-for="session in group.items"
              :key="session.id"
              class="qa-session-item"
              :class="{ active: session.id === activeSessionId }"
            >
              <button class="qa-session-main" type="button" @click="selectSession(session.id)">
                <strong>{{ session.title || '新对话' }}</strong>
                <span>{{ session.messageCount }} 条 · {{ formatSessionTime(session.updatedAt) }}</span>
              </button>
              <button
                class="qa-delete-btn"
                type="button"
                aria-label="删除会话"
                title="删除会话"
                @click.stop="removeSession(session.id)"
              >
                <el-icon><Delete /></el-icon>
              </button>
            </div>
          </section>
          <div v-if="!filteredSessionGroups.length" class="qa-empty-side">没有匹配的会话。</div>
        </div>
      </div>

      <div v-else class="qa-collapsed-actions">
        <button class="icon-btn" type="button" aria-label="新建对话" title="新建对话" @click="() => createEmptySession()">
          <el-icon><Plus /></el-icon>
        </button>
      </div>
    </aside>

    <section class="qa-main">
      <header class="qa-header">
        <div class="qa-header-copy">
          <div class="qa-header-kicker"><span></span> AI 学习助教</div>
          <h2>{{ sessionTitle }}</h2>
          <p>自由提问、跨学科交流；需要时也能结合学习内容生成课件与练习。</p>
        </div>
        <div class="qa-header-meta" aria-label="当前对话信息">
          <span>{{ activeSubject }}</span>
          <span>{{ activeMessages.length }} 条消息</span>
        </div>
      </header>

      <div ref="messagesRef" class="qa-messages">
        <div v-if="qaError" class="qa-system-card qa-error" role="alert">
          <div class="qa-error-copy">
            <strong>{{ qaError.title }}</strong>
            <span>{{ qaError.message }}</span>
          </div>
          <button
            v-if="qaError.retryable && lastFailedQuestion"
            class="qa-retry-btn"
            type="button"
            :disabled="sending"
            @click="retryLastQuestion"
          >
            重试
          </button>
        </div>
        <div v-else-if="!activeMessages.length" class="qa-empty-chat">
          <div class="qa-empty-icon"><el-icon><ChatDotRound /></el-icon></div>
          <strong>今天想弄懂什么？</strong>
          <p>学习、生活或跨学科问题都可以直接问；当前知识点仅在你选择时加入上下文。</p>
          <div class="qa-suggestion-list">
            <button v-for="item in suggestionQuestions" :key="item" type="button" @click="useSuggestion(item)">
              {{ item }}
            </button>
          </div>
        </div>

        <article
          v-for="message in activeMessages"
          :key="message.id"
          class="qa-bubble-wrap"
          :class="message.role"
        >
          <div class="qa-message-avatar" aria-hidden="true">
            <span v-if="message.role === 'user'">你</span>
            <el-icon v-else><ChatDotRound /></el-icon>
          </div>
          <div class="qa-message-column">
            <div class="qa-role">{{ message.role === 'user' ? '你' : 'AI 学习助教' }}</div>
            <div class="qa-bubble">
              <div class="qa-bubble-content">{{ message.content }}</div>
              <div class="qa-bubble-meta">
                <span>{{ formatSessionTime(message.created_at) }}</span>
                <span v-if="formatModelUsed(message.model_used)">{{ formatModelUsed(message.model_used) }}</span>
                <span v-if="message.confidence !== null && message.confidence !== undefined">
                  置信度 {{ Math.round(message.confidence * 100) }}%
                </span>
              </div>
              <p v-if="(message.generatedExercises?.exercises?.length ?? 0) > 2" class="qa-card-summary">
                其余题目已带入练习测评页，可在那里继续答题、提交和记录错题。
              </p>
            </div>

            <div v-if="message.generatedResource" class="qa-generated-card">
              <div class="qa-card-kicker">生成课件</div>
              <h4>{{ message.generatedResource.generation_plan?.title_suggestion || `${message.generatedResource.knowledge_point} 课件` }}</h4>
              <p class="qa-card-meta">
                {{ message.generatedResource.knowledge_point }}
                <span>·</span>
                <span>{{ message.generatedResource.resource_style }}</span>
              </p>
              <div v-if="message.generatedResource.generation_plan?.suggested_outline?.length" class="qa-chip-row">
                <span
                  v-for="item in message.generatedResource.generation_plan.suggested_outline.slice(0, 5)"
                  :key="item"
                  class="qa-chip"
                >
                  {{ item }}
                </span>
              </div>
              <pre class="qa-resource-preview">{{ resourcePreview(message.generatedResource.content) }}</pre>
            </div>

            <div v-if="message.generatedExercises" class="qa-generated-card">
              <div class="qa-card-kicker">生成习题</div>
              <h4>{{ message.generatedExercises.knowledge_point }}</h4>
              <p class="qa-card-summary">{{ message.generatedExercises.summary }}</p>
              <button class="qa-action-btn" @click="openExercisesInPractice(message.generatedExercises)">
                去练习测评做题
              </button>
              <div class="qa-exercise-list">
                <section
                  v-for="exercise in message.generatedExercises.exercises.slice(0, 2)"
                  :key="exercise.exercise_id"
                  class="qa-exercise-item"
                >
                  <div class="qa-exercise-head">
                    <strong>{{ exercise.prompt }}</strong>
                    <span>{{ exercise.difficulty }}</span>
                  </div>
                  <ul v-if="exercise.options?.length" class="qa-option-list">
                    <li v-for="option in exercise.options ?? []" :key="option">{{ option }}</li>
                  </ul>
                  <p class="qa-answer">答案：{{ exercise.answer }}</p>
                  <p class="qa-analysis-text">解析：{{ exercise.analysis }}</p>
                </section>
              </div>
            </div>

            <div v-if="message.analysis" class="qa-analysis-card">
              <div class="qa-card-kicker">学习诊断</div>
              <h4>本轮学习分析</h4>
              <p v-if="message.analysis.learning_state">{{ message.analysis.learning_state }}</p>

              <div v-if="message.analysis.identified_knowledge_gaps?.length" class="qa-chip-row">
                <span v-for="gap in message.analysis.identified_knowledge_gaps ?? []" :key="gap" class="qa-chip">{{ gap }}</span>
              </div>

              <ul v-if="message.analysis.study_suggestions?.length" class="qa-analysis-list">
                <li v-for="item in message.analysis.study_suggestions ?? []" :key="item">{{ item }}</li>
              </ul>
            </div>
          </div>
        </article>

        <div v-if="sending" class="qa-system-card qa-typing"><span></span><span></span><span></span> AI 正在思考</div>
      </div>

      <footer class="qa-composer">
        <details class="qa-context-details">
          <summary><el-icon><Setting /></el-icon>补充学习上下文（可选）</summary>
          <label v-if="workspaceContext?.topic" class="qa-context-toggle">
            <input v-model="useWorkspaceContext" type="checkbox" />
            <span>结合当前知识点：{{ workspaceContext.topic }}</span>
          </label>
          <div class="qa-input-grid">
            <label>学科（可选）<input v-model="qaForm.subject" class="qa-mini-input" placeholder="例如：高等数学" /></label>
            <label>我的思路<input v-model="qaForm.student_answer" class="qa-mini-input" placeholder="可填写目前的解题思路" /></label>
          </div>
        </details>

        <div class="qa-textarea-wrap">
          <textarea
            v-model="qaForm.question"
            class="qa-textarea"
            rows="2"
            placeholder="输入你的问题，Enter 发送，Shift + Enter 换行"
            @keydown.enter.exact.prevent="askQaAgent"
          />
          <button
            class="qa-send-btn"
            type="button"
            :aria-label="sending ? '正在发送' : '发送消息'"
            :title="sending ? '正在发送' : '发送消息'"
            :disabled="sending || !qaForm.question.trim()"
            @click="askQaAgent"
          >
            <el-icon><Promotion /></el-icon>
          </button>
        </div>
        <div class="qa-composer-tip">可直接询问任意主题；重要信息请核对来源。</div>
      </footer>
    </section>
  </div>
</template>

<style scoped>
.qa-shell {
  display: grid;
  grid-template-columns: 272px minmax(0, 1fr);
  gap: 14px;
  height: calc(100dvh - 160px);
  min-height: 600px;
  transition: grid-template-columns 0.2s ease;
}

.qa-shell.history-collapsed {
  grid-template-columns: 62px minmax(0, 1fr);
}

.qa-sidebar,
.qa-main {
  border: 1px solid var(--line);
  border-radius: 20px;
  background: var(--panel);
  box-shadow: var(--shadow-soft);
}

.qa-sidebar {
  display: flex;
  flex-direction: column;
  padding: 16px 14px;
  gap: 16px;
  overflow: hidden;
  min-width: 0;
}

.qa-sidebar.collapsed {
  align-items: center;
  padding-inline: 10px;
}

.qa-sidebar-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  min-height: 38px;
}

.qa-sidebar.collapsed .qa-sidebar-head {
  justify-content: center;
}

.qa-sidebar-kicker,
.qa-header-kicker,
.qa-card-kicker {
  font-size: 10px;
  font-weight: 750;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--accent);
}

.qa-sidebar h3 {
  margin: 3px 0 0;
  font-size: 17px;
  letter-spacing: -0.02em;
}

.icon-btn,
.new-chat-btn,
.qa-delete-btn,
.qa-suggestion-list button,
.qa-send-btn,
.qa-action-btn {
  font-family: inherit;
}

.icon-btn {
  width: 36px;
  height: 36px;
  flex: 0 0 36px;
  display: grid;
  place-items: center;
  border: 1px solid var(--line);
  border-radius: 10px;
  color: var(--muted);
  background: var(--panel);
  cursor: pointer;
  transition: color 0.16s ease, border-color 0.16s ease, background 0.16s ease;
}

.icon-btn:hover {
  color: var(--accent);
  border-color: color-mix(in srgb, var(--accent) 36%, var(--line));
  background: var(--accent-soft);
}

.qa-collapsed-actions {
  display: flex;
  justify-content: center;
}

.qa-side-body {
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr);
  gap: 10px;
  min-height: 0;
  flex: 1;
}

.new-chat-btn {
  width: 100%;
  height: 42px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  border: 1px solid color-mix(in srgb, var(--accent) 72%, var(--line));
  border-radius: 12px;
  color: #fff;
  background: linear-gradient(135deg, var(--accent), var(--accent-deep));
  box-shadow: 0 8px 18px color-mix(in srgb, var(--accent) 18%, transparent);
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
}

.qa-search-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 40px;
  padding: 0 12px;
  border: 1px solid var(--line);
  border-radius: 12px;
  color: var(--muted);
  background: var(--surface-soft);
}

.qa-search-wrap:focus-within {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}

.qa-search-input {
  min-width: 0;
  flex: 1;
  border: 0;
  padding: 0;
  background: transparent;
  color: var(--text);
  font-family: inherit;
  outline: none;
  font-size: 13px;
}

.qa-session-list {
  display: flex;
  flex-direction: column;
  gap: 13px;
  overflow: auto;
  padding-right: 3px;
  scrollbar-width: thin;
}

.qa-session-group {
  display: grid;
  gap: 5px;
}

.qa-session-group-title {
  font-size: 11px;
  font-weight: 650;
  color: var(--muted);
  padding: 2px 8px;
}

.qa-session-item {
  position: relative;
  display: flex;
  align-items: center;
  border: 1px solid transparent;
  border-radius: 12px;
  background: transparent;
  transition: border-color 0.16s ease, background 0.16s ease;
}

.qa-session-item:hover {
  border-color: var(--line);
  background: var(--surface-soft);
}

.qa-session-item.active {
  border-color: color-mix(in srgb, var(--accent) 28%, var(--line));
  background: var(--accent-soft);
}

.qa-session-item.active::before {
  content: '';
  position: absolute;
  left: -1px;
  top: 10px;
  bottom: 10px;
  width: 3px;
  border-radius: 999px;
  background: var(--accent);
}

.qa-session-main {
  min-width: 0;
  flex: 1;
  display: grid;
  gap: 3px;
  padding: 10px 8px 10px 12px;
  border: 0;
  color: var(--text);
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.qa-session-main strong {
  overflow: hidden;
  font-size: 13px;
  line-height: 1.5;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.qa-session-main span,
.qa-empty-side {
  color: var(--muted);
  font-size: 11px;
}

.qa-delete-btn {
  width: 30px;
  height: 30px;
  flex: 0 0 30px;
  display: grid;
  place-items: center;
  margin-right: 6px;
  border: 0;
  border-radius: 8px;
  color: var(--muted);
  background: transparent;
  opacity: 0;
  cursor: pointer;
  transition: opacity 0.16s ease, color 0.16s ease, background 0.16s ease;
}

.qa-session-item:hover .qa-delete-btn,
.qa-session-item.active .qa-delete-btn,
.qa-delete-btn:focus-visible {
  opacity: 1;
}

.qa-delete-btn:hover {
  color: var(--red);
  background: color-mix(in srgb, var(--red) 9%, transparent);
}

.qa-main {
  display: grid;
  grid-template-rows: auto 1fr auto;
  min-height: 0;
  overflow: hidden;
}

.qa-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  min-height: 88px;
  padding: 16px 24px;
  border-bottom: 1px solid var(--line);
}

.qa-header-copy {
  min-width: 0;
}

.qa-header-kicker {
  display: flex;
  align-items: center;
  gap: 7px;
}

.qa-header-kicker span {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--green);
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--green) 12%, transparent);
}

.qa-header h2 {
  overflow: hidden;
  margin: 4px 0 0;
  font-size: 20px;
  line-height: 1.25;
  letter-spacing: -0.025em;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.qa-header p {
  margin: 5px 0 0;
  color: var(--muted);
  font-size: 12px;
}

.qa-header-meta {
  display: flex;
  align-items: center;
  gap: 7px;
  flex: 0 0 auto;
}

.qa-header-meta span {
  padding: 6px 9px;
  border: 1px solid var(--line);
  border-radius: 8px;
  color: var(--muted);
  background: var(--surface-soft);
  font-size: 11px;
}

.qa-messages {
  padding: 24px clamp(20px, 4vw, 56px);
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 22px;
  min-height: 0;
  scroll-behavior: smooth;
  scrollbar-width: thin;
}

.qa-system-card {
  border: 1px dashed var(--line);
  border-radius: 14px;
  padding: 14px 16px;
  color: var(--muted);
  background: var(--surface-soft);
}

.qa-empty-chat {
  width: min(680px, 100%);
  margin: auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 28px 16px;
  text-align: center;
}

.qa-empty-icon {
  width: 52px;
  height: 52px;
  display: grid;
  place-items: center;
  margin-bottom: 15px;
  border-radius: 16px;
  color: #fff;
  background: linear-gradient(135deg, var(--accent), var(--accent-deep));
  box-shadow: 0 12px 28px color-mix(in srgb, var(--accent) 24%, transparent);
  font-size: 23px;
}

.qa-empty-chat strong {
  color: var(--text);
  font-size: 22px;
  letter-spacing: -0.025em;
}

.qa-empty-chat p {
  max-width: 520px;
  margin: 8px 0 18px;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.7;
}

.qa-suggestion-list {
  width: 100%;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.qa-suggestion-list button {
  min-height: 58px;
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-radius: 12px;
  color: var(--text);
  background: var(--panel);
  font-size: 12px;
  line-height: 1.5;
  cursor: pointer;
  transition: transform 0.16s ease, border-color 0.16s ease, background 0.16s ease;
}

.qa-suggestion-list button:hover {
  transform: translateY(-1px);
  border-color: color-mix(in srgb, var(--accent) 38%, var(--line));
  background: var(--accent-soft);
}

.qa-error {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  color: var(--red);
}

.qa-error-copy {
  display: grid;
  gap: 4px;
}

.qa-error-copy strong {
  color: var(--text);
  font-size: 13px;
}

.qa-error-copy span {
  color: var(--red);
  font-size: 12px;
  line-height: 1.6;
}

.qa-retry-btn {
  flex: 0 0 auto;
  border: 1px solid color-mix(in srgb, var(--red) 35%, var(--line));
  border-radius: 9px;
  padding: 7px 12px;
  color: var(--red);
  background: var(--panel);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}

.qa-retry-btn:hover {
  background: color-mix(in srgb, var(--red) 8%, var(--panel));
}

.qa-retry-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.qa-bubble-wrap {
  display: flex;
  gap: 10px;
  width: min(900px, 100%);
  margin-inline: auto;
}

.qa-bubble-wrap.user {
  justify-content: flex-end;
}

.qa-bubble-wrap.user .qa-message-avatar {
  order: 2;
  color: var(--accent);
  background: var(--accent-soft);
}

.qa-bubble-wrap.user .qa-message-column {
  order: 1;
  align-items: flex-end;
}

.qa-message-avatar {
  width: 32px;
  height: 32px;
  flex: 0 0 32px;
  display: grid;
  place-items: center;
  border: 1px solid var(--line);
  border-radius: 10px;
  color: #fff;
  background: linear-gradient(135deg, var(--accent), var(--accent-deep));
  font-size: 13px;
  font-weight: 750;
}

.qa-message-column {
  min-width: 0;
  width: min(820px, calc(100% - 42px));
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
}

.qa-role {
  font-size: 11px;
  font-weight: 650;
  color: var(--muted);
}

.qa-bubble,
.qa-analysis-card,
.qa-generated-card {
  max-width: 100%;
}

.qa-bubble {
  border-radius: 16px;
  border: 1px solid var(--line);
  padding: 13px 15px;
  background: var(--surface-soft);
}

.qa-bubble-wrap.user .qa-bubble {
  border-color: color-mix(in srgb, var(--accent) 22%, var(--line));
  background: var(--accent-soft);
}

.qa-bubble-content {
  white-space: pre-wrap;
  line-height: 1.75;
  font-size: 14px;
}

.qa-bubble-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
  font-size: 10px;
  color: var(--muted);
}

.qa-generated-card,
.qa-analysis-card {
  width: 100%;
  padding: 14px 15px;
  border-radius: 14px;
  border: 1px solid var(--line);
}

.qa-generated-card {
  background: linear-gradient(180deg, color-mix(in srgb, var(--accent) 6%, var(--panel)), var(--panel));
}

.qa-analysis-card {
  border-left: 3px solid var(--accent);
  background: color-mix(in srgb, var(--accent) 5%, var(--panel));
}

.qa-generated-card h4,
.qa-analysis-card h4 {
  margin: 3px 0 7px;
  font-size: 14px;
}

.qa-card-meta,
.qa-card-summary,
.qa-analysis-card p {
  margin: 0 0 10px;
  color: var(--muted);
}

.qa-card-meta {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 11px;
}

.qa-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}

.qa-chip {
  padding: 4px 9px;
  border-radius: 999px;
  font-size: 11px;
  background: var(--accent-soft);
  color: var(--accent);
}

.qa-resource-preview {
  margin: 0;
  white-space: pre-wrap;
  font-family: inherit;
  line-height: 1.7;
  color: var(--text);
}

.qa-action-btn {
  border: none;
  border-radius: 10px;
  padding: 9px 14px;
  margin-bottom: 12px;
  background: linear-gradient(135deg, var(--accent), var(--accent-deep));
  color: #fff;
  font-family: inherit;
  font-weight: 600;
  cursor: pointer;
}

.qa-exercise-list {
  display: grid;
  gap: 12px;
}

.qa-exercise-item {
  border: 1px solid color-mix(in srgb, var(--line) 90%, transparent);
  border-radius: 12px;
  padding: 12px 14px;
  background: color-mix(in srgb, var(--panel) 88%, transparent);
}

.qa-exercise-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.qa-exercise-head strong {
  font-size: 14px;
  line-height: 1.7;
}

.qa-exercise-head span {
  font-size: 12px;
  color: var(--muted);
  text-transform: capitalize;
}

.qa-option-list,
.qa-analysis-list {
  margin: 8px 0 0;
  padding-left: 18px;
  color: var(--muted);
  line-height: 1.7;
}

.qa-answer,
.qa-analysis-text {
  margin: 8px 0 0;
  line-height: 1.7;
}

.qa-answer {
  color: var(--text);
}

.qa-analysis-text {
  color: var(--muted);
}

.qa-composer {
  border-top: 1px solid var(--line);
  padding: 10px clamp(18px, 4vw, 48px) 12px;
  display: grid;
  gap: 8px;
  background: color-mix(in srgb, var(--panel) 96%, transparent);
  box-shadow: 0 -12px 28px color-mix(in srgb, var(--text) 3%, transparent);
}

.qa-context-details {
  width: min(900px, 100%);
  margin-inline: auto;
}

.qa-context-details summary {
  width: max-content;
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--muted);
  font-size: 11px;
  cursor: pointer;
  list-style: none;
}

.qa-context-details summary::-webkit-details-marker {
  display: none;
}

.qa-context-details[open] summary {
  margin-bottom: 8px;
  color: var(--accent);
}

.qa-context-toggle {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-bottom: 8px;
  color: var(--text);
  font-size: 12px;
  cursor: pointer;
}

.qa-context-toggle input {
  accent-color: var(--accent);
}

.qa-input-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.qa-input-grid label {
  display: grid;
  gap: 4px;
  color: var(--muted);
  font-size: 10px;
}

.qa-mini-input,
.qa-textarea {
  width: 100%;
  border: 1px solid var(--line);
  background: var(--panel);
  color: var(--text);
  border-radius: 12px;
  padding: 10px 12px;
  font-family: inherit;
  outline: none;
  transition: border-color 0.16s ease, box-shadow 0.16s ease;
}

.qa-mini-input:focus,
.qa-textarea:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}

.qa-textarea-wrap {
  width: min(900px, 100%);
  margin-inline: auto;
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 8px;
  align-items: end;
  padding: 7px;
  border: 1px solid var(--line);
  border-radius: 16px;
  background: var(--panel);
  box-shadow: 0 8px 24px color-mix(in srgb, var(--text) 5%, transparent);
}

.qa-textarea-wrap:focus-within {
  border-color: color-mix(in srgb, var(--accent) 65%, var(--line));
  box-shadow: 0 0 0 3px var(--accent-soft), 0 8px 24px color-mix(in srgb, var(--text) 5%, transparent);
}

.qa-textarea {
  border: 0;
  padding: 8px 9px;
  resize: none;
  min-height: 54px;
  max-height: 130px;
  line-height: 1.6;
}

.qa-textarea:focus {
  box-shadow: none;
}

.qa-send-btn {
  width: 42px;
  height: 42px;
  display: grid;
  place-items: center;
  border: none;
  border-radius: 12px;
  background: linear-gradient(135deg, var(--accent), var(--accent-deep));
  color: #fff;
  cursor: pointer;
  font-size: 18px;
  box-shadow: 0 8px 16px color-mix(in srgb, var(--accent) 22%, transparent);
}

.qa-send-btn:disabled {
  opacity: 0.42;
  cursor: not-allowed;
  box-shadow: none;
}

.qa-composer-tip {
  color: var(--muted);
  font-size: 10px;
  text-align: center;
}

.qa-typing {
  width: max-content;
  display: flex;
  align-items: center;
  gap: 5px;
  margin-inline: max(0px, calc((100% - 900px) / 2 + 42px));
  font-size: 11px;
}

.qa-typing span {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--accent);
  animation: qaTyping 1.1s ease-in-out infinite;
}

.qa-typing span:nth-child(2) {
  animation-delay: 0.14s;
}

.qa-typing span:nth-child(3) {
  animation-delay: 0.28s;
}

@keyframes qaTyping {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.45; }
  30% { transform: translateY(-3px); opacity: 1; }
}

@media (max-width: 1100px) {
  .qa-shell {
    grid-template-columns: 232px minmax(0, 1fr);
  }

  .qa-shell.history-collapsed {
    grid-template-columns: 58px minmax(0, 1fr);
  }

  .qa-header-meta span:first-child {
    display: none;
  }
}

@media (max-width: 820px) {
  .qa-shell,
  .qa-shell.history-collapsed {
    height: auto;
    min-height: 0;
    grid-template-columns: 1fr;
  }

  .qa-sidebar {
    max-height: 250px;
  }

  .qa-sidebar.collapsed {
    min-height: 56px;
  }

  .qa-main {
    height: calc(100dvh - 120px);
    min-height: 620px;
  }

  .qa-header {
    padding: 14px 18px;
  }

  .qa-header p,
  .qa-header-meta {
    display: none;
  }

  .qa-messages {
    padding-inline: 16px;
  }

  .qa-suggestion-list {
    grid-template-columns: 1fr;
  }

  .qa-input-grid,
  .qa-exercise-head {
    grid-template-columns: 1fr;
  }

  .qa-composer {
    padding-inline: 12px;
  }

  .qa-message-avatar {
    display: none;
  }

  .qa-message-column {
    width: 100%;
  }
}
</style>
