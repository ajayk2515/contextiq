import { beforeEach, describe, expect, it, vi } from 'vitest'

import { askQuestion } from './chat'

describe('chat API', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('sends only the authenticated user question', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(
        new Response(
          JSON.stringify({ answer: 'Grounded answer', sources: [], insufficient_context: false }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      )

    await askQuestion('signed-token', 'What is the leave policy?')

    const [url, init] = fetchMock.mock.calls[0] ?? []
    expect(url).toContain('/api/chat')
    expect(init?.method).toBe('POST')
    expect((init?.headers as Headers).get('Authorization')).toBe('Bearer signed-token')
    expect(JSON.parse(init?.body as string)).toEqual({ message: 'What is the leave policy?' })
  })
})
