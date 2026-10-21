<script setup lang="ts">
import { computed, ref } from 'vue'
import { number, statusNames, timestamp } from './charts'
const props = defineProps<{ workers?: any; error?: string }>()
const drawer = ref(false), abnormal = ref(false)
const colors: Record<string,string> = {ONLINE:'#6973ff',STALE:'#c4b7fc',STOPPED:'#cbd2e2',DEGRADED:'#ffab24',OFFLINE:'#f06988'}
const items = computed(()=>props.workers?.items.filter((w:any)=>!abnormal.value || ['STALE','DEGRADED'].includes(w.status)) || [])
function open(onlyAbnormal=false) {abnormal.value=onlyAbnormal;drawer.value=true}
</script>
<template>
 <article class="dashboard-card worker-health"><header><h2>Worker 运行状态</h2><button class="text-button" @click="open()">查看全部 →</button></header>
 <p v-if="error" class="error" role="alert">{{error}}</p>
 <template v-else-if="workers">
  <div class="worker-state" v-for="(count,state) in workers.distribution" :key="state"><i :style="{background:colors[state]||'#a5aeca'}"/><span>{{statusNames[state]||state}} <small>{{state}}</small></span><strong>{{count}}</strong><span>{{workers.registered ? (Number(count)/workers.registered*100).toFixed(1) : '0'}}%</span></div>
  <div class="worker-stack"><span v-for="(count,state) in workers.distribution" :key="state" :style="{width:`${Number(count)/workers.registered*100}%`,background:colors[state]||'#a5aeca'}"/></div>
  <button v-if="workers.items.some((w:any)=>['STALE','DEGRADED'].includes(w.status))" class="worker-warning" @click="open(true)">待核查 {{workers.items.filter((w:any)=>['STALE','DEGRADED'].includes(w.status)).length}} 个注册 · 过期心跳不等同系统故障</button>
  <h4>最近心跳 <small>实时 · UTC</small></h4>
  <div v-for="row in workers.items.slice(0,4)" :key="row.id" class="heartbeat"><span><i :style="{background:colors[row.status]||'#ffab24'}"/>{{row.pid}}<small>{{row.kind}}</small></span><time>{{timestamp(row.heartbeat_at)}}</time></div>
  <p v-if="!workers.items.length" class="dashboard-note">暂无注册，未接入心跳的旧进程不可观测。</p>
 </template>
 <el-drawer v-model="drawer" append-to-body title="Worker 注册与心跳" size="min(900px, 96vw)"><el-switch v-model="abnormal" active-text="仅看待核查注册"/><p class="dashboard-note">ONLINE 依据心跳间隔的三倍（至少15秒）判定；STALE 可能来自历史未正常退出，需结合 PID 排查。已退出注册不计入活跃分母。</p><el-table :data="items"><el-table-column prop="pid" label="PID" width="90"/><el-table-column prop="kind" label="类型"/><el-table-column label="状态"><template #default="{row}">{{statusNames[row.status]||row.status}} ({{row.status}})</template></el-table-column><el-table-column label="最近心跳 UTC" min-width="170"><template #default="{row}">{{timestamp(row.heartbeat_at)}}</template></el-table-column><el-table-column label="详情" type="expand"><template #default="{row}"><p>ID：{{row.id}}</p><p>能力：{{row.capabilities.join('、')}}</p><p>启动 {{timestamp(row.started_at)}} · 退出 {{timestamp(row.stopped_at)}}</p><p>已处理 {{number(row.batches)}} 轮 · 心跳年龄 {{Math.round(row.heartbeat_age_seconds)}} 秒 · 阈值 {{row.stale_after_seconds}} 秒 · 错误代码 {{row.error_code||'无'}}</p></template></el-table-column></el-table></el-drawer>
 </article>
</template>
