<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { ApiError } from '@/api/client'
import {
  fetchQueries,
  fetchQuery,
  fetchRetrieval,
  type QueryDetail,
  type QuerySummary,
  type RetrievalSnapshot,
} from '@/api/inspector'
import AppHeader from '@/components/AppHeader.vue'
import { useAuthStore } from '@/stores/auth'
import { formatIdentifierLabel, formatStrategyLabel } from '@/utils/labels'

const auth = useAuthStore()
const route = useRoute()
const queries = ref<QuerySummary[]>([])
const activeQueryId = ref<string | null>(null)
const detail = ref<QueryDetail | null>(null)
const retrieval = ref<RetrievalSnapshot[]>([])
const loadingList = ref(true)
const loadingDetail = ref(false)
const errorMessage = ref('')

function dateLabel(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(value))
}

function sourceLabel(item: RetrievalSnapshot) {
  const parts = [item.filename]
  if (item.page !== null) parts.push(`Page ${item.page}`)
  if (item.section) parts.push(item.section)
  return parts.join(' \u00b7 ')
}

function score(value: number) {
  return value.toFixed(4)
}

function candidateStatus(item: RetrievalSnapshot) {
  if (item.included_in_context) return 'Final context'
  if (
    detail.value?.retrieval_strategy === 'HYBRID_RRF_RERANK' &&
    item.rank_after !== null &&
    item.rank_after > 5
  ) {
    return 'Dropped after reranking'
  }
  return 'Not included in bounded context'
}

async function selectQuery(queryId: string) {
  if (!auth.token) return
  activeQueryId.value = queryId
  loadingDetail.value = true
  errorMessage.value = ''
  try {
    const [queryDetail, snapshots] = await Promise.all([
      fetchQuery(auth.token, queryId),
      fetchRetrieval(auth.token, queryId),
    ])
    detail.value = queryDetail
    retrieval.value = snapshots
  } catch (error) {
    detail.value = null
    retrieval.value = []
    errorMessage.value =
      error instanceof ApiError ? error.message : 'Retrieval details could not be loaded.'
  } finally {
    loadingDetail.value = false
  }
}

onMounted(async () => {
  if (!auth.token) return
  try {
    queries.value = await fetchQueries(auth.token)
    const requestedId =
      typeof route.query.query_id === 'string'
        ? route.query.query_id
        : typeof route.query.query === 'string'
          ? route.query.query
          : null
    const initial = queries.value.find((query) => query.id === requestedId) ?? queries.value[0]
    if (initial) await selectQuery(initial.id)
  } catch (error) {
    errorMessage.value =
      error instanceof ApiError ? error.message : 'Retrieval history could not be loaded.'
  } finally {
    loadingList.value = false
  }
})
</script>

