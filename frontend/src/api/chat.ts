import { apiRequest } from './client'

export interface ChatSource {
  document_id: string
  chunk_id: string
  filename: string
  page: number | null
  section: string | null
  snippet: string
}

export type QueryCategory =
  'FAQ' | 'SPECIFIC_SEARCH' | 'MULTI_DOC_COMPARISON' | 'SUMMARIZATION' | 'RESTRICTED_DATA'

export type RetrievalProfile = 'FAST' | 'BALANCED' | 'ACCURATE'

export interface QueryIntelligenceMetadata {
  query_id: string
  category: QueryCategory
  profile: RetrievalProfile
  intended_strategy: 'DENSE' | 'HYBRID' | 'HYBRID_WITH_RERANK'
  executed_strategy: 'DENSE' | 'DENSE_FALLBACK'
  candidate_top_k: number
  classification_fallback: boolean
}

export interface ChatResponse {
  answer: string
  sources: ChatSource[]
  insufficient_context: boolean
  query_intelligence: QueryIntelligenceMetadata
}

export function askQuestion(token: string, message: string): Promise<ChatResponse> {
  return apiRequest<ChatResponse>('/api/chat', {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify({ message }),
  })
}
