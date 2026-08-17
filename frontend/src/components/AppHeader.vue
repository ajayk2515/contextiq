<script setup lang="ts">
import { useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()

async function signOut() {
  auth.logout()
  await router.replace({ name: 'login' })
}
</script>

<template>
  <header class="border-b border-line bg-white">
    <div
      class="mx-auto flex min-h-16 max-w-6xl flex-wrap items-center justify-between gap-x-6 px-5 sm:px-8"
    >
      <div class="flex h-16 items-center gap-3">
        <div class="grid size-9 place-items-center bg-ink text-sm font-bold text-white">EK</div>
        <div>
          <p class="text-sm font-semibold">EKIP</p>
          <p class="hidden text-xs text-muted sm:block">
            Enterprise Knowledge Intelligence Platform
          </p>
        </div>
      </div>

      <nav
        aria-label="Primary"
        class="order-3 flex h-11 w-full items-end gap-6 sm:order-2 sm:h-16 sm:w-auto"
      >
        <RouterLink class="nav-link" :to="{ name: 'foundation' }">Status</RouterLink>
        <RouterLink class="nav-link" :to="{ name: 'chat' }">Chat</RouterLink>
        <RouterLink class="nav-link" :to="{ name: 'documents' }">Documents</RouterLink>
      </nav>

      <div class="order-2 flex items-center gap-4 sm:order-3">
        <div class="hidden text-right md:block">
          <p class="text-xs font-medium">{{ auth.user?.email }}</p>
          <p class="text-xs text-muted">{{ auth.user?.role }}</p>
        </div>
        <button
          class="text-sm font-medium text-muted hover:text-ink"
          type="button"
          @click="signOut"
        >
          Sign out
        </button>
      </div>
    </div>
  </header>
</template>
