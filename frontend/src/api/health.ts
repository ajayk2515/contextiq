export interface ServiceHealth {
  database: 'ok' | 'unavailable'
  qdrant: 'ok' | 'unavailable'
}

export interface HealthResponse {
  status: 'ok' | 'degraded'
  services: ServiceHealth
}

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')

export async function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const request: RequestInit = {
    headers: { Accept: 'application/json' },
  }
  if (signal) request.signal = signal

  const response = await fetch(`${apiBaseUrl}/health`, request)

  const data = (await response.json()) as HealthResponse
  if (!response.ok && response.status !== 503) {
    throw new Error('Unable to reach the EKIP API')
  }
  return data
}
