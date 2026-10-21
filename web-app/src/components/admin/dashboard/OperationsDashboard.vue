<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { agentApi } from '../../../api/http'
import DashboardChart from './DashboardChart.vue'
import DashboardKpiCards from './DashboardKpiCards.vue'
import WorkerHealthPanel from './WorkerHealthPanel.vue'
import CallRecordDetails from './CallRecordDetails.vue'
import TaskRecordDetails from './TaskRecordDetails.vue'
import {cartesian, number, operationName, palette, stateColors, stateLabels, statusNames, timestamp} from './charts'
const dateString=(d:Date)=>d.toISOString().slice(0,10)
const initial=new Date(), earlier=new Date(initial);earlier.setUTCDate(earlier.getUTCDate()-6)
const range=ref<string[]>([dateString(earlier),dateString(initial)]),preset=ref(7),mode=ref('LIVE'),grain=ref('day'),distributionView=ref('models'),metric=ref('calls')
const data=ref<any>(), workers=ref<any>(), budget=ref<any>(),recent=ref<any>(), loading=ref(false),updated=ref('')
const errors=ref<Record<string,string>>({}), callsOpen=ref(false),tasksOpen=ref(false),callSelection=ref<any>(),taskSelection=ref<any>()
const taskDetails=ref<InstanceType<typeof TaskRecordDetails>>()
const policy=ref<any>({day_call_limit:null,user_day_call_limit:null}),saving=ref(false),policyMessage=ref(''),policyLoaded=ref(false)
let request:AbortController|undefined
const dateParams=()=>({start:range.value[0],end:range.value[1]})
async function load(){
 if(!range.value?.[0]||!range.value?.[1])return
 request?.abort();const current=new AbortController();request=current;loading.value=true;errors.value={}
 data.value=undefined;workers.value=undefined;budget.value=undefined;recent.value=undefined;policyLoaded.value=false
 const sources=[['statistics','/admin/dashboard',data],['workers','/admin/workers',workers],['budget','/admin/model-budget',budget],['recent','/admin/operations/tasks',recent]] as const
 await Promise.allSettled(sources.map(async([key,url,target])=>{
  try{const r=await agentApi.get(url,{params:{...dateParams(),mode:mode.value,size:6},signal:current.signal,timeout:20000});if(current.signal.aborted)return;target.value=r.data;if(key==='budget'){policy.value={...r.data.configured};policyLoaded.value=true}}
  catch{if(!current.signal.aborted)errors.value[key]=({statistics:'用量统计',workers:'Worker 心跳',budget:'预算配置',recent:'最近任务'}[key])+'读取失败，请刷新重试。'}
 }))
 if(!current.signal.aborted){loading.value=false;updated.value=new Date().toISOString()}
}
function choose(days:number){preset.value=days;const end=new Date(),start=new Date(end);start.setUTCDate(start.getUTCDate()-days+1);range.value=[dateString(start),dateString(end)];void load()}
function changeRange(){preset.value=0;void load()}
const buckets=computed(()=>{
 const rows:any[]=data.value?.daily||[];if(grain.value==='day')return rows.map((r:any)=>({...r,end:r.date}))
 const result:any[]=[];for(let i=0;i<rows.length;i+=7){const group=rows.slice(i,i+7);result.push({date:group[0].date,end:group.at(-1).date,calls:group.reduce((a,r)=>a+r.calls,0),input:group.reduce((a,r)=>a+r.input,0),output:group.reduce((a,r)=>a+r.output,0)})}return result
})
const labels=computed(()=>buckets.value.map(r=>r.date.slice(5)))
const trendOption=computed(()=>cartesian(labels.value,((distributionView.value==='models'?data.value?.model_series:data.value?.tool_series)||[]).map((s:any,index:number)=>({name:s.name,type:'line',areaStyle:{opacity:.10},itemStyle:{color:palette[index%palette.length]},data:grain.value==='day'?s.data:buckets.value.map((_:any,i:number)=>s.data.slice(i*7,i*7+7).reduce((a:number,b:number)=>a+b,0))}))))
const distribution=computed(()=>distributionView.value==='models'?(data.value?.distribution||[]):(data.value?.tool_distribution||[]))
const totalDistribution=computed(()=>distribution.value.reduce((a:number,r:any)=>a+r.value,0))
const donutOption=computed(()=>({color:palette,tooltip:{trigger:'item',confine:true,renderMode:'richText',formatter:'{b}\n{c} 次 ({d}%)'},
 title:{text:number(totalDistribution.value),subtext:distributionView.value==='models'?'模型调用次数':'工具调用次数',left:'center',top:'36%',textStyle:{fontSize:26,color:'#202c52'},subtextStyle:{fontSize:11,color:'#8692af'}},
 series:[{type:'pie',radius:['66%','87%'],center:['50%','49%'],label:{show:false},emphasis:{scale:true},data:distribution.value}]}))
