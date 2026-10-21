<script setup lang="ts">
import { computed } from 'vue'
const props = withDefaults(defineProps<{ title: string; rows: { label: string; value: number; secondary?: number }[]; kind?: 'bars' | 'donut'; legends?: string[] }>(), { kind: 'bars', legends: () => [] })
const colors = ['#5385ee', '#50c5a0', '#f0b44c', '#9975df', '#ef8796', '#46b6ce', '#8b9aaf']
const maximum = computed(() => Math.max(1, ...props.rows.map(row => Math.max(row.value, row.secondary ?? 0))))
const total = computed(() => props.rows.reduce((sum, row) => sum + row.value, 0))
const gradient = computed(() => {
  let offset = 0
  return `conic-gradient(${props.rows.map((row, index) => {
    const start = offset
    offset += total.value ? row.value / total.value * 100 : 0
    return `${colors[index % colors.length]} ${start}% ${offset}%`
  }).join(',') || '#edf1f6 0% 100%'})`
})
</script>
<template>
  <article class="chart-card" :aria-label="title">
    <header><h4>{{ title }}</h4><span v-if="kind === 'bars'" class="chart-legend"><span v-for="(legend, index) in legends" :key="legend"><i :style="{background: colors[index]}"/>{{ legend }}</span></span></header>
    <p v-if="!rows.length || !total && !rows.some(row => row.secondary)" class="chart-empty">当前筛选下暂无数据</p>
    <template v-else-if="kind === 'donut'">
      <div class="donut-area"><div class="donut" :style="{background:gradient}" role="img" :aria-label="rows.map(row => `${row.label} ${row.value} 次`).join('，')"><div><strong>{{ total.toLocaleString() }}</strong><span>调用次数</span></div></div></div>
      <ul class="distribution"><li v-for="(row, index) in rows" :key="row.label" :title="row.label"><i :style="{background:colors[index % colors.length]}"/><span>{{ row.label }}</span><strong>{{ row.value.toLocaleString() }}</strong></li></ul>
    </template>
    <template v-else>
      <div class="bar-scroll"><div class="bar-plot" :style="{minWidth:`${Math.max(320, rows.length * 38)}px`}">
        <div class="grid-lines"><span v-for="step in [4,3,2,1,0]" :key="step">{{ Math.ceil(maximum * step / 4).toLocaleString() }}</span></div>
        <div class="bar-columns"><div v-for="row in rows" :key="row.label" class="bar-column" tabindex="0" :aria-label="`${row.label}：${legends[0] || '调用'} ${row.value}${row.secondary === undefined ? '' : `，${legends[1]} ${row.secondary}`}`" :title="`${row.label} · ${legends[0] || '调用'} ${row.value.toLocaleString()}${row.secondary === undefined ? '' : ` / ${legends[1]} ${row.secondary.toLocaleString()}`}`">
          <div class="bars"><div class="bar primary" :style="{height:`${row.value / maximum * 100}%`}"/><div v-if="row.secondary !== undefined" class="bar secondary" :style="{height:`${row.secondary / maximum * 100}%`}"/></div><span class="bar-label">{{ row.label.slice(5) || row.label }}</span>
        </div></div>
      </div></div><p class="chart-hint">悬停或聚焦柱形查看数值 · UTC</p>
    </template>
  </article>
</template>
<style scoped>
.chart-card{background:var(--surface-card,#fff);border:1px solid var(--border-color,#e7ebf2);border-radius:14px;padding:22px;min-width:0;box-shadow:0 3px 12px #233b6410}header{display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:22px}h4{margin:0;font-size:15px;color:var(--text-primary,#27364e)}.chart-legend,.chart-legend>span{display:flex;align-items:center;gap:7px}.chart-legend{font-size:12px;color:var(--text-secondary,#738196);flex-wrap:wrap;gap:14px}i{display:inline-block;width:9px;height:9px;border-radius:50%;flex:none}.bar-scroll{overflow-x:auto}.bar-plot{height:210px;position:relative;padding-left:50px}.grid-lines{position:absolute;inset:0 0 26px;display:flex;flex-direction:column;justify-content:space-between;pointer-events:none}.grid-lines span{border-bottom:1px solid var(--border-color,#edf0f5);color:#8a95a6;font-size:10px;height:0;line-height:1}.bar-columns{height:100%;display:flex;position:relative;gap:10px}.bar-column{flex:1;min-width:22px;height:100%;outline-offset:-2px}.bars{height:calc(100% - 26px);display:flex;align-items:flex-end;justify-content:center;gap:4px}.bar{max-width:32px;min-width:5px;width:38%;border-radius:4px 4px 0 0;background:#5385ee}.secondary{background:#50c5a0}.bar-column:hover .bar,.bar-column:focus .bar{filter:brightness(.9)}.bar-label{display:block;text-align:center;font-size:10px;color:#8a95a6;padding-top:9px;white-space:nowrap}.chart-hint{font-size:11px;color:#8a95a6;margin:14px 0 0}.chart-empty{min-height:210px;display:grid;place-items:center;color:#8a95a6;font-size:13px}.donut-area{display:flex;justify-content:center}.donut{width:170px;height:170px;border-radius:50%;display:grid;place-items:center}.donut>div{width:120px;height:120px;border-radius:50%;background:var(--surface-card,#fff);display:flex;flex-direction:column;align-items:center;justify-content:center;gap:5px}.donut strong{font-size:26px;color:var(--text-primary,#27364e)}.donut span{font-size:12px;color:#8a95a6}.distribution{list-style:none;padding:0;margin:22px 0 0;display:grid;gap:9px;font-size:12px}.distribution li{display:flex;gap:8px;align-items:center}.distribution li>span{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text-secondary,#738196)}.distribution strong{color:var(--text-primary,#27364e)}
</style>
