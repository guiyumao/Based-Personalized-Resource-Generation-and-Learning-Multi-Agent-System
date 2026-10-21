<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { Close, CopyDocument, Expand, Fold, Promotion, Refresh, Setting, Tickets } from '@element-plus/icons-vue'
import { getChatSession, listChatSessions, type ChatSessionSummary } from '../api/chat'
import { cancelAssistantTask, requestAssistantTaskCancel, confirmAssistantPath, deleteAssistantAttachment, deleteAssistantMemory, getAssistantTask, listAssistantAttachments, listAssistantMemory, listAssistantTasks, retryAssistantTask, saveAssistantMemory, sendAssistantMessage, streamAssistantMessage, uploadAssistantAttachment, type AssistantAction, type AssistantAttachment, type AssistantCard, type AssistantMemory } from '../api/assistant'
import { useAuthStore } from '../stores/auth'
import { renderLearningMarkdown } from '../utils/renderLearningMarkdown'
import { EXERCISE_STORAGE_KEY } from '../utils/studentWorkspace'
import XiaoZhiAvatar, { type XiaoZhiState } from './XiaoZhiAvatar.vue'

type PetMessage = {
  id: string
  role: 'user' | 'assistant' | 'task'
  content: string
  cards?: AssistantCard[]
  sources?: Array<Record<string, unknown>>
  taskId?: number
  status?: string
  attachments?: AssistantAttachment[]
}

type DragTarget = 'pet' | 'panel'
type DragState = {
  target: DragTarget
  startX: number
  startY: number
  originX: number
  originY: number
  moved: boolean
}

const PET_WIDTH = 92
const PET_HEIGHT = 104
const PANEL_MAX_WIDTH = 420
const PANEL_MAX_HEIGHT = 640
const VIEWPORT_GAP = 14
const POSITION_STORAGE_KEY = 'learning-assistant-pet-position'
const MOTION_STORAGE_KEY = 'learning-assistant-motion'

const authStore = useAuthStore()
const router = useRouter()
const dashboardDocked = computed(() => router.currentRoute.value.name === 'admin')
const isOpen = ref(false)
const mode = ref<'chat' | 'workspace'>('chat')
const historyOpen = ref(false)
const settingsOpen = ref(false)
const motionEnabled = ref(true)
const sessions = ref<ChatSessionSummary[]>([])
const selectedAction = ref<AssistantAction | null>(null)
const teachingMode = ref('standard')
const useLearningContext = ref(false)
const allowWebKnowledge = ref(true)
const courseKey = ref('')
const memories = ref<AssistantMemory[]>([])
const storedAttachments = ref<AssistantAttachment[]>([])
const attachmentError = ref('')
const memoryType = ref<AssistantMemory['memory_type']>('goal')
const memoryDraft = ref('')
const memoryCourse = ref('')
const editingMemoryId = ref<number | null>(null)
const memoryError = ref('')
const currentTaskId = ref<number | null>(null)
const cancellingTask = ref(false)
const unreadCount = ref(0)
const avatarMood = ref<XiaoZhiState>('idle')
const positionReady = ref(false)
const dragging = ref(false)
const draft = ref('')
const sending = ref(false)
const errorMessage = ref('')
const sessionId = ref<number | null>(null)
const messages = ref<PetMessage[]>([])
const selectedAttachments = ref<AssistantAttachment[]>([])
const uploadingAttachment = ref(false)
const attachmentInputRef = ref<HTMLInputElement | null>(null)
const inputRef = ref<HTMLTextAreaElement | null>(null)
const messagesRef = ref<HTMLDivElement | null>(null)
const viewport = reactive({ width: 0, height: 0 })
const petPosition = reactive({ x: 0, y: 0 })
const panelPosition = reactive({ x: VIEWPORT_GAP, y: VIEWPORT_GAP })
let dragState: DragState | null = null
let suppressPetClickUntil = 0
let taskPollTimer: ReturnType<typeof setInterval> | null = null
let pendingRequest: { content: string; action: AssistantAction | null; requestId: string; conversationId: number | null; attachmentIds: string; partialId?: string } | null = null
let streamController: AbortController | null = null
let removeRouteHook: (() => void) | null = null
const retryRequestIds = new Map<number, string>()

const suggestions: Array<{ label: string; action: AssistantAction; prompt: string }> = [
  { label: '向小智提问', action: 'qa', prompt: '用一个例子解释二叉树的前序遍历' },
  { label: '分析我的学情', action: 'profile', prompt: '分析我的学情和薄弱知识点' },
  { label: '查找教材资料', action: 'search', prompt: '查找二叉树前序遍历的教材资料' },
  { label: '生成学习课件', action: 'courseware', prompt: '帮我生成二叉树前序遍历的学习课件' },
  { label: '生成针对性练习', action: 'exercise', prompt: '生成二叉树前序遍历的针对性练习' },
  { label: '制定学习计划', action: 'plan', prompt: '制定数据结构复习计划' },
  { label: '推荐学习资源', action: 'recommend', prompt: '根据我的学习情况推荐学习资源' },
]
const availableSuggestions = computed(() => authStore.user?.role === 'teacher'
  ? suggestions.filter((item) => item.action === 'qa' || item.action === 'search') : suggestions)

const assistantState = computed<XiaoZhiState>(() => {
  if (sending.value) return currentTaskId.value ? 'working' : avatarMood.value === 'searching' || avatarMood.value === 'speaking' ? avatarMood.value : 'thinking'
  if (errorMessage.value) return 'error'
  if (draft.value) return 'listening'
  return avatarMood.value
})

const panelDimensions = computed(() => ({
  width: Math.min(mode.value === 'workspace' ? 980 : PANEL_MAX_WIDTH, Math.max(280, viewport.width - VIEWPORT_GAP * 2)),
  height: Math.min(mode.value === 'workspace' ? 740 : PANEL_MAX_HEIGHT, Math.max(320, viewport.height - VIEWPORT_GAP * 2)),
}))

const petStyle = computed(() => ({
  left: `${petPosition.x}px`,
  top: `${petPosition.y}px`,
}))

const panelStyle = computed(() => ({
  left: `${panelPosition.x}px`,
  top: `${panelPosition.y}px`,
  width: `${panelDimensions.value.width}px`,
  height: `${panelDimensions.value.height}px`,
}))

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), Math.max(min, max))
}

function clampPetPosition() {
  petPosition.x = clamp(petPosition.x, VIEWPORT_GAP, viewport.width - PET_WIDTH - VIEWPORT_GAP)
  petPosition.y = clamp(petPosition.y, VIEWPORT_GAP, viewport.height - PET_HEIGHT - VIEWPORT_GAP)
}

function clampPanelPosition() {
  panelPosition.x = clamp(
    panelPosition.x,
    VIEWPORT_GAP,
    viewport.width - panelDimensions.value.width - VIEWPORT_GAP,
  )
  panelPosition.y = clamp(
    panelPosition.y,
    VIEWPORT_GAP,
    viewport.height - panelDimensions.value.height - VIEWPORT_GAP,
  )
}

function savePetPosition() {
  localStorage.setItem(POSITION_STORAGE_KEY, JSON.stringify(petPosition))
}

function avoidInteractiveControls() {
  if (isOpen.value || viewport.width < 620) return
  const controls = Array.from(document.querySelectorAll<HTMLElement>('button, input, textarea, select, a, [role="button"]'))
    .filter((el) => !el.closest('.assistant-layer'))
    .map((el) => el.getBoundingClientRect())
    .filter((box) => box.width > 0 && box.height > 0 && box.width < viewport.width * .8)
  const overlaps = (x: number, y: number) => controls.some((box) =>
    x < box.right + 8 && x + PET_WIDTH > box.left - 8 && y < box.bottom + 8 && y + PET_HEIGHT > box.top - 8,
  )
  if (!overlaps(petPosition.x, petPosition.y)) return
  const edgeX = [VIEWPORT_GAP, viewport.width - PET_WIDTH - VIEWPORT_GAP]
  const candidates: Array<{ x: number; y: number; distance: number }> = []
  for (const x of edgeX) {
    for (let y = VIEWPORT_GAP; y <= viewport.height - PET_HEIGHT - VIEWPORT_GAP; y += 22) {
      if (!overlaps(x, y)) candidates.push({ x, y, distance: Math.abs(x - petPosition.x) + Math.abs(y - petPosition.y) })
    }
  }
  candidates.sort((a, b) => a.distance - b.distance)
  if (candidates[0]) {
    petPosition.x = candidates[0].x
    petPosition.y = candidates[0].y
    savePetPosition()
  }
}

