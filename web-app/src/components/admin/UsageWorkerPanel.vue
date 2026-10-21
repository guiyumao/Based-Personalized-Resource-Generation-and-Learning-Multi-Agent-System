<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import UsageChart from './UsageChart.vue'
import { agentApi } from '../../api/http'
const mode = ref('LIVE'); const days = ref(7); const status = ref(''); const page = ref(1)
const usage = ref<any>(); const workers = ref<any>(); const error = ref(''); const loading = ref(false)
const policy = ref<any>({day_call_limit:null,user_day_call_limit:null}); const effective = ref<any>({}); const policySaved = ref(false)
const number = (value: number | null | undefined) => value == null ? '未知' : value.toLocaleString()
const featureNames: Record<string, string> = {agent_coordination:'智能体协作',resource_generation:'资源生成',exercise_generation:'练习生成',qa:'智能问答',path_adaptation:'路径调整'}
const daily = computed(() => {
  const groups = new Map((usage.value?.groups.daily ?? []).map((row: any) => [String(row.key), row]))
  const now = new Date()
  return Array.from({length: days.value + 1}, (_, index) => {
    const date = new Date(now)
    date.setUTCDate(date.getUTCDate() - days.value + index)
    const label = date.toISOString().slice(0, 10)
    const row = groups.get(label) as any
    return {label, value: row?.calls ?? 0, incoming: row?.known_input_subtotal ?? 0, outgoing: row?.known_output_subtotal ?? 0}
  })
})
const tokenTrend = computed(() => daily.value.map(row => ({label:row.label, value:row.incoming, secondary:row.outgoing})))
function distribution(name: string) {
  const rows = [...(usage.value?.groups[name] ?? [])].sort((a:any,b:any) => b.calls-a.calls)
  const result = rows.slice(0,6).map((row:any) => ({label: name === 'features' ? featureNames[row.key] || row.key || '未归属' : String(row.key ?? '未归属'), value:row.calls}))
  if (rows.length > 6) result.push({label:'其他', value:rows.slice(6).reduce((sum:number,row:any) => sum+row.calls,0)})
  return result
}
const budgetPercent = computed(() => {
  const budget=usage.value?.day_call_budget
  return !budget || budget.limit == null ? 0 : budget.limit === 0 ? 100 : Math.min(100, Math.round(budget.used / budget.limit * 100))
})
let loadVersion = 0
async function load() {
  const version = ++loadVersion
  loading.value = true; error.value = ''
  try {
    const responses = await Promise.all([agentApi.get('/admin/usage', { params: { mode: mode.value, days: days.value, page: page.value, status: status.value || undefined } }), agentApi.get('/admin/workers'), agentApi.get('/admin/model-budget')])
    if (version !== loadVersion) return
    usage.value = responses[0].data; workers.value = responses[1].data
    policy.value=responses[2].data.configured; effective.value=responses[2].data.effective
  } catch { if (version === loadVersion) { usage.value = undefined; workers.value = undefined; error.value = '调用台账或 Worker 注册数据读取失败。' } }
  finally { if (version === loadVersion) loading.value = false }
}
function query() { page.value = 1; void load() }
async function savePolicy() {
  policySaved.value=false
  try { await agentApi.put('/admin/model-budget',{day_call_limit:policy.value.day_call_limit??null,user_day_call_limit:policy.value.user_day_call_limit??null}); await load(); policySaved.value=true }
  catch {error.value='预算保存失败，请检查权限和数值。'}
}
onMounted(load)
</script>
<template>
  <section class="usage-worker" aria-label="模型调用台账与Worker心跳">
    <header class="dashboard-heading"><div><span class="eyebrow">运行监测 / AI 用量</span><h3>模型调用台账与 Worker 心跳</h3><p>查看调用趋势、模型分布与服务运行状态</p></div><span class="environment">{{ mode === 'LIVE' ? '真实环境' : '隔离测试环境' }} · UTC</span></header>
    <details class="budget-settings"><summary>设置模型调用预算</summary><p>按 UTC 日累计所有调用尝试，包括失败。留空表示不额外设限，0 表示禁止新调用；保存后 API 与 Worker 自动生效，环境上限仍有效。</p><label>平台每日调用上限 <el-input-number v-model="policy.day_call_limit" :min="0" :max="1000000" aria-label="平台每日调用上限"/></label><label>每用户每日调用上限 <el-input-number v-model="policy.user_day_call_limit" :min="0" :max="1000000" aria-label="每用户每日调用上限"/></label><el-button @click="savePolicy">保存调用预算</el-button><p v-if="policySaved">调用预算已保存并生效。</p><p>有效平台上限 {{effective.day_call_limit??'未设限'}}；有效用户上限 {{effective.user_day_call_limit??'未设限'}}。</p></details>
    <div class="usage-filters"><el-select v-model="mode" aria-label="调用环境" @change="query"><el-option value="LIVE" label="真实环境调用"/><el-option value="TEST" label="隔离测试调用"/></el-select><el-select v-model="days" aria-label="用量统计天数" @change="query"><el-option :value="1" label="近1天"/><el-option :value="7" label="近7天"/><el-option :value="30" label="近30天"/></el-select><el-select v-model="status" placeholder="全部结果" aria-label="调用结果" @change="query"><el-option value="" label="全部结果"/><el-option value="SUCCEEDED" label="成功"/><el-option value="FAILED" label="失败"/><el-option value="STARTED" label="未闭合"/></el-select><el-button :loading="loading" @click="load">刷新调用与心跳</el-button></div>
    <el-alert v-if="error" type="error" :title="error" :closable="false"/>
    <template v-if="usage">
      <div class="metric-grid">
        <article class="metric blue"><span>模型调用</span><strong>{{ number(usage.summary.calls) }}<small>次</small></strong><p>已记录 {{ usage.summary.calls }} 次调用 · 近 {{ days }} 天</p></article>
        <article class="metric green"><span>输入 Token{{ usage.summary.input_tokens == null ? ' · 已知小计' : '' }}</span><strong>{{ number(usage.summary.known_input_subtotal) }}</strong><p>{{ usage.summary.input_tokens == null ? '统计不完整，完整总量未知' : '包含缓存输入，不重复计数' }}</p></article>
        <article class="metric amber"><span>输出 Token{{ usage.summary.output_tokens == null ? ' · 已知小计' : '' }}</span><strong>{{ number(usage.summary.known_output_subtotal) }}</strong><p>{{ usage.summary.output_tokens == null ? '统计不完整，完整总量未知' : '当前筛选下的已记录用量' }}</p></article>
        <article class="metric violet"><span>在线 Worker</span><strong>{{ number(workers?.online) }}<small>/ {{ workers?.items.length ?? '—' }} 已注册</small></strong><p>{{ usage.summary.unknown_or_partial_calls }} 次调用用量未知或不完整</p></article>
      </div>
      <div class="charts-grid">
        <UsageChart title="每日模型调用趋势" :rows="daily" :legends="['调用次数']"/>
        <UsageChart title="功能调用分布" kind="donut" :rows="distribution('features')"/>
        <UsageChart :title="usage.summary.unknown_or_partial_calls ? '每日 Token 用量（已知部分）' : '每日 Token 用量'" :rows="tokenTrend" :legends="['输入 Token','输出 Token']"/>
        <UsageChart title="请求模型分布" kind="donut" :rows="distribution('models')"/>
      </div>
      <div class="budget-overview"><div><h4>今日调用预算</h4><p>已预留 <strong>{{ number(usage.day_call_budget.used) }}</strong> / {{ usage.day_call_budget.limit == null ? '未配置上限' : number(usage.day_call_budget.limit) }} 次 · 失败尝试仍占用额度</p></div><div class="budget-meter"><el-progress :percentage="budgetPercent" :show-text="false" :status="usage.day_call_budget.limit != null && usage.day_call_budget.used >= usage.day_call_budget.limit ? 'exception' : undefined"/><span>{{ usage.day_call_budget.limit == null ? '当前未设调用上限' : `已使用 ${budgetPercent}%` }}</span></div></div>
      <p class="coverage-note">{{ mode === 'TEST' ? '隔离测试台账，与真实环境分开统计。' : '' }}只统计接入台账后的调用，历史用量未回填。缓存输入已包含在输入 Token 内；供应商账单与金额尚未核验。{{ usage.summary.unknown_or_partial_calls ? '部分 Token 未知，图表仅展示已知小计。' : '' }}</p>
      <div class="detail-heading"><h4>调用明细</h4><span>共 {{ usage.total }} 条 · 按时间倒序</span></div>
      <el-table :data="usage.items" aria-label="调用明细"><el-table-column prop="started_at" label="时间 UTC" min-width="180"/><el-table-column prop="feature" label="功能" min-width="160"/><el-table-column prop="model" label="请求模型" min-width="140"/><el-table-column prop="response_model" label="响应模型" min-width="140"/><el-table-column prop="user_id" label="用户" width="75"/><el-table-column prop="status" label="结果" min-width="110"/><el-table-column label="输入/输出" min-width="120"><template #default="{row}">{{ row.input_tokens ?? '?' }} / {{ row.output_tokens ?? '?' }}</template></el-table-column></el-table>
      <el-pagination v-model:current-page="page" :page-size="20" :total="usage.total" layout="prev,pager,next" @current-change="load"/>
      <details class="budget-settings"><summary>更多分组明细</summary><div v-for="(rows, name) in usage.groups" :key="name"><h4>{{ ({models:'请求模型',providers:'供应商',features:'功能',users:'用户',daily:'日期 UTC'} as Record<string,string>)[name] || name }}</h4><p v-for="row in rows" :key="String(row.key)">{{ row.key ?? '未归属' }} · {{ row.calls }} 次 · 已知输入 {{ row.known_input_subtotal }} / 输出 {{ row.known_output_subtotal }} · 未知 {{ row.unknown_or_partial_calls }}</p></div></details>
    </template>
    <template v-if="workers"><h3>独立 Worker 注册</h3><p>{{ workers.status }} · 在线 {{ workers.online }}。旧版未注册进程不在此统计。</p><el-table :data="workers.items"><el-table-column prop="kind" label="类型"/><el-table-column prop="pid" label="PID"/><el-table-column prop="status" label="状态"/><el-table-column prop="heartbeat_at" label="最近心跳 UTC" min-width="180"/><el-table-column prop="batches" label="处理轮次"/></el-table></template>
  </section>
