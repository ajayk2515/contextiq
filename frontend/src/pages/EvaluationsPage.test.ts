import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  fetchEvaluation,
  fetchEvaluationRuns,
  startEvaluation,
  type EvaluationRunDetail,
} from '@/api/evaluations'
import {
  dismissRecommendation,
  fetchRecommendations,
  type OptimizationRecommendation,
} from '@/api/recommendations'
import { useAuthStore } from '@/stores/auth'

import EvaluationsPage from './EvaluationsPage.vue'

vi.mock('@/api/evaluations', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/evaluations')>()
  return {
    ...actual,
    fetchEvaluation: vi.fn(),
    fetchEvaluationRuns: vi.fn(),
    startEvaluation: vi.fn(),
  }
})

vi.mock('@/api/recommendations', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/recommendations')>()
  return {
    ...actual,
    dismissRecommendation: vi.fn(),
    fetchRecommendations: vi.fn(),
  }
})

const recommendation: OptimizationRecommendation = {
  id: 'recommendation-1',
  evaluation_run_id: 'run-1',
  metric: 'CONTEXT_RECALL',
  current_value: 0.5,
  threshold: 0.65,
  recommendation: 'Hybrid retrieval has low context recall. Increase the candidate pool.',
  status: 'OPEN',
  profile: 'BALANCED',
  strategy: 'HYBRID_RRF',
  created_at: '2026-08-18T10:03:00Z',
}

const completedRun: EvaluationRunDetail = {
  id: 'run-1',
  status: 'COMPLETED',
  total_cases: 1,
  completed_cases: 1,
  error_message: null,
  averages: {
    faithfulness: 0.9,
    answer_relevancy: null,
    context_precision: 0.7,
    context_recall: 0.6,
  },
  started_at: '2026-08-18T10:00:00Z',
  completed_at: '2026-08-18T10:02:00Z',
  created_at: '2026-08-18T10:00:00Z',
  evaluations: [
    {
      id: 'result-1',
      evaluation_case_id: 'faq-annual-leave',
      query_id: 'query-1',
      question: 'How many leave days?',
      role: 'Developer',
      expected_answer: 'Twenty days.',
      expected_document: 'evaluation-employee-handbook.md',
      generated_answer: 'Employees receive twenty days.',
      faithfulness: 0.9,
      answer_relevancy: null,
      context_precision: 0.7,
      context_recall: 0.6,
      failure_category: 'METRIC',
      error_message: 'Metrics unavailable: answer_relevancy',
      insufficient_context: false,
      created_at: '2026-08-18T10:01:00Z',
    },
  ],
}

function mountPage() {
  return mount(EvaluationsPage, {
    global: {
      stubs: {
        AppHeader: true,
        RouterLink: { template: '<a><slot /></a>' },
      },
    },
  })
}

describe('EvaluationsPage', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    const auth = useAuthStore()
    auth.token = 'signed-token'
    auth.user = {
      id: 'be43f811-482a-4bca-a062-04e6f91291ac',
      email: 'developer@demo.com',
      role: 'Developer',
    }
    vi.clearAllMocks()
    vi.mocked(fetchEvaluationRuns).mockResolvedValue([completedRun])
    vi.mocked(fetchEvaluation).mockResolvedValue(completedRun)
    vi.mocked(startEvaluation).mockResolvedValue(completedRun)
    vi.mocked(fetchRecommendations).mockResolvedValue([recommendation])
    vi.mocked(dismissRecommendation).mockResolvedValue({
      ...recommendation,
      status: 'DISMISSED',
    })
  })

  it('renders aggregate and per-case metrics with null values as N/A', async () => {
    const wrapper = mountPage()
    await flushPromises()

    expect(fetchEvaluationRuns).toHaveBeenCalledWith('signed-token')
    expect(fetchEvaluation).toHaveBeenCalledWith('signed-token', 'run-1')
    expect(fetchRecommendations).toHaveBeenCalledWith('signed-token', 'run-1')
    expect(wrapper.text()).toContain('0.900')
    expect(wrapper.text()).toContain('N/A')
    expect(wrapper.text()).toContain('METRIC: Metrics unavailable: answer_relevancy')
    expect(wrapper.text()).toContain('Inspect retrieval')
  })

  it('renders persisted recommendation values and profile context', async () => {
    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.text()).toContain('Optimization recommendations')
    expect(wrapper.text()).toContain('Context recall')
    expect(wrapper.text()).toContain('0.500')
    expect(wrapper.text()).toContain('0.650')
    expect(wrapper.text()).toContain('BALANCED · HYBRID_RRF')
    expect(wrapper.text()).toContain('Increase the candidate pool.')
    expect(wrapper.text()).not.toContain('Apply Recommendation')
  })

  it('dismisses an open recommendation and shows the empty state', async () => {
    const wrapper = mountPage()
    await flushPromises()

    const dismissButton = wrapper.findAll('button').find((button) => button.text() === 'Dismiss')
    expect(dismissButton).toBeDefined()
    await dismissButton!.trigger('click')
    await flushPromises()

    expect(dismissRecommendation).toHaveBeenCalledWith('signed-token', 'recommendation-1')
    expect(wrapper.text()).toContain('No optimization recommendations were generated for this run.')
  })

  it('shows recommendation empty and error states', async () => {
    vi.mocked(fetchRecommendations).mockResolvedValueOnce([])
    const empty = mountPage()
    await flushPromises()
    expect(empty.text()).toContain('No optimization recommendations were generated for this run.')

    vi.mocked(fetchRecommendations).mockRejectedValueOnce(new Error('unavailable'))
    const failed = mountPage()
    await flushPromises()
    expect(failed.text()).toContain('Optimization recommendations are unavailable.')
  })

  it('shows the recommendation loading state', async () => {
    vi.mocked(fetchRecommendations).mockReturnValueOnce(new Promise(() => undefined))

    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.text()).toContain('Loading recommendations...')
  })

  it('starts the representative five-case run by default', async () => {
    const wrapper = mountPage()
    await flushPromises()

    await wrapper.get('button.primary-button').trigger('click')
    await flushPromises()

    expect(startEvaluation).toHaveBeenCalledWith('signed-token', [
      'faq-annual-leave',
      'specific-deployment-freeze',
      'compare-expansion-sequence',
      'restricted-retention-bonus',
      'summary-strategy',
    ])
  })
})