function restorePetPosition() {
  try {
    const saved = JSON.parse(localStorage.getItem(POSITION_STORAGE_KEY) || '{}') as Partial<typeof petPosition>
    if (Number.isFinite(saved.x) && Number.isFinite(saved.y)) {
      petPosition.x = Number(saved.x)
      petPosition.y = Number(saved.y)
      clampPetPosition()
      return
    }
  } catch {
    localStorage.removeItem(POSITION_STORAGE_KEY)
  }
  petPosition.x = viewport.width - PET_WIDTH - 24
  petPosition.y = viewport.height - PET_HEIGHT - 24
  clampPetPosition()
}

function handleViewportResize() {
  viewport.width = window.innerWidth
  viewport.height = window.innerHeight
  clampPetPosition()
  clampPanelPosition()
  avoidInteractiveControls()
}

function openPanel() {
  const dimensions = panelDimensions.value
  panelPosition.x = petPosition.x + PET_WIDTH - dimensions.width
  panelPosition.y = petPosition.y + PET_HEIGHT - dimensions.height
  clampPanelPosition()
  isOpen.value = true
  unreadCount.value = 0
  avatarMood.value = 'greeting'
  void loadSessions()
  void nextTick(() => inputRef.value?.focus())
}

function closePanel() {
  const dimensions = panelDimensions.value
  petPosition.x = panelPosition.x + dimensions.width - PET_WIDTH
  petPosition.y = panelPosition.y + dimensions.height - PET_HEIGHT
  clampPetPosition()
  savePetPosition()
  isOpen.value = false
  settingsOpen.value = false
  avatarMood.value = 'idle'
}

function toggleWorkspace() {
  mode.value = mode.value === 'chat' ? 'workspace' : 'chat'
  const dimensions = panelDimensions.value
  panelPosition.x = mode.value === 'workspace' ? (viewport.width - dimensions.width) / 2 : petPosition.x + PET_WIDTH - dimensions.width
  panelPosition.y = mode.value === 'workspace' ? (viewport.height - dimensions.height) / 2 : petPosition.y + PET_HEIGHT - dimensions.height
  clampPanelPosition()
}

function handlePetClick() {
  if (Date.now() < suppressPetClickUntil) {
    return
  }
  openPanel()
}

function startDrag(event: PointerEvent, target: DragTarget) {
  if (event.button !== 0) {
    return
  }
  if (target === 'panel' && (event.target as HTMLElement).closest('button')) {
    return
  }
  event.preventDefault()
  const origin = target === 'pet' ? petPosition : panelPosition
  dragState = {
    target,
    startX: event.clientX,
    startY: event.clientY,
    originX: origin.x,
    originY: origin.y,
    moved: false,
  }
  window.addEventListener('pointermove', handleDrag)
  window.addEventListener('pointerup', finishDrag, { once: true })
}

function handleDrag(event: PointerEvent) {
  if (!dragState) {
    return
  }
  const deltaX = event.clientX - dragState.startX
  const deltaY = event.clientY - dragState.startY
  if (!dragState.moved && Math.hypot(deltaX, deltaY) < 4) {
    return
  }
  dragState.moved = true
  dragging.value = true
  if (dragState.target === 'pet') {
    petPosition.x = dragState.originX + deltaX
    petPosition.y = dragState.originY + deltaY
    clampPetPosition()
  } else {
    panelPosition.x = dragState.originX + deltaX
    panelPosition.y = dragState.originY + deltaY
    clampPanelPosition()
  }
}

function finishDrag() {
  const finishedState = dragState
  dragState = null
  dragging.value = false
  window.removeEventListener('pointermove', handleDrag)
  if (!finishedState) {
    return
  }
  if (finishedState.target === 'pet') {
    if (finishedState.moved) {
      petPosition.x = petPosition.x + PET_WIDTH / 2 < viewport.width / 2
        ? VIEWPORT_GAP : viewport.width - PET_WIDTH - VIEWPORT_GAP
      clampPetPosition()
    }
    savePetPosition()
    avoidInteractiveControls()
    suppressPetClickUntil = finishedState.moved ? Date.now() + 250 : 0
  }
}

function useSuggestion(value: { prompt: string; action: AssistantAction }) {
  draft.value = value.prompt
  selectedAction.value = value.action
  void nextTick(() => inputRef.value?.focus())
}

async function loadMemories() {
  try {
    memories.value = await listAssistantMemory()
    memoryError.value = ''
  } catch { memoryError.value = '学习记忆暂时无法读取。' }
}

async function loadAttachments() {
  try { storedAttachments.value = await listAssistantAttachments(); attachmentError.value = '' }
  catch { attachmentError.value = '已上传资料暂时无法读取。' }
}

async function removeStoredAttachment(id: number) {
  try {
    await deleteAssistantAttachment(id)
    selectedAttachments.value = selectedAttachments.value.filter((item) => item.id !== id)
    await loadAttachments()
  } catch { attachmentError.value = '删除资料失败，请稍后重试。' }
}

function toggleSettings() {
  settingsOpen.value = !settingsOpen.value
  if (settingsOpen.value) {
    void loadMemories()
    void loadAttachments()
  }
}

function editMemory(memory: AssistantMemory) {
  editingMemoryId.value = memory.id
  memoryType.value = memory.memory_type
  memoryDraft.value = memory.content
  memoryCourse.value = memory.course_key
}

async function saveMemory() {
  const content = memoryDraft.value.trim()
  if (!content) { memoryError.value = '请填写要保存的学习记忆。'; return }
  try {
    await saveAssistantMemory({ memory_type: memoryType.value, content, course_key: memoryCourse.value.trim() }, editingMemoryId.value || undefined)
    memoryDraft.value = ''
    editingMemoryId.value = null
    memoryError.value = ''
    await loadMemories()
  } catch { memoryError.value = '保存学习记忆失败，请稍后重试。' }
}

async function removeMemory(id: number) {
  try { await deleteAssistantMemory(id); await loadMemories() }
  catch { memoryError.value = '删除学习记忆失败，请稍后重试。' }
}

function scrollMessages() {
  void nextTick(() => {
    if (messagesRef.value) {
      messagesRef.value.scrollTop = messagesRef.value.scrollHeight
    }
  })
}

function sourceLabel(source: Record<string, unknown>) {
  const nested = source.source && typeof source.source === 'object' ? source.source as Record<string, unknown> : {}
  return String(source.title || source.document_name || nested.title || '知识资料')
}

function sourceSummary(source: Record<string, unknown>) {
  return String(source.summary || source.chapter || source.knowledge_point || '').slice(0, 180)
}

function sourceLink(source: Record<string, unknown>) {
  const nested = source.source && typeof source.source === 'object' ? source.source as Record<string, unknown> : {}
  const link = String(source.source_url || source.url || nested.source_url || nested.url || '')
  return /^https?:\/\//i.test(link) ? link : ''
}

async function loadSessions() {
  if (!authStore.user) return
  try {
    sessions.value = await listChatSessions(authStore.user.userId, 30)
  } catch { /* Keep the current conversation available when history fails. */ }
}