const budgetOption=computed(()=>{
 const m=metric.value,limit=budget.value?.day_call_budget.limit
 const unit=m==='rate'?'%':m==='calls'?'次':'Token'
 const title={calls:'模型及工具请求',input:'输入 Token（已知）',output:'输出 Token（已知）',total:'Token 总量（已知）',rate:'调用 / 当前上限'}[m]||m
 const values=buckets.value.map(r=>m==='total'?r.input+r.output:m==='rate'?(limit>0?r.calls/limit*100:null):r[m])
 const series:any[]=[{name:title,type:'bar',itemStyle:{borderRadius:[4,4,0,0]},data:m==='rate'&&grain.value==='week'?buckets.value.map(r=>limit>0?r.calls/(limit*((new Date(r.end).getTime()-new Date(r.date).getTime())/86400000+1))*100:null):values}]
 if(m==='calls'&&limit!=null)series.push({name:'当前每日上限参考（非历史配置）',type:'line',lineStyle:{type:'dashed',color:'#bac5e5'},itemStyle:{color:'#bac5e5'},data:buckets.value.map(r=>limit*((new Date(r.end).getTime()-new Date(r.date).getTime())/86400000+1))})
 return cartesian(labels.value,series,unit)
})
const taskGroups=computed(()=>{
 const groups=new Map<string,any>();for(const row of data.value?.tasks||[]){const key=`${row.kind}:${row.operation}`;if(!groups.has(key))groups.set(key,{key,kind:row.kind,operation:row.operation,name:row.kind==='knowledge'?'知识建设 · '+operationName(row.operation):operationName(row.operation),states:{}});const g=groups.get(key);g.states[row.state]=(g.states[row.state]||0)+row.count}return [...groups.values()]
})
const taskOption=computed(()=>{
 const option=cartesian(taskGroups.value.map(g=>g.name),Object.keys(stateLabels).filter(state=>taskGroups.value.some(g=>g.states[state])).map(state=>({name:stateLabels[state],type:'bar',stack:'tasks',itemStyle:{color:stateColors[state],borderRadius:[2,2,0,0]},data:taskGroups.value.map(g=>g.states[state]||0)})))
 return {...option,xAxis:{...option.xAxis,axisLabel:{fontSize:10,interval:0,rotate:25,formatter:(name:string)=>name.length>7?name.slice(0,6)+'…':name}}}
})
function openCalls(selection:any={}){callSelection.value={call_type:distributionView.value,...selection};callsOpen.value=true}
function selectTrend(event:any){const bucket=buckets.value[event.dataIndex];if(bucket)openCalls({model:event.seriesName,start:bucket.date,end:bucket.end})}
function selectDistribution(name:string){openCalls({model:name})}
function selectTask(event:any){const g=taskGroups.value[event.dataIndex];if(g){taskSelection.value={kind:g.kind,operation:g.operation,state:Object.keys(stateLabels).find(k=>stateLabels[k]===event.seriesName)};tasksOpen.value=true}}
function allTasks(){taskSelection.value={};tasksOpen.value=true}
async function savePolicy(){
 if(!policyLoaded.value)return
 saving.value=true;policyMessage.value=''
 try{await agentApi.put('/admin/model-budget',{day_call_limit:policy.value.day_call_limit??null,user_day_call_limit:policy.value.user_day_call_limit??null});policyMessage.value='调用预算已保存并生效。';await load()}catch{policyMessage.value='预算保存失败，请检查权限和数值。'}finally{saving.value=false}
}
onMounted(load);onBeforeUnmount(()=>request?.abort())
</script>
<template>
 <section class="operations-dashboard" aria-label="管理员运营数据看板">
  <header class="dashboard-toolbar"><div><h1>数据看板</h1><p>模型用量、任务执行与服务运行一览</p></div><div class="dashboard-controls"><el-date-picker v-model="range" type="daterange" value-format="YYYY-MM-DD" range-separator="~" :clearable="false" start-placeholder="开始日期" end-placeholder="结束日期" aria-label="看板日期范围" @change="changeRange"/><div class="range-presets"><button v-for="days in [7,30,90]" :key="days" :class="{active:preset===days}" @click="choose(days)">近 {{days}} 天</button></div><el-button :loading="loading" @click="load">刷新</el-button></div></header>
  <div class="dashboard-meta"><span>统计时区 UTC · 自然日 · {{updated?'最后更新 '+timestamp(updated):'正在读取'}}</span><div><el-select v-model="mode" aria-label="看板调用环境" @change="load"><el-option label="真实环境" value="LIVE"/><el-option label="隔离测试环境" value="TEST"/></el-select><el-select v-model="grain" aria-label="图表聚合粒度"><el-option label="按日聚合" value="day"/><el-option label="每7天聚合" value="week"/></el-select></div></div>
  <el-alert v-for="(message,key) in errors" :key="key" :title="message" type="error" :closable="false" show-icon/>
  <el-skeleton v-if="loading" :rows="4" animated/>
  <DashboardKpiCards v-else :data="data" :workers="workers" :budget="budget?.day_call_budget"/>
  <p v-if="!data" class="dashboard-note" role="status">{{loading?'正在加载统计图表…':'统计图表未加载，请刷新重试；未使用替代统计数据。'}}</p><div class="dashboard-main-grid">
   <article class="dashboard-card model-trend"><header><h2>{{preset?'最近 '+preset+' 天':'所选时段'}}{{distributionView==='models'?'模型':'工具'}}调用趋势</h2><button class="text-button" @click="openCalls()">调用明细 →</button></header><DashboardChart v-if="data" label="模型调用趋势" :option="trendOption" :height="240" :empty="!(distributionView==='models'?data?.model_summary.calls:data?.tool_summary.calls)" @select="selectTrend"/><p class="dashboard-note">模型按请求名称统计，工具按网关记录单独切换；每次尝试计一次（含失败）。</p></article>
   <article class="dashboard-card model-distribution"><header><h2>{{distributionView==='models'?'模型调用占比':'工具调用占比'}}</h2><el-select v-model="distributionView" aria-label="分布统计口径"><el-option label="模型" value="models"/><el-option label="工具" value="tools"/></el-select></header><DashboardChart v-if="data" label="模型与工具分布" :option="donutOption" :height="208" :empty="!totalDistribution" @select="selectDistribution($event.name)"/><div class="distribution-legend"><button v-for="(row,index) in distribution" :key="row.name" @click="selectDistribution(row.name)"><i :style="{background:palette[Number(index)%palette.length]}"/><span>{{row.name}}</span><strong>{{number(row.value)}}</strong><small>{{totalDistribution?(row.value/totalDistribution*100).toFixed(1):'0'}}%</small></button></div><p v-if="distributionView==='tools'" class="dashboard-note">来源 deepseek-tools 逐次台账，与模型分开计数；含失败尝试，不与预算预留混用。</p></article>
   <WorkerHealthPanel :workers="workers" :error="errors.workers"/>
   <article class="dashboard-card budget-chart"><header><h2>预算与 Token 消耗</h2><el-select v-model="metric" aria-label="预算图指标"><el-option value="calls" label="每日调用次数"/><el-option value="input" label="输入 Token"/><el-option value="output" label="输出 Token"/><el-option value="total" label="已知 Token 总量"/><el-option value="rate" label="预算使用率"/></el-select></header><DashboardChart v-if="data" label="预算与 Token 消耗趋势" :option="budgetOption" :height="206" :empty="!data?.summary.calls || metric==='rate' && !(budget?.day_call_budget.limit>0)" @select="openCalls({start:buckets[$event.dataIndex]?.date,end:buckets[$event.dataIndex]?.end})"/><p class="dashboard-note">{{!budget?'预算配置未加载。':budget.day_call_budget.limit==null?'未配置预算上限。':'上限线仅表示当前配置参考；历史配置未回填。'}} {{data?.model_summary.unknown_or_partial_calls?data.model_summary.unknown_or_partial_calls+' 次用量不完整，仅显示已知小计。':''}}缓存已含在输入中；失败调用的已知用量计入。费用未核验。</p></article>
   <article class="dashboard-card task-chart"><header><h2>各类任务执行情况</h2><button class="text-button" @click="allTasks">查看全部 →</button></header><DashboardChart v-if="data" label="各类任务执行情况" :option="taskOption" :height="206" :empty="!taskGroups.length" @select="selectTask"/><p class="dashboard-note">成功率 = 成功 /（成功 + 失败），排除执行中、等待及取消。按任务创建时间归属周期；全部环境任务。</p></article>
   <article class="dashboard-card recent-tasks"><header><h2>最近任务记录</h2><button class="text-button" @click="allTasks">查看更多 →</button></header><p v-if="errors.recent" class="error" role="alert">{{errors.recent}}</p><div class="recent-table-scroll" v-else><table class="recent-table"><thead><tr><th>任务名称</th><th>类型</th><th>状态</th><th>创建时间 UTC</th></tr></thead><tbody><tr v-for="row in recent?.items||[]" :key="`${row.kind}-${row.id}`"><td><button class="text-button" :aria-label="`查看${row.kind}任务${row.id}`" @click="taskDetails?.detail(row)">{{row.kind}} #{{row.id}}</button></td><td :title="row.operation">{{operationName(row.operation)}}</td><td><span class="task-status" :class="row.status" :title="row.status">{{statusNames[row.status]||row.status}}</span></td><td>{{timestamp(row.created_at).slice(5,16)}}</td></tr></tbody></table><p v-if="recent&&!recent.items.length" class="dashboard-note">所选范围暂无任务</p></div><p class="dashboard-note">任务详情保留执行尝试、阶段记录、时间和心跳。</p></article>
  </div>
  <details class="dashboard-card budget-settings"><summary>调用预算配置与统计口径</summary><p class="dashboard-note">模型及工具按环境分别计数；工具以 deepseek-tools 服务商标记区分，不按名称猜测。工具预算预留另见原有运营明细。日预算按 UTC 统计所有调用尝试，含失败；当前额度计数为预算预留，不能作为供应商账单。接入台账前的历史调用未回填。任务成功率按创建周期统计，与上一同长度周期比较。</p><template v-if="policyLoaded"><div class="detail-filters"><label>平台每日调用上限 <el-input-number v-model="policy.day_call_limit" :min="0" :max="1000000" aria-label="平台每日调用上限"/></label><label>每用户每日调用上限 <el-input-number v-model="policy.user_day_call_limit" :min="0" :max="1000000" aria-label="每用户每日调用上限"/></label><el-button :loading="saving" @click="savePolicy">保存调用预算</el-button></div><p class="dashboard-note">留空不额外设限；0 禁止新调用。环境限制仍生效。有效平台上限 {{budget?.effective.day_call_limit??'未设限'}}，每用户 {{budget?.effective.user_day_call_limit??'未设限'}}。</p></template><p v-else class="dashboard-note">预算配置尚未成功读取，请刷新后重试。</p><p role="status">{{policyMessage}}</p></details>
  <CallRecordDetails v-model:open="callsOpen" :range="range" :mode="mode" :selection="callSelection"/>
  <TaskRecordDetails ref="taskDetails" v-model:open="tasksOpen" :range="range" :selection="taskSelection"/>
 </section>
</template>
<style src="./dashboard.css"></style>
