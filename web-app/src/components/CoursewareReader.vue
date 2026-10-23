<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { renderLearningMarkdown } from '../utils/renderLearningMarkdown'
import LearningContent from './LearningContent.vue'
import GenerationProgress from './GenerationProgress.vue'
import { normalizeMermaidSource } from '../utils/normalizeMermaidSource'
import { useAuthStore } from '../stores/auth'
import { agentApi, evaluationApi } from '../api/http'

const props = defineProps<{ content: string; resourceId?: number; version?: string; structured?: string; hideNavigation?: boolean }>()
const auth = useAuthStore()
const completed = ref<string[]>([]); const last = ref(''); const host = ref<HTMLElement>()
const status = ref(''); const busy = ref(false)

const videoUrl = ref(''); const videoStatus = ref(''); const videoBusy = ref(false)
const videoJob = ref<{id: number; status: string; current_step: string; created_at?: string; started_at?: string | null} | null>(null)
const videoChecking = ref(true)
let videoDisposed = false
let videoSequence = 0
let videoTimer: ReturnType<typeof setTimeout> | undefined
async function loadVideo() {
  if (videoDisposed) return
  const sequence = ++videoSequence
  videoChecking.value = true
  if (videoUrl.value) URL.revokeObjectURL(videoUrl.value)
  videoUrl.value = ''
  if (!props.resourceId) { videoChecking.value = false; return }
  try {
    const response = await agentApi.get(`/resources/${props.resourceId}/video`, { responseType: 'blob' })
    if (sequence === videoSequence) videoUrl.value = URL.createObjectURL(response.data)
  } catch (error: any) {
    if (sequence === videoSequence) videoStatus.value = error?.response?.status === 404 ? '当前课件还没有视频，可单独制作，无需重新生成正文。' : '视频暂不可读取，请稍后重试。'
  }
  finally { if (sequence === videoSequence) videoChecking.value = false }
}
async function createVideo() {
  if (videoBusy.value || !props.resourceId || !props.version) return
  videoBusy.value = true
  const resourceId = props.resourceId
  const version = props.version
  try {
    const { data } = await agentApi.post(`/resources/${resourceId}/video`, { expected_version: version, client_request_id: crypto.randomUUID() })
    const poll = async () => {
      if (videoDisposed || props.resourceId !== resourceId || props.version !== version) return
      try {
        const task = (await agentApi.get(`/assistant/tasks/${data.id}`)).data
        if (videoDisposed || props.resourceId !== resourceId || props.version !== version) return
        videoJob.value = task
        videoStatus.value = task.current_step
        if (['SUCCEEDED', 'FAILED', 'CANCELLED'].includes(task.status)) {
          videoBusy.value = false
          if (task.status === 'SUCCEEDED') { await loadVideo(); videoStatus.value = '字幕课件视频（无声）' }
          else videoStatus.value = task.result?.content || '视频制作失败，可重试。'
        } else videoTimer = setTimeout(poll, 1500)
      } catch { videoBusy.value = false; videoStatus.value = '视频任务状态读取失败。' }
    }
    await poll()
  } catch { videoBusy.value = false; videoStatus.value = '视频任务未能提交，请重新打开当前课件。' }
}
watch(() => [props.resourceId, props.version], () => { clearTimeout(videoTimer); videoBusy.value = false; void loadVideo() })
onMounted(() => void loadVideo())
onUnmounted(() => { videoDisposed = true; videoSequence++; clearTimeout(videoTimer); if (videoUrl.value) URL.revokeObjectURL(videoUrl.value) })

