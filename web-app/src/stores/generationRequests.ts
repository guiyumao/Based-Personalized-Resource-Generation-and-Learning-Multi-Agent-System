import { reactive } from 'vue'

// Synchronous generation requests have no server task receipt yet. Keep their
// visible state outside routed components for as long as the request is open.
export const generationRequests = reactive<Record<string, { userId: number; id: number; status: string; current_step: string; label: string; topic: string; created_at: string; route: string }>>({})
let sequence = 0
export function beginGenerationRequest(userId: number, url: string, data: any) {
  if (!/^\/(?:exercises\/generate|resources\/generate|agents\/coordinate)$/.test(url)) return ''
  const key = `request:${++sequence}`
  const label = url.includes('exercises') ? '练习' : url.includes('coordinate') ? '学习资源' : '资源'
  generationRequests[key] = { userId, id: sequence, status: 'RUNNING', label,
    topic: data?.knowledge_point || '', current_step: '正在生成，等待服务端返回；暂无可用的分步进度', created_at: new Date().toISOString(),
    route: url.includes('exercises') ? '/student/exercise' : '/student/resources' }
  return key
}
export function endGenerationRequest(key?: string) { if (key) delete generationRequests[key] }