async function loadSession(id: number) {
  if (!authStore.user || sending.value) return
  try {
    const [session, tasks] = await Promise.all([
      getChatSession(id, authStore.user.userId),
      listAssistantTasks(id),
    ])
    sessionId.value = id
    pendingRequest = null
    localStorage.setItem(`learning-assistant-session-${authStore.user.userId}`, String(id))
    const taskById = new Map(tasks.map((task) => [task.id, task]))
    messages.value = session.messages.filter((item) => item.role !== 'system').map((item) => {
      const taskId = Number(item.metadata?.task_id || 0)
      const task = taskById.get(taskId)
      return {
        id: `${item.role}-${item.id}`,
        role: item.role as 'user' | 'assistant',
        content: item.content,
        taskId: taskId || undefined,
        attachments: (item.metadata?.attachments as AssistantAttachment[] | undefined) || [],
        cards: task?.result.cards || (item.metadata?.cards as AssistantCard[] | undefined),
        sources: task?.result.sources || (item.metadata?.sources as Array<Record<string, unknown>> | undefined) || (item.metadata?.knowledge_sources as Array<Record<string, unknown>> | undefined),
      }
    })
    const displayedTaskIds = new Set(messages.value.filter((item) => item.role === 'assistant' && item.taskId).map((item) => item.taskId))
    const unfinished = tasks.filter((task) => task.status === 'PENDING' || task.status === 'RUNNING' || task.status === 'CANCEL_REQUESTED')
    for (const task of tasks.slice().reverse()) {
      if (displayedTaskIds.has(task.id)) continue
      messages.value.push({
        id: `task-${task.id}`,
        role: 'task',
        content: task.status === 'FAILED' || task.status === 'TIMED_OUT' ? task.result.content || '任务暂时未完成，请重试。'
          : task.status === 'CANCELLED' ? task.result.content || '任务已取消。'
            : task.status === 'SUCCEEDED' ? task.result.content || '任务完成' : task.current_step,
        taskId: task.id,
        status: task.status,
        cards: task.result.cards || [],
        sources: task.result.sources || [],
      })
    }
    if (unfinished[0]) startTaskPolling(unfinished[0].id)
    historyOpen.value = false
    scrollMessages()
  } catch {
    errorMessage.value = '历史会话暂时无法读取，请稍后重试。'
  }
}

function stopTaskPolling() {
  if (taskPollTimer) clearInterval(taskPollTimer)
  taskPollTimer = null
  currentTaskId.value = null
}

async function refreshTask(taskId: number) {
  try {
    const task = await getAssistantTask(taskId)
    const target = messages.value.find((item) => item.taskId === taskId)
    if (!target) return
    target.status = task.status
    target.content = task.status === 'SUCCEEDED' ? task.result.content || '任务完成'
      : task.status === 'FAILED' || task.status === 'TIMED_OUT' ? task.result.content || '任务暂时未完成，请重试。'
        : task.status === 'CANCELLED' ? task.result.content || '任务已取消。' : task.current_step
    target.cards = task.result.cards || []
    target.sources = task.result.sources || []
    if (task.status === 'SUCCEEDED' || task.status === 'FAILED' || task.status === 'TIMED_OUT' || task.status === 'CANCELLED') {
      if (!isOpen.value && task.status === 'SUCCEEDED') unreadCount.value += 1
      stopTaskPolling()
      sending.value = false
      avatarMood.value = task.status === 'SUCCEEDED' ? 'success' : task.status === 'FAILED' || task.status === 'TIMED_OUT' ? 'warning' : 'idle'
      void loadSessions()
    }
    scrollMessages()
  } catch {
    stopTaskPolling()
    sending.value = false
    errorMessage.value = '任务状态暂时无法读取，请稍后查看历史会话。'
  }
}

function startTaskPolling(taskId: number) {
  stopTaskPolling()
  currentTaskId.value = taskId
  sending.value = true
  void refreshTask(taskId)
  taskPollTimer = setInterval(() => void refreshTask(taskId), 2500)
}

async function send() {
  const content = draft.value.trim()
  if (!content || sending.value || uploadingAttachment.value) {
    return
  }
  if (!authStore.user) {
    errorMessage.value = '登录状态已失效，请重新登录后继续使用。'
    return
  }
  draft.value = ''
  errorMessage.value = ''
  const action = selectedAction.value || undefined
  selectedAction.value = null
  const attachmentIds = selectedAttachments.value.map((item) => item.id).join(',')
  const isRetry = pendingRequest?.content === content && pendingRequest.action === (action || null)
    && pendingRequest.conversationId === sessionId.value && pendingRequest.attachmentIds === attachmentIds
  const requestId = isRetry && pendingRequest ? pendingRequest.requestId : crypto.randomUUID()
  if (isRetry) {
    if (pendingRequest?.partialId) messages.value = messages.value.filter((item) => item.id !== pendingRequest?.partialId)
  } else {
    messages.value.push({ id: `user-${Date.now()}`, role: 'user', content, attachments: [...selectedAttachments.value] })
  }
  pendingRequest = null
  scrollMessages()
  sending.value = true
  avatarMood.value = 'thinking'
  try {
    const request = {
      conversation_id: sessionId.value,
      client_request_id: requestId,
      message: content,
      action,
      teaching_mode: teachingMode.value,
      use_learning_context: useLearningContext.value,
      allow_web_knowledge: allowWebKnowledge.value,
      course_key: courseKey.value.trim(),
      attachment_ids: selectedAttachments.value.map((item) => item.id),
    }
    const useStream = action === 'qa' || (!action && !/(课件|讲义|练习|习题|出题|计划|学情|薄弱|掌握情况|成绩分析|查找资料|检索资料|教材资料|知识库|推荐学习资源|推荐资料|资源推荐)/i.test(content))
    if (useStream) {
      const streamed: PetMessage = { id: `assistant-stream-${Date.now()}`, role: 'assistant', content: '' }
      messages.value.push(streamed)
      streamController = new AbortController()
      let pendingText = ''
      let updateTimer: ReturnType<typeof setTimeout> | null = null
      const flushText = () => {
        if (pendingText) streamed.content += pendingText
        pendingText = ''
        updateTimer = null
        scrollMessages()
      }
      try {
        await streamAssistantMessage({ ...request, action: 'qa' }, (event) => {
          if (event.event === 'start') {
            sessionId.value = event.data.conversation_id
            localStorage.setItem(`learning-assistant-session-${authStore.user!.userId}`, String(event.data.conversation_id))
          } else if (event.event === 'stage') {
            avatarMood.value = event.data.stage === 'searching' ? 'searching' : 'thinking'
          } else if (event.event === 'delta') {
            pendingText += event.data.text
            avatarMood.value = 'speaking'
            if (!updateTimer) updateTimer = setTimeout(flushText, 50)
          } else if (event.event === 'final') {
            if (updateTimer) clearTimeout(updateTimer)
            flushText()
            streamed.id = `assistant-${event.data.message_id}`
            streamed.content = event.data.content
            streamed.sources = event.data.metadata?.knowledge_sources as Array<Record<string, unknown>> | undefined
            if (!isOpen.value) unreadCount.value += 1
          }
        }, streamController.signal)
      } finally {
        if (updateTimer) clearTimeout(updateTimer)
        flushText()
      }
      sending.value = false
      pendingRequest = null
      selectedAttachments.value = []
      void loadSessions()
      return
    }
    const response = await sendAssistantMessage(request)
    sessionId.value = response.conversation_id
    localStorage.setItem(`learning-assistant-session-${authStore.user.userId}`, String(response.conversation_id))
    if (response.kind === 'message') {
      messages.value.push({
        id: `assistant-${response.message.message_id}`,
        role: 'assistant',
        content: response.message.content,
        sources: response.message.metadata?.knowledge_sources as Array<Record<string, unknown>> | undefined,
      })
      avatarMood.value = 'speaking'
      sending.value = false
      pendingRequest = null
      selectedAttachments.value = []
      void loadSessions()
    } else {
      const task = response.task
      messages.value.push({ id: `task-${task.id}`, role: 'task', content: task.current_step, taskId: task.id, status: task.status })
      startTaskPolling(task.id)
      pendingRequest = null
      selectedAttachments.value = []
    }
    scrollMessages()
  } catch (error: any) {
    const partial = messages.value.at(-1)
    const partialId = partial?.id.startsWith('assistant-stream-') ? partial.id : undefined
    if (partial?.id.startsWith('assistant-stream-')) {
      if (partial.content.trim()) partial.content += '\n\n_回答已中断，请查看历史确认保存状态。_'
      else messages.value.pop()
    }
    if (error?.name === 'AbortError') {
      pendingRequest = { content, action: action || null, requestId, conversationId: sessionId.value, attachmentIds, partialId }
      draft.value = content
      selectedAction.value = action || null
      errorMessage.value = '已停止生成。请查看历史确认回答是否保存，或重试这条提问。'
      sending.value = false
      return
    }
    pendingRequest = { content, action: action || null, requestId, conversationId: sessionId.value, attachmentIds, partialId }
    draft.value = content
    selectedAction.value = action || null
    const detail = error?.response?.data?.detail
    errorMessage.value = error?.message || (typeof detail === 'object' ? detail?.message : detail)
      || '助手暂时没有完成回答，请稍后重试。'
    sending.value = false
  } finally {
    streamController = null
    void nextTick(() => inputRef.value?.focus())
  }
}

