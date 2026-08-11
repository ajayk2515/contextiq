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
})
