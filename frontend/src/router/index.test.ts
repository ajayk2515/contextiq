import { createPinia } from 'pinia'
import { createMemoryHistory } from 'vue-router'
import { beforeEach, describe, expect, it } from 'vitest'

import { createAppRouter } from './index'

describe('authentication route guard', () => {
  beforeEach(() => {
    sessionStorage.clear()
  })

  it('redirects an unauthenticated user to login', async () => {
    const router = createAppRouter(createPinia(), createMemoryHistory())

    await router.push('/')
    await router.isReady()

    expect(router.currentRoute.value.name).toBe('login')
    expect(router.currentRoute.value.query.redirect).toBe('/')
  })

  it('protects the documents route', async () => {
    const router = createAppRouter(createPinia(), createMemoryHistory())

    await router.push('/documents')
    await router.isReady()

    expect(router.currentRoute.value.name).toBe('login')
    expect(router.currentRoute.value.query.redirect).toBe('/documents')
  })

  it('protects the chat route', async () => {
    const router = createAppRouter(createPinia(), createMemoryHistory())

    await router.push('/chat')
    await router.isReady()

    expect(router.currentRoute.value.name).toBe('login')
    expect(router.currentRoute.value.query.redirect).toBe('/chat')
  })

  it('protects the retrieval inspector route', async () => {
    const router = createAppRouter(createPinia(), createMemoryHistory())

    await router.push('/inspector')
    await router.isReady()

    expect(router.currentRoute.value.name).toBe('login')
    expect(router.currentRoute.value.query.redirect).toBe('/inspector')
  })
})
