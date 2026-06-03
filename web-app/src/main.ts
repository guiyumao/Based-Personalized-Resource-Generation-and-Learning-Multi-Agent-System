import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'

import App from './App.vue'
import router from './router'
import { useAuthStore } from './stores/auth'
import { useTheme } from './composables/useTheme'
import './styles.css'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
const authStore = useAuthStore(pinia)
authStore.restore()

// Restore saved theme before router triggers first render
useTheme().init()

app.use(router)
app.use(ElementPlus)

app.mount('#app')