function stopStream() { streamController?.abort() }

async function uploadSelectedFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  if (selectedAttachments.value.length >= 3) {
    errorMessage.value = '每条消息最多添加 3 个文件。'
    return
  }
  uploadingAttachment.value = true
  errorMessage.value = ''
  try {
    const attachment = await uploadAssistantAttachment(file)
    if (!selectedAttachments.value.some((item) => item.id === attachment.id)) selectedAttachments.value.push(attachment)
    if (selectedAction.value && !['qa', 'courseware', 'exercise', 'combined'].includes(selectedAction.value)) selectedAction.value = null
    if (settingsOpen.value) void loadAttachments()
  } catch (error: any) {
    errorMessage.value = error?.response?.data?.detail || '文件上传失败，请检查格式和大小。'
  } finally {
    uploadingAttachment.value = false
  }
}

function handleInput(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    void send()
  }
}

function resetConversation() {
  stopTaskPolling()
  sending.value = false
  messages.value = []
  pendingRequest = null
  selectedAttachments.value = []
  sessionId.value = null
  if (authStore.user) localStorage.removeItem(`learning-assistant-session-${authStore.user.userId}`)
  errorMessage.value = ''
  avatarMood.value = 'greeting'
}

async function cancelCurrentTask() {
  if (!currentTaskId.value || cancellingTask.value) return
  const id = currentTaskId.value
  cancellingTask.value = true
  try {
    const task = await getAssistantTask(id)
    if (task.status === 'RUNNING') await requestAssistantTaskCancel(id)
    else if (task.status === 'PENDING') {
      try { await cancelAssistantTask(id) }
      catch { await requestAssistantTaskCancel(id) }
    }
    await refreshTask(id)
  } catch { errorMessage.value = '取消任务失败，请稍后重试。' }
  finally { cancellingTask.value = false }
}

async function retryFailedTask(taskId: number) {
  if (sending.value) return
  let confirmSideEffects = false
  try {
    const original = await getAssistantTask(taskId)
    if (original.status !== 'FAILED' && original.status !== 'TIMED_OUT') {
      errorMessage.value = '任务状态已变化，请刷新会话后查看。'
      return
    }
    if (['courseware', 'exercise', 'plan', 'combined'].includes(original.task_type)) {
      await ElMessageBox.confirm(
        '原任务可能已保存部分课件、练习或学习路径。请先查看已有成果；继续重试可能产生重复内容。',
        '确认重新生成',
        { confirmButtonText: '仍要重试', cancelButtonText: '返回查看', type: 'warning' },
      )
      confirmSideEffects = true
    }
  } catch (error: any) {
    if (error === 'cancel' || error === 'close') return
    errorMessage.value = error?.response?.data?.detail || '无法核对任务状态，请稍后重试。'
    return
  }
  sending.value = true
  errorMessage.value = ''
  avatarMood.value = 'working'
  try {
    const requestId = retryRequestIds.get(taskId) || crypto.randomUUID()
    retryRequestIds.set(taskId, requestId)
    const response = await retryAssistantTask(taskId, requestId, confirmSideEffects)
    retryRequestIds.delete(taskId)
    if (!messages.value.some((message) => message.id === `task-${response.task.id}`)) {
      messages.value.push({ id: `task-${response.task.id}`, role: 'task', content: response.task.current_step, taskId: response.task.id, status: response.task.status })
    }
    startTaskPolling(response.task.id)
    scrollMessages()
  } catch (error: any) {
    sending.value = false
    errorMessage.value = error?.response?.data?.detail || '重试任务失败，请稍后再试。'
    avatarMood.value = 'warning'
  }
}

function saveMotionPreference() {
  localStorage.setItem(MOTION_STORAGE_KEY, motionEnabled.value ? 'on' : 'off')
}

async function copyMessage(content: string) {
  try { await navigator.clipboard.writeText(content) } catch { errorMessage.value = '复制失败，请手动选择文字。' }
}

async function openCard(card: AssistantCard, taskId?: number) {
  if (card.type === 'plan_draft' && taskId) {
    try {
      const task = await getAssistantTask(taskId)
      const stages = task.result.path_draft?.stages
      if (!Array.isArray(stages) || !stages.length) throw new Error('学习计划草案不可用。')
      await ElMessageBox.confirm(
        `确认保存这份包含 ${stages.length} 个阶段的学习路径？当前正在使用的学习路径将归档。`,
        '保存学习计划',
        { confirmButtonText: '确认保存', cancelButtonText: '继续查看草案', type: 'warning' },
      )
      const saved = await confirmAssistantPath(taskId)
      const message = messages.value.find((item) => item.taskId === taskId)
      if (message) {
        message.content = saved.result.content || message.content
        message.cards = saved.result.cards || []
      }
      avatarMood.value = 'success'
    } catch (error: any) {
      if (error === 'cancel' || error === 'close') return
      errorMessage.value = error?.response?.data?.detail || error?.message || '保存学习计划失败，请稍后重试。'
    }
    return
  }
  if (card.type === 'exercise' && taskId) {
    try {
      const task = await getAssistantTask(taskId)
      const set = task.result.exercise_set
      if (set && Array.isArray(set.exercises) && set.exercises.length) {
        sessionStorage.setItem(EXERCISE_STORAGE_KEY, JSON.stringify({ source: 'assistant', exerciseSet: set, generatedAt: Date.now() }))
        closePanel()
        void router.push('/student/exercise')
        return
      }
    } catch { /* The task may have expired. */ }
    errorMessage.value = '练习题暂时无法载入，请稍后重试。'
    return
  }
  if (card.route) {
    closePanel()
    if (card.resource_id && card.route === '/student/resources') {
      void router.push({ path: card.route, query: { resource: String(card.resource_id) } })
    } else {
      void router.push(card.route)
    }
  }
}

onMounted(() => {
  viewport.width = window.innerWidth
  viewport.height = window.innerHeight
  restorePetPosition()
  motionEnabled.value = localStorage.getItem(MOTION_STORAGE_KEY) !== 'off'
  if (authStore.user) {
    try {
      const savedPreferences = JSON.parse(localStorage.getItem(`learning-assistant-preferences-${authStore.user.userId}`) || '{}')
      useLearningContext.value = savedPreferences.useLearningContext === true
      teachingMode.value = typeof savedPreferences.teachingMode === 'string' ? savedPreferences.teachingMode : 'standard'
      courseKey.value = typeof savedPreferences.courseKey === 'string' ? savedPreferences.courseKey : ''
    } catch { /* Use privacy-preserving defaults. */ }
    const savedSession = Number(localStorage.getItem(`learning-assistant-session-${authStore.user.userId}`))
    if (Number.isInteger(savedSession) && savedSession > 0) void loadSession(savedSession)
  }
  positionReady.value = true
  window.addEventListener('resize', handleViewportResize)
  removeRouteHook = router.afterEach(() => window.setTimeout(avoidInteractiveControls, 250))
  window.setTimeout(avoidInteractiveControls, 250)
})

