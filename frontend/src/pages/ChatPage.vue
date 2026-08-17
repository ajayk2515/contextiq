<script setup lang="ts">
import { ref } from 'vue'

import { askQuestion, type ChatResponse, type ChatSource } from '@/api/chat'
import { ApiError } from '@/api/client'
import AppHeader from '@/components/AppHeader.vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const message = ref('')
const submittedQuestion = ref('')
const response = ref<ChatResponse | null>(null)
const loading = ref(false)
const errorMessage = ref('')

function sourceLabel(source: ChatSource) {
  const parts = [source.filename]
  if (source.page !== null) parts.push(`Page ${source.page}`)
  if (source.section) parts.push(source.section)
  return parts.join(' \u00b7 ')
}

async function submitQuestion() {
  const question = message.value.trim()
  if (!auth.token || !question || loading.value) return

  loading.value = true
  errorMessage.value = ''
  response.value = null
  submittedQuestion.value = question
  try {
    response.value = await askQuestion(auth.token, question)
  } catch (error) {
    errorMessage.value =
      error instanceof ApiError ? error.message : 'The question could not be answered.'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="min-h-screen bg-surface text-ink">
    <AppHeader />

    <main class="mx-auto max-w-5xl px-5 py-8 sm:px-8 sm:py-10">
      <div>
        <p class="mb-1 text-xs font-semibold uppercase text-accent">Authorized knowledge</p>
        <h1 class="text-3xl font-semibold">Chat</h1>
        <p class="mt-2 max-w-2xl text-sm leading-6 text-muted">
          Ask a question about documents available to your {{ auth.user?.role }} account.
        </p>
      </div>

      <form class="mt-7 border border-line bg-white p-5 sm:p-6" @submit.prevent="submitQuestion">
        <label class="field-label" for="chat-message">Question</label>
        <textarea
          id="chat-message"
          v-model="message"
          class="min-h-28 w-full resize-y border border-line bg-white px-3 py-2.5 text-sm leading-6 outline-none focus:border-accent"
          maxlength="2000"
          placeholder="What does the policy say about annual leave?"
          required
        />
        <div class="mt-3 flex items-center justify-between gap-4">
          <span class="text-xs text-muted">{{ message.length }} / 2000</span>
          <button
            class="primary-button h-10 min-w-28"
            type="submit"
            :disabled="loading || !message.trim()"
          >
            {{ loading ? 'Answering...' : 'Ask' }}
          </button>
        </div>
      </form>

      <p
        v-if="errorMessage"
        class="mt-5 border border-error-line bg-error-bg px-4 py-3 text-sm text-error"
        role="alert"
      >
        {{ errorMessage }}
      </p>

      <section v-if="loading" class="mt-8 border-t border-line pt-8" aria-live="polite">
        <p class="text-sm font-medium">Searching authorized documents</p>
        <p class="mt-1 text-sm text-muted">Building a grounded answer...</p>
      </section>

      <section v-else-if="response" class="mt-8" aria-live="polite">
        <p class="text-xs font-semibold uppercase text-muted">Your question</p>
        <p class="mt-2 text-sm font-medium leading-6">{{ submittedQuestion }}</p>

        <div class="mt-6 border-t border-line pt-6">
          <div class="flex items-center justify-between gap-4">
            <h2 class="text-base font-semibold">Answer</h2>
            <span v-if="response.insufficient_context" class="status-label status-pending">
              Insufficient context
            </span>
          </div>
          <p class="mt-3 whitespace-pre-wrap text-sm leading-7">{{ response.answer }}</p>
        </div>

        <div v-if="response.sources.length" class="mt-8 border-t border-line pt-6">
          <h2 class="text-base font-semibold">Sources</h2>
          <ol class="mt-4 grid gap-3">
            <li
              v-for="(source, index) in response.sources"
              :key="source.chunk_id"
              class="border border-line bg-white p-4"
            >
              <p class="text-sm font-semibold">[{{ index + 1 }}] {{ sourceLabel(source) }}</p>
              <p class="mt-2 text-sm leading-6 text-muted">{{ source.snippet }}</p>
            </li>
          </ol>
        </div>
      </section>

      <section v-else-if="!errorMessage" class="mt-8 border-t border-line pt-8">
        <p class="text-sm font-medium">No question submitted</p>
        <p class="mt-1 text-sm text-muted">Your current answer and its sources will appear here.</p>
      </section>
    </main>
  </div>
</template>
