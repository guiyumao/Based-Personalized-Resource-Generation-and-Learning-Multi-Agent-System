<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { agentApi } from '../../api/http'
import UsageWorkerPanel from './UsageWorkerPanel.vue'
type Task = { kind: string; id: number; user_id: number; operation: string; status: string; attempt: number; heartbeat_at: string | null; lease_observation: string; error_code: string }
type Operations = { counts: Record<string, Record<string, number>>; recent_tasks: Task[]; daily_tasks: {kind: string; date: string; count: number}[]; knowledge_budget_reservations: {scope: string; model_calls: number; reserved_input_tokens: number; reserved_output_tokens: number}[]; as_of: string }
const data = ref<Operations>(); const error = ref(''); const loading = ref(false); const days = ref(7)
const selected = ref<any>(); const dialog = ref(false)
async function load() {
  loading.value = true; error.value = ''
  try { data.value = (await agentApi.get('/admin/operations', { params: { days: days.value } })).data }
  catch { data.value = undefined; error.value = '任务运营数据暂不可用，请稍后刷新。' }
  finally { loading.value = false }
}
async function detail(task: Task) {
  try { selected.value = (await agentApi.get(`/admin/operations/tasks/${task.kind}/${task.id}`)).data; dialog.value = true }
  catch { error.value = '无法读取任务执行记录。' }
}
onMounted(load)
</script>
<template>
  <section class="workspace-panel task-operations" aria-label="持久任务运营概览">
    <div id="model-usage"><UsageWorkerPanel /></div>
    <div class="action-row"><el-select v-model="days" aria-label="任务统计天数" style="max-width:180px"><el-option :value="1" label="近1天"/><el-option :value="7" label="近7天"/><el-option :value="30" label="近30天"/></el-select><el-button :loading="loading" @click="load">刷新运营数据</el-button></div>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <template v-if="data">
      <p>统计时区 UTC · {{ data.as_of }}</p>
      <div v-for="(counts, kind) in data.counts" :key="kind"><strong>{{ kind === 'assistant' ? '学习助手任务' : '知识建设任务' }}</strong><span v-for="(count, status) in counts" :key="status" class="task-count">{{ status }} {{ count }}</span><span v-if="!Object.keys(counts).length">当前时段无任务</span></div>
      <details><summary>知识建设预算预留</summary><p v-if="!data.knowledge_budget_reservations.length">当前日/月无预算预留记录。</p><p v-for="row in data.knowledge_budget_reservations" :key="row.scope">{{ row.scope }} · 模型调用预留 {{ row.model_calls }} · 输入预留 {{ row.reserved_input_tokens }} · 输出预留 {{ row.reserved_output_tokens }}</p></details>
      <el-table :data="data.recent_tasks" style="width:100%"><el-table-column label="任务" min-width="140"><template #default="{ row }">{{ row.kind }} #{{ row.id }}</template></el-table-column><el-table-column prop="operation" label="功能" min-width="130"/><el-table-column prop="status" label="状态" min-width="120"/><el-table-column prop="attempt" label="执行代次" width="95"/><el-table-column prop="lease_observation" label="任务心跳" min-width="100"/><el-table-column label="执行记录" width="100"><template #default="{ row }"><el-button size="small" @click="detail(row)">查看</el-button></template></el-table-column></el-table>
      <details><summary>每日任务分布（UTC）</summary><p v-for="row in data.daily_tasks" :key="`${row.kind}-${row.date}`">{{ row.date }} · {{ row.kind }} · {{ row.count }}</p></details>
    </template>
    <el-dialog v-model="dialog" append-to-body title="任务执行记录" width="min(760px, 94vw)"><template v-if="selected"><p>{{ selected.kind }} #{{ selected.id }} · {{ selected.operation }} · {{ selected.status }}</p><p>用户 #{{ selected.user_id }} · 代次 {{ selected.attempt }} · 错误代码 {{ selected.error_code || '无' }}</p><p>最近心跳 {{ selected.heartbeat_at || '未知' }}</p><el-table :data="selected.stages"><el-table-column prop="agent" label="智能体"/><el-table-column prop="status" label="状态"/><el-table-column prop="elapsed_ms" label="耗时 ms"/></el-table><h4>执行尝试</h4><el-table :data="selected.attempts"><el-table-column prop="attempt" label="代次" width="75"/><el-table-column prop="status" label="状态"/><el-table-column prop="started_at" label="开始 UTC" min-width="180"/><el-table-column prop="finished_at" label="结束 UTC" min-width="180"/><el-table-column prop="error_code" label="错误代码"/></el-table><p>显示接入记录后的执行尝试；历史尝试未回填，硬退出的未闭合记录会在接管时更新。</p></template></el-dialog>
  </section>
</template>
<style scoped>.task-count { display:inline-block; padding:6px 10px; }.task-operations { min-width:0; }.task-operations p { overflow-wrap:anywhere; }</style>
