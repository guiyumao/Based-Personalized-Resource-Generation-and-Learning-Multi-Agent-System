<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { agentApi } from '../api/http'
import type { LearningPathResponse } from '../api'

type TaskChange = { task_id: string; title: string; stage?: string }
type ValueChange = { task_id: string; title: string; before: unknown; after: unknown }
type Diff = {
  added_tasks: TaskChange[]
  removed_tasks: TaskChange[]
  kept_task_ids: string[]
  reordered_task_ids: string[]
  duration_changes: ValueChange[]
  difficulty_changes: ValueChange[]
  stage_changes: { stage_id?: string; change: string }[]
  overview_changed: boolean
  impact: {
    total_tasks_before: number; total_tasks_after: number
    estimated_days_before: number | null; estimated_days_after: number | null
    daily_minutes_before: number | null; daily_minutes_after: number | null
  }
}
type Proposal = {
  status: string; message: string; proposal_id: string; feedback_text: string; diff: Diff
}
const emit = defineEmits<{ updated: [path: LearningPathResponse] }>()
const feedbackText = ref('')
const loading = ref(false)
const error = ref('')
const proposal = ref<Proposal | null>(null)
const visible = ref(false)
const hasChanges = computed(() => {
  const diff = proposal.value?.diff
  if (!diff) return false
  return Boolean(diff.added_tasks.length || diff.removed_tasks.length || diff.reordered_task_ids.length
    || diff.duration_changes.length || diff.difficulty_changes.length || diff.stage_changes.length
    || diff.overview_changed || diff.impact.daily_minutes_before !== diff.impact.daily_minutes_after
    || diff.impact.estimated_days_before !== diff.impact.estimated_days_after)
})
const difficultyLabel = (value: unknown) => ({ foundation: '基础', intermediate: '中等', advanced: '进阶' } as Record<string, string>)[String(value)] ?? String(value)
async function preview() {
  const text = feedbackText.value.trim()
  if (!text) { ElMessage.warning('请先填写修改意见'); return }
  error.value = ''; loading.value = true
  try {
    proposal.value = (await agentApi.post('/paths/feedback/preview', { feedback_text: text })).data
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
    feedbackText.value = ''
    ElMessage.success('已按你的意见更新计划，刷新后结果保持一致')
  } catch (reason: any) { error.value = String(reason?.response?.data?.detail ?? reason?.message ?? '修改未生效，请重试') }
  finally { loading.value = false }
}
</script>

<template>
  <section class="plan-feedback" aria-label="计划制定反馈">
    <div>
      <strong>向 AI 提出修改意见</strong>
      <p>例如“太难了”“先学链表再学栈”“压缩到四周”“改成中文”。AI 会生成修改方案，你确认后才更新计划，已完成任务与成绩保留。</p>
    </div>
    <el-input v-model="feedbackText" type="textarea" :rows="2" maxlength="2000" show-word-limit aria-label="计划修改意见" placeholder="输入你的修改意见" />
    <el-button type="primary" :loading="loading" @click="preview">查看反馈方案</el-button>
    <el-alert v-if="error && !visible" :title="error" type="error" :closable="false" />

    <el-dialog v-model="visible" title="计划修改方案预览" width="min(680px, 94vw)" :close-on-click-modal="false">
      <template v-if="proposal">
        <p class="feedback-summary">{{ proposal.message }}</p>
        <table class="feedback-comparison"><thead><tr><th>项目</th><th>当前</th><th>确认后</th></tr></thead><tbody>
          <tr><td>任务总数</td><td>{{ proposal.diff.impact.total_tasks_before }}</td><td>{{ proposal.diff.impact.total_tasks_after }}</td></tr>
          <tr><td>每天学习分钟</td><td>{{ proposal.diff.impact.daily_minutes_before ?? '未记录' }}</td><td>{{ proposal.diff.impact.daily_minutes_after }}</td></tr>
          <tr><td>预计天数</td><td>{{ proposal.diff.impact.estimated_days_before ?? '未记录' }}</td><td>{{ proposal.diff.impact.estimated_days_after }}</td></tr>
        </tbody></table>

        <div v-if="hasChanges" class="feedback-changes">
          <div v-if="proposal.diff.added_tasks.length"><h4>新增任务</h4><ul><li v-for="t in proposal.diff.added_tasks" :key="t.task_id">{{ t.title }}<small v-if="t.stage"> · {{ t.stage }}</small></li></ul></div>
          <div v-if="proposal.diff.removed_tasks.length"><h4>删除/取消任务</h4><ul><li v-for="t in proposal.diff.removed_tasks" :key="t.task_id">{{ t.title }}</li></ul></div>
          <div v-if="proposal.diff.reordered_task_ids.length"><h4>调整顺序</h4><p>共 {{ proposal.diff.reordered_task_ids.length }} 个任务调整了先后顺序。</p></div>
          <div v-if="proposal.diff.duration_changes.length"><h4>调整时长</h4><ul><li v-for="c in proposal.diff.duration_changes" :key="c.task_id">{{ c.title }}：{{ c.before }} → {{ c.after }} 分钟</li></ul></div>
          <div v-if="proposal.diff.difficulty_changes.length"><h4>调整难度</h4><ul><li v-for="c in proposal.diff.difficulty_changes" :key="c.task_id">{{ c.title }}：{{ difficultyLabel(c.before) }} → {{ difficultyLabel(c.after) }}</li></ul></div>
          <div v-if="proposal.diff.overview_changed"><h4>计划概述</h4><p>概述内容已更新。</p></div>
        </div>
        <p v-else class="feedback-none">没有检测到需要修改的内容，请换一种表述再试。</p>
        <el-alert v-if="error" :title="error" type="error" :closable="false" />
      </template>
      <template #footer>
        <el-button :disabled="loading" @click="visible = false">保留原计划</el-button>
        <el-button type="primary" :disabled="!hasChanges" :loading="loading" @click="confirm">确认修改</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<style scoped>
.plan-feedback { display:grid; gap:12px; padding:16px; border:1px solid var(--line); border-radius:12px; margin-bottom:20px; background:var(--panel); }
.plan-feedback p { color:var(--muted); line-height:1.7; margin:0; }
.feedback-summary { margin:0 0 12px; color:var(--text); }
.feedback-comparison { width:100%; border-collapse:collapse; margin-bottom:14px; }
.feedback-comparison th,.feedback-comparison td { border-bottom:1px solid var(--line); padding:8px 10px; text-align:left; }
.feedback-changes { display:grid; gap:12px; }
.feedback-changes h4 { margin:0 0 6px; }
.feedback-changes ul { margin:0; padding-left:20px; line-height:1.8; }
.feedback-changes small { color:var(--muted); }
.feedback-none { color:var(--muted); }
</style>
