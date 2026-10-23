<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { agentApi } from '../api/http'
import GenerationProgress from './GenerationProgress.vue'
const props = defineProps<{contextId: string}>()
type Artifact = {id: string; kind: string; size: number; resource_version: string}
type ArtifactJob = {id: number; status: string; current_step: string; created_at?: string; started_at?: string | null; result?: {content?: string}}
const artifacts = ref<Artifact[]>([]); const error = ref(''); const status = ref(''); const busy = ref(false)
const job = ref<ArtifactJob | null>(null); const kind = ref('')
const previews = ref<Record<string,string>>({})
const KIND_LABELS: Record<string,string> = { video: '字幕视频', pptx: 'PPTX', animation: '步骤动画', audio: '语音' }
const artifactLabel = computed(() => KIND_LABELS[kind.value] || '学习产物')
const storageKey = computed(() => `artifact-task:${props.contextId}`)
let timer: ReturnType<typeof setTimeout> | undefined
let disposed = false
async function load() { artifacts.value = (await agentApi.get(`/learning/contexts/${props.contextId}/artifacts`)).data.items }
function settle(current: ArtifactJob) {
  busy.value = false
  sessionStorage.removeItem(storageKey.value)
  status.value = current.status === 'SUCCEEDED' ? `${artifactLabel.value}已生成` : (current.result?.content || `${artifactLabel.value}生成未完成，可重试`)
  if (current.status === 'SUCCEEDED') void load()
}
function watchJob(taskId: number) {
  clearTimeout(timer)
  const poll = async () => {
    if (disposed) return
    try {
      const current = (await agentApi.get(`/assistant/tasks/${taskId}`)).data as ArtifactJob
      if (disposed) return
      job.value = current
      if (['SUCCEEDED','FAILED','CANCELLED','TIMED_OUT'].includes(current.status)) settle(current)
      else timer = setTimeout(poll, 1000)
    } catch { busy.value = false; error.value = '无法读取产物任务状态。' }
  }
  return poll()
}
async function create(artifactKind: string) {
  error.value = ''; status.value = ''; busy.value = true; kind.value = artifactKind
  try {
    const task = (await agentApi.post(`/learning/contexts/${props.contextId}/artifacts`, {kind: artifactKind, client_request_id: crypto.randomUUID()})).data
    sessionStorage.setItem(storageKey.value, JSON.stringify({ id: task.id, kind: artifactKind }))
    job.value = task
    await watchJob(task.id)
  } catch { busy.value = false; error.value = '无法创建产物任务，请检查上下文或服务状态。' }
}
async function open(item: Artifact) {
  try {
    const response = await agentApi.get(`/learning/artifacts/${item.id}/file`, {responseType:'blob'})
    if (disposed) return
    if (previews.value[item.id]) URL.revokeObjectURL(previews.value[item.id])
    const url = URL.createObjectURL(response.data)
    previews.value[item.id] = url
    if(item.kind === 'pptx') { const link=document.createElement('a'); link.href=url; link.download=`learning-${item.id}.pptx`; link.click() }
  } catch { error.value='产物不可读取，可能来源版本已变化或文件校验失败。' }
}
async function resume() {
  // Returning to the page mid-generation must still show live progress.
  let pending: { id?: number; kind?: string } = {}
  try { pending = JSON.parse(sessionStorage.getItem(storageKey.value) || '{}') } catch { pending = {} }
  const taskId = Number(pending.id || 0)
  if (!taskId) return
  kind.value = String(pending.kind || '')
  busy.value = true
  try {
    const current = (await agentApi.get(`/assistant/tasks/${taskId}`)).data as ArtifactJob
    if (disposed) return
    job.value = current
    if (['SUCCEEDED','FAILED','CANCELLED','TIMED_OUT'].includes(current.status)) { busy.value = false; sessionStorage.removeItem(storageKey.value) }
    else await watchJob(taskId)
  } catch { busy.value = false; sessionStorage.removeItem(storageKey.value) }
}
onMounted(async () => {
  try { await load(); for (const item of artifacts.value.filter(item => item.kind === 'video')) await open(item) }
  catch { error.value='产物列表暂不可用。' }
  await resume()
})
onUnmounted(() => { disposed = true; clearTimeout(timer); Object.values(previews.value).forEach(url=>URL.revokeObjectURL(url)) })
</script>
<template><section class="resource-artifacts" aria-label="本地学习产物"><h3>本地学习产物</h3><p>从当前课件制作字幕视频（无声）、PPTX、步骤动画或本机语音。视频使用课件正文逐页播放；语音朗读前1600字。</p><div class="artifact-actions"><el-button :disabled="busy" @click="create('video')">生成字幕视频</el-button><el-button :disabled="busy" @click="create('pptx')">生成PPTX</el-button><el-button :disabled="busy" @click="create('animation')">生成步骤动画</el-button><el-button :disabled="busy" @click="create('audio')">生成语音</el-button></div><GenerationProgress v-if="busy" :job="job" :label="artifactLabel"/><p v-else-if="status" role="status">{{status}}</p><el-alert v-if="error" :title="error" type="error" :closable="false"/><article v-for="item in artifacts" :key="item.id"><p>{{item.kind}} · {{item.size}} bytes · 版本 {{item.resource_version.slice(0,12)}}</p><el-button @click="open(item)">{{item.kind === 'pptx' ? '下载PPTX' : '加载预览'}}</el-button><img v-if="item.kind==='animation' && previews[item.id]" :src="previews[item.id]" alt="当前课件的步骤动画"/><video v-if="item.kind==='video' && previews[item.id]" :src="previews[item.id]" controls preload="metadata" aria-label="当前课件字幕视频（无声）"/><audio v-if="item.kind==='audio' && previews[item.id]" :src="previews[item.id]" controls preload="metadata" aria-label="当前课件语音"/></article></section></template>
<style scoped>.resource-artifacts { margin:20px 0; border-top:1px solid var(--line); padding-top:12px; }.artifact-actions { display:flex; flex-wrap:wrap; gap:8px; }.resource-artifacts img,.resource-artifacts audio,.resource-artifacts video { display:block; width:100%; max-width:100%; margin-top:12px; }</style>
