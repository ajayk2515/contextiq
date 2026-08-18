import { beforeEach, describe, expect, it, vi } from 'vitest'

import { fetchQueries, fetchQuery, fetchRetrieval } from './inspector'

describe('retrieval inspector API', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('uses authenticated history, detail, and retrieval endpoints', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify([]), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: 'query-1' }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify([]), { status: 200 }))

    await fetchQueries('token')
    await fetchQuery('token', 'query-1')
    await fetchRetrieval('token', 'query-1')

    expect(fetchMock).toHaveBeenCalledTimes(3)
    for (const [, init] of fetchMock.mock.calls) {
      expect((init?.headers as Headers).get('Authorization')).toBe('Bearer token')
    }
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      '/api/queries',
      '/api/queries/query-1',
      '/api/queries/query-1/retrieval',
    ])
  })
})
