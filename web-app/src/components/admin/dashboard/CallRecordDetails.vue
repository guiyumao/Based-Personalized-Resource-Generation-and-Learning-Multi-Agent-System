<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { agentApi } from '../../../api/http'
import { number, operationName, statusNames, timestamp } from './charts'
const props = defineProps<{ open: boolean; range: string[]; mode: string; selection?: {model?:string;start?:string;end?:string;call_type?:string} }>()
const emit = defineEmits<{ 'update:open':[value:boolean] }>()
const callType=ref(''), search=ref(''), model=ref(''), feature=ref(''), status=ref(''), page=ref(1), dates=ref<string[]>([])
const payload=ref<any>(), error=ref(''), loading=ref(false), exporting=ref(false), selected=ref<any>()
let request: AbortController|undefined
const params = ()=>({start:dates.value[0],end:dates.value[1],mode:props.mode,search:search.value||undefined,model:model.value||undefined,feature:feature.value||undefined,status:status.value||undefined,page:page.value,call_type:callType.value||undefined})
async function load(reset=false) {
 if(reset)page.value=1
 request?.abort();const current=new AbortController();request=current
 loading.value=true;error.value='';payload.value=undefined
 try {const r=await agentApi.get('/admin/usage',{params:params(),signal:current.signal,timeout:20000});if(!current.signal.aborted)payload.value=r.data}
 catch {if(!current.signal.aborted)error.value='调用记录读取失败，请重试。'}
 finally {if(!current.signal.aborted)loading.value=false}
}
async function exportCsv() {
 exporting.value=true;error.value=''
 try {
  const r=await agentApi.get('/admin/usage/export',{params:params(),responseType:'blob',timeout:30000})
  const url=URL.createObjectURL(r.data), link=document.createElement('a');link.href=url;link.download='模型调用明细-UTC.csv';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000)
 }catch{error.value='导出失败，请重试或缩小范围（上限50,000条）。'}finally{exporting.value=false}
}
watch(()=>props.open,value=>{if(value){dates.value=[props.selection?.start||props.range[0]!,props.selection?.end||props.range[1]!];model.value=props.selection?.model||'';callType.value=props.selection?.call_type||'';feature.value='';status.value='';search.value='';selected.value=undefined;void load(true)}else request?.abort()})
onBeforeUnmount(()=>request?.abort())
</script>
<template>
 <el-drawer :model-value="open" @update:model-value="emit('update:open',$event)" append-to-body title="模型调用明细" size="min(1180px, 97vw)">
  <p class="dashboard-note">{{mode==='LIVE'?'真实':'隔离测试'}}环境 · UTC 自然日 · 请求模型与响应模型分别显示；缓存输入已包含在输入 Token 中，金额尚未核验。</p>
  <div class="detail-filters"><el-date-picker v-model="dates" type="daterange" value-format="YYYY-MM-DD" aria-label="明细日期范围" :clearable="false"/><el-select v-model="callType" aria-label="调用类别筛选"><el-option value="" label="模型与工具"/><el-option value="models" label="模型调用"/><el-option value="tools" label="工具调用"/></el-select><el-input v-model="search" placeholder="搜索调用 ID、请求 ID、模型或功能" aria-label="搜索调用记录" @keyup.enter="load(true)"/><el-input v-model="model" placeholder="精确请求模型" aria-label="模型筛选"/><el-input v-model="feature" placeholder="精确功能代码" aria-label="功能筛选"/><el-select v-model="status" aria-label="调用状态筛选"><el-option value="" label="全部状态"/><el-option value="SUCCEEDED" label="成功"/><el-option value="FAILED" label="失败"/><el-option value="STARTED" label="未闭合"/></el-select><el-button :loading="loading" @click="load(true)">查询明细</el-button><el-button :loading="exporting" @click="exportCsv">导出 CSV</el-button></div>
  <el-alert v-if="error" :title="error" type="error" :closable="false"/>
  <el-skeleton v-if="loading" :rows="5" animated/>
  <template v-if="payload"><p class="dashboard-note">共 {{number(payload.total)}} 条 · 已知输入 {{number(payload.summary.known_input_subtotal)}} / 输出 {{number(payload.summary.known_output_subtotal)}} · {{payload.summary.unknown_or_partial_calls}} 条用量不完整</p>
  <el-table :data="payload.items" empty-text="当前筛选无调用记录"><el-table-column label="时间 UTC" min-width="170"><template #default="{row}">{{timestamp(row.started_at)}}</template></el-table-column><el-table-column label="功能" min-width="130"><template #default="{row}"><span :title="row.feature">{{operationName(row.feature)}}</span></template></el-table-column><el-table-column prop="model" label="请求模型" min-width="145"/><el-table-column prop="response_model" label="响应模型" min-width="145"/><el-table-column prop="user_id" label="用户" width="70"/><el-table-column label="状态" width="90"><template #default="{row}"><span :title="row.status">{{statusNames[row.status]||row.status}}</span></template></el-table-column><el-table-column label="Token" min-width="190"><template #default="{row}"><span title="缺失显示 —；失败调用的已知 Token 同样计入；缓存已包含在输入中">输入 {{number(row.input_tokens)}} · 输出 {{number(row.output_tokens)}}</span></template></el-table-column><el-table-column label="详情" width="80" fixed="right"><template #default="{row}"><el-button link type="primary" @click="selected=row">查看</el-button></template></el-table-column></el-table>
  <el-pagination v-model:current-page="page" :page-size="20" :total="payload.total" layout="total, prev, pager, next" @current-change="load()"/>
  <details><summary>更多分组统计</summary><div v-for="(rows,key) in payload.groups" :key="key"><h4>{{({models:'请求模型',providers:'供应商',features:'功能',users:'用户',daily:'日期 UTC'} as Record<string,string>)[key]||key}}</h4><p v-for="r in (rows as any[])" :key="r.key">{{r.key??'未归属'}} · {{r.calls}} 次 · 已知输入 {{number(r.known_input_subtotal)}} / 输出 {{number(r.known_output_subtotal)}} · 未知 {{r.unknown_or_partial_calls}}</p></div></details></template>
  <el-drawer :model-value="!!selected" @close="selected=undefined" append-to-body title="调用元数据" size="min(540px, 95vw)"><el-descriptions v-if="selected" :column="1" border><el-descriptions-item v-for="(value,key) in selected" :key="key" :label="String(key)"><span style="overflow-wrap:anywhere">{{value??'未记录'}}</span></el-descriptions-item></el-descriptions></el-drawer>
 </el-drawer>
</template>
