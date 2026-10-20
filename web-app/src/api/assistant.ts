import { agentApi, serviceEndpoints } from './http'

export type AssistantAction = 'qa' | 'profile' | 'search' | 'courseware' | 'exercise' | 'plan' | 'recommend' | 'combined'
export type AssistantTaskStatus = 'PENDING' | 'RUNNING' | 'CANCEL_REQUESTED' | 'SUCCEEDED' | 'FAILED' | 'TIMED_OUT' | 'CANCELLED'

export interface AssistantCard {
  type: string
  title: string
  route?: string
  resource_id?: number
  reason?: string
}

export interface AssistantTask {
  id: number
  conversation_id: number
  task_type: AssistantAction
  status: AssistantTaskStatus
  current_step: string
  result: { content?: string; cards?: AssistantCard[]; sources?: Array<Record<string, unknown>>; evidence?: Record<string, unknown>; exercise_set?: Record<string, unknown> | null; path_draft?: { stages?: unknown[] } | null; path_saved?: boolean }
  error_code: string
  created_at: string
  completed_at: string | null
  agent_executions?: Array<{ agent_code: string; status: string; elapsed_ms: number; error_code: string }>
}

export interface AssistantChatRequest {
  conversation_id?: number | null
  client_request_id: string
  message: string
  action?: AssistantAction
  knowledge_point?: string
  exercise_count?: number
  teaching_mode?: string
  use_learning_context?: boolean
  course_key?: string
  attachment_ids?: number[]
}

export interface AssistantAttachment {
  id: number
  file_name: string
  content_type: string
  size_bytes: number
  created_at: string
}

export async function uploadAssistantAttachment(file: File): Promise<AssistantAttachment> {
  const form = new FormData()
  form.append('file', file)
  return (await agentApi.post<AssistantAttachment>('/assistant/attachments', form)).data
}

export async function listAssistantAttachments(): Promise<AssistantAttachment[]> {
  return (await agentApi.get<AssistantAttachment[]>('/assistant/attachments')).data
}

export async function deleteAssistantAttachment(id: number): Promise<void> {
  await agentApi.delete(`/assistant/attachments/${id}`)
}

export interface AssistantMemory {
  id: number
  memory_type: 'goal' | 'preference' | 'focus' | 'context'
  content: string
  course_key: string
  source_reference: string
  created_at: string
  updated_at: string
}

export type AssistantMemoryPayload = Pick<AssistantMemory, 'memory_type' | 'content' | 'course_key'>

export type AssistantChatResponse =
  | { kind: 'message'; conversation_id: number; message: { message_id: number; content: string; metadata: Record<string, unknown> } }
  | { kind: 'task'; conversation_id: number; task: AssistantTask }

export type AssistantStreamEvent =
  | { event: 'start'; data: { conversation_id: number } }
  | { event: 'stage'; data: { stage: string; message: string } }
  | { event: 'delta'; data: { text: string } }
  | { event: 'final'; data: { conversation_id: number; message_id: number; content: string; metadata: Record<string, unknown> } }
  | { event: 'error'; data: { code: string; message: string } }

export async function streamAssistantMessage(
  payload: AssistantChatRequest,
  onEvent: (event: AssistantStreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const rawAuth = localStorage.getItem('learning-system-auth')
  const token = rawAuth ? (JSON.parse(rawAuth) as { token?: string }).token : ''
  const response = await fetch(`${serviceEndpoints.agent}/assistant/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: JSON.stringify(payload),
    signal,
  })
  if (!response.ok || !response.body) {
    let detail = '流式问答暂时不可用。'
    try { const body = await response.json(); detail = body?.detail?.message || body?.detail || detail } catch { /* Keep fallback text. */ }
    throw new Error(detail)
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let finished = false
  try {
    while (true) {
      const { value, done } = await reader.read()
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done }).replace(/\r\n/g, '\n')
      let separator = buffer.indexOf('\n\n')
      while (separator >= 0) {
        const frame = buffer.slice(0, separator)
        buffer = buffer.slice(separator + 2)
        const event = frame.split('\n').find((line) => line.startsWith('event: '))?.slice(7)
        const data = frame.split('\n').find((line) => line.startsWith('data: '))?.slice(6)
        if (event && data) {
          const parsed = { event, data: JSON.parse(data) } as AssistantStreamEvent
          onEvent(parsed)
          if (event === 'error') throw new Error((parsed as Extract<AssistantStreamEvent, { event: 'error' }>).data.message)
          if (event === 'final') finished = true
        }
        separator = buffer.indexOf('\n\n')
      }
      if (done) break
    }
  } finally { reader.releaseLock() }
  if (!finished) throw new Error('连接中断，回答是否保存尚未确认。请刷新历史或重试。')
}

export async function sendAssistantMessage(payload: AssistantChatRequest): Promise<AssistantChatResponse> {
  return (await agentApi.post<AssistantChatResponse>('/assistant/chat', payload)).data
}

export async function getAssistantTask(taskId: number): Promise<AssistantTask> {
  return (await agentApi.get<AssistantTask>(`/assistant/tasks/${taskId}`)).data
}

export async function listAssistantTasks(conversationId: number): Promise<AssistantTask[]> {
  return (await agentApi.get<AssistantTask[]>('/assistant/tasks', { params: { conversation_id: conversationId } })).data
}

export async function cancelAssistantTask(taskId: number): Promise<AssistantTask> {
  return (await agentApi.post<AssistantTask>(`/assistant/tasks/${taskId}/cancel`)).data
}

export async function requestAssistantTaskCancel(taskId: number): Promise<AssistantTask> {
  return (await agentApi.post<AssistantTask>(`/assistant/tasks/${taskId}/request-cancel`)).data
}

export async function retryAssistantTask(taskId: number, clientRequestId: string, confirmSideEffects = false): Promise<{ kind: 'task'; conversation_id: number; original_task_id: number; task: AssistantTask }> {
  return (await agentApi.post<{ kind: 'task'; conversation_id: number; original_task_id: number; task: AssistantTask }>(`/assistant/tasks/${taskId}/retry`, { client_request_id: clientRequestId, confirm_side_effects: confirmSideEffects })).data
}

export async function confirmAssistantPath(taskId: number): Promise<AssistantTask> {
  return (await agentApi.post<AssistantTask>(`/assistant/tasks/${taskId}/confirm-path`)).data
}

export async function listAssistantMemory(): Promise<AssistantMemory[]> {
  return (await agentApi.get<AssistantMemory[]>('/assistant/memory')).data
}

export async function saveAssistantMemory(payload: AssistantMemoryPayload, id?: number): Promise<AssistantMemory> {
  return id
    ? (await agentApi.put<AssistantMemory>(`/assistant/memory/${id}`, payload)).data
    : (await agentApi.post<AssistantMemory>('/assistant/memory', payload)).data
}

export async function deleteAssistantMemory(id: number): Promise<void> {
  await agentApi.delete(`/assistant/memory/${id}`)
}
