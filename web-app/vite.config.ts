import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    host: process.env.FRONTEND_HOST || '127.0.0.1',
    port: Number(process.env.FRONTEND_PORT || 5175),
  },
})
