<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { LineChart, BarChart, PieChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, TitleComponent, AriaComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
echarts.use([LineChart, BarChart, PieChart, GridComponent, TooltipComponent, LegendComponent, TitleComponent, AriaComponent, CanvasRenderer])
const props = withDefaults(defineProps<{ option: any; label: string; height?: number; empty?: boolean; mini?: boolean }>(), { height: 246 })
const emit = defineEmits<{ select: [value: any] }>()
const host = ref<HTMLDivElement>()
let chart: echarts.ECharts | undefined
let observer: ResizeObserver | undefined
function render() { chart?.setOption({ animationDuration: 250, ...props.option }, { notMerge: true }) }
function exportPng() {
  if (!chart) return
  const link = document.createElement('a')
  link.href = chart.getDataURL({ type: 'png', pixelRatio: 2, backgroundColor: '#ffffff' })
  link.download = `${props.label}.png`; link.click()
}
onMounted(() => {
  chart = echarts.init(host.value!, undefined, { renderer: 'canvas' })
  chart.on('click', event => emit('select', event))
  observer = new ResizeObserver(() => chart?.resize()); observer.observe(host.value!)
  render()
})
watch(() => props.option, render, { deep: true })
onBeforeUnmount(() => { observer?.disconnect(); chart?.dispose(); chart = undefined })
</script>
<template>
  <div class="dashboard-chart" :class="{ mini }">
    <button v-if="!mini && !empty" class="chart-export" type="button" :aria-label="`导出${label} PNG`" @click="exportPng">PNG ↓</button>
    <div ref="host" role="img" :aria-label="label" :style="{ height: `${height}px` }" />
    <div v-if="empty" class="chart-empty">当前范围暂无记录</div>
  </div>
</template>
<style scoped>
.dashboard-chart{position:relative;min-width:0;width:100%}.chart-export{position:absolute;right:0;top:0;z-index:1;border:0;background:transparent;color:#7985a7;font-size:10px;cursor:pointer}.chart-empty{position:absolute;inset:45% 0 auto;text-align:center;color:#7d8aa5;font-size:13px;pointer-events:none}.mini{pointer-events:none}
</style>
