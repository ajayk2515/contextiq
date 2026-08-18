import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { streamQuestion } from '@/api/chat'
import { ApiError } from '@/api/client'
import {
  createConversation,
  deleteConversation,
  fetchConversation,
  fetchConversations,
  type ConversationDetail,
  type ConversationSummary,
} from '@/api/conversations'
import { useAuthStore } from '@/stores/auth'

import ChatPage from './ChatPage.vue'

vi.mock('@/api/chat', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/chat')>()
  return { ...actual, streamQuestion: vi.fn() }
})

vi.mock('@/api/conversations', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/conversations')>()
  return {
    ...actual,
    createConversation: vi.fn(),
    deleteConversation: vi.fn(),
    fetchConversation: vi.fn(),
    fetchConversations: vi.fn(),
  }
})

const summary: ConversationSummary = {
  id: 'conversation-1',
  title: 'Leave policy',
  created_at: '2026-08-18T10:00:00Z',
  updated_at: '2026-08-18T10:01:00Z',
}

const detail: ConversationDetail = {
  ...summary,
  messages: [
    {
      id: 'message-1',
      role: 'USER',
      content: 'What is annual leave?',
      query_id: null,
      query_intelligence: null,
      sources: [],
      insufficient_context: false,
      created_at: '2026-08-18T10:00:00Z',
    },
    {
      id: 'message-2',
      role: 'ASSISTANT',
      content: 'Employees receive twenty days.',
      query_id: 'query-1',
      query_intelligence: {
        query_id: 'query-1',
        category: 'FAQ',
        profile: 'FAST',
        intended_strategy: 'DENSE',
        executed_strategy: 'DENSE',
        candidate_top_k: 3,
        classification_fallback: false,
      },
      sources: [
        {
          document_id: 'document-1',
          chunk_id: 'chunk-1',
          filename: 'handbook.md',
          page: null,
          section: 'Annual Leave',
          snippet: 'Employees receive twenty days.',
        },
      ],
      insufficient_context: false,
      created_at: '2026-08-18T10:01:00Z',
    },
  ],
}

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
    vi.mocked(fetchConversations).mockResolvedValue([summary])
    vi.mocked(fetchConversation).mockResolvedValue(detail)
    vi.mocked(createConversation).mockResolvedValue({
      ...summary,
      id: 'conversation-2',
      title: 'New conversation',
    })
    vi.mocked(deleteConversation).mockResolvedValue()
  })

  it('renders recent conversations and restored message citations', async () => {
    const wrapper = mountPage()
    await flushPromises()

    expect(fetchConversations).toHaveBeenCalledWith('signed-token')
    expect(fetchConversation).toHaveBeenCalledWith('signed-token', 'conversation-1')
    expect(wrapper.text()).toContain('Leave policy')
    expect(wrapper.text()).toContain('Employees receive twenty days.')
    expect(wrapper.text()).toContain('[1] handbook.md \u00b7 Annual Leave')
  })

  it('creates a new empty conversation from New Chat', async () => {
    const wrapper = mountPage()
    await flushPromises()

    await wrapper.get('button').trigger('click')
    await flushPromises()

    expect(createConversation).toHaveBeenCalledWith('signed-token')
    expect(wrapper.text()).toContain('New conversation')
    expect(wrapper.text()).toContain('Start a conversation')
  })

  it('appends streamed tokens and attaches sources to the assistant message', async () => {
    vi.mocked(streamQuestion).mockImplementation(async (_token, _id, _message, handlers) => {
      handlers.onMetadata({
        query_id: 'query-2',
        category: 'MULTI_DOC_COMPARISON',
        profile: 'ACCURATE',
        intended_strategy: 'HYBRID_WITH_RERANK',
        executed_strategy: 'HYBRID_RRF_RERANK',
        candidate_top_k: 15,
        classification_fallback: false,
      })
      handlers.onToken('The policies ')
      handlers.onToken('differ.')
      handlers.onCitations([
        {
          document_id: 'document-2',
          chunk_id: 'chunk-2',
          filename: 'benefits.md',
          page: null,
          section: 'Parental Leave',
          snippet: 'Sixteen weeks.',
        },
      ])
      handlers.onComplete({
        query_id: 'query-2',
        assistant_message_id: 'message-4',
        insufficient_context: false,
      })
    })
    const wrapper = mountPage()
    await flushPromises()

    await wrapper.get('textarea').setValue('Compare the leave policies')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(streamQuestion).toHaveBeenCalledWith(
      'signed-token',
      'conversation-1',
      'Compare the leave policies',
      expect.any(Object),
    )
    expect(wrapper.text()).toContain('The policies differ.')
    expect(wrapper.text()).toContain('[1] benefits.md \u00b7 Parental Leave')
    expect(wrapper.text()).toContain(
      'Multi Doc Comparison \u00b7 ACCURATE \u00b7 Hybrid RRF Reranker \u00b7 Top 15',
    )
  })

  it('shows stream errors and reloads persisted server history', async () => {
    vi.mocked(streamQuestion).mockRejectedValue(
      new ApiError('Unable to generate a response.', 503, 'ANSWER_GENERATION_FAILED'),
    )
    const wrapper = mountPage()
    await flushPromises()

    await wrapper.get('textarea').setValue('Question')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toBe('Unable to generate a response.')
    expect(fetchConversation).toHaveBeenCalledTimes(2)
  })

  it('deletes the active conversation after confirmation', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const wrapper = mountPage()
    await flushPromises()

    await wrapper.get('[aria-label="Delete Leave policy"]').trigger('click')
    await flushPromises()

    expect(deleteConversation).toHaveBeenCalledWith('signed-token', 'conversation-1')
    expect(wrapper.text()).toContain('Start a conversation')
  })
})
