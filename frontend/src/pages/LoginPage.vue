<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { ApiError } from '@/api/client'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const email = ref('')
const password = ref('')
const errorMessage = ref('')
const submitting = ref(false)

async function submit() {
  errorMessage.value = ''
  submitting.value = true
  try {
    await auth.login({ email: email.value, password: password.value })
    const requestedRedirect = route.query.redirect
    const redirect =
      typeof requestedRedirect === 'string' &&
      requestedRedirect.startsWith('/') &&
      !requestedRedirect.startsWith('//')
        ? requestedRedirect
        : '/'
    await router.replace(redirect)
  } catch (error) {
    errorMessage.value =
      error instanceof ApiError ? error.message : 'Unable to sign in. Please try again.'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="min-h-screen bg-surface text-ink">
    <header class="border-b border-line bg-white">
      <div class="mx-auto flex h-16 max-w-6xl items-center px-5 sm:px-8">
        <div class="flex items-center gap-3">
          <div class="grid size-9 place-items-center bg-ink text-sm font-bold text-white">EK</div>
          <div>
            <p class="text-sm font-semibold">EKIP</p>
            <p class="text-xs text-muted">Enterprise Knowledge Intelligence Platform</p>
          </div>
        </div>
      </div>
    </header>

    <main class="mx-auto grid min-h-[calc(100vh-4rem)] max-w-6xl items-center px-5 py-10 sm:px-8">
      <section class="w-full max-w-md" aria-labelledby="login-heading">
        <p class="mb-2 text-xs font-semibold uppercase text-accent">Secure access</p>
        <h1 id="login-heading" class="text-3xl font-semibold">Sign in to EKIP</h1>
        <p class="mt-3 text-sm leading-6 text-muted">Use your assigned demo account.</p>

        <form class="mt-8 border border-line bg-white p-5 sm:p-6" @submit.prevent="submit">
          <div>
            <label for="email" class="block text-sm font-medium">Email</label>
            <input
              id="email"
              v-model="email"
              class="mt-2 h-11 w-full border border-line bg-white px-3 text-sm outline-none transition focus:border-accent focus:ring-2 focus:ring-accent/15"
              type="email"
              name="email"
              autocomplete="username"
              placeholder="developer@demo.com"
              required
            />
          </div>

          <div class="mt-5">
            <label for="password" class="block text-sm font-medium">Password</label>
            <input
              id="password"
              v-model="password"
              class="mt-2 h-11 w-full border border-line bg-white px-3 text-sm outline-none transition focus:border-accent focus:ring-2 focus:ring-accent/15"
              type="password"
              name="password"
              autocomplete="current-password"
              required
            />
          </div>

          <p
            v-if="errorMessage"
            class="mt-4 border border-[#e3b8aa] bg-[#fff4ef] px-3 py-2 text-sm text-[#9a3e24]"
            role="alert"
          >
            {{ errorMessage }}
          </p>

          <button
            class="mt-6 h-11 w-full bg-ink px-4 text-sm font-semibold text-white transition hover:bg-[#26343a] disabled:cursor-not-allowed disabled:opacity-60"
            type="submit"
            :disabled="submitting"
          >
            {{ submitting ? 'Signing in...' : 'Sign in' }}
          </button>
        </form>
      </section>
    </main>
  </div>
</template>
