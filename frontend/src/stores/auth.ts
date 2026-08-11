import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import {
  fetchCurrentUser,
  login as requestLogin,
  type AuthUser,
  type LoginCredentials,
  type UserRole,
} from '@/api/auth'

const STORAGE_KEY = 'ekip.auth'
const USER_ROLES: UserRole[] = ['Developer', 'HR', 'Finance', 'Executive']

interface PersistedAuth {
  token: string
  user: AuthUser
}

function isAuthUser(value: unknown): value is AuthUser {
  if (!value || typeof value !== 'object') return false
  const user = value as Partial<AuthUser>
  return (
    typeof user.id === 'string' &&
    typeof user.email === 'string' &&
    USER_ROLES.includes(user.role as UserRole)
  )
}

function readPersistedAuth(): PersistedAuth | null {
  const stored = sessionStorage.getItem(STORAGE_KEY)
  if (!stored) return null

  try {
    const value = JSON.parse(stored) as Partial<PersistedAuth>
    if (typeof value.token === 'string' && isAuthUser(value.user)) {
      return { token: value.token, user: value.user }
    }
  } catch {
    // Invalid browser state is cleared below.
  }

  sessionStorage.removeItem(STORAGE_KEY)
  return null
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(null)
  const user = ref<AuthUser | null>(null)
  const initialized = ref(false)
  const isAuthenticated = computed(() => Boolean(token.value && user.value))
  let initialization: Promise<void> | null = null

  function persist() {
    if (token.value && user.value) {
      sessionStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({ token: token.value, user: user.value } satisfies PersistedAuth),
      )
    }
  }

  function logout() {
    token.value = null
    user.value = null
    sessionStorage.removeItem(STORAGE_KEY)
  }

  async function login(credentials: LoginCredentials) {
    const response = await requestLogin(credentials)
    token.value = response.access_token
    user.value = response.user
    persist()
  }

  async function restoreSession() {
    const persisted = readPersistedAuth()
    if (!persisted) {
      initialized.value = true
      return
    }

    token.value = persisted.token
    user.value = persisted.user
    try {
      user.value = await fetchCurrentUser(persisted.token)
      persist()
    } catch {
      logout()
    } finally {
      initialized.value = true
    }
  }

  async function initialize() {
    if (initialized.value) return
    initialization ??= restoreSession()
    await initialization
  }

  return { token, user, initialized, isAuthenticated, initialize, login, logout }
})