</template>
<style scoped>
.usage-worker{min-width:0;padding:8px 0 24px;color:var(--text-primary,#27364e)}.dashboard-heading{display:flex;justify-content:space-between;gap:16px;align-items:center;margin:0 0 22px}.eyebrow{font-size:11px;letter-spacing:1px;color:#8491a5}.dashboard-heading h3{font-size:23px;line-height:1.4;margin:8px 0}.dashboard-heading p{margin:0;color:#8491a5;font-size:13px}.environment{font-size:12px;white-space:nowrap;padding:8px 12px;border-radius:20px;background:#edf4ff;color:#527ac8}.budget-settings{border:1px solid var(--border-color,#e7ebf2);background:var(--surface-card,#fff);border-radius:10px;padding:12px 16px;margin-bottom:18px;font-size:13px}.budget-settings summary{cursor:pointer;color:#527ac8}.budget-settings label{display:inline-flex;align-items:center;gap:10px;margin:8px 16px 8px 0}.usage-filters{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:22px}.usage-filters .el-select{width:165px}.metric-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px;margin-bottom:20px}.metric{position:relative;overflow:hidden;min-width:0;border:1px solid var(--border-color,#e7ebf2);border-radius:12px;padding:20px;background:var(--surface-card,#fff);box-shadow:0 3px 12px #233b6410;border-top:3px solid var(--accent)}.metric:after{content:'';position:absolute;width:70px;height:70px;border:15px solid var(--accent);opacity:.06;right:-16px;bottom:-25px;border-radius:50%;pointer-events:none}.metric>span{font-size:12px;color:#7a89a0}.metric strong{display:block;font-size:28px;line-height:1.5;margin:10px 0 3px;font-variant-numeric:tabular-nums}.metric small{font-size:11px;font-weight:400;margin-left:6px;color:#8a95a6}.metric p{font-size:11px;color:#8a95a6;margin:0}.blue{--accent:#5385ee}.green{--accent:#50c5a0}.amber{--accent:#f0b44c}.violet{--accent:#9975df}.charts-grid{display:grid;grid-template-columns:minmax(0,1.65fr) minmax(0,1fr);gap:18px;margin-bottom:20px}.budget-overview{display:flex;align-items:center;justify-content:space-between;gap:24px;border:1px solid var(--border-color,#e7ebf2);border-radius:12px;padding:18px 22px;background:var(--surface-card,#fff)}h4{margin:0;font-size:15px}.budget-overview p,.coverage-note{font-size:12px;color:#8491a5;line-height:1.8}.budget-overview p{margin:7px 0 0}.budget-meter{width:32%;min-width:130px}.budget-meter span{display:block;font-size:11px;color:#8491a5;margin-top:9px}.coverage-note{margin:14px 0 22px}.detail-heading{display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:14px}.detail-heading span{font-size:12px;color:#8491a5}.el-pagination{margin:16px 0 28px}.usage-worker p{overflow-wrap:anywhere}@media(max-width:1100px){.metric-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:700px){.dashboard-heading{align-items:flex-start;flex-direction:column}.dashboard-heading h3{font-size:19px}.charts-grid{grid-template-columns:minmax(0,1fr)}.metric-grid{gap:10px}.metric{padding:14px}.metric strong{font-size:23px}.budget-overview{align-items:stretch;flex-direction:column;gap:12px}.budget-meter{width:100%}.usage-filters .el-select{width:calc(50% - 5px)}.budget-settings label{display:flex;flex-wrap:wrap}.detail-heading{flex-wrap:wrap}}
</style>