watch([useLearningContext, teachingMode, courseKey], () => {
  if (authStore.user) localStorage.setItem(`learning-assistant-preferences-${authStore.user.userId}`, JSON.stringify({
    useLearningContext: useLearningContext.value,
    teachingMode: teachingMode.value,
    courseKey: courseKey.value,
  }))
})

onBeforeUnmount(() => {
  stopTaskPolling()
  streamController?.abort()
  window.removeEventListener('resize', handleViewportResize)
  window.removeEventListener('pointermove', handleDrag)
  window.removeEventListener('pointerup', finishDrag)
  removeRouteHook?.()
})
</script>

<template>
  <div class="assistant-layer" :class="{'dashboard-docked-layer':dashboardDocked}">
    <Teleport to="body">
    <transition name="pet-panel">
      <section
        v-if="positionReady && isOpen"
        class="assistant-pet-panel"
        :class="{ dragging, 'is-workspace': mode === 'workspace' }"
        :style="panelStyle"
        aria-label="AI 学习助手"
      >
        <header class="pet-panel-header" title="拖动移动助手" @pointerdown="startDrag($event, 'panel')">
          <div class="pet-title-row">
            <XiaoZhiAvatar :state="assistantState" :motion="motionEnabled" size="small" />
            <div>
              <strong>小智</strong>
              <p>{{ sending ? '正在处理学习任务' : '你的 AI 智能学习伙伴' }}</p>
            </div>
          </div>
          <div class="pet-header-actions">
            <span class="drag-hint">拖动移动</span>
            <button type="button" title="历史会话" aria-label="历史会话" @click="historyOpen = !historyOpen"><el-icon><Tickets /></el-icon></button>
            <button type="button" title="开始新对话" aria-label="开始新对话" @click="resetConversation">
              <el-icon><Refresh /></el-icon>
            </button>
            <button type="button" title="助手设置" aria-label="助手设置" @click="toggleSettings"><el-icon><Setting /></el-icon></button>
            <button type="button" :title="mode === 'workspace' ? '返回聊天窗口' : '打开学习工作台'" :aria-label="mode === 'workspace' ? '返回聊天窗口' : '打开学习工作台'" @click="toggleWorkspace"><el-icon><Fold v-if="mode === 'workspace'" /><Expand v-else /></el-icon></button>
            <button type="button" title="关闭助手" aria-label="关闭助手" @click="closePanel">
              <el-icon><Close /></el-icon>
            </button>
          </div>
        </header>

        <div v-if="settingsOpen" class="pet-settings">
          <label><input v-model="motionEnabled" type="checkbox" @change="saveMotionPreference" /> 动态效果</label>
          <label><input v-model="useLearningContext" type="checkbox" /> 使用学习上下文</label>
          <label><input v-model="allowWebKnowledge" type="checkbox" /> 允许补充公开课程资料</label>
          <small>默认不向模型提供历史学情；明确要求基于自己的学情或错题生成时，会按本次请求读取。</small>
          <label>讲解方式 <select v-model="teachingMode"><option value="basic">基础讲解</option><option value="standard">标准学习</option><option value="deep">深入推导</option><option value="socratic">引导提问</option><option value="exam">考试训练</option></select></label>
          <label>当前课程 <input v-model="courseKey" type="text" maxlength="100" placeholder="可选，用于隔离记忆" /></label>
          <details class="pet-memory-manager"><summary>学习记忆（{{ memories.length }}）</summary><p>仅保存你主动确认的目标与偏好；关闭“使用学习上下文”后不会发送给模型。</p><div v-for="memory in memories" :key="memory.id" class="pet-memory-item"><strong>{{ memory.course_key || '通用' }} · {{ memory.memory_type }}</strong><span>{{ memory.content }}</span><button type="button" @click="editMemory(memory)">修正</button><button type="button" @click="removeMemory(memory.id)">删除</button></div><div class="pet-memory-form"><select v-model="memoryType"><option value="goal">学习目标</option><option value="preference">讲解偏好</option><option value="focus">重点知识点</option><option value="context">其他学习背景</option></select><input v-model="memoryCourse" maxlength="100" placeholder="课程（可选）" /><input v-model="memoryDraft" maxlength="500" placeholder="输入并确认要保存的内容" /><button type="button" @click="saveMemory">{{ editingMemoryId ? '保存修正' : '保存记忆' }}</button></div><p v-if="memoryError" class="pet-memory-error">{{ memoryError }}</p></details>
          <details class="pet-memory-manager"><summary>已提取的资料（{{ storedAttachments.length }}）</summary><p>仅保存提取文本；删除后无法重新用于提问，历史消息仍显示文件名。</p><div v-for="file in storedAttachments" :key="file.id" class="pet-memory-item"><strong>{{ file.file_name }}</strong><span>{{ Math.ceil(file.size_bytes / 1024) }} KB</span><button type="button" @click="removeStoredAttachment(file.id)">删除</button></div><p v-if="attachmentError" class="pet-memory-error">{{ attachmentError }}</p></details>
        </div>

        <div class="pet-panel-body">
          <aside v-if="historyOpen || mode === 'workspace'" class="pet-history" aria-label="历史会话">
            <strong>历史会话</strong>
            <button type="button" class="pet-history-new" @click="resetConversation">＋ 新对话</button>
            <button v-for="session in sessions" :key="session.id" type="button" :class="{ active: session.id === sessionId }" @click="loadSession(session.id)">
              <span>{{ session.title || '未命名会话' }}</span><small>{{ session.message_count }} 条消息</small>
            </button>
            <p v-if="!sessions.length">暂无历史会话</p>
          </aside>

          <div class="pet-chat-column">

        <div ref="messagesRef" class="pet-messages" aria-live="polite">
          <div v-if="!messages.length" class="pet-empty">
            <XiaoZhiAvatar :state="assistantState" :motion="motionEnabled" />
            <strong>你好，我是小智</strong>
            <p>{{ authStore.user?.role === 'teacher' ? '可以向我提问、查找教材资料，并管理自己的会话与学习偏好。' : '你的 AI 智能学习伙伴。可以提问，也可以让我查资料、分析学情、生成资源和学习计划。' }}</p>
            <div class="pet-suggestions">
              <button v-for="item in availableSuggestions" :key="item.label" type="button" @click="useSuggestion(item)">{{ item.label }}</button>
            </div>
          </div>

          <article v-for="message in messages" :key="message.id" class="pet-message" :class="message.role">
            <div class="pet-message-label"><XiaoZhiAvatar v-if="message.role !== 'user'" :state="message.status === 'FAILED' || message.status === 'TIMED_OUT' ? 'warning' : 'idle'" :motion="motionEnabled" size="small" />{{ message.role === 'user' ? '你' : '小智' }}</div>
            <div class="pet-message-content" v-html="renderLearningMarkdown(message.content)"></div>
            <div v-if="message.attachments?.length" class="pet-message-attachments"><span v-for="file in message.attachments" :key="file.id">📄 {{ file.file_name }}</span></div>
            <div v-if="message.role !== 'user'" class="pet-message-actions"><button type="button" title="复制消息" @click="copyMessage(message.content)"><el-icon><CopyDocument /></el-icon> 复制</button><button v-if="message.role === 'task' && ['FAILED', 'TIMED_OUT'].includes(message.status || '') && message.taskId" type="button" :disabled="sending" @click="retryFailedTask(message.taskId)">重试任务</button></div>
            <div v-if="message.role === 'task' && ['RUNNING', 'CANCEL_REQUESTED'].includes(message.status || '')" class="pet-task-status">{{ message.status === 'CANCEL_REQUESTED' ? '正在取消' : '正在执行' }} · {{ message.content }}</div>
            <div v-if="message.cards?.length" class="pet-result-cards"><button v-for="card in message.cards" :key="`${card.type}-${card.title}`" type="button" :disabled="!card.route && !(['exercise', 'plan_draft'].includes(card.type) && message.taskId)" @click="openCard(card, message.taskId)"><strong>{{ card.title }}<small v-if="card.reason">{{ card.reason }}</small></strong><span>{{ card.type === 'courseware' || card.type === 'recommendation' ? '查看资源' : card.type === 'exercise' ? '开始练习' : card.type === 'plan_draft' ? '确认保存' : '查看详情' }} →</span></button></div>
            <details v-if="message.sources?.length" class="pet-sources"><summary>查看来源（{{ message.sources.length }}）</summary><div v-for="(source, index) in message.sources" :key="index" class="pet-source-item"><a v-if="sourceLink(source)" :href="sourceLink(source)" target="_blank" rel="noopener noreferrer">{{ sourceLabel(source) }}</a><strong v-else>{{ sourceLabel(source) }}</strong><p v-if="sourceSummary(source)">{{ sourceSummary(source) }}</p></div></details>
          </article>
          <div v-if="sending && !currentTaskId" class="pet-thinking"><span></span><span></span><span></span> 小智正在思考…</div>
        </div>

        <div v-if="errorMessage" class="pet-error">{{ errorMessage }}</div>
        <div v-if="selectedAction" class="pet-selected-action">当前任务：{{ suggestions.find((item) => item.action === selectedAction)?.label || selectedAction }} <button type="button" @click="selectedAction = null">取消选择</button></div>
        <div class="pet-attachment-bar"><input ref="attachmentInputRef" type="file" accept=".txt,.md,.pdf,.docx" hidden @change="uploadSelectedFile"><button type="button" :disabled="sending || uploadingAttachment || selectedAttachments.length >= 3" @click="attachmentInputRef?.click()">{{ uploadingAttachment ? '正在读取文件…' : '＋ 添加资料' }}</button><span v-if="!selectedAttachments.length">TXT、Markdown、PDF、DOCX · 问答、课件和练习</span><span v-for="file in selectedAttachments" :key="file.id" class="pet-attachment-chip">{{ file.file_name }} <button type="button" :aria-label="`移除 ${file.file_name}`" @click="selectedAttachments = selectedAttachments.filter((item) => item.id !== file.id)">×</button></span></div>
        <form class="pet-composer" @submit.prevent="send">
          <textarea
            ref="inputRef"
            v-model="draft"
            placeholder="输入你的学习问题…"
            rows="2"
            :disabled="sending"
            @keydown="handleInput"
          ></textarea>
          <button class="pet-send" type="submit" :disabled="sending || uploadingAttachment || !draft.trim()" aria-label="发送">
            <el-icon><Promotion /></el-icon>
          </button>
        </form>
        <div class="pet-hint"><button v-if="sending && !currentTaskId" type="button" @click="stopStream">停止生成</button><button v-if="currentTaskId && ['PENDING', 'RUNNING'].includes(messages.find((item) => item.taskId === currentTaskId)?.status || '')" type="button" :disabled="cancellingTask" @click="cancelCurrentTask">{{ cancellingTask ? '正在取消…' : '取消任务' }}</button><span v-if="currentTaskId && messages.find((item) => item.taskId === currentTaskId)?.status === 'CANCEL_REQUESTED'">正在取消，等待当前步骤结束</span> Enter 发送 · Shift + Enter 换行</div>
          </div>
          <aside v-if="mode === 'workspace'" class="pet-context" aria-label="学习工具"><strong>学习工具</strong><button v-for="item in availableSuggestions.slice(1)" :key="item.action" type="button" @click="useSuggestion(item)">{{ item.label }}</button><p>{{ authStore.user?.role === 'teacher' ? '知识查询结果保留在当前会话中。' : '任务成果会保存在现有学习模块中。' }}</p></aside>
        </div>
      </section>
    </transition>
    </Teleport>

    <Teleport to="body" :disabled="dashboardDocked">
    <button
      v-if="positionReady && !isOpen"
      class="assistant-pet-button"
      :class="{ dragging, 'dashboard-docked': dashboardDocked }"
      :style="dashboardDocked ? {} : petStyle"
      type="button"
      aria-label="打开可拖动的 AI 学习助手"
      title="点击打开，按住可拖动"
      @pointerdown="!dashboardDocked && startDrag($event, 'pet')"
      @click="handlePetClick"
    >
      <XiaoZhiAvatar class="pet-character" :state="assistantState" :motion="motionEnabled" />
      <span v-if="unreadCount" class="pet-unread" :aria-label="`${unreadCount} 条任务提醒`">{{ unreadCount }}</span>
      <span class="pet-name">小智</span>
      <span class="pet-drag-copy">拖动我</span>
    </button>
    </Teleport>
  </div>
