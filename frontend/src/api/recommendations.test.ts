import { beforeEach, describe, expect, it, vi } from 'vitest'

import { dismissRecommendation, fetchRecommendations } from './recommendations'

describe('recommendation API', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('loads open recommendations for one evaluation run', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(
        new Response('[]', { status: 200, headers: { 'Content-Type': 'application/json' } }),
      )

    await fetchRecommendations('token', 'run id')

    expect(fetchMock.mock.calls[0][0]).toBe('/api/recommendations?evaluation_run_id=run+id')
    const headers = new Headers(fetchMock.mock.calls[0][1]?.headers)
    expect(headers.get('Authorization')).toBe('Bearer token')
  })

  it('dismisses without exposing an apply action', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ id: 'recommendation-1', status: 'DISMISSED' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )

    await dismissRecommendation('token', 'recommendation-1')

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/recommendations/recommendation-1',
      expect.objectContaining({
        method: 'PATCH',
        body: JSON.stringify({ status: 'DISMISSED' }),
      }),
    )
  })
})
