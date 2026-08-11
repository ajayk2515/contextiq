<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { fetchHealth, type HealthResponse } from '@/api/health'

const health = ref<HealthResponse | null>(null)
const loading = ref(true)
const requestFailed = ref(false)
const controller = new AbortController()

const overallLabel = computed(() => {
  if (loading.value) return 'Checking services'
  if (requestFailed.value) return 'API unavailable'
  return health.value?.status === 'ok' ? 'All systems operational' : 'Service attention required'
})

async function loadHealth() {
  try {
    health.value = await fetchHealth(controller.signal)
  } catch {
    requestFailed.value = true
  } finally {
    loading.value = false
  }
}

onMounted(loadHealth)
onBeforeUnmount(() => controller.abort())
</script>

<template>
  <div class="min-h-screen bg-surface text-ink">
    <header class="border-b border-line bg-white">
      <div class="mx-auto flex h-16 max-w-6xl items-center justify-between px-5 sm:px-8">
        <div class="flex items-center gap-3">
          <div class="grid size-9 place-items-center bg-ink text-sm font-bold text-white">EK</div>
          <div>
            <p class="text-sm font-semibold">EKIP</p>
            <p class="text-xs text-muted">Enterprise Knowledge Intelligence Platform</p>
          </div>
        </div>
        <span class="border border-line bg-surface px-2.5 py-1 text-xs font-medium text-muted">
          Foundation
        </span>
      </div>
    </header>

    <main class="mx-auto max-w-6xl px-5 py-10 sm:px-8 sm:py-14">
      <section aria-labelledby="status-heading" class="max-w-3xl">
        <p class="mb-2 text-xs font-semibold uppercase text-accent">Local environment</p>
        <h1 id="status-heading" class="text-3xl font-semibold sm:text-4xl">System status</h1>
        <p class="mt-3 max-w-xl text-sm leading-6 text-muted">
          {{ overallLabel }}
        </p>

        <div class="mt-8 border border-line bg-white">
          <div
            class="grid min-h-16 grid-cols-[1fr_auto] items-center gap-4 border-b border-line px-5"
          >
            <div>
              <p class="text-sm font-medium">FastAPI</p>
              <p class="text-xs text-muted">Application API</p>
            </div>
            <span
              class="status-label"
              :class="requestFailed ? 'status-error' : loading ? 'status-pending' : 'status-ok'"
            >
              {{ requestFailed ? 'Unavailable' : loading ? 'Checking' : 'Connected' }}
            </span>
          </div>
          <div
            class="grid min-h-16 grid-cols-[1fr_auto] items-center gap-4 border-b border-line px-5"
          >
            <div>
              <p class="text-sm font-medium">PostgreSQL</p>
              <p class="text-xs text-muted">Application data</p>
            </div>
            <span
              class="status-label"
              :class="health?.services.database === 'ok' ? 'status-ok' : 'status-pending'"
            >
              {{
                health?.services.database === 'ok'
                  ? 'Connected'
                  : loading
                    ? 'Checking'
                    : 'Unavailable'
              }}
            </span>
          </div>
          <div class="grid min-h-16 grid-cols-[1fr_auto] items-center gap-4 px-5">
            <div>
              <p class="text-sm font-medium">Qdrant</p>
              <p class="text-xs text-muted">Vector database</p>
            </div>
            <span
              class="status-label"
              :class="health?.services.qdrant === 'ok' ? 'status-ok' : 'status-pending'"
            >
              {{
                health?.services.qdrant === 'ok'
                  ? 'Connected'
                  : loading
                    ? 'Checking'
                    : 'Unavailable'
              }}
            </span>
          </div>
        </div>
      </section>
    </main>
  </div>
</template>
