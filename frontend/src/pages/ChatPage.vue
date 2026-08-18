<script setup lang="ts">
import { nextTick, onMounted, ref } from 'vue'

import { streamQuestion, type QueryIntelligenceMetadata } from '@/api/chat'
import { ApiError } from '@/api/client'
import {
  createConversation,
  deleteConversation,
  fetchConversation,
  fetchConversations,
  type ConversationMessage,
  type ConversationSummary,
} from '@/api/conversations'
import AppHeader from '@/components/AppHeader.vue'
import { useAuthStore } from '@/stores/auth'
import { formatIdentifierLabel, formatStrategyLabel } from '@/utils/labels'

interface DisplayMessage extends ConversationMessage {
  query_intelligence?: QueryIntelligenceMetadata | null
  streaming?: boolean
}

const auth = useAuthStore()
const conversations = ref<ConversationSummary[]>([])
const activeConversationId = ref<string | null>(null)
const messages = ref<DisplayMessage[]>([])
const draft = ref('')
const loadingList = ref(true)
const loadingConversation = ref(false)
const streaming = ref(false)
const errorMessage = ref('')
const messageRegion = ref<HTMLElement | null>(null)

function sourceLabel(message: DisplayMessage, index: number) {
  const source = message.sources[index]
  if (!source) return ''
  const parts = [source.filename]
  if (source.page !== null) parts.push(`Page ${source.page}`)
  if (source.section) parts.push(source.section)
  return parts.join(' \u00b7 ')
}

function relativeUpdated(value: string) {
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric' }).format(
    new Date(value),
  )
}

async function scrollToNewest() {
  await nextTick()
  const region = messageRegion.value
  if (!region) return
  if (typeof region.scrollTo === 'function') {
    region.scrollTo({ top: region.scrollHeight, behavior: 'smooth' })
  } else {
    region.scrollTop = region.scrollHeight
  }
}

async function refreshConversations() {
  if (!auth.token) return
  conversations.value = await fetchConversations(auth.token)
}

async function openConversation(id: string) {
  if (!auth.token || streaming.value) return
  activeConversationId.value = id
  loadingConversation.value = true
  errorMessage.value = ''
  try {
    const conversation = await fetchConversation(auth.token, id)
    messages.value = conversation.messages
    await scrollToNewest()
  } catch (error) {
    messages.value = []
    errorMessage.value =
      error instanceof ApiError ? error.message : 'The conversation could not be loaded.'
  } finally {
    loadingConversation.value = false
  }
}

async function startNewConversation() {
  if (!auth.token || streaming.value) return
  errorMessage.value = ''
  try {
    const conversation = await createConversation(auth.token)
    conversations.value = [conversation, ...conversations.value]
    activeConversationId.value = conversation.id
    messages.value = []
    draft.value = ''
  } catch (error) {
    errorMessage.value =
      error instanceof ApiError ? error.message : 'A new conversation could not be created.'
  }
}

async function removeConversation(id: string) {
  if (!auth.token || streaming.value) return
  if (!window.confirm('Delete this conversation and its messages?')) return
  try {
    await deleteConversation(auth.token, id)
    conversations.value = conversations.value.filter((conversation) => conversation.id !== id)
    if (activeConversationId.value === id) {
      activeConversationId.value = null
      messages.value = []
      const nextConversation = conversations.value[0]
      if (nextConversation) await openConversation(nextConversation.id)
    }
  } catch (error) {
    errorMessage.value =
      error instanceof ApiError ? error.message : 'The conversation could not be deleted.'
  }
}

