import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { fetchAnalyticsSummary, type AnalyticsSummaryResponse } from '@/api/analytics'
import { ApiError } from '@/api/client'
import { useAuthStore } from '@/stores/auth'

import AnalyticsPage from './AnalyticsPage.vue'

vi.mock('@/api/analytics', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/analytics')>()
  return { ...actual, fetchAnalyticsSummary: vi.fn() }
})

const response: AnalyticsSummaryResponse = {
  summary: {
    total_queries: 42,
    avg_retrieval_latency_ms: 812.4,
    faithfulness: 0.83,
    answer_relevancy: 0.89,
    context_precision: 1,
    context_recall: 0.75,
  },
  strategy_distribution: [{ strategy: 'HYBRID_RRF_RERANK', count: 12 }],
  latency_series: [
    { query_id: 'query-1', timestamp: '2026-08-18T10:00:00Z', retrieval_latency_ms: 812 },
  ],
  evaluation_history: [
    {
      run_id: 'run-1',
      completed_at: '2026-08-18T10:00:00Z',
      faithfulness: 0.83,
      answer_relevancy: 0.89,
      context_precision: 1,
      context_recall: 0.75,
    },
  ],
  recommendations: [
    {
      id: 'recommendation-1',
      evaluation_run_id: 'run-1',
      metric: 'RETRIEVAL_LATENCY_MS',
      current_value: 3621,
      threshold: 2500,
      recommendation: 'Use FAST or BALANCED for queries that do not require reranking.',
      status: 'OPEN',
      profile: 'ACCURATE',
      strategy: 'HYBRID_RRF_RERANK',
      created_at: '2026-08-18T10:03:00Z',
    },
  ],
}

function mountPage() {
  return mount(AnalyticsPage, {
    global: {
      stubs: {
        AppHeader: true,
        AnalyticsChart: {
          props: ['option', 'label'],
          template: '<div data-test="chart" :aria-label="label"></div>',
        },
        RouterLink: { template: '<a><slot /></a>' },
      },
    },
  })
}

describe('AnalyticsPage', () => {
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
    vi.mocked(fetchAnalyticsSummary).mockResolvedValue(response)
  })

  it('renders metric cards, all required charts, and persisted recommendations', async () => {
    const wrapper = mountPage()
    await flushPromises()

    expect(fetchAnalyticsSummary).toHaveBeenCalledWith('signed-token')
    expect(wrapper.text()).toContain('42')
    expect(wrapper.text()).toContain('812 ms')
    expect(wrapper.text()).toContain('0.830')
    expect(wrapper.findAll('[data-test="chart"]')).toHaveLength(3)
    expect(wrapper.text()).toContain('Retrieval latency')
    expect(wrapper.text()).toContain('3621 ms')
    expect(wrapper.text()).toContain('ACCURATE · Hybrid RRF + Reranker')
    expect(wrapper.text()).toContain('Use FAST or BALANCED')
  })

  it('renders N/A metrics and useful empty states without chart containers', async () => {
    vi.mocked(fetchAnalyticsSummary).mockResolvedValueOnce({
      summary: {
        total_queries: 0,
        avg_retrieval_latency_ms: null,
        faithfulness: null,
        answer_relevancy: null,
        context_precision: null,
        context_recall: null,
      },
      strategy_distribution: [],
      latency_series: [],
      evaluation_history: [],
      recommendations: [],
    })

    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.text().match(/N\/A/g)).toHaveLength(5)
    expect(wrapper.text()).toContain('No retrieval strategies have been recorded.')
    expect(wrapper.text()).toContain('No completed evaluations are available.')
    expect(wrapper.text()).toContain('No latency samples are available yet.')
    expect(wrapper.text()).toContain('No open recommendations.')
    expect(wrapper.findAll('[data-test="chart"]')).toHaveLength(0)
  })

  it('renders loading and safe error states', async () => {
    vi.mocked(fetchAnalyticsSummary).mockReturnValueOnce(new Promise(() => undefined))
    const loading = mountPage()
    await flushPromises()
    expect(loading.text()).toContain('Loading analytics...')

    vi.mocked(fetchAnalyticsSummary).mockRejectedValueOnce(
      new ApiError('Analytics service is unavailable.', 503, 'SERVICE_UNAVAILABLE'),
    )
    const failed = mountPage()
    await flushPromises()
    expect(failed.get('[role="alert"]').text()).toBe('Analytics service is unavailable.')
  })
})
