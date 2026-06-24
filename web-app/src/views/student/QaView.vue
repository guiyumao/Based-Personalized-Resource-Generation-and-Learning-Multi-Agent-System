<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../../stores/auth'
import {
  createChatSession,
  deleteChatSession,
  getChatSession,
  listChatSessions,
  qaApi,
  type ChatMessageItem,
  type ChatSessionDetail,
  type ChatSessionSummary,
  type ExerciseGenerationResponse,
  type QAAnalysisPayload,
  type QARequestPayload,
  type QAResponsePayload,
  type ResourceResult,
} from '../../api'
import {
  EXERCISE_STORAGE_KEY,
  readStudentWorkspaceContext,
  sameWorkspaceTopic,
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

const authStore = useAuthStore()
const user = authStore.user!
const router = useRouter()
const workspaceContext = ref<StudentWorkspaceContext | null>(null)

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
const activeSessionId = ref<number | null>(null)
const sending = ref(false)
const loadingSessions = ref(false)
const qaError = ref('')
const sideCollapsed = ref(false)
const sessionSearch = ref('')
const messagesRef = ref<HTMLDivElement | null>(null)

const activeSession = computed(() => sessions.value.find((item) => item.id === activeSessionId.value) ?? null)
const activeMessages = computed(() => activeSession.value?.messages ?? [])
const sessionTitle = computed(() => activeSession.value?.title || '新对话')

function formatModelUsed(modelUsed?: string) {
  const normalized = modelUsed?.trim()
  if (!normalized) {
    return ''
  }
  const labelMap: Record<string, string> = {
    qa_learning_llm: '学习助教',
    qa_general_llm: '通用助手',
    qa_general_grounded: '检索辅助',
    qa_general_fallback: '基础回答',
    qa_realtime: '实时信息',
    qa_orchestrated: '学习助教',
    large_model: '深度回答',
    small_model: '快速回答',
    fallback: '基础回答',
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
  const source = keyword
    ? sessions.value.filter((item) => {
        const title = item.title.toLowerCase()
        const hasMessage = item.messages.some((msg) => msg.content.toLowerCase().includes(keyword))
        return title.includes(keyword) || hasMessage
      })
    : sessions.value

  const groups = new Map<string, SessionGroup['items']>()
  for (const session of source) {
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

function createLocalDraftSession() {
  const draftTitle = workspaceContext.value ? buildWorkspaceSessionTitle(workspaceContext.value.topic) : '新对话'
  const id = Date.now()
  const session: UiSession = {
    id,
    title: draftTitle,
    subject: workspaceContext.value?.subject ?? '',
    topicHint: workspaceContext.value?.topic ?? '',
    updatedAt: new Date().toISOString(),
    messageCount: 0,
    messages: [],
    persisted: false,
    loaded: true,
  }
  sessions.value = [session, ...sessions.value.filter((item) => item.persisted || item.messageCount > 0)]
  activeSessionId.value = id
  qaForm.session_id = null
  qaForm.session_title = draftTitle
  qaError.value = ''
}

async function createEmptySession(persist = true) {
  if (!persist) {
    createLocalDraftSession()
    return
  }
  try {
    const detail = await createChatSession({
      user_id: user.userId,
      title: workspaceContext.value ? buildWorkspaceSessionTitle(workspaceContext.value.topic) : '新对话',
      subject: qaForm.subject,
    })
    const session = mapSessionDetail(detail)
    sessions.value = [session, ...sessions.value.filter((item) => item.persisted || item.messageCount > 0)]
    activeSessionId.value = session.id
    qaForm.session_id = session.id
    qaForm.session_title = session.title
    qaError.value = ''
    await scrollToBottom()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail ?? error?.message ?? '新建会话失败，已切换到临时会话')
    createLocalDraftSession()
  }
}

async function loadPersistedSessions() {
  loadingSessions.value = true
  qaError.value = ''
  try {
    applyWorkspaceContext()
    const rows = await listChatSessions(user.userId)
    sessions.value = rows.map(mapSessionSummary)
    if (workspaceContext.value && shouldStartWorkspaceDraft()) {
      createLocalDraftSession()
    } else if (sessions.value.length) {
      await selectSession(sessions.value[0].id)
    } else {
      createLocalDraftSession()
    }
  } catch (error: any) {
    qaError.value = error?.response?.data?.detail ?? error?.message ?? '加载历史会话失败'
    ElMessage.error(qaError.value)
    createLocalDraftSession()
  } finally {
    loadingSessions.value = false
  }
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
  const session = sessions.value.find((item) => item.id === sessionId)
  if (!session) {
    return
  }
  if (session.persisted && !session.loaded) {
    try {
      const detail = await getChatSession(sessionId, user.userId)
      const hydrated = mapSessionDetail(detail)
      sessions.value = sessions.value.map((item) => item.id === sessionId ? hydrated : item)
    } catch (error: any) {
      qaError.value = error?.response?.data?.detail ?? error?.message ?? '加载会话失败'
      ElMessage.error(qaError.value)
      return
    }
  }
  const selected = sessions.value.find((item) => item.id === sessionId)
  qaForm.session_id = selected?.persisted ? selected.id : null
  qaForm.session_title = selected?.title ?? session.title
  if (selected?.subject?.trim()) {
    qaForm.subject = selected.subject
  }
  if (selected?.topicHint?.trim()) {
    qaForm.current_knowledge_points = [selected.topicHint]
  }
  qaError.value = ''
  await scrollToBottom()
}

async function removeSession(sessionId: number) {
  const target = sessions.value.find((item) => item.id === sessionId)
  if (target?.persisted) {
    try {
      await deleteChatSession(sessionId, user.userId)
    } catch (error: any) {
      ElMessage.error(error?.response?.data?.detail ?? error?.message ?? '删除会话失败')
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
  if (!workspaceContext.value) {
    return
  }

  qaForm.subject = workspaceContext.value.subject || workspaceContext.value.topic
  qaForm.current_knowledge_points = [workspaceContext.value.topic]
  qaForm.learning_route = {
    subject: workspaceContext.value.subject,
    knowledge_point: workspaceContext.value.topic,
    overview: workspaceContext.value.goal ?? '',
  }
  if (!qaForm.session_title.trim() || qaForm.session_title === '新对话') {
    qaForm.session_title = buildWorkspaceSessionTitle(workspaceContext.value.topic)
  }
}

function shouldStartWorkspaceDraft() {
  if (!workspaceContext.value) {
    return false
  }
  const latestSession = sessions.value[0]
  if (!latestSession) {
    return true
  }
  return !sessionMatchesWorkspace(latestSession, workspaceContext.value)
}

function sessionMatchesWorkspace(session: UiSession, context: StudentWorkspaceContext) {
  if (sameWorkspaceTopic(session.topicHint, context.topic)) {
    return true
  }
  if (sameWorkspaceTopic(session.subject, context.topic)) {
    return true
  }
  if (sameWorkspaceTopic(session.subject, context.subject)) {
    return session.title.includes(context.topic)
  }
  return session.title.includes(context.topic)
}

function buildWorkspaceSessionTitle(topic: string) {
  return `${topic} 问答`
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

  applyWorkspaceContext()
  if (workspaceContext.value && activeSession.value && !sessionMatchesWorkspace(activeSession.value, workspaceContext.value)) {
    createLocalDraftSession()
  }

  const currentSession = activeSession.value
  if (!currentSession) {
    createLocalDraftSession()
  }

  sending.value = true
  qaError.value = ''
  try {
    const { data } = await qaApi.post<QAResponsePayload>('/qa/analyze', {
      ...qaForm,
      student_id: String(user.userId),
      question,
      session_id: qaForm.session_id,
      session_title: qaForm.session_title || currentSession?.title || question.slice(0, 24),
    })

    upsertSessionFromResponse(data, question)
    qaForm.question = ''
    qaForm.student_answer = ''
    qaForm.wrong_answer = ''
    await scrollToBottom()
  } catch (error: any) {
    qaError.value = error?.response?.data?.detail ?? error?.message ?? '发送失败'
    ElMessage.error(qaError.value)
  } finally {
    sending.value = false
  }
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

onMounted(() => {
  void loadPersistedSessions()
})
</script>

<template>
  <div class="qa-shell">
    <aside class="qa-sidebar" :class="{ collapsed: sideCollapsed }">
      <div class="qa-sidebar-head">
        <div>
          <div class="qa-sidebar-kicker">智能问答</div>
          <h3>历史会话</h3>
        </div>
        <button class="ghost-btn" @click="() => createEmptySession()">新建</button>
      </div>

      <button class="collapse-toggle" @click="sideCollapsed = !sideCollapsed">
        {{ sideCollapsed ? '展开会话' : '收起会话' }}
      </button>

      <div v-if="!sideCollapsed" class="qa-side-body">
        <input v-model="sessionSearch" class="qa-search-input" placeholder="搜索会话或消息内容" />

        <div class="qa-session-list">
          <section v-for="group in filteredSessionGroups" :key="group.label" class="qa-session-group">
            <div class="qa-session-group-title">{{ group.label }}</div>
            <button
              v-for="session in group.items"
              :key="session.id"
              class="qa-session-item"
              :class="{ active: session.id === activeSessionId }"
              @click="selectSession(session.id)"
            >
              <div class="qa-session-main">
                <strong>{{ session.title || '新对话' }}</strong>
                <span>{{ session.messageCount }} 条消息</span>
                <span>{{ formatSessionTime(session.updatedAt) }}</span>
              </div>
              <button class="qa-delete-btn" @click.stop="removeSession(session.id)">删除</button>
            </button>
          </section>
          <div v-if="!filteredSessionGroups.length" class="qa-empty-side">没有匹配的会话。</div>
        </div>
      </div>
    </aside>

    <section class="qa-main">
      <header class="qa-header">
        <div>
          <div class="qa-header-kicker">Chat Workspace</div>
          <h2>{{ sessionTitle }}</h2>
          <p>这里会保留上下文连续对话，你可以继续追问，也可以直接要求生成课件、习题和知识点补充。</p>
        </div>
      </header>

      <div ref="messagesRef" class="qa-messages">
        <div v-if="qaError" class="qa-system-card qa-error">{{ qaError }}</div>
        <div v-else-if="!activeMessages.length" class="qa-empty-chat">
          <strong>开始一段连续对话</strong>
          <p>例如：我要学习高等数学的定积分，补充说明知识点，再生成课件和习题。</p>
        </div>

        <article
          v-for="message in activeMessages"
          :key="message.id"
          class="qa-bubble-wrap"
          :class="message.role"
        >
          <div class="qa-role">{{ message.role === 'user' ? '你' : 'AI 助手' }}</div>
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
            <h4>本轮学习分析</h4>
            <p v-if="message.analysis.learning_state">{{ message.analysis.learning_state }}</p>

            <div v-if="message.analysis.identified_knowledge_gaps?.length" class="qa-chip-row">
              <span v-for="gap in message.analysis.identified_knowledge_gaps ?? []" :key="gap" class="qa-chip">{{ gap }}</span>
            </div>

            <ul v-if="message.analysis.study_suggestions?.length" class="qa-analysis-list">
              <li v-for="item in message.analysis.study_suggestions ?? []" :key="item">{{ item }}</li>
            </ul>
          </div>
        </article>

        <div v-if="sending" class="qa-system-card">AI 正在回复中...</div>
      </div>

      <footer class="qa-composer">
        <div class="qa-input-grid">
          <input v-model="qaForm.subject" class="qa-mini-input" placeholder="学科，可选，例如：高等数学" />
          <input v-model="qaForm.student_answer" class="qa-mini-input" placeholder="你的思路，可选" />
        </div>

        <div class="qa-textarea-wrap">
          <textarea
            v-model="qaForm.question"
            class="qa-textarea"
            rows="4"
            placeholder="输入问题，例如：继续讲一下定积分应用题，再来 5 道更难一点的题"
            @keydown.enter.exact.prevent="askQaAgent"
          />
          <button class="qa-send-btn" :disabled="sending || !qaForm.question.trim()" @click="askQaAgent">
            {{ sending ? '发送中...' : '发送' }}
          </button>
        </div>
      </footer>
    </section>
  </div>
</template>

<style scoped>
.qa-shell {
  display: grid;
  grid-template-columns: 300px 1fr;
  gap: 18px;
  min-height: calc(100vh - 140px);
}

.qa-sidebar,
.qa-main {
  border: 1px solid var(--line);
  border-radius: 24px;
  background: var(--panel);
}

.qa-sidebar {
  display: flex;
  flex-direction: column;
  padding: 18px;
  gap: 14px;
  overflow: hidden;
}

.qa-sidebar-head,
.qa-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
}

.qa-sidebar-kicker,
.qa-header-kicker,
.qa-card-kicker {
  font-size: 11px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--accent);
}

.qa-sidebar h3,
.qa-header h2 {
  margin: 8px 0 0;
}

.qa-header {
  padding: 22px 24px 0;
}

.qa-header p {
  color: var(--muted);
  margin: 8px 0 0;
}

.ghost-btn,
.collapse-toggle,
.qa-delete-btn {
  border: 1px solid var(--line);
  background: transparent;
  color: var(--text);
  border-radius: 12px;
  padding: 9px 14px;
  cursor: pointer;
  font-family: inherit;
}

.collapse-toggle {
  width: 100%;
}

.qa-side-body {
  display: grid;
  gap: 12px;
  min-height: 0;
}

.qa-search-input {
  width: 100%;
  border: 1px solid var(--line);
  background: var(--panel-strong);
  color: var(--text);
  border-radius: 14px;
  padding: 12px 14px;
  font-family: inherit;
  outline: none;
}

.qa-session-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
  overflow: auto;
}

.qa-session-group {
  display: grid;
  gap: 8px;
}

.qa-session-group-title {
  font-size: 12px;
  color: var(--muted);
  padding-left: 4px;
}

.qa-session-item {
  border: 1px solid var(--line);
  background: color-mix(in srgb, var(--text) 3%, transparent);
  color: var(--text);
  border-radius: 16px;
  padding: 14px;
  text-align: left;
  cursor: pointer;
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: flex-start;
}

.qa-session-item.active {
  border-color: color-mix(in srgb, var(--accent) 40%, transparent);
  background: color-mix(in srgb, var(--accent) 10%, transparent);
}

.qa-session-main {
  display: grid;
  gap: 4px;
}

.qa-session-main strong {
  font-size: 14px;
}

.qa-session-main span,
.qa-empty-side {
  color: var(--muted);
  font-size: 12px;
}

.qa-delete-btn {
  padding: 6px 10px;
  font-size: 12px;
}

.qa-main {
  display: grid;
  grid-template-rows: auto 1fr auto;
  min-height: 0;
}

.qa-messages {
  padding: 22px 24px;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 18px;
  min-height: 420px;
}

.qa-empty-chat,
.qa-system-card {
  border: 1px dashed var(--line);
  border-radius: 18px;
  padding: 18px;
  color: var(--muted);
  background: color-mix(in srgb, var(--text) 2%, transparent);
}

.qa-empty-chat strong {
  display: block;
  color: var(--text);
  margin-bottom: 8px;
}

.qa-error {
  color: var(--red);
}

.qa-bubble-wrap {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.qa-bubble-wrap.user {
  align-items: flex-end;
}

.qa-bubble-wrap.assistant {
  align-items: flex-start;
}

.qa-role {
  font-size: 12px;
  color: var(--muted);
}

.qa-bubble,
.qa-analysis-card,
.qa-generated-card {
  max-width: min(860px, 92%);
}

.qa-bubble {
  border-radius: 20px;
  border: 1px solid var(--line);
  padding: 16px 18px;
  background: color-mix(in srgb, var(--text) 4%, transparent);
}

.qa-bubble-wrap.user .qa-bubble {
  background: linear-gradient(135deg, color-mix(in srgb, var(--accent) 16%, transparent), color-mix(in srgb, var(--accent-deep) 12%, transparent));
}

.qa-bubble-content {
  white-space: pre-wrap;
  line-height: 1.8;
  font-size: 14px;
}

.qa-bubble-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 10px;
  font-size: 12px;
  color: var(--muted);
}

.qa-generated-card,
.qa-analysis-card {
  padding: 14px 16px;
  border-radius: 18px;
  border: 1px solid var(--line);
}

.qa-generated-card {
  background: linear-gradient(180deg, color-mix(in srgb, var(--accent) 8%, transparent), color-mix(in srgb, var(--accent-deep) 4%, transparent));
}

.qa-analysis-card {
  background: color-mix(in srgb, var(--accent) 6%, transparent);
}

.qa-generated-card h4,
.qa-analysis-card h4 {
  margin: 4px 0 8px;
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
  font-size: 12px;
}

.qa-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}

.qa-chip {
  padding: 5px 12px;
  border-radius: 999px;
  font-size: 12px;
  background: color-mix(in srgb, var(--accent) 14%, transparent);
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
  border-radius: 12px;
  padding: 10px 16px;
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
  border-radius: 14px;
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
  padding: 18px 24px 24px;
  display: grid;
  gap: 12px;
}

.qa-input-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.qa-mini-input,
.qa-textarea {
  width: 100%;
  border: 1px solid var(--line);
  background: var(--panel-strong);
  color: var(--text);
  border-radius: 14px;
  padding: 12px 14px;
  font-family: inherit;
  outline: none;
}

.qa-textarea-wrap {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 12px;
  align-items: end;
}

.qa-textarea {
  resize: none;
  min-height: 96px;
}

.qa-send-btn {
  border: none;
  border-radius: 14px;
  padding: 14px 22px;
  background: linear-gradient(135deg, var(--accent), var(--accent-deep));
  color: #fff;
  cursor: pointer;
  font-weight: 700;
  font-family: inherit;
}

.qa-send-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

@media (max-width: 1100px) {
  .qa-shell {
    grid-template-columns: 1fr;
  }

  .qa-sidebar.collapsed {
    display: none;
  }
}

@media (max-width: 720px) {
  .qa-input-grid,
  .qa-textarea-wrap,
  .qa-exercise-head {
    grid-template-columns: 1fr;
  }

  .qa-bubble,
  .qa-analysis-card,
  .qa-generated-card {
    max-width: 100%;
  }
}
</style>
