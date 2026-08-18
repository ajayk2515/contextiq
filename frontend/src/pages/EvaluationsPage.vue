<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { ApiError } from '@/api/client'
import {
  fetchEvaluation,
  fetchEvaluationRuns,
  startEvaluation,
  type EvaluationRunDetail,
  type EvaluationRunSummary,
} from '@/api/evaluations'
import {
  dismissRecommendation,
  fetchRecommendations,
  type OptimizationMetric,
  type OptimizationRecommendation,
} from '@/api/recommendations'
import AppHeader from '@/components/AppHeader.vue'
import { useAuthStore } from '@/stores/auth'

const REPRESENTATIVE_CASES = [
  'faq-annual-leave',
  'specific-deployment-freeze',
  'compare-expansion-sequence',
  'restricted-retention-bonus',
  'summary-strategy',
]

const auth = useAuthStore()
const runs = ref<EvaluationRunSummary[]>([])
const selected = ref<EvaluationRunDetail | null>(null)
const recommendations = ref<OptimizationRecommendation[]>([])
const scope = ref<'all' | 'representative'>('representative')
const loading = ref(true)
const starting = ref(false)
const error = ref('')
const recommendationsLoading = ref(false)
const recommendationsError = ref('')
const dismissingId = ref<string | null>(null)
let pollTimer: ReturnType<typeof window.setTimeout> | undefined

const progress = computed(() => {
  if (!selected.value?.total_cases) return 0
  return Math.round((selected.value.completed_cases / selected.value.total_cases) * 100)
})

function message(errorValue: unknown) {
  return errorValue instanceof ApiError ? errorValue.message : 'Evaluation data is unavailable.'
}

function score(value: number | null) {
  return value === null ? 'N/A' : value.toFixed(3)
}

function metricLabel(metric: OptimizationMetric) {
  return {
    CONTEXT_RECALL: 'Context recall',
    CONTEXT_PRECISION: 'Context precision',
    RETRIEVAL_LATENCY_MS: 'Retrieval latency',
  }[metric]
}

function optimizationValue(metric: OptimizationMetric, value: number) {
  return metric === 'RETRIEVAL_LATENCY_MS' ? `${Math.round(value)} ms` : value.toFixed(3)
}

function date(value: string) {
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(
    new Date(value),
  )
}

function schedulePoll() {
  if (selected.value?.status !== 'RUNNING') return
  pollTimer = window.setTimeout(async () => {
    await loadRun(selected.value!.id)
    await loadRuns()
    schedulePoll()
  }, 2000)
}

async function loadRun(runId: string) {
  if (!auth.token) return
  recommendations.value = []
  recommendationsError.value = ''
  try {
    selected.value = await fetchEvaluation(auth.token, runId)
    error.value = ''
    if (selected.value.status === 'COMPLETED') await loadRecommendations(runId)
  } catch (errorValue) {
    error.value = message(errorValue)
  }
}

async function loadRecommendations(runId: string) {
  if (!auth.token) return
  recommendationsLoading.value = true
  try {
    recommendations.value = await fetchRecommendations(auth.token, runId)
    recommendationsError.value = ''
  } catch (errorValue) {
    recommendationsError.value =
      errorValue instanceof ApiError
        ? errorValue.message
        : 'Optimization recommendations are unavailable.'
  } finally {
    recommendationsLoading.value = false
  }
}

async function dismiss(item: OptimizationRecommendation) {
  if (!auth.token) return
  dismissingId.value = item.id
  try {
    await dismissRecommendation(auth.token, item.id)
    recommendations.value = recommendations.value.filter(
      (recommendation) => recommendation.id !== item.id,
    )
    recommendationsError.value = ''
  } catch (errorValue) {
    recommendationsError.value =
      errorValue instanceof ApiError ? errorValue.message : 'The recommendation was not dismissed.'
  } finally {
    dismissingId.value = null
  }
}

async function loadRuns() {
  if (!auth.token) return
  try {
    runs.value = await fetchEvaluationRuns(auth.token)
    error.value = ''
  } catch (errorValue) {
    error.value = message(errorValue)
  }
}

async function selectRun(runId: string) {
  if (pollTimer) window.clearTimeout(pollTimer)
  await loadRun(runId)
  schedulePoll()
}