async function submitMessage() {
  const question = draft.value.trim()
  if (!auth.token || !question || streaming.value) return

  if (!activeConversationId.value) {
    await startNewConversation()
  }
  const conversationId = activeConversationId.value
  if (!conversationId) return

  const now = new Date().toISOString()
  const userMessage: DisplayMessage = {
    id: `pending-user-${Date.now()}`,
    role: 'USER',
    content: question,
    query_id: null,
    sources: [],
    insufficient_context: false,
    created_at: now,
  }
  const assistantMessage: DisplayMessage = {
    id: `pending-assistant-${Date.now()}`,
    role: 'ASSISTANT',
    content: '',
    query_id: null,
    sources: [],
    insufficient_context: false,
    created_at: now,
    streaming: true,
  }
  messages.value.push(userMessage, assistantMessage)
  draft.value = ''
  errorMessage.value = ''
  streaming.value = true
  await scrollToNewest()

  try {
    await streamQuestion(auth.token, conversationId, question, {
      onMetadata(metadata) {
        assistantMessage.query_intelligence = metadata
        assistantMessage.query_id = metadata.query_id
      },
      onToken(text) {
        assistantMessage.content += text
        void scrollToNewest()
      },
      onCitations(sources) {
        assistantMessage.sources = sources
      },
      onComplete(complete) {
        assistantMessage.id = complete.assistant_message_id
        assistantMessage.query_id = complete.query_id
        assistantMessage.insufficient_context = complete.insufficient_context
        assistantMessage.streaming = false
      },
    })
  } catch (error) {
    const streamError =
      error instanceof ApiError ? error.message : 'The response stream could not be completed.'
    streaming.value = false
    await openConversation(conversationId)
    await refreshConversations().catch(() => undefined)
    errorMessage.value = streamError
    return
  } finally {
    streaming.value = false
  }

  try {
    await refreshConversations()
  } catch {
    errorMessage.value = 'The answer was saved, but recent conversations could not be refreshed.'
  }
}

onMounted(async () => {
  try {
    await refreshConversations()
    const mostRecent = conversations.value[0]
    if (mostRecent) await openConversation(mostRecent.id)
  } catch (error) {
    errorMessage.value =
      error instanceof ApiError ? error.message : 'Recent conversations could not be loaded.'
  } finally {
    loadingList.value = false
  }
})
</script>

