import { apiRequest } from './client'

export type UserRole = 'Developer' | 'HR' | 'Finance' | 'Executive'

export interface AuthUser {
  id: string
  email: string
  role: UserRole
}

export interface LoginCredentials {
  email: string
  password: string
}

export interface LoginResponse {
  access_token: string
  token_type: 'bearer'
  user: AuthUser
}

export function login(credentials: LoginCredentials): Promise<LoginResponse> {
  return apiRequest<LoginResponse>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify(credentials),
  })
}

export function fetchCurrentUser(token: string): Promise<AuthUser> {
  return apiRequest<AuthUser>('/api/auth/me', {
    headers: { Authorization: `Bearer ${token}` },
  })
}
