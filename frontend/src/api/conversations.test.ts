import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  createConversation,
  deleteConversation,
  fetchConversation,
  fetchConversations,
} from './conversations'

describe('conversations API', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('uses authenticated summary and detail endpoints', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ id: 'conversation-1' }), { status: 201 }),
      )
      .mockResolvedValueOnce(new Response(JSON.stringify([]), { status: 200 }))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ id: 'conversation-1', messages: [] }), { status: 200 }),
      )
      .mockResolvedValueOnce(new Response(null, { status: 204 }))

    await createConversation('token')
    await fetchConversations('token')
    await fetchConversation('token', 'conversation-1')
    await deleteConversation('token', 'conversation-1')

    expect(fetchMock).toHaveBeenCalledTimes(4)
    for (const [, init] of fetchMock.mock.calls) {
      expect((init?.headers as Headers).get('Authorization')).toBe('Bearer token')
    }
    expect(fetchMock).toHaveBeenLastCalledWith(
      expect.stringContaining('/api/conversations/conversation-1'),
      expect.objectContaining({ method: 'DELETE' }),
    )
  })
})
