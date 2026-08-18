import { beforeEach, describe, expect, it, vi } from 'vitest'

import { fetchEvaluation, fetchEvaluationRuns, startEvaluation } from './evaluations'

describe('evaluation API', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('starts a selected evaluation without exposing a file path', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ id: 'run-1' }), {
        status: 202,
        headers: { 'Content-Type': 'application/json' },
      }),
    )

    await startEvaluation('token', ['faq-annual-leave'])

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/evaluations/run',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ case_ids: ['faq-annual-leave'] }),
      }),
    )
    const headers = new Headers(fetchMock.mock.calls[0][1]?.headers)
    expect(headers.get('Authorization')).toBe('Bearer token')
  })

  it('loads run summaries and detail', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response('[]', { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: 'run-2' }), { status: 200 }))

    await fetchEvaluationRuns('token')
    await fetchEvaluation('token', 'run-2')

    expect(fetchMock.mock.calls[0][0]).toBe('/api/evaluations')
    expect(fetchMock.mock.calls[1][0]).toBe('/api/evaluations/run-2')
  })
})
