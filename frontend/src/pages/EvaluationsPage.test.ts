import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  fetchEvaluation,
  fetchEvaluationRuns,
  startEvaluation,
  type EvaluationRunDetail,
} from '@/api/evaluations'
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
  })

  it('renders aggregate and per-case metrics with null values as N/A', async () => {
    const wrapper = mountPage()
    await flushPromises()

    expect(fetchEvaluationRuns).toHaveBeenCalledWith('signed-token')
    expect(fetchEvaluation).toHaveBeenCalledWith('signed-token', 'run-1')
    expect(wrapper.text()).toContain('0.900')
    expect(wrapper.text()).toContain('N/A')
    expect(wrapper.text()).toContain('METRIC: Metrics unavailable: answer_relevancy')
    expect(wrapper.text()).toContain('Inspect retrieval')
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
