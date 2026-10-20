<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { agentApi } from '../api/http'
import type { LearningPathResponse } from '../api'

type Proposal = {
  status: string; message: string; proposal_id: string
  before: { daily_minutes: number | null; task_count: number; estimated_days: number }
  after: { daily_minutes: number | null; task_count: number; estimated_days: number }
  added_tasks: { task_id: string; title: string; objective: string }[]
  evidence: { name: string; graded_answers: number; accuracy_percent: number }[]
}
const emit = defineEmits<{ updated: [path: LearningPathResponse] }>()
const dailyMinutes = ref(45)
const loading = ref(false)
const error = ref('')
const proposal = ref<Proposal | null>(null)
const visible = ref(false)
async function preview() {
  error.value = ''; loading.value = true
  try {
    proposal.value = (await agentApi.post('/paths/adaptation/preview', { daily_minutes: dailyMinutes.value })).data
    if (proposal.value?.status === 'no_change') ElMessage.info(proposal.value.message)
    else visible.value = true
  } catch (reason: any) { error.value = String(reason?.response?.data?.detail ?? reason?.message ?? '调整预览失败') }
  finally { loading.value = false }
}
async function confirm() {
  if (!proposal.value) return
  error.value = ''; loading.value = true
  try {
    const { data } = await agentApi.post(`/paths/adaptation/${proposal.value.proposal_id}/confirm`)
    emit('updated', data.path)
    visible.value = false
    ElMessage.success('已确认调整，学习目录已更新')
  } catch (reason: any) { error.value = String(reason?.response?.data?.detail ?? reason?.message ?? '调整未生效，请重试') }
  finally { loading.value = false }
}
</script>

<template>
  <section class="plan-adaptation" aria-label="学情驱动计划调整">
    <div><strong>根据学情调整后续计划</strong><p>近30天同知识点至少3次判分、正确率低于60%时建议补强；确认后才修改。</p></div>
    <label>每天可用分钟 <el-input-number v-model="dailyMinutes" :min="5" :max="480" :step="5" /></label>
    <el-button :loading="loading" @click="preview">预览调整</el-button>
    <el-alert v-if="error && !visible" :title="error" type="error" :closable="false" />
    <el-dialog v-model="visible" title="确认学习计划变化" width="min(620px, 94vw)" :close-on-click-modal="false">
      <template v-if="proposal">
        <p>{{ proposal.message }}</p>
        <table class="adaptation-comparison"><thead><tr><th>项目</th><th>当前</th><th>确认后</th></tr></thead><tbody>
          <tr><td>任务总数</td><td>{{ proposal.before.task_count }}</td><td>{{ proposal.after.task_count }}</td></tr>
          <tr><td>每天学习分钟</td><td>{{ proposal.before.daily_minutes ?? '未记录' }}</td><td>{{ proposal.after.daily_minutes }}</td></tr>
          <tr><td>预计剩余天数</td><td>原计划估计 {{ proposal.before.estimated_days }}</td><td>{{ proposal.after.estimated_days }}</td></tr>
        </tbody></table>
        <ul><li v-for="evidence in proposal.evidence" :key="evidence.name">{{ evidence.name }}：{{ evidence.graded_answers }} 次判分，正确率 {{ evidence.accuracy_percent }}%（练习证据，不能代表整体能力）。</li></ul>
        <ul><li v-for="task in proposal.added_tasks" :key="task.task_id">{{ task.title }}</li></ul>
        <p v-if="!proposal.added_tasks.length">未新增补强任务，仅按可用时间重算剩余安排。</p>
        <el-alert v-if="error" :title="error" type="error" :closable="false" />
      </template>
      <template #footer><el-button :disabled="loading" @click="visible = false">保留原计划</el-button><el-button type="primary" :loading="loading" @click="confirm">确认应用调整</el-button></template>
    </el-dialog>
  </section>
</template>

<style scoped>
.plan-adaptation { display:flex; flex-wrap:wrap; gap:14px; align-items:center; padding:16px; border:1px solid var(--line); border-radius:12px; margin-bottom:20px; background:var(--panel); }
.plan-adaptation>div { flex:1; min-width:180px; }.plan-adaptation p { color:var(--muted); line-height:1.7; }.plan-adaptation label { display:flex; align-items:center; flex-wrap:wrap; gap:8px; }
.adaptation-comparison { width:100%; border-collapse:collapse; }.adaptation-comparison th,.adaptation-comparison td { border-bottom:1px solid var(--line); padding:10px; text-align:left; } li { line-height:1.8; }
</style>
