import type { Pinia } from 'pinia'
import { createRouter, createWebHistory, type RouterHistory, type RouteRecordRaw } from 'vue-router'

import ChatPage from '@/pages/ChatPage.vue'
import FoundationPage from '@/pages/FoundationPage.vue'
import InspectorPage from '@/pages/InspectorPage.vue'
import DocumentsPage from '@/pages/DocumentsPage.vue'
import LoginPage from '@/pages/LoginPage.vue'
import { pinia } from '@/stores'
import { useAuthStore } from '@/stores/auth'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: LoginPage,
    meta: { guestOnly: true },
  },
  {
    path: '/',
    name: 'foundation',
    component: FoundationPage,
    meta: { requiresAuth: true },
  },
  {
    path: '/chat',
    name: 'chat',
    component: ChatPage,
    meta: { requiresAuth: true },
  },
  {
    path: '/documents',
    name: 'documents',
    component: DocumentsPage,
    meta: { requiresAuth: true },
  },
  {
    path: '/inspector',
    name: 'inspector',
    component: InspectorPage,
    meta: { requiresAuth: true },
  },
]

export function createAppRouter(
  authPinia: Pinia = pinia,
  history: RouterHistory = createWebHistory(import.meta.env.BASE_URL),
) {
  const router = createRouter({ history, routes })

  router.beforeEach(async (to) => {
    const auth = useAuthStore(authPinia)
    await auth.initialize()

    if (to.meta.requiresAuth && !auth.isAuthenticated) {
      return { name: 'login', query: { redirect: to.fullPath } }
    }
    if (to.meta.guestOnly && auth.isAuthenticated) {
      return { name: 'foundation' }
    }
  })

  return router
}

export default createAppRouter()
