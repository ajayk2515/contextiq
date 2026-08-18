import { apiRequest } from './client'
import type { ChatSource, QueryIntelligenceMetadata } from './chat'

export type MessageRole = 'USER' | 'ASSISTANT'

export interface ConversationSummary {
  id: string
  title: string
  created_at: string
  updated_at: string
}

export interface ConversationMessage {
  id: string
  role: MessageRole
  content: string
  query_id: string | null
  query_intelligence?: QueryIntelligenceMetadata | null
  sources: ChatSource[]
  insufficient_context: boolean
  created_at: string
}

export interface ConversationDetail extends ConversationSummary {
  messages: ConversationMessage[]
}

function authorization(token: string) {
  return { Authorization: `Bearer ${token}` }
}

export function createConversation(token: string): Promise<ConversationSummary> {
  return apiRequest('/api/conversations', {
    method: 'POST',
    headers: authorization(token),
  })
}

export function fetchConversations(token: string): Promise<ConversationSummary[]> {
  return apiRequest('/api/conversations', { headers: authorization(token) })
}

export function fetchConversation(token: string, id: string): Promise<ConversationDetail> {
  return apiRequest(`/api/conversations/${id}`, { headers: authorization(token) })
}

export function deleteConversation(token: string, id: string): Promise<void> {
  return apiRequest(`/api/conversations/${id}`, {
    method: 'DELETE',
    headers: authorization(token),
  })
}
