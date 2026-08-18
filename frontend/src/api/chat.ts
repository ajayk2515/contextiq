import { ApiError, apiErrorFromResponse, apiRequest, apiUrl } from './client'

export interface ChatSource {
  document_id: string
  chunk_id: string
  filename: string
  page: number | null
  section: string | null
  snippet: string
}

export type QueryCategory =
  'FAQ' | 'SPECIFIC_SEARCH' | 'MULTI_DOC_COMPARISON' | 'SUMMARIZATION' | 'RESTRICTED_DATA'

export type RetrievalProfile = 'FAST' | 'BALANCED' | 'ACCURATE'
export type ExecutedRetrievalStrategy =
  'DENSE' | 'DENSE_FALLBACK' | 'HYBRID_RRF' | 'HYBRID_RRF_RERANK'

export interface QueryIntelligenceMetadata {
  query_id: string
  category: QueryCategory
  profile: RetrievalProfile
  intended_strategy: 'DENSE' | 'HYBRID' | 'HYBRID_WITH_RERANK'
  executed_strategy: ExecutedRetrievalStrategy
  candidate_top_k: number
  classification_fallback: boolean
}

export interface ChatResponse {
  answer: string
  sources: ChatSource[]
  insufficient_context: boolean
  query_intelligence: QueryIntelligenceMetadata
}

export interface StreamComplete {
  query_id: string
  assistant_message_id: string
  insufficient_context: boolean
}

export interface StreamHandlers {
  onMetadata(metadata: QueryIntelligenceMetadata): void
  onToken(text: string): void
  onCitations(sources: ChatSource[]): void
  onComplete(complete: StreamComplete): void
}

export function askQuestion(token: string, message: string): Promise<ChatResponse> {
  return apiRequest<ChatResponse>('/api/chat', {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify({ message }),
  })
}

function parseEvent(block: string, handlers: StreamHandlers): boolean {
  let event = ''
  const data: string[] = []
  for (const line of block.split(/\r?\n/)) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    if (line.startsWith('data:')) data.push(line.slice(5).trimStart())
  }
  if (!event || !data.length) return false

  const payload = JSON.parse(data.join('\n')) as Record<string, unknown>
  if (event === 'metadata') handlers.onMetadata(payload as unknown as QueryIntelligenceMetadata)
  if (event === 'token') handlers.onToken(String(payload.text ?? ''))
  if (event === 'citations') handlers.onCitations((payload.sources ?? []) as ChatSource[])
  if (event === 'complete') {
    handlers.onComplete(payload as unknown as StreamComplete)
    return true
  }
  if (event === 'error') {
    throw new ApiError(
      typeof payload.message === 'string' ? payload.message : 'The response stream failed.',
      503,
      typeof payload.code === 'string' ? payload.code : 'CHAT_STREAM_FAILED',
    )
  }
  return false
}

export async function streamQuestion(
  token: string,
  conversationId: string,
  message: string,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(apiUrl('/api/chat/stream'), {
    method: 'POST',
    headers: {
      Accept: 'text/event-stream',
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ conversation_id: conversationId, message }),
    signal: signal ?? null,
  })
  if (!response.ok) throw await apiErrorFromResponse(response)
  if (!response.body) throw new ApiError('The response stream was unavailable.', 503)

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let completed = false
  while (true) {
    const { done, value } = await reader.read()
    buffer += decoder.decode(value, { stream: !done }).replace(/\r\n/g, '\n')
    let boundary = buffer.indexOf('\n\n')
    while (boundary >= 0) {
      const block = buffer.slice(0, boundary)
      buffer = buffer.slice(boundary + 2)
      completed = parseEvent(block, handlers) || completed
      boundary = buffer.indexOf('\n\n')
    }
    if (done) break
  }
  if (buffer.trim()) completed = parseEvent(buffer, handlers) || completed
  if (!completed) throw new ApiError('The response stream ended unexpectedly.', 503)
}
