<script setup lang="ts">
import { computed } from 'vue'
import { DataAnalysis, CircleCheckFilled, UserFilled, WalletFilled } from '@element-plus/icons-vue'
import DashboardChart from './DashboardChart.vue'
import { number, spark } from './charts'
const props = defineProps<{ data?: any; workers?: any; budget?: any }>()
const percent = computed(() => props.budget?.limit == null || props.budget.limit === 0 ? null : props.budget.used / props.budget.limit * 100)
const change = (v: number|null|undefined, unit='%') => v == null ? '暂无可比较数据' : `${v >= 0 ? '↑' : '↓'} ${Math.abs(v).toFixed(1)}${unit}`
</script>
<template>
  <div class="dashboard-kpis">
    <article class="kpi"><span class="kpi-icon violet"><el-icon><DataAnalysis/></el-icon></span><div><h3>今日调用次数</h3><strong>{{ number(data?.today.calls) }}</strong><small :class="{'positive':data?.today.change_percent >= 0}">{{ change(data?.today.change_percent) }} <span>较昨日同期</span></small><p>模型 {{number(data?.today.models)}} · 工具 {{number(data?.today.tools)}} · UTC 今日</p></div><DashboardChart v-if="data" mini label="每日模型调用微趋势" :height="60" :option="spark(data.daily.map((d:any)=>d.calls),'#6554ff')"/></article>
    <article class="kpi"><span class="kpi-icon green"><el-icon><CircleCheckFilled/></el-icon></span><div><h3>任务成功率</h3><strong>{{ data?.completion.rate == null ? '—' : data.completion.rate.toFixed(1)+'%' }}</strong><small class="positive">{{ change(data?.completion.change_points,' 个百分点') }}</small><p>成功 {{ number(data?.completion.success) }} / 失败 {{ number(data?.completion.failed) }}</p></div><DashboardChart v-if="data" mini label="任务成功率微趋势" :height="60" :option="spark(data.task_daily.map((d:any)=>d.rate),'#20c997')"/></article>
    <article class="kpi"><span class="kpi-icon blue"><el-icon><UserFilled/></el-icon></span><div><h3>活跃 Worker <em>实时</em></h3><strong>{{ number(workers?.online) }} <b>/ {{ number(workers?.active_registered) }}</b></strong><small class="positive">{{ !workers ? '暂不可用' : workers.active_registered ? (workers.online/workers.active_registered*100).toFixed(1)+'% 在线' : '暂无有效注册' }}</small><p>不含已正常退出的注册</p></div><DashboardChart v-if="workers?.items.length" mini label="最近注册心跳状态" :height="60" :option="spark(workers.items.slice(0,7).reverse().map((w:any)=>w.status==='ONLINE'?1:0),'#7693ff','bar')"/></article>
    <article class="kpi"><span class="kpi-icon orange"><el-icon><WalletFilled/></el-icon></span><div><h3>预算使用率 <em>今日</em></h3><strong :class="{'text-value':percent==null}">{{ !budget ? '暂不可用' : budget.limit == null ? '未配置预算上限' : budget.limit === 0 ? '禁止新调用' : percent!.toFixed(0)+'%' }}</strong><el-progress v-if="budget?.limit != null" :percentage="Math.min(100,percent??100)" :show-text="false" :stroke-width="7" color="#5861ff"/><p>模型及工具 · 已预留 {{ number(budget?.used) }} / {{ !budget ? '—' : budget.limit == null ? '未设限' : number(budget.limit) }} 次</p></div></article>
  </div>
</template>
