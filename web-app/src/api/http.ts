import axios from 'axios'

const userBaseUrl = 'http://127.0.0.1:8001'
const agentBaseUrl = 'http://127.0.0.1:8002'
const evaluationBaseUrl = 'http://127.0.0.1:8004'
const teacherBaseUrl = 'http://127.0.0.1:8005'
const systemBaseUrl = 'http://127.0.0.1:8006'

function createHttpClient(baseURL: string) {
  const client = axios.create({
    baseURL,
    timeout: 120000,  // 2 min — DeepSeek LLM can take 30-60s per request
  })

  client.interceptors.request.use((config) => {
    const raw = localStorage.getItem('learning-system-auth')
    if (!raw) {
      return config
    }
    try {
      const parsed = JSON.parse(raw) as { token?: string }
      if (parsed.token) {
        config.headers.Authorization = `Bearer ${parsed.token}`
      }
    } catch {
      // Ignore malformed localStorage payloads and proceed without token.
    }
    return config
  })

  return client
}

export const userApi = createHttpClient(userBaseUrl)
export const agentApi = createHttpClient(agentBaseUrl)
export const qaApi = createHttpClient(agentBaseUrl)
export const contentApi = createHttpClient(agentBaseUrl)
export const evaluationApi = createHttpClient(evaluationBaseUrl)
export const teacherApi = createHttpClient(teacherBaseUrl)
export const systemApi = createHttpClient(systemBaseUrl)
export const resourceApi = createHttpClient('http://127.0.0.1:8003')
