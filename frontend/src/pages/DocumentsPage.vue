<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import {
  deleteDocument,
  fetchDocuments,
  uploadDocument,
  type DocumentRecord,
} from '@/api/documents'
import type { UserRole } from '@/api/auth'
import { ApiError } from '@/api/client'
import AppHeader from '@/components/AppHeader.vue'
import { useAuthStore } from '@/stores/auth'

const roles: UserRole[] = ['Developer', 'HR', 'Finance', 'Executive']
const auth = useAuthStore()
const documents = ref<DocumentRecord[]>([])
const selectedFile = ref<globalThis.File | null>(null)
const selectedRoles = ref<UserRole[]>([])
const loading = ref(true)
const uploading = ref(false)
const deletingId = ref<string | null>(null)
const errorMessage = ref('')
const controller = new AbortController()
let pollTimer: ReturnType<typeof globalThis.setTimeout> | undefined

const hasProcessing = computed(() => documents.value.some((item) => item.status === 'PROCESSING'))

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

function statusClass(status: DocumentRecord['status']) {
  if (status === 'READY') return 'status-ok'
  if (status === 'FAILED') return 'status-error'
  return 'status-pending'
}

function setError(error: unknown) {
  errorMessage.value =
    error instanceof ApiError ? error.message : 'The document request could not be completed.'
}

function schedulePoll() {
  globalThis.clearTimeout(pollTimer)
  if (hasProcessing.value) pollTimer = globalThis.setTimeout(() => loadDocuments(true), 2000)
}

async function loadDocuments(silent = false) {
  if (!auth.token) return
  if (!silent) loading.value = true
  try {
    documents.value = await fetchDocuments(auth.token, controller.signal)
    if (!silent) errorMessage.value = ''
  } catch (error) {
    if (!controller.signal.aborted) setError(error)
  } finally {
    if (!silent) loading.value = false
    schedulePoll()
  }
}

function chooseFile(event: globalThis.Event) {
  const input = event.target as globalThis.HTMLInputElement
  selectedFile.value = input.files?.[0] ?? null
}

async function submitUpload() {
  if (!auth.token || !selectedFile.value || selectedRoles.value.length === 0) return
  uploading.value = true
  errorMessage.value = ''
  try {
    const document = await uploadDocument(auth.token, selectedFile.value, selectedRoles.value)
    documents.value = [document, ...documents.value]
    selectedFile.value = null
    selectedRoles.value = []
    const input = globalThis.document.querySelector<globalThis.HTMLInputElement>('#document-file')
    if (input) input.value = ''
    schedulePoll()
  } catch (error) {
    setError(error)
  } finally {
    uploading.value = false
  }
}

async function removeDocument(document: DocumentRecord) {
  if (!auth.token || !globalThis.confirm(`Delete ${document.filename}?`)) return
  deletingId.value = document.id
  errorMessage.value = ''
  try {
    await deleteDocument(auth.token, document.id)
    documents.value = documents.value.filter((item) => item.id !== document.id)
  } catch (error) {
    setError(error)
  } finally {
    deletingId.value = null
  }
}

onMounted(() => loadDocuments())
onBeforeUnmount(() => {
  controller.abort()
  globalThis.clearTimeout(pollTimer)
})
</script>

