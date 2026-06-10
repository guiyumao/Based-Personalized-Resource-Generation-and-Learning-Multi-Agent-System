import axios from 'axios'

type ServiceKey = 'user' | 'agent' | 'resource' | 'evaluation' | 'teacher' | 'system'

function readRequiredEnv(name: string) {
  const value = import.meta.env[name]
  if (!value) {
    throw new Error(`Missing required frontend environment variable: ${name}`)
  }
  return value
}

export const serviceEndpoints: Record<ServiceKey, string> = {
  user: readRequiredEnv('VITE_USER_API_BASE_URL'),
  agent: readRequiredEnv('VITE_AGENT_API_BASE_URL'),
  resource: readRequiredEnv('VITE_RESOURCE_API_BASE_URL'),
  evaluation: readRequiredEnv('VITE_EVALUATION_API_BASE_URL'),
  teacher: readRequiredEnv('VITE_TEACHER_API_BASE_URL'),
  system: readRequiredEnv('VITE_SYSTEM_API_BASE_URL'),
}

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

export const userApi = createHttpClient(serviceEndpoints.user)
export const agentApi = createHttpClient(serviceEndpoints.agent)
export const qaApi = createHttpClient(serviceEndpoints.agent)
export const contentApi = createHttpClient(serviceEndpoints.agent)
export const evaluationApi = createHttpClient(serviceEndpoints.evaluation)
export const teacherApi = createHttpClient(serviceEndpoints.teacher)
export const systemApi = createHttpClient(serviceEndpoints.system)
export const resourceApi = createHttpClient(serviceEndpoints.resource)
