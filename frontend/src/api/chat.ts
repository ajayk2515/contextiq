import { apiRequest } from './client'

export interface ChatSource {
  document_id: string
  chunk_id: string
  filename: string
  page: number | null
  section: string | null
  snippet: string
}

export interface ChatResponse {
  answer: string
  sources: ChatSource[]
  insufficient_context: boolean
}

export function askQuestion(token: string, message: string): Promise<ChatResponse> {
  return apiRequest<ChatResponse>('/api/chat', {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify({ message }),
  })
}
