import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '@/api/client'
import {
  fetchQueries,
  fetchQuery,
  fetchRetrieval,
  type QueryDetail,
  type RetrievalSnapshot,
} from '@/api/inspector'
import { useAuthStore } from '@/stores/auth'

import InspectorPage from './InspectorPage.vue'

const { routeQuery } = vi.hoisted(() => ({
  routeQuery: {} as Record<string, string>,
}))

vi.mock('vue-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('vue-router')>()
  return { ...actual, useRoute: () => ({ query: routeQuery }) }
})

vi.mock('@/api/inspector', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/inspector')>()
  return {
    ...actual,
    fetchQueries: vi.fn(),
    fetchQuery: vi.fn(),
    fetchRetrieval: vi.fn(),
  }
})

const accurateDetail: QueryDetail = {
  id: 'query-1',
  query_text: 'Compare the leave policies',
  query_category: 'MULTI_DOC_COMPARISON',
  retrieval_profile: 'ACCURATE',
  retrieval_strategy: 'HYBRID_RRF_RERANK',
  retrieval_latency_ms: 47,
  classifier_fallback: false,
  created_at: '2026-08-18T10:00:00Z',
  candidate_count: 7,
  final_context_count: 5,
  reranked: true,
}

function snapshot(overrides: Partial<RetrievalSnapshot> = {}): RetrievalSnapshot {
  return {
    id: 'snapshot-1',
    query_id: 'query-1',
    document_id: 'document-1',
    chunk_id: 'chunk-1',
    filename: 'policy.pdf',
    page: 4,
    section: 'Leave',
    snippet: 'Employees receive twenty days of annual leave.',
    rank_before: 2,
    rank_after: 6,
    retrieval_score: null,
    rrf_score: 0.024,
    reranker_score: 0.78,
    included_in_context: false,
    created_at: '2026-08-18T10:00:01Z',
    ...overrides,
  }
}

function mountPage() {
  return mount(InspectorPage, { global: { stubs: { AppHeader: true } } })
}

describe('InspectorPage', () => {
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
    for (const key of Object.keys(routeQuery)) delete routeQuery[key]
    vi.mocked(fetchQueries).mockResolvedValue([accurateDetail])
    vi.mocked(fetchQuery).mockResolvedValue(accurateDetail)
    vi.mocked(fetchRetrieval).mockResolvedValue([snapshot()])
  })

  it('shows ACCURATE pre/post ranks, scores, and dropped candidates', async () => {
    const wrapper = mountPage()
    await flushPromises()

    expect(fetchQueries).toHaveBeenCalledWith('signed-token')
    expect(fetchQuery).toHaveBeenCalledWith('signed-token', 'query-1')
    expect(fetchRetrieval).toHaveBeenCalledWith('signed-token', 'query-1')
    expect(wrapper.text()).toContain('Hybrid RRF + Reranker')
    expect(wrapper.text()).toContain('Pre-rerank rank')
    expect(wrapper.text()).toContain('RRF score')
    expect(wrapper.text()).toContain('Reranker score')
    expect(wrapper.text()).toContain('Post-rerank rank')
    expect(wrapper.text()).toContain('Dropped after reranking')
    expect(wrapper.text()).toContain('policy.pdf · Page 4 · Leave')
  })

  it('shows only the available score fields for FAST retrieval', async () => {
    vi.mocked(fetchQuery).mockResolvedValue({
      ...accurateDetail,
      retrieval_profile: 'FAST',
      retrieval_strategy: 'DENSE',
      candidate_count: 1,
      final_context_count: 1,
      reranked: false,
    })
    vi.mocked(fetchRetrieval).mockResolvedValue([
      snapshot({
        page: null,
        section: null,
        rank_before: 1,
        rank_after: null,
        retrieval_score: 0.91,
        rrf_score: null,
        reranker_score: null,
        included_in_context: true,
      }),
    ])

    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.text()).toContain('Dense score')
    expect(wrapper.text()).toContain('Final context')
    expect(wrapper.text()).not.toContain('RRF score')
    expect(wrapper.text()).not.toContain('Reranker score')
    expect(wrapper.text()).not.toContain('Page ')
  })

  it('shows BALANCED RRF fields without reranker metadata', async () => {
    vi.mocked(fetchQuery).mockResolvedValue({
      ...accurateDetail,
      retrieval_profile: 'BALANCED',
      retrieval_strategy: 'HYBRID_RRF',
      candidate_count: 1,
      final_context_count: 1,
      reranked: false,
    })
    vi.mocked(fetchRetrieval).mockResolvedValue([
      snapshot({ rank_after: null, reranker_score: null, included_in_context: true }),
    ])

    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.text()).toContain('Hybrid RRF')
    expect(wrapper.text()).toContain('RRF score')
    expect(wrapper.text()).not.toContain('Dense score')
    expect(wrapper.text()).not.toContain('Reranker score')
    expect(wrapper.text()).not.toContain('Post-rerank rank')
  })

  it('loads a selected query from the recent-query list', async () => {
    const second = {
      ...accurateDetail,
      id: 'query-2',
      query_text: 'Find the travel policy',
    }
    vi.mocked(fetchQueries).mockResolvedValue([accurateDetail, second])
    vi.mocked(fetchQuery).mockResolvedValueOnce(accurateDetail).mockResolvedValueOnce(second)

    const wrapper = mountPage()
    await flushPromises()
    await wrapper.findAll('aside button')[1].trigger('click')
    await flushPromises()

    expect(fetchQuery).toHaveBeenLastCalledWith('signed-token', 'query-2')
    expect(fetchRetrieval).toHaveBeenLastCalledWith('signed-token', 'query-2')
    expect(wrapper.text()).toContain('Find the travel policy')
  })

  it('opens the query_id supplied by evaluation and chat links', async () => {
    const second = {
      ...accurateDetail,
      id: 'query-2',
      query_text: 'Find the travel policy',
    }
    routeQuery.query_id = 'query-2'
    vi.mocked(fetchQueries).mockResolvedValue([accurateDetail, second])
    vi.mocked(fetchQuery).mockResolvedValue(second)

    mountPage()
    await flushPromises()

    expect(fetchQuery).toHaveBeenCalledWith('signed-token', 'query-2')
    expect(fetchRetrieval).toHaveBeenCalledWith('signed-token', 'query-2')
  })

  it('renders empty and safe API error states', async () => {
    vi.mocked(fetchQueries).mockResolvedValueOnce([])
    const empty = mountPage()
    await flushPromises()
    expect(empty.text()).toContain('No retrieval history yet.')

    vi.mocked(fetchQueries).mockRejectedValueOnce(
      new ApiError('Retrieval history is unavailable.', 503, 'SERVICE_UNAVAILABLE'),
    )
    const failed = mountPage()
    await flushPromises()
    expect(failed.get('[role="alert"]').text()).toBe('Retrieval history is unavailable.')
  })
})
