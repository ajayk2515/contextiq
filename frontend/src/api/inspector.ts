import { apiRequest } from './client'
import type { ExecutedRetrievalStrategy, QueryCategory, RetrievalProfile } from './chat'

export interface QuerySummary {
  id: string
  query_text: string
  query_category: QueryCategory
  retrieval_profile: RetrievalProfile
  retrieval_strategy: ExecutedRetrievalStrategy
  retrieval_latency_ms: number
  classifier_fallback: boolean
  created_at: string
}

export interface QueryDetail extends QuerySummary {
  candidate_count: number
  final_context_count: number
  reranked: boolean
}

export interface RetrievalSnapshot {
  id: string
  query_id: string
  document_id: string
  chunk_id: string
  filename: string
  page: number | null
  section: string | null
  snippet: string
  rank_before: number | null
  rank_after: number | null
  retrieval_score: number | null
  rrf_score: number | null
  reranker_score: number | null
  included_in_context: boolean
  created_at: string
}

function authorization(token: string) {
  return { Authorization: `Bearer ${token}` }
}

export function fetchQueries(token: string): Promise<QuerySummary[]> {
  return apiRequest('/api/queries', { headers: authorization(token) })
}

export function fetchQuery(token: string, queryId: string): Promise<QueryDetail> {
  return apiRequest(`/api/queries/${queryId}`, { headers: authorization(token) })
}

export function fetchRetrieval(token: string, queryId: string): Promise<RetrievalSnapshot[]> {
  return apiRequest(`/api/queries/${queryId}/retrieval`, { headers: authorization(token) })
}
