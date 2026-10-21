<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { agentApi } from '../api/http'
const props = defineProps<{contextId: string}>()
type Artifact = {id: string; kind: string; size: number; resource_version: string}
const artifacts = ref<Artifact[]>([]); const error = ref(''); const status = ref(''); const busy = ref(false)
const previews = ref<Record<string,string>>({})
let timer: ReturnType<typeof setTimeout> | undefined
let disposed = false
async function load() { artifacts.value = (await agentApi.get(`/learning/contexts/${props.contextId}/artifacts`)).data.items }
async function create(kind: string) {
  error.value = ''; busy.value = true
  try {
    const task = (await agentApi.post(`/learning/contexts/${props.contextId}/artifacts`, {kind, client_request_id:crypto.randomUUID()})).data
    const poll = async () => {
      if (disposed) return
      try {
        const job = (await agentApi.get(`/assistant/tasks/${task.id}`)).data
        if (disposed) return
        status.value = `${job.status} · ${job.current_step}`
        if (['SUCCEEDED','FAILED','CANCELLED'].includes(job.status)) { busy.value=false; if(job.status !== 'SUCCEEDED') error.value=job.result?.content || '产物生成未完成'; await load() }
        else timer = setTimeout(poll, 1000)
      } catch { busy.value=false; error.value='无法读取产物任务状态。' }
    }
    await poll()
  } catch { busy.value=false; error.value='无法创建产物任务，请检查上下文或服务状态。' }
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
onMounted(async () => {
  try { await load(); for (const item of artifacts.value.filter(item => item.kind === 'video')) await open(item) }
  catch { error.value='产物列表暂不可用。' }
})
onUnmounted(() => { disposed = true; clearTimeout(timer); Object.values(previews.value).forEach(url=>URL.revokeObjectURL(url)) })
</script>
<template><section class="resource-artifacts" aria-label="本地学习产物"><h3>本地学习产物</h3><p>从当前课件制作字幕视频（无声）、PPTX、步骤动画或本机语音。视频使用课件正文逐页播放；语音朗读前1600字。</p><div class="artifact-actions"><el-button :disabled="busy" @click="create('video')">生成字幕视频</el-button><el-button :disabled="busy" @click="create('pptx')">生成PPTX</el-button><el-button :disabled="busy" @click="create('animation')">生成步骤动画</el-button><el-button :disabled="busy" @click="create('audio')">生成语音</el-button></div><p v-if="status">{{status}}</p><el-alert v-if="error" :title="error" type="error" :closable="false"/><article v-for="item in artifacts" :key="item.id"><p>{{item.kind}} · {{item.size}} bytes · 版本 {{item.resource_version.slice(0,12)}}</p><el-button @click="open(item)">{{item.kind === 'pptx' ? '下载PPTX' : '加载预览'}}</el-button><img v-if="item.kind==='animation' && previews[item.id]" :src="previews[item.id]" alt="当前课件的步骤动画"/><video v-if="item.kind==='video' && previews[item.id]" :src="previews[item.id]" controls preload="metadata" aria-label="当前课件字幕视频（无声）"/><audio v-if="item.kind==='audio' && previews[item.id]" :src="previews[item.id]" controls preload="metadata" aria-label="当前课件语音"/></article></section></template>
<style scoped>.resource-artifacts { margin:20px 0; border-top:1px solid var(--line); padding-top:12px; }.artifact-actions { display:flex; flex-wrap:wrap; gap:8px; }.resource-artifacts img,.resource-artifacts audio,.resource-artifacts video { display:block; width:100%; max-width:100%; margin-top:12px; }</style>
