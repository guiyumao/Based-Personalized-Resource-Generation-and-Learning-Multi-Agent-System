import { agentApi } from './http'

export interface ChatSessionCreate {
  user_id: number
  title?: string
  subject?: string
}

export interface ChatMessageInput {
  session_id: number
  user_id: number
  content: string
  context?: Record<string, unknown>
}

export interface ChatMessageItem {
  id: number
  role: 'user' | 'assistant' | 'system'
  content: string
  model_used: string
  metadata: Record<string, unknown>
  created_at: string
}

export interface ChatSessionDetail {
  id: number
  user_id: number
  title: string
  subject: string
  is_active: boolean
  created_at: string
  last_message_at: string
  message_count: number
  messages: ChatMessageItem[]
}

export interface ChatSessionSummary {
  id: number
  user_id: number
  title: string
  subject: string
  is_active: boolean
  created_at: string
  last_message_at: string
  message_count: number
}

export interface ChatResponse {
  session_id: number
  message_id: number
  role: string
  content: string
  model_used: string
  metadata: Record<string, unknown>
  created_at: string
}

export async function createChatSession(data: ChatSessionCreate): Promise<ChatSessionDetail> {
  const response = await agentApi.post<ChatSessionDetail>('/chat/sessions/new', data)
  return response.data
}

export async function listChatSessions(userId: number, limit: number = 50): Promise<ChatSessionSummary[]> {
  const response = await agentApi.get<ChatSessionSummary[]>('/chat/sessions', {
    params: { user_id: userId, limit },
  })
  return response.data
}

export async function getChatSession(sessionId: number, userId: number): Promise<ChatSessionDetail> {
  const response = await agentApi.get<ChatSessionDetail>(`/chat/sessions/${sessionId}`, {
    params: { user_id: userId },
  })
  return response.data
}

export async function sendChatMessage(data: ChatMessageInput): Promise<ChatResponse> {
  const response = await agentApi.post<ChatResponse>('/chat/chat', data)
  return response.data
}

export async function deleteChatSession(sessionId: number, userId: number): Promise<void> {
  await agentApi.delete(`/chat/sessions/${sessionId}`, {
    params: { user_id: userId },
  })
}
