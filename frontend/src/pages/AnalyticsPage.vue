<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { fetchAnalyticsSummary, type AnalyticsSummaryResponse } from '@/api/analytics'
import { ApiError } from '@/api/client'
import type { OptimizationMetric } from '@/api/recommendations'
import {
  evaluationChartOption,
  latencyChartOption,
  strategyChartOption,
} from '@/analytics/chartOptions'
import AnalyticsChart from '@/components/AnalyticsChart.vue'
import AppHeader from '@/components/AppHeader.vue'
import { useAuthStore } from '@/stores/auth'
import { formatStrategyLabel } from '@/utils/labels'

const auth = useAuthStore()
const analytics = ref<AnalyticsSummaryResponse | null>(null)
const loading = ref(true)
const errorMessage = ref('')

const strategyOption = computed(() =>
  strategyChartOption(analytics.value?.strategy_distribution ?? []),
)
const evaluationOption = computed(() =>
  evaluationChartOption(analytics.value?.evaluation_history ?? []),
)
const latencyOption = computed(() => latencyChartOption(analytics.value?.latency_series ?? []))

function score(value: number | null | undefined) {
  return value == null ? 'N/A' : value.toFixed(3)
}

function latency(value: number | null | undefined) {
  return value == null ? 'N/A' : `${Math.round(value)} ms`
}

function metricLabel(metric: OptimizationMetric) {
  return {
    CONTEXT_RECALL: 'Context recall',
    CONTEXT_PRECISION: 'Context precision',
    RETRIEVAL_LATENCY_MS: 'Retrieval latency',
  }[metric]
}

function recommendationValue(metric: OptimizationMetric, value: number) {
  return metric === 'RETRIEVAL_LATENCY_MS' ? `${Math.round(value)} ms` : value.toFixed(3)
}

async function loadAnalytics() {
  if (!auth.token) return
  loading.value = true
  errorMessage.value = ''
  try {
    analytics.value = await fetchAnalyticsSummary(auth.token)
  } catch (error) {
    errorMessage.value =
      error instanceof ApiError ? error.message : 'Analytics are unavailable. Please try again.'
  } finally {
    loading.value = false
  }
}

onMounted(loadAnalytics)
</script>

