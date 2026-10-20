<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { agentApi } from '../../api/http'
const mode = ref('LIVE'); const days = ref(7); const status = ref(''); const page = ref(1)
const usage = ref<any>(); const workers = ref<any>(); const error = ref(''); const loading = ref(false)
async function load() {
  loading.value = true; error.value = ''
  try {
    const responses = await Promise.all([agentApi.get('/admin/usage', { params: { mode: mode.value, days: days.value, page: page.value, status: status.value || undefined } }), agentApi.get('/admin/workers')])
    usage.value = responses[0].data; workers.value = responses[1].data
  } catch { usage.value = undefined; workers.value = undefined; error.value = '调用台账或 Worker 注册数据读取失败。' }
  finally { loading.value = false }
}
function query() { page.value = 1; void load() }
onMounted(load)
</script>
<template>
  <section class="usage-worker" aria-label="模型调用台账与Worker心跳">
    <h3>模型调用台账与 Worker 心跳</h3>
    <div class="usage-filters"><el-select v-model="mode" aria-label="调用环境" @change="query"><el-option value="LIVE" label="真实环境调用"/><el-option value="TEST" label="隔离测试调用"/></el-select><el-select v-model="days" aria-label="用量统计天数" @change="query"><el-option :value="1" label="近1天"/><el-option :value="7" label="近7天"/><el-option :value="30" label="近30天"/></el-select><el-select v-model="status" aria-label="调用结果" @change="query"><el-option value="" label="全部结果"/><el-option value="SUCCEEDED" label="成功"/><el-option value="FAILED" label="失败"/><el-option value="STARTED" label="未闭合"/></el-select><el-button :loading="loading" @click="load">刷新调用与心跳</el-button></div>
    <el-alert v-if="error" type="error" :title="error" :closable="false"/>
    <template v-if="usage">
      <p>{{ mode === 'TEST' ? '隔离测试台账，与真实环境分开统计' : '真实环境台账' }} · UTC · 已记录 {{ usage.summary.calls }} 次调用 · {{ usage.summary.usage_status }}</p>
      <p>输入 Token：{{ usage.summary.input_tokens ?? 'UNKNOWN' }}；输出 Token：{{ usage.summary.output_tokens ?? 'UNKNOWN' }}；未知或不完整用量 {{ usage.summary.unknown_or_partial_calls }} 次。</p>
      <p v-if="usage.summary.unknown_or_partial_calls">已知部分小计：输入 {{ usage.summary.known_input_subtotal }}，输出 {{ usage.summary.known_output_subtotal }}，不是完整总量。</p>
      <p>只统计接入台账后的调用，历史用量未回填。缓存输入已包含在输入 Token 内；供应商账单与金额尚未核验。</p>
      <p>今日调用预留 {{ usage.day_call_budget.used }} / {{ usage.day_call_budget.limit ?? '未配置上限' }}。失败尝试仍占用额度。</p>
      <el-table :data="usage.items" aria-label="调用明细"><el-table-column prop="started_at" label="时间 UTC" min-width="180"/><el-table-column prop="feature" label="功能" min-width="160"/><el-table-column prop="model" label="请求模型" min-width="140"/><el-table-column prop="response_model" label="响应模型" min-width="140"/><el-table-column prop="user_id" label="用户" width="75"/><el-table-column prop="status" label="结果" min-width="110"/><el-table-column label="输入/输出" min-width="120"><template #default="{row}">{{ row.input_tokens ?? '?' }} / {{ row.output_tokens ?? '?' }}</template></el-table-column></el-table>
      <el-pagination v-model:current-page="page" :page-size="20" :total="usage.total" layout="prev,pager,next" @current-change="load"/>
      <details v-for="(rows, name) in usage.groups" :key="name"><summary>{{ name }} 分布</summary><p v-for="row in rows" :key="String(row.key)">{{ row.key ?? '未归属' }} · {{ row.calls }} 次 · 已知输入 {{ row.known_input_subtotal }} / 输出 {{ row.known_output_subtotal }} · 未知 {{ row.unknown_or_partial_calls }}</p></details>
    </template>
    <template v-if="workers"><h3>独立 Worker 注册</h3><p>{{ workers.status }} · 在线 {{ workers.online }}。旧版未注册进程不在此统计。</p><el-table :data="workers.items"><el-table-column prop="kind" label="类型"/><el-table-column prop="pid" label="PID"/><el-table-column prop="status" label="状态"/><el-table-column prop="heartbeat_at" label="最近心跳 UTC" min-width="180"/><el-table-column prop="batches" label="处理轮次"/></el-table></template>
  </section>
</template>
<style scoped>.usage-worker { min-width:0; padding:18px 0; }.usage-filters { display:flex; flex-wrap:wrap; gap:10px; }.usage-filters .el-select { width:165px; }.usage-worker p { overflow-wrap:anywhere; }</style>
