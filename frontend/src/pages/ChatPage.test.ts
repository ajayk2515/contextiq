import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { askQuestion } from '@/api/chat'
import { ApiError } from '@/api/client'
import { useAuthStore } from '@/stores/auth'

import ChatPage from './ChatPage.vue'

vi.mock('@/api/chat', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/chat')>()
  return { ...actual, askQuestion: vi.fn() }
})

function mountPage() {
  return mount(ChatPage, { global: { stubs: { AppHeader: true } } })
}

describe('ChatPage', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    const auth = useAuthStore()
    auth.token = 'signed-token'
    auth.user = {
      id: 'be43f811-482a-4bca-a062-04e6f91291ac',
      email: 'hr@demo.com',
      role: 'HR',
    }
    vi.clearAllMocks()
  })

  it('renders an answer and source metadata with an optional page', async () => {
    vi.mocked(askQuestion).mockResolvedValue({
      answer: 'Employees receive twenty days of annual leave.',
      insufficient_context: false,
      query_intelligence: {
        query_id: 'e8789c91-e6bd-42a8-9dfb-326955bad3ee',
        category: 'FAQ',
        profile: 'FAST',
        intended_strategy: 'DENSE',
        executed_strategy: 'DENSE',
        candidate_top_k: 3,
        classification_fallback: false,
      },
      sources: [
        {
          document_id: '2418ac1e-d459-4a62-b3a7-a9228120a6bb',
          chunk_id: '16d67b2f-5c12-4330-99bf-810ec86f8266',
          filename: 'handbook.md',
          page: null,
          section: 'Annual Leave',
          snippet: 'Employees receive twenty days of annual leave.',
        },
      ],
    })
    const wrapper = mountPage()

    await wrapper.get('textarea').setValue('How much annual leave is provided?')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(askQuestion).toHaveBeenCalledWith('signed-token', 'How much annual leave is provided?')
    expect(wrapper.text()).toContain('Employees receive twenty days of annual leave.')
    expect(wrapper.text()).toContain('[1] handbook.md \u00b7 Annual Leave')
    expect(wrapper.get('[aria-label="Query routing"]').text()).toContain(
      'FAQ · FAST · Dense · Top 3',
    )
  })

  it('shows the loading and insufficient-context states', async () => {
    let resolveRequest: ((value: Awaited<ReturnType<typeof askQuestion>>) => void) | undefined
    vi.mocked(askQuestion).mockReturnValue(
      new Promise((resolve) => {
        resolveRequest = resolve
      }),
    )
    const wrapper = mountPage()

    await wrapper.get('textarea').setValue('Unknown topic')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.text()).toContain('Searching authorized documents')

    resolveRequest?.({
      answer: "I couldn't find enough information.",
      sources: [],
      insufficient_context: true,
      query_intelligence: {
        query_id: '3cd386aa-870e-44f3-99a3-86808a31016a',
        category: 'SPECIFIC_SEARCH',
        profile: 'BALANCED',
        intended_strategy: 'HYBRID',
        executed_strategy: 'HYBRID_RRF',
        candidate_top_k: 8,
        classification_fallback: true,
      },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('Insufficient context')
    expect(wrapper.text()).toContain("I couldn't find enough information.")
    expect(wrapper.get('[aria-label="Query routing"]').text()).toContain(
      'Specific Search · BALANCED · Hybrid RRF · Top 8',
    )
  })

  it('shows safe API errors', async () => {
    vi.mocked(askQuestion).mockRejectedValue(
      new ApiError('Document retrieval is temporarily unavailable.', 503, 'RETRIEVAL_FAILED'),
    )
    const wrapper = mountPage()

    await wrapper.get('textarea').setValue('Question')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toBe(
      'Document retrieval is temporarily unavailable.',
    )
  })
})
