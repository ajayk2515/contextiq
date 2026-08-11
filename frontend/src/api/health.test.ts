import { afterEach, describe, expect, it, vi } from 'vitest'

import { fetchHealth } from './health'

describe('fetchHealth', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('returns service health from the backend', async () => {
    const payload = {
      status: 'ok' as const,
      services: { database: 'ok' as const, qdrant: 'ok' as const },
    }
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchHealth()).resolves.toEqual(payload)
    expect(fetchMock).toHaveBeenCalledWith('/health', {
      headers: { Accept: 'application/json' },
    })
  })

  it('preserves a degraded dependency response', async () => {
    const payload = {
      status: 'degraded' as const,
      services: { database: 'unavailable' as const, qdrant: 'ok' as const },
    }
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(payload), {
          status: 503,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    )

    await expect(fetchHealth()).resolves.toEqual(payload)
  })
})
