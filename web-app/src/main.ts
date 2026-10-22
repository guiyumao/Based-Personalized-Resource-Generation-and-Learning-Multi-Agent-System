import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'

import App from './App.vue'
import { userApi } from './api'
import router from './router'
import { useAuthStore } from './stores/auth'
import { useTheme } from './composables/useTheme'
import './styles.css'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
const authStore = useAuthStore(pinia)
authStore.restore()

async function validateRestoredSession() {
  if (!authStore.isAuthenticated) {
    return
  }

  try {
    const token = authStore.token
    const { data } = await userApi.get<{ id: number; username: string; role: 'student' | 'teacher' | 'admin' }>('/users/me', { timeout: 5000 })
    authStore.verifyIdentity(token, { userId: data.id, username: data.username, role: data.role })
  } catch (error: any) {
    const status = error?.response?.status
    if (status === 401 || status === 404) {
      authStore.clear()
    }
  }
}

async function bootstrap() {
  await validateRestoredSession()

  // Restore saved theme before router triggers first render
  useTheme().init()

  app.use(ElementPlus)
  app.use(router)
  await router.isReady()
  app.mount('#app')
}

void bootstrap()