const answers = ref<Record<number, string>>({}); const receipts = ref<Record<number, string>>({})
const feedback = ref<Record<number, string>>({}); const submitting = ref<number>()
const sections = computed(() => {
  let fence = false
  const blocks: { key: string; title: string; body: string }[] = []
  for (const line of props.content.split('\n')) {
    if (/^```/.test(line)) fence = !fence
    if (!fence && /^## /.test(line)) blocks.push({ key: String(blocks.length), title: line.slice(3), body: '' })
    else {
      if (!blocks.length) blocks.push({ key: '0', title: '课程概览', body: '' })
      blocks[blocks.length - 1]!.body += line + '\n'
    }
  }
  return blocks.filter(s => s.body.trim())
})
const metadata = computed(() => { try { return JSON.parse(props.structured || '{}') } catch { return {} } })
const progress = computed(() => sections.value.length ? Math.round(100 * sections.value.filter(s => completed.value.includes(s.key)).length / sections.value.length) : 0)
const storageKey = computed(() => {
  let hash = 0
  for (const char of props.content) hash = ((hash << 5) - hash + char.charCodeAt(0)) | 0
  return `courseware-reading:v2:${auth.user?.userId}:${props.resourceId ?? ''}:${props.version ?? hash}`
})
function save() { localStorage.setItem(storageKey.value, JSON.stringify({ completed: completed.value, last: last.value })) }
function mark(key: string) { completed.value = completed.value.includes(key) ? completed.value.filter(k => k !== key) : [...completed.value, key]; last.value = key; save() }
function open(key: string) {
  const section = host.value?.querySelector<HTMLDetailsElement>(`[data-section="${key}"]`)
  if (section) { section.open = true; section.scrollIntoView({ behavior: 'smooth', block: 'start' }); last.value = key; save() }
}
function openHeading(title: string) {
  const normalize = (value: string) => value.replace(/\*\*|`/g, '').trim()
  const section = sections.value.find(item => normalize(item.title) === normalize(title))
  if (section) open(section.key)
}
defineExpose({ openHeading })
function isUntrustedProfile(title: string) {
  return /你的当前学习情况|当前学情|学习画像/.test(title)
    && metadata.value.personalization?.evidence?.version !== 'point-evidence-v4'
}
function renderBody(body: string) {
  // Split only model-produced answer headings; render both sides through the safe Markdown renderer.
  // Existing saved lessons retain their original text; omit flowcharts and their standalone heading from reading.
  const readable = body.replace(/(^#{3,6}[^\n]*流程图[^\n]*\n\s*)?^[ \t]*```mermaid[^\n]*\n([\s\S]*?)^[ \t]*```[ \t]*$/gm,
    (whole, _heading, source: string) => /^(?:\s|%%[^\n]*\n)*(?:flowchart|graph)\b/i.test(source) ? '' : whole)
  const parts = readable.split(/(?=^###\s)/m)
  return parts.map((part) => /^###\s*答案与解析/.test(part) ? `<details class="courseware-answer"><summary>查看答案与解析</summary>${renderLearningMarkdown(part)}</details>` : renderLearningMarkdown(part)).join('')
}
async function draw() {
  await nextTick()
  const nodes = [...(host.value?.querySelectorAll<HTMLElement>('pre code.language-mermaid') ?? [])]
  if (!nodes.length) return
  const { default: mermaid } = await import('mermaid')
  mermaid.initialize({ startOnLoad: false, securityLevel: 'strict', suppressErrorRendering: true })
  for (const node of nodes) {
    const text = normalizeMermaidSource(node.textContent || '')
    try {
      await mermaid.parse(text)
      const { svg } = await mermaid.render(`courseware-${crypto.randomUUID()}`, text)
      if (!host.value?.contains(node)) continue
      const wrapper = document.createElement('div'); wrapper.className = 'courseware-diagram'; wrapper.innerHTML = svg
      node.parentElement?.replaceWith(wrapper)
    } catch {
      node.parentElement?.setAttribute('aria-label', '图示无法渲染，保留源文与完整文字说明')
      if (node.parentElement && !node.parentElement.dataset.diagramError) {
        node.parentElement.dataset.diagramError = 'true'
        const notice = document.createElement('p'); notice.textContent = '图示格式需要修订，已保留源代码及完整文字说明。'
        node.parentElement.before(notice)
      }
    }
  }
}
async function revise(index: number) {
  const chapter = metadata.value.chapters?.find((c: any) => c.heading === sections.value[index]?.title)
  if (!chapter || !props.resourceId || !props.version || busy.value) return
  busy.value = true
  try {
    const { data } = await agentApi.post(`/resources/${props.resourceId}/chapters/${chapter.key}/regenerate`, {
      expected_version: props.version, client_request_id: crypto.randomUUID(),
    })
    status.value = `章节修订任务 #${data.id} 已保存，可在学习助手任务列表查看；生成后作为新课件保留。`
  } catch (error: any) { status.value = String(error?.response?.data?.detail || '章节修订未能提交') }
  finally { busy.value = false }
}
async function submit(exercise: any) {
  if (submitting.value || !auth.user) return
  const userId = auth.user.userId; const resourceId = props.resourceId; const version = props.version
  submitting.value = exercise.exercise_id
  receipts.value[exercise.exercise_id] ??= crypto.randomUUID()
  try {
    const { data } = await evaluationApi.post('/evaluation/practice/submit', {
      user_id: auth.user.userId, exercise_id: exercise.exercise_id,
      knowledge_point: metadata.value.knowledge_point, question_type: exercise.question_type,
      user_answer: answers.value[exercise.exercise_id] || '', correct_answer: '', analysis: '',
      client_request_id: receipts.value[exercise.exercise_id],
    })
    if (auth.user?.userId !== userId || props.resourceId !== resourceId || props.version !== version) return
    feedback.value[exercise.exercise_id] = `${data.is_correct ? '回答正确' : '需要复习'}：${data.explanation || data.comment || ''}`
  } catch (error: any) { if (auth.user?.userId !== userId || props.resourceId !== resourceId) return; feedback.value[exercise.exercise_id] = String(error?.response?.data?.detail || '评分暂不可用，答案已保留') }
  finally { submitting.value = undefined }
}
function restore() {
  try { const stored = JSON.parse(localStorage.getItem(storageKey.value) || '{}'); completed.value = stored.completed || []; last.value = stored.last || '' } catch { completed.value = []; last.value = '' }
  void draw()
}
watch(() => [props.content, auth.user?.userId], () => { answers.value = {}; receipts.value = {}; feedback.value = {}; status.value = ''; restore() })
onMounted(restore)
</script>

<template>
  <div class="courseware-reader-shell"><div ref="host" class="courseware-reader" :class="{ 'without-navigation': hideNavigation }">
    <nav v-if="!hideNavigation" aria-label="课件章节目录">
      <strong>章节阅读进度 {{ progress }}%</strong>
      <progress :value="progress" max="100" />
      <p>阅读完成状态仅记录本机学习进度；掌握度由真实作答评估。</p>
      <button v-if="last" @click="open(last)">继续上次阅读</button>
      <button v-for="section in sections" :key="section.key" @click="open(section.key)">{{ completed.includes(section.key) ? '✓ ' : '' }}{{ section.title }}</button>
    </nav>
    <main>
      <details v-if="resourceId" class="courseware-video" open><summary>课件视频 · 无声字幕</summary><p>来源：当前课件正文，由本机排版合成为无声字幕视频。</p><video v-if="videoUrl" :src="videoUrl" controls preload="metadata" aria-label="当前课件视频（无声字幕）"/><GenerationProgress v-if="videoBusy" :job="videoJob" label="课件视频"/><p v-else-if="videoStatus">{{ videoStatus }}</p><button v-if="!videoUrl && version && !videoChecking" :disabled="videoBusy" @click="createVideo">{{ videoBusy ? '视频制作中' : '制作当前课件视频' }}</button></details>
      <p v-if="metadata.schema !== 'teaching-v2'" role="status" class="legacy-notice">这是一份历史课件，正文不会随系统升级自动重写。旧版学情段落已停止展示，不能作为当前掌握度依据；请打开已生成的新版，或重新生成完整课件。</p>
      <p v-if="status" role="status">{{ status }}</p>
      <details v-for="(section, index) in sections" :key="section.key" :data-section="section.key" open>
        <summary>{{ section.title }}</summary>
        <p v-if="isUntrustedProfile(section.title)" class="legacy-notice">此段来自旧版生成时的学情快照，未经当前证据规则核验，已停止展示。当前掌握度请以学习面板中的有效作答统计为准；通用教学内容仍可继续阅读。</p>
        <div v-else class="learning-markdown" v-html="renderBody(section.body)" />
        <button @click="mark(section.key)">{{ completed.includes(section.key) ? '标为未读' : '本章已读' }}</button>
        <button v-if="resourceId && version && metadata.schema === 'teaching-v2' && metadata.chapters?.some((c: any) => c.heading === section.title)" :disabled="busy" @click="revise(index)">重新生成本章</button>
      </details>
      <details v-if="metadata.exercises?.length"><summary>提交配套练习并更新学情</summary>
        <section v-for="exercise in metadata.exercises" :key="exercise.exercise_id">
          <div v-html="renderLearningMarkdown(exercise.prompt)" />
          <textarea v-model="answers[exercise.exercise_id]" :aria-label="`配套练习${exercise.exercise_id}答案`" />
          <button :disabled="Boolean(submitting)" @click="submit(exercise)">提交作答</button>
          <p v-if="feedback[exercise.exercise_id]" role="status">{{ feedback[exercise.exercise_id] }}</p><button v-if="feedback[exercise.exercise_id]" @click="delete receipts[exercise.exercise_id]; delete feedback[exercise.exercise_id]">开始新的作答</button>
        </section>
      </details>
      <details><summary>知识来源与可信度</summary>
        <p v-if="metadata.knowledge_evidence?.coverage">知识覆盖：{{ metadata.knowledge_evidence.coverage.state }}；检索命中 {{ metadata.sources?.length || 0 }} 条。</p>
        <p v-if="metadata.knowledge_evidence?.supplementation?.candidate_ids?.length">{{ metadata.knowledge_evidence.supplementation.reused ? '复用已保存资料' : '补充资料已入库' }}：候选 #{{ metadata.knowledge_evidence.supplementation.candidate_ids.join('、#') }}，尚待审核发布。</p>
        <p v-else-if="metadata.knowledge_evidence?.supplementation">本次补充状态：{{ metadata.knowledge_evidence.supplementation.status }}，未新增候选资料。</p>
        <p>模型生成教学内容；结构检查不等同于学科事实核验。{{ metadata.sources?.length ? '参考资料如下。' : '暂无可回指的检索资料，建议结合教材核验。' }}</p>
        <article v-for="(source, i) in metadata.sources || []" :key="i"><strong>{{ source.metadata?.title || source.metadata?.source || source.id }}</strong><LearningContent class="source-content" :content="source.content" /></article>
      </details>
    </main>
  </div></div>
</template>

<style scoped>
.courseware-video video{display:block;width:100%;max-width:100%;margin-top:12px}.legacy-notice{padding:14px;border:1px solid #e8c775;background:#fff9e8;color:#614500;border-radius:8px}.courseware-reader-shell{container-type:inline-size}.courseware-reader{display:grid;grid-template-columns:minmax(150px,220px) minmax(0,1fr);gap:24px;line-height:1.8}
.courseware-reader.without-navigation{display:block}nav{position:sticky;top:16px;align-self:start;display:grid;gap:8px}nav p{font-size:12px;color:var(--muted,#666)}progress{width:100%}
button{padding:8px 12px;cursor:pointer;border:1px solid var(--border,#ddd);background:var(--surface,#fff);color:inherit;border-radius:6px;text-align:left;margin:4px}
main,details{min-width:0}details{padding:16px;border-bottom:1px solid var(--border,#ddd);scroll-margin-top:24px}summary{cursor:pointer;font-weight:600;font-size:18px}
:deep(pre),:deep(table){max-width:100%;overflow-x:auto;display:block}:deep(pre){padding:16px;background:#f5f7fa}:deep(svg){max-width:100%;height:auto}:deep(.courseware-answer){margin-top:16px;background:var(--surface,#f6f8fa)}:deep(th),:deep(td){padding:8px;border:1px solid #ddd}
@container(max-width:800px){.courseware-reader{grid-template-columns:1fr}nav{position:static;display:flex;flex-wrap:wrap;max-height:240px;overflow:auto}nav strong,nav p,nav progress{width:100%}nav button{font-size:12px;margin:2px;padding:6px}}
@media(max-width:760px){.courseware-reader{grid-template-columns:1fr}nav{position:static}details{padding:10px}}
</style>
