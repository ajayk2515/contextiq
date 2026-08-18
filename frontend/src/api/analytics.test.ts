import { beforeEach, describe, expect, it, vi } from 'vitest'

import { fetchAnalyticsSummary } from './analytics'

describe('analytics API', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('loads the authenticated dashboard summary', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          summary: { total_queries: 0 },
          strategy_distribution: [],
          latency_series: [],
          evaluation_history: [],
          recommendations: [],
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    )

    await fetchAnalyticsSummary('signed-token')

    expect(fetchMock.mock.calls[0][0]).toBe('/api/analytics/summary')
    const headers = new Headers(fetchMock.mock.calls[0][1]?.headers)
    expect(headers.get('Authorization')).toBe('Bearer signed-token')
  })
})
