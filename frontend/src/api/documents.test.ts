import { beforeEach, describe, expect, it, vi } from 'vitest'

import { deleteDocument, fetchDocuments, uploadDocument } from './documents'

describe('documents API', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('uploads multipart content with repeated role fields', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ id: 'document-id' }), {
        status: 202,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    const file = new File(['# Policy'], 'policy.md', { type: 'text/markdown' })

    await uploadDocument('token', file, ['HR', 'Executive'])

    const [, init] = fetchMock.mock.calls[0] ?? []
    const body = init?.body as FormData
    expect(init?.headers).toEqual(expect.any(Headers))
    expect((init?.headers as Headers).get('Authorization')).toBe('Bearer token')
    expect((init?.headers as Headers).has('Content-Type')).toBe(false)
    expect(body.get('file')).toBe(file)
    expect(body.getAll('allowed_roles')).toEqual(['HR', 'Executive'])
  })

  it('lists authenticated documents and accepts a no-content deletion', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(
        new Response(JSON.stringify([]), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
      .mockResolvedValueOnce(new Response(null, { status: 204 }))

    await expect(fetchDocuments('token')).resolves.toEqual([])
    await expect(deleteDocument('token', 'document-id')).resolves.toBeUndefined()
    expect(fetchMock).toHaveBeenLastCalledWith(
      expect.stringContaining('/api/documents/document-id'),
      expect.objectContaining({ method: 'DELETE' }),
    )
  })
})
