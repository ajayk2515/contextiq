import type { AuthUser, UserRole } from './auth'
import { apiRequest } from './client'

export type DocumentStatus = 'PROCESSING' | 'READY' | 'FAILED'

export interface DocumentRecord {
  id: string
  filename: string
  file_hash: string
  status: DocumentStatus
  allowed_roles: UserRole[]
  chunk_count: number
  error_message: string | null
  uploader: Pick<AuthUser, 'id' | 'email'>
  created_at: string
  updated_at: string
}

function bearer(token: string) {
  return { Authorization: `Bearer ${token}` }
}

export function fetchDocuments(token: string, signal?: AbortSignal): Promise<DocumentRecord[]> {
  return apiRequest<DocumentRecord[]>('/api/documents', {
    headers: bearer(token),
    ...(signal ? { signal } : {}),
  })
}

export function uploadDocument(
  token: string,
  file: File,
  roles: UserRole[],
): Promise<DocumentRecord> {
  const body = new FormData()
  body.append('file', file)
  roles.forEach((role) => body.append('allowed_roles', role))
  return apiRequest<DocumentRecord>('/api/documents', {
    method: 'POST',
    headers: bearer(token),
    body,
  })
}

export function deleteDocument(token: string, documentId: string): Promise<void> {
  return apiRequest<void>(`/api/documents/${documentId}`, {
    method: 'DELETE',
    headers: bearer(token),
  })
}
