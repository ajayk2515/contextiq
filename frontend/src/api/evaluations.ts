import { apiRequest } from './client'

export type EvaluationRunStatus = 'RUNNING' | 'COMPLETED' | 'FAILED'
export type EvaluationFailureCategory =
  'RETRIEVAL' | 'GENERATION' | 'METRIC' | 'AUTHORIZATION' | 'SYSTEM'

export interface EvaluationAverages {
  faithfulness: number | null
  answer_relevancy: number | null
  context_precision: number | null
  context_recall: number | null
}

export interface EvaluationRunSummary {
  id: string
  status: EvaluationRunStatus
  total_cases: number
  completed_cases: number
  error_message: string | null
  averages: EvaluationAverages
  started_at: string
  completed_at: string | null
  created_at: string
}

export interface EvaluationResult {
  id: string
  evaluation_case_id: string
  query_id: string | null
  question: string
  role: 'Developer' | 'HR' | 'Finance' | 'Executive'
  expected_answer: string
  expected_document: string
  generated_answer: string | null
  faithfulness: number | null
  answer_relevancy: number | null
  context_precision: number | null
  context_recall: number | null
  failure_category: EvaluationFailureCategory | null
  error_message: string | null
  insufficient_context: boolean
  created_at: string
}

export interface EvaluationRunDetail extends EvaluationRunSummary {
  evaluations: EvaluationResult[]
}

function authorization(token: string) {
  return { Authorization: `Bearer ${token}` }
}

export function startEvaluation(
  token: string,
  caseIds: string[] | null = null,
): Promise<EvaluationRunSummary> {
  return apiRequest('/api/evaluations/run', {
    method: 'POST',
    headers: authorization(token),
    body: JSON.stringify({ case_ids: caseIds }),
  })
}

export function fetchEvaluationRuns(token: string): Promise<EvaluationRunSummary[]> {
  return apiRequest('/api/evaluations', { headers: authorization(token) })
}

export function fetchEvaluation(token: string, runId: string): Promise<EvaluationRunDetail> {
  return apiRequest(`/api/evaluations/${runId}`, { headers: authorization(token) })
}