async function runEvaluation() {
  if (!auth.token) return
  starting.value = true
  error.value = ''
  try {
    const created = await startEvaluation(
      auth.token,
      scope.value === 'representative' ? REPRESENTATIVE_CASES : null,
    )
    await loadRuns()
    await selectRun(created.id)
  } catch (errorValue) {
    error.value = message(errorValue)
  } finally {
    starting.value = false
  }
}

onMounted(async () => {
  await loadRuns()
  const firstRun = runs.value[0]
  if (firstRun) await selectRun(firstRun.id)
  loading.value = false
})

onBeforeUnmount(() => {
  if (pollTimer) window.clearTimeout(pollTimer)
})
</script>

<template>
  <div class="min-h-screen bg-surface text-ink">
    <AppHeader />
    <main class="mx-auto max-w-6xl px-5 py-8 sm:px-8">
      <div class="flex flex-wrap items-end justify-between gap-4 border-b border-line pb-6">
        <div>
          <h1 class="text-2xl font-semibold">RAG evaluation</h1>
          <p class="mt-1 text-sm text-muted">Dataset version 1 · 23 synthetic cases</p>
        </div>
        <div class="flex items-end gap-3">
          <label>
            <span class="field-label">Run scope</span>
            <select v-model="scope" class="h-10 border border-line bg-white px-3 text-sm">
              <option value="representative">Representative 5</option>
              <option value="all">All 23 cases</option>
            </select>
          </label>
          <button
            class="primary-button h-10"
            type="button"
            :disabled="starting"
            @click="runEvaluation"
          >
            {{ starting ? 'Starting…' : 'Run evaluation' }}
          </button>
        </div>
      </div>

      <p
        v-if="error"
        class="mt-5 border border-error-line bg-error-bg p-3 text-sm text-error"
        role="alert"
      >
        {{ error }}
      </p>

      <div class="mt-6 grid gap-6 lg:grid-cols-[17rem_minmax(0,1fr)]">
        <aside class="border-r border-line pr-5">
          <h2 class="text-sm font-semibold">Recent runs</h2>
          <p v-if="loading" class="mt-4 text-sm text-muted">Loading runs…</p>
          <p v-else-if="!runs.length" class="mt-4 text-sm text-muted">No evaluations yet.</p>
          <ul v-else class="mt-3 space-y-2">
            <li v-for="run in runs" :key="run.id">
              <button
                class="w-full border border-line bg-white p-3 text-left hover:border-accent"
                :class="selected?.id === run.id ? 'border-accent' : ''"
                type="button"
                @click="selectRun(run.id)"
              >
                <span class="flex items-center justify-between gap-2">
                  <span class="text-sm font-semibold">{{ date(run.created_at) }}</span>
                  <span class="text-xs text-muted">{{ run.status }}</span>
                </span>
                <span class="mt-2 block text-xs text-muted">
                  {{ run.completed_cases }} / {{ run.total_cases }} cases
                </span>
              </button>
            </li>
          </ul>
        </aside>

        <section v-if="selected" aria-live="polite">
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 class="text-lg font-semibold">Run {{ selected.id.slice(0, 8) }}</h2>
              <p class="mt-1 text-sm text-muted">
                {{ selected.status }} · {{ selected.completed_cases }} /
                {{ selected.total_cases }} cases
              </p>
            </div>
            <span
              class="status-label"
              :class="
                selected.status === 'FAILED'
                  ? 'status-error'
                  : selected.status === 'COMPLETED'
                    ? 'status-ok'
                    : 'status-pending'
              "
            >
              {{ progress }}%
            </span>
          </div>

          <div class="mt-5 grid grid-cols-2 gap-px border border-line bg-line sm:grid-cols-4">
            <div
              v-for="metric in [
                ['Faithfulness', selected.averages.faithfulness],
                ['Answer relevancy', selected.averages.answer_relevancy],
                ['Context precision', selected.averages.context_precision],
                ['Context recall', selected.averages.context_recall],
              ]"
              :key="String(metric[0])"
              class="bg-white p-4"
            >
              <p class="text-xs text-muted">{{ metric[0] }}</p>
              <p class="mt-2 text-xl font-semibold">{{ score(metric[1] as number | null) }}</p>
            </div>
          </div>

          <p v-if="selected.error_message" class="mt-5 text-sm text-error">
            {{ selected.error_message }}
          </p>

          <section v-if="selected.status === 'COMPLETED'" class="mt-8 border-t border-line pt-6">
            <h2 class="text-base font-semibold">Optimization recommendations</h2>
            <p v-if="recommendationsLoading" class="mt-4 text-sm text-muted">
              Loading recommendations...
            </p>
            <p
              v-else-if="recommendationsError"
              class="mt-4 border border-error-line bg-error-bg p-3 text-sm text-error"
              role="alert"
            >
              {{ recommendationsError }}
            </p>
            <p
              v-else-if="!recommendations.length"
              class="mt-4 border border-line bg-white p-4 text-sm text-muted"
            >
              No optimization recommendations were generated for this run.
            </p>
            <div v-else class="mt-4 space-y-3">
              <article
                v-for="item in recommendations"
                :key="item.id"
                class="border border-line bg-white p-4"
              >
                <div class="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p class="text-sm font-semibold">{{ metricLabel(item.metric) }}</p>
                    <p class="mt-1 text-xs text-muted">
                      {{ item.profile ?? 'All profiles' }} · {{ item.strategy ?? 'Mixed strategy' }}
                    </p>
                  </div>
                  <div class="flex items-center gap-3">
                    <span class="status-label status-pending">{{ item.status }}</span>
                    <button
                      class="text-xs font-semibold text-muted hover:text-ink"
                      type="button"
                      :disabled="dismissingId === item.id"
                      @click="dismiss(item)"
                    >
                      {{ dismissingId === item.id ? 'Dismissing...' : 'Dismiss' }}
                    </button>
                  </div>
                </div>
                <dl class="mt-4 flex flex-wrap gap-6 border-t border-line pt-3">
                  <div>
                    <dt class="text-xs text-muted">Current</dt>
                    <dd class="mt-1 text-sm font-semibold">
                      {{ optimizationValue(item.metric, item.current_value) }}
                    </dd>
                  </div>
                  <div>
                    <dt class="text-xs text-muted">Threshold</dt>
                    <dd class="mt-1 text-sm font-semibold">
                      {{ optimizationValue(item.metric, item.threshold) }}
                    </dd>
                  </div>
                </dl>
                <p class="mt-4 text-sm leading-6">{{ item.recommendation }}</p>
              </article>
            </div>
          </section>

          <div class="mt-6 space-y-3">
            <article
              v-for="item in selected.evaluations"
              :key="item.id"
              class="border border-line bg-white p-4"
            >
              <div class="flex flex-wrap items-start justify-between gap-3">
                <div class="min-w-0">
                  <p class="text-xs font-semibold text-muted">
                    {{ item.evaluation_case_id }} · {{ item.role }}
                  </p>
                  <h3 class="mt-1 text-sm font-semibold">{{ item.question }}</h3>
                </div>
                <RouterLink
                  v-if="item.query_id"
                  class="text-xs font-semibold text-accent"
                  :to="{ name: 'inspector', query: { query_id: item.query_id } }"
                >
                  Inspect retrieval
                </RouterLink>
              </div>
              <p class="mt-3 text-sm leading-6 text-muted">
                {{ item.generated_answer ?? 'No answer generated.' }}
              </p>
              <dl class="mt-4 grid grid-cols-2 gap-3 border-t border-line pt-3 sm:grid-cols-4">
                <div>
                  <dt class="text-xs text-muted">Faithfulness</dt>
                  <dd class="text-sm font-semibold">{{ score(item.faithfulness) }}</dd>
                </div>
                <div>
                  <dt class="text-xs text-muted">Answer relevancy</dt>
                  <dd class="text-sm font-semibold">{{ score(item.answer_relevancy) }}</dd>
                </div>
                <div>
                  <dt class="text-xs text-muted">Context precision</dt>
                  <dd class="text-sm font-semibold">{{ score(item.context_precision) }}</dd>
                </div>
                <div>
                  <dt class="text-xs text-muted">Context recall</dt>
                  <dd class="text-sm font-semibold">{{ score(item.context_recall) }}</dd>
                </div>
              </dl>
              <p v-if="item.error_message" class="mt-3 text-xs text-error">
                {{ item.failure_category }}: {{ item.error_message }}
              </p>
            </article>
          </div>
        </section>
        <section v-else class="grid min-h-72 place-content-center text-sm text-muted">
          Select or start an evaluation run.
        </section>
      </div>
    </main>
  </div>
</template>
