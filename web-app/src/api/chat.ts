"""Frontend API for continuous chat with large-small model collaboration."""

import axios from 'axios'
import type { AxiosResponse } from 'axios'

const AGENT_SERVICE_URL = import.meta.env.VITE_AGENT_SERVICE_URL || 'http://localhost:8002'

export interface ChatSessionCreate {
  user_id: number
  title?: string
  subject?: string
}

export interface ChatMessageInput {
  session_id: number
  user_id: number
  content: string
  context?: Record<string, any>
}

export interface ChatMessageItem {
  id: number
  role: 'user' | 'assistant' | 'system'
  content: string
  model_used: string
  metadata: Record<string, any>
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
  metadata: Record<string, any>
  created_at: string
}

/**
 * Create a new chat session
 */
export async function createChatSession(data: ChatSessionCreate): Promise<ChatSessionDetail> {
  const response: AxiosResponse<ChatSessionDetail> = await axios.post(
    `${AGENT_SERVICE_URL}/chat/sessions/new`,
    data
  )
  return response.data
}

/**
 * List all chat sessions for a user
 */
export async function listChatSessions(userId: number, limit: number = 50): Promise<ChatSessionSummary[]> {
  const response: AxiosResponse<ChatSessionSummary[]> = await axios.get(
    `${AGENT_SERVICE_URL}/chat/sessions`,
    {
      params: { user_id: userId, limit }
    }
  )
  return response.data
}

/**
 * Get a chat session with message history
 */
export async function getChatSession(sessionId: number, userId: number): Promise<ChatSessionDetail> {
  const response: AxiosResponse<ChatSessionDetail> = await axios.get(
    `${AGENT_SERVICE_URL}/chat/sessions/${sessionId}`,
    {
      params: { user_id: userId }
    }
  )
  return response.data
}

/**
 * Send a message in a chat session
 */
export async function sendChatMessage(data: ChatMessageInput): Promise<ChatResponse> {
  const response: AxiosResponse<ChatResponse> = await axios.post(
    `${AGENT_SERVICE_URL}/chat/chat`,
    data
  )
  return response.data
}

/**
 * Delete a chat session
 */
export async function deleteChatSession(sessionId: number, userId: number): Promise<void> {
  await axios.delete(
    `${AGENT_SERVICE_URL}/chat/sessions/${sessionId}`,
    {
      params: { user_id: userId }
    }
  )
}
