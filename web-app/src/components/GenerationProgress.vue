<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'

type Job = { id: number | string; status: string; current_step: string; task_type?: string; started_at?: string | null; created_at?: string | null; progress?: { completed: number; total: number; unit: string } | null }

const props = withDefaults(defineProps<{ job?: Job | null; submitting?: boolean; label?: string }>(), {
  job: null, submitting: false, label: '资源',
})

const STATUS_LABELS: Record<string, string> = {
  PENDING: '排队中', QUEUED: '排队中', RUNNING: '生成中', CANCEL_REQUESTED: '正在停止', SUCCEEDED: '已完成', FAILED: '生成失败', CANCELLED: '已取消', TIMED_OUT: '执行超时', UNKNOWN: '状态待确认',
}
const AGENT_LABELS: [RegExp, string][] = [
  [/learner_profiling_agent/, '学情画像分析'],
  [/knowledge_base_agent/, '知识库资料检索'],
  [/resource_generation_agent/, '课件内容生成'],
  [/exercise_generation_agent/, '练习题生成'],
  [/path_planning_agent/, '学习路径规划'],
]

const finished = computed(() => !!props.job && ['SUCCEEDED', 'FAILED', 'CANCELLED', 'TIMED_OUT'].includes(props.job.status))
const statusLabel = computed(() => (props.submitting && !props.job ? '提交中' : STATUS_LABELS[props.job?.status ?? ''] ?? (props.job?.status ?? '准备中')))

const stepText = computed(() => {
  if (props.submitting && !props.job) return '正在提交生成任务…'
  const raw = String(props.job?.current_step || '').trim()
  if (!raw || raw === '等待执行') return '任务已受理，等待后台执行'
  const chapter = raw.match(/课件章节\s*(\d+)\s*\/\s*(\d+)/)
  if (chapter) return raw.replace(/课件章节\s*\d+\s*\/\s*\d+/, `已保存 ${chapter[1]}/${chapter[2]} 章`)
  for (const [pattern, label] of AGENT_LABELS) {
    if (pattern.test(raw)) return `正在${label}`
  }
  return raw
})

// Only show measurable saved units. Chapter completion is not a claimed overall
// percentage: validation and media generation may still follow the last chapter.
const measured = computed(() => {
  const supplied = props.job?.progress
  const match = String(props.job?.current_step || '').match(/课件章节\s*(\d+)\s*\/\s*(\d+)/)
  const value = supplied ?? (match ? { completed: Number(match[1]), total: Number(match[2]), unit: '章' } : null)
  return value && Number.isFinite(value.completed) && Number.isFinite(value.total) && value.total > 0 && value.completed >= 0 && value.completed <= value.total ? value : null
})

// Elapsed time ticks once per second while the job is still running.
const now = ref(Date.now())
let timer: ReturnType<typeof setInterval> | undefined
watch(() => [props.job?.id, finished.value] as const, () => {
  if (timer) { clearInterval(timer); timer = undefined }
  if (props.job && !finished.value) {
    now.value = Date.now()
    timer = setInterval(() => { now.value = Date.now() }, 1000)
  }
}, { immediate: true })
onUnmounted(() => { if (timer) clearInterval(timer) })
const elapsed = computed(() => {
  const raw = props.job?.started_at || props.job?.created_at
  if (!raw || finished.value) return ''
  const iso = /[Zz]|[+-]\d{2}:?\d{2}$/.test(raw) ? raw : `${raw}Z`
  const start = new Date(iso).getTime()
  if (!Number.isFinite(start)) return ''
  const seconds = Math.max(0, Math.floor((now.value - start) / 1000))
  return seconds >= 60 ? `已进行 ${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒` : `已进行 ${seconds} 秒`
})
</script>

<template>
  <section class="generation-progress" role="status" aria-live="polite">
    <div class="generation-progress-head">
      <strong>{{ label }}生成进度</strong>
      <span class="generation-progress-status">{{ statusLabel }}</span>
    </div>
    <template v-if="measured"><progress :value="measured.completed" :max="measured.total" :aria-label="`已保存 ${measured.completed}/${measured.total} ${measured.unit}`"/><small>已保存 {{ measured.completed }}/{{ measured.total }} {{ measured.unit }}，后续校验与保存以任务状态为准</small></template>
    <div v-else-if="!finished && job?.status !== 'UNKNOWN'" class="generation-indeterminate" role="progressbar" aria-label="正在处理，总进度未知" :aria-valuetext="stepText"><span /></div>
    <p class="generation-progress-step">{{ stepText }}</p>
    <p v-if="elapsed" class="generation-progress-meta">{{ elapsed }}<span v-if="!measured"> · 暂无可用的百分比进度</span></p>
  </section>
</template>

<style scoped>
.generation-progress { margin: 14px 0; padding: 14px 16px; border: 1px solid var(--line, #ddd); background: var(--surface-muted, #f7f8fa); border-radius: 12px; display: grid; gap: 8px; }
.generation-progress-head { display: flex; justify-content: space-between; align-items: baseline; gap: 10px; }
.generation-progress-head strong { font-size: 15px; }
.generation-progress-status { font-size: 12px; color: var(--muted, #667); border: 1px solid var(--line, #ddd); border-radius: 999px; padding: 2px 10px; background: var(--panel, #fff); }
.generation-progress-step { margin: 0; font-size: 14px; color: var(--text, #1f2329); }
.generation-progress-meta { margin: 0; font-size: 12px; color: var(--muted, #667); }
progress { width:100%; height:10px; accent-color:var(--accent); }
small { color:var(--muted); line-height:1.5; }
.generation-indeterminate { height:8px; border-radius:5px; background:var(--line); overflow:hidden; }
.generation-indeterminate span { display:block; height:100%; width:30%; background:var(--accent); border-radius:inherit; animation:generation-moving 1.8s infinite ease-in-out; }
@keyframes generation-moving { from { transform:translateX(-100%); } to { transform:translateX(340%); } }
@media(prefers-reduced-motion:reduce) { .generation-indeterminate span { animation:none; transform:translateX(100%); } }
</style>
