import { apiRequest } from './client'
import type { ExecutedRetrievalStrategy, RetrievalProfile } from './chat'

export type OptimizationMetric = 'CONTEXT_RECALL' | 'CONTEXT_PRECISION' | 'RETRIEVAL_LATENCY_MS'
export type OptimizationStatus = 'OPEN' | 'DISMISSED'

export interface OptimizationRecommendation {
  id: string
  evaluation_run_id: string
  metric: OptimizationMetric
  current_value: number
  threshold: number
  recommendation: string
  status: OptimizationStatus
  profile: RetrievalProfile | null
  strategy: ExecutedRetrievalStrategy | null
  created_at: string
}

function authorization(token: string) {
  return { Authorization: `Bearer ${token}` }
}

export function fetchRecommendations(
  token: string,
  evaluationRunId: string,
): Promise<OptimizationRecommendation[]> {
  const query = new URLSearchParams({ evaluation_run_id: evaluationRunId })
  return apiRequest(`/api/recommendations?${query}`, { headers: authorization(token) })
}

export function dismissRecommendation(
  token: string,
  recommendationId: string,
): Promise<OptimizationRecommendation> {
  return apiRequest(`/api/recommendations/${recommendationId}`, {
    method: 'PATCH',
    headers: authorization(token),
    body: JSON.stringify({ status: 'DISMISSED' }),
  })
}
