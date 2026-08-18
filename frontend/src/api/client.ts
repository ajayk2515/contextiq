interface ApiErrorDetail {
  code?: string
  message?: string
}

interface ApiErrorBody {
  detail?: ApiErrorDetail | string
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code?: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')

export function apiUrl(path: string) {
  return `${apiBaseUrl}${path}`
}

export async function apiErrorFromResponse(response: Response): Promise<ApiError> {
  let body: ApiErrorBody | undefined
  try {
    body = (await response.json()) as ApiErrorBody
  } catch {
    body = undefined
  }
  const detail = body?.detail
  const message =
    typeof detail === 'object' && detail?.message
      ? detail.message
      : 'The request could not be completed.'
  const code = typeof detail === 'object' ? detail?.code : undefined
  return new ApiError(message, response.status, code)
}

export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  headers.set('Accept', 'application/json')
  if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json')

  const response = await fetch(apiUrl(path), { ...init, headers })
  const body = response.status === 204 ? undefined : ((await response.json()) as T & ApiErrorBody)

  if (!response.ok) {
    const detail = body?.detail
    const message =
      typeof detail === 'object' && detail?.message
        ? detail.message
        : 'The request could not be completed.'
    const code = typeof detail === 'object' ? detail?.code : undefined
    throw new ApiError(message, response.status, code)
  }

  return body as T
}
