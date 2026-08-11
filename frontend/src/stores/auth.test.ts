import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  fetchCurrentUser,
  login as requestLogin,
  type AuthUser,
  type LoginResponse,
} from '@/api/auth'

import { useAuthStore } from './auth'

vi.mock('@/api/auth', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/auth')>()
  return { ...actual, fetchCurrentUser: vi.fn(), login: vi.fn() }
})

const user: AuthUser = {
  id: 'be43f811-482a-4bca-a062-04e6f91291ac',
  email: 'developer@demo.com',
  role: 'Developer',
}

const loginResponse: LoginResponse = {
  access_token: 'signed-token',
  token_type: 'bearer',
  user,
}

describe('auth store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    sessionStorage.clear()
    vi.clearAllMocks()
  })

  it('persists successful login state for a page refresh', async () => {
    vi.mocked(requestLogin).mockResolvedValue(loginResponse)
    const auth = useAuthStore()

    await auth.login({ email: user.email, password: 'demo-password' })

    expect(auth.isAuthenticated).toBe(true)
    expect(auth.user).toEqual(user)
    expect(JSON.parse(sessionStorage.getItem('ekip.auth') ?? '')).toEqual({
      token: 'signed-token',
      user,
    })
  })

  it('restores and revalidates a persisted session', async () => {
    sessionStorage.setItem('ekip.auth', JSON.stringify({ token: 'signed-token', user }))
    const refreshedUser = { ...user, role: 'HR' as const }
    vi.mocked(fetchCurrentUser).mockResolvedValue(refreshedUser)
    const auth = useAuthStore()

    await auth.initialize()

    expect(fetchCurrentUser).toHaveBeenCalledWith('signed-token')
    expect(auth.user).toEqual(refreshedUser)
    expect(auth.isAuthenticated).toBe(true)
  })

  it('clears authentication state on logout', async () => {
    vi.mocked(requestLogin).mockResolvedValue(loginResponse)
    const auth = useAuthStore()
    await auth.login({ email: user.email, password: 'demo-password' })

    auth.logout()

    expect(auth.isAuthenticated).toBe(false)
    expect(auth.token).toBeNull()
    expect(auth.user).toBeNull()
    expect(sessionStorage.getItem('ekip.auth')).toBeNull()
  })
})