</template>

<style scoped>
.assistant-layer { position:fixed; inset:0; z-index:80; pointer-events:none; font-family:inherit; }
.assistant-layer.dashboard-docked-layer{position:static;inset:auto;z-index:auto;pointer-events:auto}
.assistant-pet-button,.assistant-pet-panel { position:fixed; pointer-events:auto; }
.assistant-pet-button:not(.dashboard-docked),.assistant-pet-panel{z-index:80}
.assistant-pet-button { width:92px; height:104px; padding:0; border:0; color:var(--text); background:transparent; cursor:grab; touch-action:none; user-select:none; filter:drop-shadow(0 12px 14px rgba(30,41,99,.2)); }
.assistant-pet-button.dragging { cursor:grabbing; }
.assistant-pet-button.dashboard-docked{position:relative;display:flex;align-items:center;width:112px;height:34px;border:1px solid var(--line);border-radius:10px;background:var(--panel);filter:none;cursor:pointer;color:var(--accent-deep)}
.dashboard-docked .pet-character{position:static;width:30px;height:32px;margin-left:7px}.dashboard-docked .pet-name{position:static;transform:none;border:0;background:none;margin-left:5px;font-size:11px}.dashboard-docked .pet-drag-copy{display:none}
@media(max-width:750px){.assistant-pet-button.dashboard-docked{width:36px}.dashboard-docked .pet-name{display:none}.dashboard-docked .pet-character{margin-left:2px}}
.pet-character { position:absolute; top:-2px; left:3px; width:86px; height:94px; }
.pet-unread { position:absolute; top:0; right:1px; display:grid; place-items:center; min-width:19px; height:19px; padding:0 4px; border:2px solid var(--panel); border-radius:99px; color:#fff; background:var(--red); font-size:10px; font-weight:800; }
.assistant-pet-button.dragging .pet-character { animation:none; }
.pet-shadow { position:absolute; left:12px; bottom:0; width:44px; height:9px; border-radius:50%; background:rgba(30,41,99,.18); filter:blur(2px); animation:pet-shadow 2.8s ease-in-out infinite; }
.pet-head { position:absolute; top:13px; left:8px; width:52px; height:43px; border:3px solid rgba(255,255,255,.72); border-radius:19px 19px 17px 17px; background:linear-gradient(145deg,#e5fbff 5%,#7dd3fc 60%,#818cf8); box-shadow:inset 0 -7px 12px rgba(67,56,202,.2); z-index:3; }
.pet-ear { position:absolute; top:19px; width:13px; height:24px; border-radius:8px; background:linear-gradient(180deg,#818cf8,#4f46e5); z-index:1; }
.pet-ear.left { left:1px; transform:rotate(-12deg); }.pet-ear.right { right:1px; transform:rotate(12deg); }
.pet-antenna { position:absolute; top:1px; left:32px; width:4px; height:15px; border-radius:4px; background:#6366f1; transform-origin:bottom; animation:pet-antenna 1.8s ease-in-out infinite; z-index:2; }
.pet-antenna i { position:absolute; top:-3px; left:-3px; width:10px; height:10px; border-radius:50%; background:#34d399; box-shadow:0 0 0 4px rgba(52,211,153,.18),0 0 12px rgba(52,211,153,.65); }
.pet-eye { position:absolute; top:15px; width:6px; height:9px; border-radius:5px; background:#172554; transform-origin:center; animation:pet-blink 4.6s infinite; }
.pet-eye.left { left:13px; }.pet-eye.right { right:13px; }
.pet-cheek { position:absolute; top:26px; width:7px; height:4px; border-radius:50%; background:rgba(244,114,182,.5); }.pet-cheek.left { left:6px; }.pet-cheek.right { right:6px; }
.pet-mouth { position:absolute; bottom:7px; left:50%; width:11px; height:5px; border-bottom:2px solid #172554; border-radius:0 0 10px 10px; transform:translateX(-50%); }
.pet-body { position:absolute; top:50px; left:18px; width:32px; height:25px; border:2px solid rgba(255,255,255,.7); border-radius:10px 10px 14px 14px; background:linear-gradient(145deg,#6366f1,#4338ca); z-index:2; }
.pet-core { position:absolute; inset:4px 8px; display:grid; place-items:center; border-radius:8px; color:#dffbff; background:rgba(255,255,255,.16); font-size:10px; }
.pet-arm { position:absolute; top:53px; width:9px; height:23px; border-radius:8px; background:#6366f1; transform-origin:top; z-index:1; }.pet-arm.left { left:12px; transform:rotate(18deg); }.pet-arm.right { right:12px; animation:pet-wave 1.9s ease-in-out infinite; }
.pet-name { position:absolute; left:50%; bottom:9px; padding:2px 8px; border:1px solid color-mix(in srgb,var(--accent) 22%,var(--line)); border-radius:9px; color:var(--accent-deep); background:color-mix(in srgb,var(--panel-strong) 92%,transparent); font-size:11px; font-weight:800; transform:translateX(-50%); white-space:nowrap; }
.pet-drag-copy { position:absolute; left:50%; bottom:-5px; color:var(--muted); font-size:9px; opacity:0; transform:translateX(-50%); transition:opacity .18s ease; white-space:nowrap; }.assistant-pet-button:hover .pet-drag-copy { opacity:1; }
.assistant-pet-panel { display:flex; flex-direction:column; overflow:hidden; border:1px solid var(--line); border-radius:22px; background:color-mix(in srgb,var(--panel-strong) 96%,transparent); box-shadow:0 20px 58px rgba(15,23,42,.2); backdrop-filter:blur(18px); }
.assistant-pet-panel.dragging { box-shadow:0 24px 70px rgba(15,23,42,.3); }
.pet-panel-header { display:flex; justify-content:space-between; align-items:center; padding:16px 17px 13px; border-bottom:1px solid var(--line); cursor:grab; touch-action:none; user-select:none; }.assistant-pet-panel.dragging .pet-panel-header { cursor:grabbing; }
.pet-title-row { display:flex; align-items:center; gap:10px; }.pet-mini-avatar { position:relative; width:36px; height:34px; border-radius:13px; background:linear-gradient(145deg,#dffbff,#7dd3fc 55%,#818cf8); box-shadow:inset 0 -4px 8px rgba(67,56,202,.18); animation:mini-float 2.8s ease-in-out infinite; }
.mini-antenna { position:absolute; top:-7px; left:17px; width:3px; height:9px; border-radius:3px; background:#6366f1; }.mini-antenna::before { content:''; position:absolute; top:-3px; left:-2px; width:7px; height:7px; border-radius:50%; background:#34d399; }
.mini-eye { position:absolute; top:13px; width:4px; height:7px; border-radius:4px; background:#172554; animation:pet-blink 4.6s infinite; }.mini-eye.left { left:10px; }.mini-eye.right { right:10px; }
.pet-title-row strong { color:var(--text); font-size:14px; }.pet-title-row p { margin:3px 0 0; color:var(--muted); font-size:11px; }
.pet-header-actions { display:flex; align-items:center; gap:3px; }.drag-hint { margin-right:3px; color:var(--muted); font-size:9px; }.pet-header-actions button { display:grid; place-items:center; width:30px; height:30px; border:0; border-radius:9px; color:var(--muted); background:transparent; cursor:pointer; }.pet-header-actions button:hover { color:var(--accent); background:var(--accent-soft); }
.pet-messages { flex:1; overflow:auto; padding:12px 14px 8px; }.pet-empty { padding:28px 10px 12px; color:var(--muted); text-align:center; }.pet-empty-orb { display:grid; place-items:center; width:48px; height:48px; margin:0 auto 10px; border-radius:17px; color:#fff; background:linear-gradient(145deg,var(--accent),#38bdf8); font-size:21px; font-weight:850; box-shadow:0 8px 20px color-mix(in srgb,var(--accent) 22%,transparent); animation:mini-float 2.8s ease-in-out infinite; }.pet-empty strong { color:var(--text); font-size:14px; }.pet-empty p { max-width:280px; margin:7px auto 17px; font-size:12px; line-height:1.6; }
.pet-suggestions { display:grid; gap:7px; }.pet-suggestions button { padding:9px 11px; border:1px solid var(--line); border-radius:10px; color:var(--text); background:var(--panel); text-align:left; font-size:11px; cursor:pointer; }.pet-suggestions button:hover { border-color:color-mix(in srgb,var(--accent) 35%,var(--line)); background:var(--accent-soft); }
.pet-message { max-width:88%; margin:0 0 13px; }.pet-message.user { margin-left:auto; }.pet-message-label { margin:0 0 4px; color:var(--muted); font-size:10px; }.pet-message.user .pet-message-label { text-align:right; }.pet-message-content { padding:10px 12px; border:1px solid var(--line); border-radius:13px 13px 13px 4px; color:var(--text); background:var(--panel); font-size:12px; line-height:1.65; white-space:pre-wrap; overflow-wrap:anywhere; }.pet-message.user .pet-message-content { border-color:color-mix(in srgb,var(--accent) 20%,var(--line)); border-radius:13px 13px 4px 13px; color:var(--accent-deep); background:var(--accent-soft); }
.pet-message-label { display:flex; align-items:center; gap:4px; }.pet-message.user .pet-message-label { justify-content:flex-end; }.pet-message-label :deep(.xiaozhi-avatar) { width:22px; height:24px; }
.pet-thinking { display:flex; align-items:center; gap:4px; color:var(--muted); font-size:11px; }.pet-thinking span { width:5px; height:5px; border-radius:50%; background:var(--accent); animation:pet-thinking 1s infinite ease-in-out; }.pet-thinking span:nth-child(2) { animation-delay:.15s; }.pet-thinking span:nth-child(3) { animation-delay:.3s; }
.pet-error { margin:0 14px 8px; padding:8px 10px; border:1px solid color-mix(in srgb,var(--red) 25%,var(--line)); border-radius:9px; color:var(--red); background:color-mix(in srgb,var(--red) 7%,transparent); font-size:11px; line-height:1.5; }.pet-composer { display:flex; align-items:flex-end; gap:8px; margin:0 13px; padding:9px 9px 9px 11px; border:1px solid var(--line); border-radius:13px; background:var(--panel); }.pet-composer textarea { flex:1; min-width:0; resize:none; border:0; outline:0; color:var(--text); background:transparent; font:inherit; font-size:12px; line-height:1.5; }.pet-composer textarea::placeholder { color:var(--muted); }.pet-send { display:grid; place-items:center; width:31px; height:31px; border:0; border-radius:9px; color:#fff; background:var(--accent); cursor:pointer; }.pet-send:disabled { opacity:.4; cursor:not-allowed; }.pet-hint { padding:7px 15px 12px; color:var(--muted); font-size:10px; text-align:right; }
.pet-panel-enter-active,.pet-panel-leave-active { transition:opacity .18s ease,transform .18s ease; }.pet-panel-enter-from,.pet-panel-leave-to { opacity:0; transform:translateY(10px) scale(.98); }
.pet-panel-body { display:flex; flex:1; min-height:0; }
.pet-chat-column { display:flex; flex:1; flex-direction:column; min-width:0; min-height:0; }
.pet-history,.pet-context { display:flex; flex-direction:column; gap:7px; width:205px; flex:none; overflow:auto; padding:16px 11px; border-right:1px solid var(--line); background:var(--panel); }
.assistant-pet-panel:not(.is-workspace) .pet-history { position:absolute; z-index:3; top:64px; bottom:0; left:0; width:min(245px,85%); box-shadow:12px 0 24px rgba(15,23,42,.12); }
.pet-context { width:190px; border-right:0; border-left:1px solid var(--line); }
.pet-history strong,.pet-context strong { margin:0 4px 7px; color:var(--text); font-size:13px; }
.pet-history button,.pet-context button { display:flex; align-items:center; justify-content:space-between; gap:8px; width:100%; padding:9px 10px; border:1px solid transparent; border-radius:10px; color:var(--text); background:transparent; text-align:left; font:inherit; font-size:11px; cursor:pointer; }
.pet-history button:hover,.pet-context button:hover,.pet-history button.active { border-color:var(--line); background:var(--accent-soft); }
.pet-history button span { min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }.pet-history button small { flex:none; color:var(--muted); font-size:9px; }
.pet-history .pet-history-new { border-color:var(--line); color:var(--accent-deep); font-weight:700; }
.pet-history p,.pet-context p { color:var(--muted); font-size:11px; line-height:1.5; }
.pet-settings { display:flex; gap:15px; align-items:center; flex-wrap:wrap; padding:9px 15px; border-bottom:1px solid var(--line); color:var(--text); background:var(--panel); font-size:11px; }
.pet-settings label { display:flex; gap:5px; align-items:center; }.pet-settings select { max-width:100px; border:1px solid var(--line); border-radius:6px; color:var(--text); background:var(--panel); font:inherit; }
.pet-settings input[type=text],.pet-memory-form input { min-width:0; padding:5px 7px; border:1px solid var(--line); border-radius:7px; color:var(--text); background:var(--panel); font:inherit; }.pet-settings label input[type=text] { width:130px; }
.pet-memory-manager { width:100%; max-height:180px; overflow:auto; }.pet-memory-manager summary { cursor:pointer; font-weight:700; }.pet-memory-manager p { margin:6px 0; color:var(--muted); line-height:1.45; }.pet-memory-item { display:flex; align-items:center; gap:5px; flex-wrap:wrap; padding:6px 0; border-bottom:1px solid var(--line); }.pet-memory-item span { flex:1; min-width:120px; overflow-wrap:anywhere; }.pet-memory-item button,.pet-memory-form button { border:0; color:var(--accent-deep); background:transparent; cursor:pointer; }.pet-memory-form { display:flex; gap:5px; flex-wrap:wrap; padding-top:7px; }.pet-memory-form input { flex:1; min-width:100px; }.pet-memory-error { color:var(--red) !important; }
.pet-empty :deep(.xiaozhi-avatar) { display:block; margin:0 auto 5px; }.pet-empty strong { display:block; margin-top:7px; }
.pet-suggestions { grid-template-columns:repeat(2,minmax(0,1fr)); }.pet-suggestions button { min-height:39px; }
.pet-message.task .pet-message-content { border-color:color-mix(in srgb,var(--accent) 35%,var(--line)); background:var(--accent-soft); }
.pet-message-content :deep(p) { margin:0 0 .5em; }.pet-message-content :deep(p:last-child) { margin-bottom:0; }.pet-message-content :deep(pre) { max-width:100%; overflow:auto; padding:10px; border-radius:8px; background:color-mix(in srgb,var(--text) 7%,var(--panel)); }.pet-message-content :deep(code) { overflow-wrap:anywhere; }.pet-message-content :deep(table) { display:block; max-width:100%; overflow:auto; border-collapse:collapse; }.pet-message-content :deep(th),.pet-message-content :deep(td) { padding:5px 8px; border:1px solid var(--line); }.pet-message-content :deep(.katex-display) { overflow-x:auto; overflow-y:hidden; }
.pet-message-actions { margin:3px 0; }.pet-message-actions button,.pet-hint button,.pet-selected-action button { border:0; color:var(--accent-deep); background:transparent; font:inherit; font-size:10px; cursor:pointer; }
.pet-task-status { color:var(--muted); font-size:10px; }.pet-result-cards { display:grid; gap:6px; margin-top:8px; }.pet-result-cards button { display:flex; justify-content:space-between; gap:8px; padding:9px 11px; border:1px solid var(--line); border-radius:9px; color:var(--text); background:var(--panel); cursor:pointer; }.pet-result-cards button:disabled { cursor:default; }.pet-result-cards span { color:var(--accent-deep); font-size:10px; }
.pet-result-cards strong small { display:block; margin-top:3px; color:var(--muted); font-weight:400; }
.pet-sources { margin-top:7px; color:var(--muted); font-size:10px; }.pet-sources pre { max-height:160px; overflow:auto; white-space:pre-wrap; overflow-wrap:anywhere; }
.pet-source-item { margin-top:6px; padding:7px 9px; border:1px solid var(--line); border-radius:8px; background:var(--panel); }.pet-source-item a { color:var(--accent-deep); }.pet-source-item strong { color:var(--text); }.pet-source-item p { margin:3px 0 0; line-height:1.5; }
.pet-selected-action { display:flex; justify-content:space-between; margin:0 14px 6px; color:var(--accent-deep); font-size:11px; }
.pet-attachment-bar { display:flex; align-items:center; gap:6px; flex-wrap:wrap; margin:0 14px 7px; color:var(--muted); font-size:10px; }
.pet-attachment-bar > button { border:1px solid var(--line); border-radius:8px; padding:4px 7px; color:var(--accent-deep); background:var(--panel); cursor:pointer; }
.pet-attachment-bar > button:disabled { opacity:.5; cursor:not-allowed; }
.pet-attachment-chip,.pet-message-attachments span { display:inline-flex; align-items:center; max-width:100%; gap:3px; border:1px solid var(--line); border-radius:7px; padding:3px 6px; color:var(--text); background:var(--panel); overflow-wrap:anywhere; }
.pet-attachment-chip button { border:0; color:var(--muted); background:transparent; cursor:pointer; }
.pet-message-attachments { display:flex; flex-wrap:wrap; gap:5px; margin:5px 0; font-size:10px; }
.assistant-pet-panel.is-workspace .pet-message { max-width:82%; }
@media (max-width:740px) { .assistant-pet-panel.is-workspace .pet-history,.assistant-pet-panel.is-workspace .pet-context { display:none; }.pet-suggestions { grid-template-columns:1fr; } }
@keyframes pet-float { 0%,100% { transform:translate(-50%,0) rotate(-1deg); } 50% { transform:translate(-50%,-7px) rotate(1deg); } }
@keyframes mini-float { 0%,100% { transform:translateY(0); } 50% { transform:translateY(-3px); } }
@keyframes pet-shadow { 0%,100% { transform:scaleX(1); opacity:.6; } 50% { transform:scaleX(.78); opacity:.35; } }
@keyframes pet-blink { 0%,44%,48%,100% { transform:scaleY(1); } 46% { transform:scaleY(.12); } }
@keyframes pet-wave { 0%,100% { transform:rotate(-15deg); } 45% { transform:rotate(-65deg); } 65% { transform:rotate(-35deg); } }
@keyframes pet-antenna { 0%,100% { transform:rotate(-6deg); } 50% { transform:rotate(7deg); } }
@keyframes pet-thinking { 0%,80%,100% { transform:translateY(0); opacity:.45; } 40% { transform:translateY(-3px); opacity:1; } }
@media (max-width:560px) { .drag-hint { display:none; }.pet-panel-header { padding-inline:14px; }.pet-empty { padding-top:18px; } }
@media (prefers-reduced-motion:reduce) { .pet-character,.pet-shadow,.pet-antenna,.pet-eye,.pet-arm.right,.pet-mini-avatar,.pet-empty-orb,.pet-thinking span,.pet-panel-enter-active,.pet-panel-leave-active { animation:none; transition:none; } }
</style>