<template>
  <div class="min-h-screen bg-surface text-ink">
    <AppHeader />

    <main class="mx-auto max-w-6xl px-5 py-7 sm:px-8">
      <div>
        <p class="text-xs font-semibold uppercase text-accent">Observable retrieval facts</p>
        <h1 class="mt-1 text-2xl font-semibold">Retrieval Inspector</h1>
      </div>

      <p
        v-if="errorMessage"
        class="mt-5 border border-error-line bg-error-bg px-4 py-3 text-sm text-error"
        role="alert"
      >
        {{ errorMessage }}
      </p>

      <div class="mt-6 grid min-h-[38rem] border border-line bg-white lg:grid-cols-[18rem_1fr]">
        <aside class="border-b border-line bg-surface lg:border-r lg:border-b-0">
          <h2 class="border-b border-line px-4 py-3 text-sm font-semibold">Recent queries</h2>
          <p v-if="loadingList" class="px-4 py-5 text-sm text-muted">Loading history...</p>
          <div v-else-if="!queries.length" class="px-4 py-6">
            <p class="text-sm font-medium">No retrieval history yet.</p>
            <p class="mt-2 text-sm leading-6 text-muted">
              Ask a question in Chat to inspect how retrieval works.
            </p>
          </div>
          <ul v-else class="max-h-72 overflow-y-auto py-2 lg:max-h-[42rem]">
            <li v-for="query in queries" :key="query.id" class="px-2">
              <button
                class="w-full border-l-2 px-3 py-3 text-left"
                :class="
                  activeQueryId === query.id
                    ? 'border-accent bg-white'
                    : 'border-transparent hover:bg-white'
                "
                type="button"
                @click="selectQuery(query.id)"
              >
                <span class="block truncate text-sm font-medium">{{ query.query_text }}</span>
                <span class="mt-1 block text-xs text-muted">{{ dateLabel(query.created_at) }}</span>
              </button>
            </li>
          </ul>
        </aside>

        <section class="min-w-0 p-5 sm:p-7">
          <p v-if="loadingDetail" class="text-sm text-muted">Loading retrieval details...</p>
          <div v-else-if="detail">
            <div class="border-b border-line pb-5">
              <p class="text-xs font-semibold uppercase text-muted">Query</p>
              <p class="mt-2 text-base font-semibold leading-7">{{ detail.query_text }}</p>
              <p class="mt-1 text-xs text-muted">{{ dateLabel(detail.created_at) }}</p>
            </div>

            <dl class="grid border-b border-line sm:grid-cols-2 xl:grid-cols-3">
              <div
                class="border-b border-line py-4 sm:border-r sm:px-4 sm:first:pl-0 xl:border-b-0"
              >
                <dt class="text-xs text-muted">Classification</dt>
                <dd class="mt-1 text-sm font-semibold">
                  {{ formatIdentifierLabel(detail.query_category) }}
                </dd>
              </div>
              <div class="border-b border-line py-4 sm:px-4 xl:border-r xl:border-b-0">
                <dt class="text-xs text-muted">Profile and strategy</dt>
                <dd class="mt-1 text-sm font-semibold">
                  {{ detail.retrieval_profile }} &middot;
                  {{ formatStrategyLabel(detail.retrieval_strategy) }}
                </dd>
              </div>
              <div
                class="border-b border-line py-4 sm:border-r sm:px-4 xl:border-r-0 xl:border-b-0"
              >
                <dt class="text-xs text-muted">Retrieval latency</dt>
                <dd class="mt-1 text-sm font-semibold">{{ detail.retrieval_latency_ms }} ms</dd>
              </div>
              <div class="border-b border-line py-4 sm:px-4 xl:border-r xl:pl-0">
                <dt class="text-xs text-muted">Candidates</dt>
                <dd class="mt-1 text-sm font-semibold">{{ detail.candidate_count }}</dd>
              </div>
              <div class="border-b border-line py-4 sm:border-r sm:px-4 xl:border-r xl:border-b-0">
                <dt class="text-xs text-muted">Final context</dt>
                <dd class="mt-1 text-sm font-semibold">{{ detail.final_context_count }}</dd>
              </div>
              <div class="py-4 sm:px-4">
                <dt class="text-xs text-muted">Classifier fallback</dt>
                <dd class="mt-1 text-sm font-semibold">
                  {{ detail.classifier_fallback ? 'Used' : 'Not used' }}
                </dd>
              </div>
            </dl>

            <div class="mt-7 flex items-center justify-between gap-4">
              <h2 class="text-base font-semibold">Retrieved chunks</h2>
              <p class="text-xs text-muted">
                {{ detail.candidate_count }} candidates &rarr;
                {{ detail.final_context_count }} final
              </p>
            </div>

            <p v-if="!retrieval.length" class="mt-4 text-sm text-muted">
              No retrieval candidates were accepted for this query.
            </p>
            <ol v-else class="mt-4 grid gap-4">
              <li v-for="item in retrieval" :key="item.id" class="border border-line p-4 sm:p-5">
                <div class="flex flex-wrap items-start justify-between gap-3">
                  <div class="min-w-0">
                    <p class="text-sm font-semibold">
                      #{{ item.rank_before ?? '?' }} {{ sourceLabel(item) }}
                    </p>
                    <p class="mt-2 text-sm leading-6 text-muted">{{ item.snippet }}</p>
                  </div>
                  <span
                    class="status-label"
                    :class="item.included_in_context ? 'status-ok' : 'status-pending'"
                  >
                    {{ candidateStatus(item) }}
                  </span>
                </div>

                <dl class="mt-4 flex flex-wrap gap-x-6 gap-y-3 border-t border-line pt-3">
                  <div v-if="item.rank_before !== null">
                    <dt class="text-xs text-muted">
                      {{ detail.reranked ? 'Pre-rerank rank' : 'Retrieved rank' }}
                    </dt>
                    <dd class="mt-1 text-sm font-semibold">{{ item.rank_before }}</dd>
                  </div>
                  <div v-if="item.retrieval_score !== null">
                    <dt class="text-xs text-muted">Dense score</dt>
                    <dd class="mt-1 text-sm font-semibold">{{ score(item.retrieval_score) }}</dd>
                  </div>
                  <div v-if="item.rrf_score !== null">
                    <dt class="text-xs text-muted">RRF score</dt>
                    <dd class="mt-1 text-sm font-semibold">{{ score(item.rrf_score) }}</dd>
                  </div>
                  <div v-if="item.reranker_score !== null">
                    <dt class="text-xs text-muted">Reranker score</dt>
                    <dd class="mt-1 text-sm font-semibold">{{ score(item.reranker_score) }}</dd>
                  </div>
                  <div v-if="item.rank_after !== null">
                    <dt class="text-xs text-muted">Post-rerank rank</dt>
                    <dd class="mt-1 text-sm font-semibold">{{ item.rank_after }}</dd>
                  </div>
                </dl>
              </li>
            </ol>
          </div>
          <div v-else-if="!queries.length" class="grid min-h-72 place-content-center text-center">
            <p class="text-sm font-medium">Run a query to inspect retrieval.</p>
          </div>
        </section>
      </div>
    </main>
  </div>
</template>