<template>
  <div class="min-h-screen bg-surface text-ink">
    <AppHeader />

    <main class="mx-auto max-w-6xl px-5 py-8 sm:px-8 sm:py-10">
      <div class="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p class="mb-1 text-xs font-semibold uppercase text-accent">Knowledge sources</p>
          <h1 class="text-3xl font-semibold">Documents</h1>
        </div>
        <p class="text-sm text-muted">{{ documents.length }} total</p>
      </div>

      <section aria-labelledby="upload-heading" class="mt-7 border border-line bg-white p-5 sm:p-6">
        <h2 id="upload-heading" class="text-base font-semibold">Upload document</h2>
        <form
          class="mt-5 grid gap-5 lg:grid-cols-[minmax(14rem,1fr)_2fr_auto] lg:items-end"
          @submit.prevent="submitUpload"
        >
          <div>
            <label class="field-label" for="document-file">File</label>
            <input
              id="document-file"
              class="file-input"
              type="file"
              accept=".pdf,.docx,.pptx,.md,.markdown"
              required
              @change="chooseFile"
            />
            <p class="mt-1.5 truncate text-xs text-muted">
              {{ selectedFile?.name ?? 'PDF, DOCX, PPTX, or Markdown' }}
            </p>
          </div>

          <fieldset>
            <legend class="field-label">Allowed roles</legend>
            <div class="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-4">
              <label v-for="role in roles" :key="role" class="flex items-center gap-2 text-sm">
                <input
                  v-model="selectedRoles"
                  class="size-4 accent-accent"
                  type="checkbox"
                  :value="role"
                />
                {{ role }}
              </label>
            </div>
          </fieldset>

          <button
            class="primary-button h-10 min-w-28"
            type="submit"
            :disabled="uploading || !selectedFile || selectedRoles.length === 0"
          >
            {{ uploading ? 'Uploading...' : 'Upload' }}
          </button>
        </form>
      </section>

      <p
        v-if="errorMessage"
        class="mt-5 border border-error-line bg-error-bg px-4 py-3 text-sm text-error"
        role="alert"
      >
        {{ errorMessage }}
      </p>

      <section aria-labelledby="library-heading" class="mt-8">
        <div class="mb-3 flex items-center justify-between">
          <h2 id="library-heading" class="text-base font-semibold">Document library</h2>
          <span class="text-xs text-muted">
            {{ hasProcessing ? 'Refreshing processing status' : 'Only uploaders can delete' }}
          </span>
        </div>

        <div class="overflow-hidden border border-line bg-white">
          <div v-if="loading" class="grid min-h-36 place-items-center text-sm text-muted">
            Loading documents...
          </div>
          <div
            v-else-if="documents.length === 0"
            class="grid min-h-36 place-items-center px-5 text-center"
          >
            <div>
              <p class="text-sm font-medium">No documents uploaded</p>
              <p class="mt-1 text-xs text-muted">Uploaded knowledge sources will appear here.</p>
            </div>
          </div>

          <div v-else class="overflow-x-auto">
            <table class="w-full min-w-[760px] border-collapse text-left text-sm">
              <thead class="border-b border-line bg-surface text-xs font-semibold text-muted">
                <tr>
                  <th class="table-cell">Document</th>
                  <th class="table-cell">Roles</th>
                  <th class="table-cell">Status</th>
                  <th class="table-cell text-right">Chunks</th>
                  <th class="table-cell">Uploader</th>
                  <th class="table-cell">Uploaded</th>
                  <th class="table-cell w-20"><span class="sr-only">Actions</span></th>
                </tr>
              </thead>
              <tbody class="divide-y divide-line">
                <tr v-for="document in documents" :key="document.id" class="align-top">
                  <td class="table-cell max-w-56">
                    <p class="truncate font-medium" :title="document.filename">
                      {{ document.filename }}
                    </p>
                    <p
                      v-if="document.error_message"
                      class="mt-1 line-clamp-2 text-xs text-error"
                      :title="document.error_message"
                    >
                      {{ document.error_message }}
                    </p>
                  </td>
                  <td class="table-cell text-xs text-muted">
                    {{ document.allowed_roles.join(', ') }}
                  </td>
                  <td class="table-cell">
                    <span class="status-label" :class="statusClass(document.status)">{{
                      document.status
                    }}</span>
                  </td>
                  <td class="table-cell text-right tabular-nums">
                    {{ document.status === 'READY' ? document.chunk_count : '-' }}
                  </td>
                  <td class="table-cell text-xs text-muted">{{ document.uploader.email }}</td>
                  <td class="table-cell whitespace-nowrap text-xs text-muted">
                    {{ formatDate(document.created_at) }}
                  </td>
                  <td class="table-cell text-right">
                    <button
                      v-if="document.uploader.id === auth.user?.id"
                      class="text-xs font-medium text-error hover:underline disabled:opacity-50"
                      type="button"
                      :disabled="deletingId === document.id"
                      @click="removeDocument(document)"
                    >
                      {{ deletingId === document.id ? 'Deleting' : 'Delete' }}
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </main>
  </div>
</template>
