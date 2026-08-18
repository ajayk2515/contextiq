import { beforeEach, describe, expect, it, vi } from 'vitest'

import { askQuestion, streamQuestion } from './chat'

describe('chat API', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('sends only the authenticated user question', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          answer: 'Grounded answer',
          sources: [],
          insufficient_context: false,
          query_intelligence: {
            query_id: '4d7ef5f6-bd6e-4f45-a3f3-d0ab431d1e8a',
            category: 'FAQ',
            profile: 'FAST',
            intended_strategy: 'DENSE',
            executed_strategy: 'DENSE',
            candidate_top_k: 3,
            classification_fallback: false,
          },
        }),
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

  it('parses incrementally chunked SSE events for an authenticated POST', async () => {
    const encoder = new TextEncoder()
    const body = new ReadableStream({
      start(controller) {
        controller.enqueue(
          encoder.encode(
            'event: metadata\ndata: {"query_id":"query-1","category":"FAQ","profile":"FAST",',
          ),
        )
        controller.enqueue(
          encoder.encode(
            '"intended_strategy":"DENSE","executed_strategy":"DENSE","candidate_top_k":3,"classification_fallback":false}\n\n' +
              'event: token\ndata: {"text":"Grounded "}\n\n',
          ),
        )
        controller.enqueue(
          encoder.encode(
            'event: token\ndata: {"text":"answer"}\n\n' +
              'event: citations\ndata: {"sources":[]}\n\n' +
              'event: complete\ndata: {"query_id":"query-1","assistant_message_id":"message-1","insufficient_context":false}\n\n',
          ),
        )
        controller.close()
      },
    })
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(
        new Response(body, { status: 200, headers: { 'Content-Type': 'text/event-stream' } }),
      )
    const received: string[] = []

    await streamQuestion('signed-token', 'conversation-1', 'Question', {
      onMetadata: (metadata) => received.push(metadata.profile),
      onToken: (text) => received.push(text),
      onCitations: (sources) => received.push(`sources:${sources.length}`),
      onComplete: (complete) => received.push(complete.assistant_message_id),
    })

    expect(received).toEqual(['FAST', 'Grounded ', 'answer', 'sources:0', 'message-1'])
    const [, init] = fetchMock.mock.calls[0] ?? []
    expect(init?.method).toBe('POST')
    expect((init?.headers as Record<string, string>).Authorization).toBe('Bearer signed-token')
    expect(JSON.parse(init?.body as string)).toEqual({
      conversation_id: 'conversation-1',
      message: 'Question',
    })
  })
})
