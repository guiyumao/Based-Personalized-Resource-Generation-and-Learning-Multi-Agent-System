<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { agentApi } from '../api/http'
import type { LearningPathResponse } from '../api'
import LearningContent from './LearningContent.vue'

const FEEDBACK_OPTIONS = [
  { value: 'too_hard', label: '太难' },
  { value: 'too_easy', label: '太简单' },
  { value: 'not_understood', label: '内容不理解' },
  { value: 'not_enough_time', label: '时间不足' },
  { value: 'already_mastered', label: '已经掌握' },
  { value: 'more_practice', label: '希望更多练习' },
  { value: 'more_video', label: '希望补充视频' },
  { value: 'more_illustration', label: '希望补充图文' },
] as const
type Diff = {
  added_tasks: { task_id: string; title: string }[]
  removed_tasks: { task_id: string; title: string }[]
  duration_changes: { task_id: string; title: string; before: unknown; after: unknown }[]
  difficulty_changes: { task_id: string; title: string; before: unknown; after: unknown }[]
  status_changes: { task_id: string; title: string; before: { completed: boolean }; after: { completed: boolean } }[]
  impact: { total_tasks_before: number; total_tasks_after: number }
}
type Proposal = { status: string; message: string; proposal_id: string; diff: Diff }
const props = defineProps<{ taskId: string }>()
const emit = defineEmits<{ updated: [path: LearningPathResponse] }>()
const loading = ref(false)
const error = ref('')
const proposal = ref<Proposal | null>(null)
const visible = ref(false)
const difficultyLabel = (v: unknown) => ({ foundation: '基础', intermediate: '中等', advanced: '进阶' } as Record<string, string>)[String(v)] ?? String(v)
async function preview(type: string) {
  error.value = ''; loading.value = true
  try {
    proposal.value = (await agentApi.post('/paths/task-feedback/preview', { task_id: props.taskId, feedback_type: type })).data
    if (proposal.value?.status === 'no_change') ElMessage.info(proposal.value.message)
    else visible.value = true
  } catch (reason: any) { error.value = String(reason?.response?.data?.detail ?? reason?.message ?? '反馈提交失败') }
  finally { loading.value = false }
}
async function confirm() {
  if (!proposal.value) return
  error.value = ''; loading.value = true
  try {
    const { data } = await agentApi.post(`/paths/feedback/${proposal.value.proposal_id}/confirm`)
    emit('updated', data.path)
    visible.value = false
    ElMessage.success('已按反馈更新计划，刷新后保持一致')
  } catch (reason: any) { error.value = String(reason?.response?.data?.detail ?? reason?.message ?? '修改未生效') }
  finally { loading.value = false }
}
</script>

<template>
  <el-popover placement="bottom-end" :width="220" trigger="click">
    <template #reference>
      <button type="button" class="feedback-trigger" @click.stop>反馈</button>
    </template>
    <div class="feedback-options">
      <button v-for="option in FEEDBACK_OPTIONS" :key="option.value" type="button" @click="preview(option.value)">{{ option.label }}</button>
    </div>
  </el-popover>

  <el-alert v-if="error && !visible" :title="error" type="error" :closable="false" />
  <el-dialog v-model="visible" title="任务反馈方案预览" width="min(560px, 94vw)" :close-on-click-modal="false">
    <template v-if="proposal">
      <LearningContent class="feedback-message" :content="proposal.message" />
      <div v-if="proposal.diff.added_tasks.length"><h4>新增任务</h4><ul><li v-for="t in proposal.diff.added_tasks" :key="t.task_id">{{ t.title }}</li></ul></div>
      <div v-if="proposal.diff.removed_tasks.length"><h4>移除任务</h4><ul><li v-for="t in proposal.diff.removed_tasks" :key="t.task_id">{{ t.title }}</li></ul></div>
      <div v-if="proposal.diff.difficulty_changes.length"><h4>难度调整</h4><ul><li v-for="c in proposal.diff.difficulty_changes" :key="c.task_id">{{ c.title }}：{{ difficultyLabel(c.before) }} → {{ difficultyLabel(c.after) }}</li></ul></div>
      <div v-if="proposal.diff.duration_changes.length"><h4>时长调整</h4><ul><li v-for="c in proposal.diff.duration_changes" :key="c.task_id">{{ c.title }}：{{ c.before }} → {{ c.after }} 分钟</li></ul></div>
      <div v-if="proposal.diff.status_changes.length"><h4>状态调整</h4><ul><li v-for="c in proposal.diff.status_changes" :key="c.task_id">{{ c.title }}：{{ c.before.completed ? '已完成' : '未完成' }} → {{ c.after.completed ? '已完成' : '未完成' }}</li></ul></div>
      <p class="muted">任务总数 {{ proposal.diff.impact.total_tasks_before }} → {{ proposal.diff.impact.total_tasks_after }}</p>
      <el-alert v-if="error" :title="error" type="error" :closable="false" />
    </template>
    <template #footer>
      <el-button :disabled="loading" @click="visible = false">保留原计划</el-button>
      <el-button type="primary" :loading="loading" @click="confirm">确认修改</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.feedback-trigger { border:1px solid var(--line); border-radius:10px; background:var(--panel-strong); color:var(--text); padding:7px 12px; font:inherit; cursor:pointer; }
.feedback-options { display:grid; gap:4px; }
.feedback-options button { text-align:left; border:0; background:none; padding:8px 10px; border-radius:8px; cursor:pointer; font:inherit; color:var(--text); }
.feedback-options button:hover { background:color-mix(in srgb, var(--accent) 10%, transparent); }
h4 { margin:12px 0 4px; }
ul { margin:0; padding-left:20px; line-height:1.8; }
.muted { color:var(--muted); }
</style>