<template>
  <div class="min-h-screen bg-surface text-ink">
    <AppHeader />

    <main class="mx-auto max-w-6xl px-5 py-8 sm:px-8 sm:py-10">
      <div class="flex flex-wrap items-end justify-between gap-4 border-b border-line pb-6">
        <div>
          <p class="text-xs font-semibold uppercase text-accent">System performance</p>
          <h1 class="mt-1 text-2xl font-semibold">Analytics</h1>
          <p class="mt-2 text-sm text-muted">
            Aggregate retrieval performance and evaluation quality. No raw user content is shown.
          </p>
        </div>
        <button
          class="h-10 border border-line bg-white px-4 text-sm font-semibold hover:border-accent disabled:opacity-45"
          type="button"
          :disabled="loading"
          @click="loadAnalytics"
        >
          {{ loading ? 'Refreshing...' : 'Refresh' }}
        </button>
      </div>

      <p
        v-if="errorMessage"
        class="mt-5 border border-error-line bg-error-bg px-4 py-3 text-sm text-error"
        role="alert"
      >
        {{ errorMessage }}
      </p>

      <div
        v-if="loading && !analytics"
        class="grid min-h-64 place-content-center text-sm text-muted"
      >
        Loading analytics...
      </div>

      <template v-else-if="analytics">
        <section aria-labelledby="metrics-heading" class="mt-7">
          <h2 id="metrics-heading" class="sr-only">Current metrics</h2>
          <dl class="grid gap-px border border-line bg-line sm:grid-cols-2 lg:grid-cols-3">
            <div class="bg-white p-4 sm:p-5">
              <dt class="text-xs font-medium text-muted">Total queries</dt>
              <dd class="mt-2 text-2xl font-semibold tabular-nums">
                {{ analytics.summary.total_queries }}
              </dd>
            </div>
            <div class="bg-white p-4 sm:p-5">
              <dt class="text-xs font-medium text-muted">Avg retrieval latency</dt>
              <dd class="mt-2 text-2xl font-semibold tabular-nums">
                {{ latency(analytics.summary.avg_retrieval_latency_ms) }}
              </dd>
            </div>
            <div class="bg-white p-4 sm:p-5">
              <dt class="text-xs font-medium text-muted">Faithfulness</dt>
              <dd class="mt-2 text-2xl font-semibold tabular-nums">
                {{ score(analytics.summary.faithfulness) }}
              </dd>
            </div>
            <div class="bg-white p-4 sm:p-5">
              <dt class="text-xs font-medium text-muted">Answer relevancy</dt>
              <dd class="mt-2 text-2xl font-semibold tabular-nums">
                {{ score(analytics.summary.answer_relevancy) }}
              </dd>
            </div>
            <div class="bg-white p-4 sm:p-5">
              <dt class="text-xs font-medium text-muted">Context precision</dt>
              <dd class="mt-2 text-2xl font-semibold tabular-nums">
                {{ score(analytics.summary.context_precision) }}
              </dd>
            </div>
            <div class="bg-white p-4 sm:p-5">
              <dt class="text-xs font-medium text-muted">Context recall</dt>
              <dd class="mt-2 text-2xl font-semibold tabular-nums">
                {{ score(analytics.summary.context_recall) }}
              </dd>
            </div>
          </dl>
          <p class="mt-2 text-xs text-muted">
            Quality cards reflect the most recent completed evaluation run.
          </p>
        </section>

        <div class="mt-9 grid gap-8 xl:grid-cols-2">
          <section aria-labelledby="strategy-heading">
            <h2 id="strategy-heading" class="text-base font-semibold">
              Retrieval strategy distribution
            </h2>
            <p v-if="!analytics.strategy_distribution.length" class="empty-state mt-4">
              No retrieval strategies have been recorded. Ask a question in Chat to create data.
            </p>
            <div v-else class="mt-4 border border-line bg-white p-3">
              <AnalyticsChart :option="strategyOption" label="Retrieval strategy distribution" />
            </div>
          </section>

          <section aria-labelledby="latency-heading">
            <h2 id="latency-heading" class="text-base font-semibold">
              Retrieval latency over time
            </h2>
            <p v-if="!analytics.latency_series.length" class="empty-state mt-4">
              No latency samples are available yet.
            </p>
            <div v-else class="mt-4 border border-line bg-white p-3">
              <AnalyticsChart :option="latencyOption" label="Retrieval latency over time" />
            </div>
          </section>
        </div>

        <section aria-labelledby="evaluation-heading" class="mt-9">
          <h2 id="evaluation-heading" class="text-base font-semibold">Evaluation metrics</h2>
          <p v-if="!analytics.evaluation_history.length" class="empty-state mt-4">
            No completed evaluations are available. Start a run from Evaluations.
          </p>
          <div v-else class="mt-4 border border-line bg-white p-3">
            <AnalyticsChart
              :option="evaluationOption"
              label="Evaluation quality metrics over time"
            />
          </div>
        </section>

        <section aria-labelledby="recommendations-heading" class="mt-9">
          <div class="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 id="recommendations-heading" class="text-base font-semibold">
                Open optimization recommendations
              </h2>
              <p class="mt-1 text-sm text-muted">Persisted guidance from completed evaluations.</p>
            </div>
            <RouterLink class="text-sm font-semibold text-accent hover:underline" to="/evaluations">
              View evaluation details
            </RouterLink>
          </div>
          <p v-if="!analytics.recommendations.length" class="empty-state mt-4">
            No open recommendations. Completed runs within thresholds require no action.
          </p>
          <div v-else class="mt-4 grid gap-4 lg:grid-cols-2">
            <article
              v-for="item in analytics.recommendations"
              :key="item.id"
              class="border border-line bg-white p-4 sm:p-5"
            >
              <div class="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h3 class="text-sm font-semibold">{{ metricLabel(item.metric) }}</h3>
                  <p class="mt-1 text-xs text-muted">
                    {{ item.profile ?? 'All profiles' }} &middot;
                    {{ item.strategy ? formatStrategyLabel(item.strategy) : 'Mixed strategy' }}
                  </p>
                </div>
                <span class="status-label status-pending">Open</span>
              </div>
              <dl class="mt-4 flex flex-wrap gap-7 border-t border-line pt-3">
                <div>
                  <dt class="text-xs text-muted">Current</dt>
                  <dd class="mt-1 text-sm font-semibold tabular-nums">
                    {{ recommendationValue(item.metric, item.current_value) }}
                  </dd>
                </div>
                <div>
                  <dt class="text-xs text-muted">Threshold</dt>
                  <dd class="mt-1 text-sm font-semibold tabular-nums">
                    {{ recommendationValue(item.metric, item.threshold) }}
                  </dd>
                </div>
              </dl>
              <p class="mt-4 text-sm leading-6">{{ item.recommendation }}</p>
            </article>
          </div>
        </section>
      </template>
    </main>
  </div>
</template>
