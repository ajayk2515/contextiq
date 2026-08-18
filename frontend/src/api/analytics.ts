import { apiRequest } from './client'
import type { ExecutedRetrievalStrategy } from './chat'
import type { OptimizationRecommendation } from './recommendations'

export interface AnalyticsMetrics {
  total_queries: number
  avg_retrieval_latency_ms: number | null
  faithfulness: number | null
  answer_relevancy: number | null
  context_precision: number | null
  context_recall: number | null
}

export interface StrategyDistributionItem {
  strategy: ExecutedRetrievalStrategy
  count: number
}

export interface LatencyPoint {
  query_id: string
  timestamp: string
  retrieval_latency_ms: number
}

export interface EvaluationHistoryItem {
  run_id: string
  completed_at: string
  faithfulness: number | null
  answer_relevancy: number | null
  context_precision: number | null
  context_recall: number | null
}

export interface AnalyticsSummaryResponse {
  summary: AnalyticsMetrics
  strategy_distribution: StrategyDistributionItem[]
  latency_series: LatencyPoint[]
  evaluation_history: EvaluationHistoryItem[]
  recommendations: OptimizationRecommendation[]
}

export function fetchAnalyticsSummary(token: string): Promise<AnalyticsSummaryResponse> {
  return apiRequest('/api/analytics/summary', {
    headers: { Authorization: `Bearer ${token}` },
  })
}