<template>
  <div class="min-h-screen bg-surface text-ink">
    <AppHeader />

    <main
      class="mx-auto grid min-h-[calc(100vh-7rem)] max-w-6xl border-x border-line bg-white lg:grid-cols-[16rem_minmax(0,1fr)]"
    >
      <aside class="border-b border-line bg-surface lg:border-r lg:border-b-0">
        <div class="flex items-center justify-between border-b border-line px-4 py-4">
          <h1 class="text-sm font-semibold">Conversations</h1>
          <button
            class="text-sm font-semibold text-accent disabled:opacity-45"
            type="button"
            :disabled="streaming"
            @click="startNewConversation"
          >
            + New Chat
          </button>
        </div>

        <p v-if="loadingList" class="px-4 py-5 text-sm text-muted">Loading recent chats...</p>
        <p v-else-if="!conversations.length" class="px-4 py-5 text-sm text-muted">
          No conversations yet.
        </p>
        <ul v-else class="max-h-48 overflow-y-auto py-2 lg:max-h-[calc(100vh-11rem)]">
          <li v-for="conversation in conversations" :key="conversation.id" class="group px-2">
            <div
              class="flex items-center border-l-2"
              :class="
                activeConversationId === conversation.id
                  ? 'border-accent bg-white'
                  : 'border-transparent'
              "
            >
              <button
                class="min-w-0 flex-1 px-3 py-3 text-left disabled:cursor-not-allowed"
                type="button"
                :disabled="streaming"
                @click="openConversation(conversation.id)"
              >
                <span class="block truncate text-sm font-medium">{{ conversation.title }}</span>
                <span class="mt-1 block text-xs text-muted">
                  {{ relativeUpdated(conversation.updated_at) }}
                </span>
              </button>
              <button
                class="px-2 py-3 text-xs text-muted hover:text-error disabled:opacity-45"
                type="button"
                :aria-label="`Delete ${conversation.title}`"
                :disabled="streaming"
                @click="removeConversation(conversation.id)"
              >
                Delete
              </button>
            </div>
          </li>
        </ul>
      </aside>

      <section class="flex min-h-[36rem] min-w-0 flex-col">
        <div class="border-b border-line px-5 py-4 sm:px-7">
          <p class="text-xs font-semibold uppercase text-accent">Authorized knowledge</p>
          <p class="mt-1 text-sm text-muted">
            Asking as {{ auth.user?.role }}. Answers remain grounded in authorized documents.
          </p>
        </div>

        <p
          v-if="errorMessage"
          class="mx-5 mt-4 border border-error-line bg-error-bg px-4 py-3 text-sm text-error sm:mx-7"
          role="alert"
        >
          {{ errorMessage }}
        </p>

        <div ref="messageRegion" class="min-h-0 flex-1 overflow-y-auto px-5 py-6 sm:px-7">
          <p v-if="loadingConversation" class="text-sm text-muted">Loading messages...</p>
          <div
            v-else-if="!activeConversationId || !messages.length"
            class="grid min-h-64 place-content-center text-center"
          >
            <p class="text-base font-semibold">Start a conversation</p>
            <p class="mt-2 max-w-sm text-sm leading-6 text-muted">
              Ask about documents available to your account. Sources will remain attached to each
              answer.
            </p>
          </div>

          <ol v-else class="space-y-7" aria-live="polite">
            <li v-for="message in messages" :key="message.id">
              <p class="text-xs font-semibold uppercase text-muted">
                {{ message.role === 'USER' ? 'You' : 'EKIP' }}
              </p>
              <div v-if="message.role === 'ASSISTANT'" class="mt-2 border-l-2 border-accent pl-4">
                <p v-if="message.streaming && !message.content" class="text-sm text-muted">
                  Searching authorized documents...
                </p>
                <p class="whitespace-pre-wrap text-sm leading-7">{{ message.content }}</p>
                <p
                  v-if="message.query_intelligence"
                  class="mt-2 text-xs text-muted"
                  aria-label="Query routing"
                >
                  {{ formatIdentifierLabel(message.query_intelligence.category) }}
                  &middot; {{ message.query_intelligence.profile }} &middot;
                  {{ formatStrategyLabel(message.query_intelligence.executed_strategy) }} &middot;
                  Top
                  {{ message.query_intelligence.candidate_top_k }}
                </p>
                <RouterLink
                  v-if="message.query_id"
                  class="mt-2 inline-flex text-xs font-semibold text-accent hover:underline"
                  :to="{ name: 'inspector', query: { query_id: message.query_id } }"
                >
                  Inspect retrieval
                </RouterLink>
                <span v-if="message.insufficient_context" class="status-label status-pending mt-3">
                  Insufficient context
                </span>

                <div v-if="message.sources.length" class="mt-5 border-t border-line pt-4">
                  <p class="text-xs font-semibold uppercase text-muted">Sources</p>
                  <ol class="mt-3 grid gap-2">
                    <li
                      v-for="(_, index) in message.sources"
                      :key="message.sources[index]?.chunk_id"
                      class="border border-line bg-surface p-3"
                    >
                      <p class="text-xs font-semibold">
                        [{{ index + 1 }}] {{ sourceLabel(message, index) }}
                      </p>
                      <p class="mt-1 text-xs leading-5 text-muted">
                        {{ message.sources[index]?.snippet }}
                      </p>
                    </li>
                  </ol>
                </div>
              </div>
              <p v-else class="mt-2 whitespace-pre-wrap text-sm font-medium leading-7">
                {{ message.content }}
              </p>
            </li>
          </ol>
        </div>

        <form class="border-t border-line bg-surface p-4 sm:px-7" @submit.prevent="submitMessage">
          <label class="sr-only" for="chat-message">Ask a question</label>
          <div class="flex items-end gap-3">
            <textarea
              id="chat-message"
              v-model="draft"
              class="max-h-40 min-h-12 flex-1 resize-y border border-line bg-white px-3 py-2.5 text-sm leading-6 outline-none focus:border-accent"
              maxlength="2000"
              placeholder="Ask something about your documents..."
              :disabled="streaming"
              required
            />
            <button
              class="primary-button h-12 min-w-20"
              type="submit"
              :disabled="streaming || !draft.trim()"
            >
              {{ streaming ? 'Sending...' : 'Send' }}
            </button>
          </div>
          <p class="mt-2 text-xs text-muted">{{ draft.length }} / 2000</p>
        </form>
      </section>
    </main>
  </div>
</template>
