<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
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
  type QAAnalysisPayload,
  type QARequestPayload,
  type QAResponsePayload,
} from '../../api'

type UiMessage = {
  id: string
  role: 'user' | 'assistant'
  content: string
  created_at: string
  model_used?: string
  analysis?: QAAnalysisPayload | null
  confidence?: number | null
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
  updatedAt: string
  messageCount: number
  messages: UiMessage[]
  persisted: boolean
  loaded: boolean
}

const authStore = useAuthStore()
const user = authStore.user!

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

const filteredSessionGroups = computed<SessionGroup[]>(() => {
  const keyword = sessionSearch.value.trim().toLowerCase()
  const source = keyword
    ? sessions.value.filter((item) => item.title.toLowerCase().includes(keyword) || item.messages.some((msg) => msg.content.toLowerCase().includes(keyword)))
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
  const id = Date.now()
  const session: UiSession = {
    id,
    title: '新对话',
    updatedAt: new Date().toISOString(),
    messageCount: 0,
    messages: [] as UiMessage[],
    persisted: false,
    loaded: true,
  }
  sessions.value = [session, ...sessions.value.filter((item) => item.persisted || item.messageCount > 0)]
  activeSessionId.value = id
  qaForm.session_id = null
  qaForm.session_title = ''
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
      title: '新对话',
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
    ElMessage.error(error?.response?.data?.detail ?? error?.message ?? '新建会话失败，已临时保存在当前页面')
    createLocalDraftSession()
  }
}

async function loadPersistedSessions() {
  loadingSessions.value = true
  qaError.value = ''
  try {
    const rows = await listChatSessions(user.userId)
    sessions.value = rows.map(mapSessionSummary)
    if (sessions.value.length) {
      await selectSession(sessions.value[0].id)
    } else {
      await createEmptySession()
    }
  } catch (error: any) {
    qaError.value = error?.response?.data?.detail ?? error?.message ?? '加载历史会话失败'
    ElMessage.error(qaError.value)
    await createEmptySession(false)
  } finally {
    loadingSessions.value = false
  }
}

function mapSessionSummary(row: ChatSessionSummary): UiSession {
  return {
    id: row.id,
    title: row.title || '新对话',
    updatedAt: row.last_message_at || row.created_at,
    messageCount: row.message_count,
    messages: [],
    persisted: true,
    loaded: false,
  }
}

function mapSessionDetail(row: ChatSessionDetail): UiSession {
  return {
    id: row.id,
    title: row.title || '新对话',
    updatedAt: row.last_message_at || row.created_at,
    messageCount: row.message_count,
    messages: normalizeChatMessages(row.messages),
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
      return {
        id: `${item.role}-${item.id}`,
        role: item.role,
        content: item.content,
        created_at: item.created_at,
        model_used: item.model_used,
        analysis,
        confidence,
      } satisfies UiMessage
    })
}

function upsertSessionFromResponse(data: QAResponsePayload, question: string) {
  const normalizedMessages = normalizeQaMessages(data.message_history ?? [], data.structured_analysis, data.confidence)
  const updatedAt = normalizedMessages[normalizedMessages.length - 1]?.created_at ?? new Date().toISOString()
  const persistentId = data.session_id ?? activeSessionId.value ?? Date.now()
  const title = data.session_title?.trim() || question.slice(0, 24) || '智能问答'

  const nextSession = {
    id: persistentId,
    title,
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

function normalizeQaMessages(
  history: QAResponsePayload['message_history'],
  latestAnalysis: QAAnalysisPayload,
  confidence: number | null,
) {
  return history
    .filter((item) => item.role === 'user' || item.role === 'assistant')
    .map((item, index, source) => {
      const isLatestAssistant = item.role === 'assistant' && index === source.map((entry) => entry.role).lastIndexOf('assistant')
      return {
        id: `${item.role}-${item.id ?? index}`,
        role: item.role,
        content: item.content,
        created_at: item.created_at,
        model_used: item.model_used,
        analysis: isLatestAssistant ? latestAnalysis : null,
        confidence: isLatestAssistant ? confidence : null,
      } satisfies UiMessage
    })
}

async function askQaAgent() {
  const question = qaForm.question.trim()
  if (!question || sending.value) {
    return
  }

  const currentSession = activeSession.value
  if (!currentSession) {
    await createEmptySession()
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
          <p>这里按网页版聊天的方式保留历史上下文，你可以连续追问，不再是单轮表单式问答。</p>
        </div>
      </header>

      <div ref="messagesRef" class="qa-messages">
        <div v-if="qaError" class="qa-system-card qa-error">{{ qaError }}</div>
        <div v-else-if="!activeMessages.length" class="qa-empty-chat">
          <strong>开始一段连续对话</strong>
          <p>首轮提问后，这个会话会自动生成标题，并一直带着历史上下文继续。</p>
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
              <span v-if="message.model_used">{{ message.model_used }}</span>
              <span v-if="message.confidence !== null && message.confidence !== undefined">置信度 {{ Math.round(message.confidence * 100) }}%</span>
            </div>
          </div>

          <div v-if="message.analysis" class="qa-analysis-card">
            <h4>本轮学习分析</h4>
            <p v-if="message.analysis.learning_state">{{ message.analysis.learning_state }}</p>

            <div v-if="message.analysis.identified_knowledge_gaps.length" class="qa-chip-row">
              <span v-for="gap in message.analysis.identified_knowledge_gaps" :key="gap" class="qa-chip">{{ gap }}</span>
            </div>

            <ul v-if="message.analysis.study_suggestions.length" class="qa-analysis-list">
              <li v-for="item in message.analysis.study_suggestions" :key="item">{{ item }}</li>
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
            placeholder="输入你的问题，系统会按当前会话上下文继续聊天"
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
.qa-header-kicker {
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

.qa-bubble {
  max-width: min(820px, 88%);
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

.qa-analysis-card {
  max-width: min(820px, 88%);
  padding: 14px 16px;
  border-radius: 18px;
  border: 1px solid var(--line);
  background: color-mix(in srgb, var(--accent) 6%, transparent);
}

.qa-analysis-card h4 {
  margin: 0 0 8px;
}

.qa-analysis-card p {
  margin: 0 0 10px;
  color: var(--muted);
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

.qa-analysis-list {
  margin: 0;
  padding-left: 18px;
  color: var(--muted);
  line-height: 1.7;
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
  .qa-textarea-wrap {
    grid-template-columns: 1fr;
  }

  .qa-bubble,
  .qa-analysis-card {
    max-width: 100%;
  }
}
</style>
