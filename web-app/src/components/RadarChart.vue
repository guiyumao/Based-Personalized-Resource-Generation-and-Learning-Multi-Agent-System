<script setup lang="ts">
import { computed } from 'vue'

export type RadarAxis = {
  key: string
  label: string
  value: number | null
  source?: string
}

const props = withDefaults(defineProps<{
  axes: RadarAxis[]
  min?: number
  max?: number
  label?: string
}>(), { min: 0, max: 100, label: '多维数据雷达图' })

const validScale = computed(() => Number.isFinite(props.min) && Number.isFinite(props.max) && props.max > props.min)
const values = computed(() => props.axes.map((axis) => ({
  ...axis,
  value: validScale.value && typeof axis.value === 'number' && Number.isFinite(axis.value) ? axis.value : null,
})))
const known = computed(() => values.value.filter((axis) => axis.value !== null).length)
function position(index: number, scale = 1) {
  const angle = -Math.PI / 2 + index * Math.PI * 2 / Math.max(3, props.axes.length)
  return { x: 200 + Math.cos(angle) * 108 * scale, y: 180 + Math.sin(angle) * 108 * scale }
}
function scale(value: number) {
  return Math.max(0, Math.min(1, (value - props.min) / (props.max - props.min)))
}
const points = computed(() => values.value.flatMap((axis, index) => {
  if (axis.value === null) return []
  const point = position(index, scale(axis.value))
  return [`${point.x},${point.y}`]
}).join(' '))
function ringPoints(ring: number) {
  return values.value.map((_, index) => {
    const point = position(index, ring)
    return `${point.x},${point.y}`
  }).join(' ')
}
function anchor(index: number) {
  const x = position(index).x
  return x > 201 ? 'start' : x < 199 ? 'end' : 'middle'
}
</script>

<template>
  <div class="radar-chart">
    <svg v-if="axes.length >= 3" viewBox="0 0 400 360" role="img" :aria-label="label">
      <title>{{ label }}</title>
      <desc>{{ known }}/{{ axes.length }}项已获得；连线与填充仅连接已知数据，缺失维度保持为空。</desc>
      <polygon v-for="ring in [.25, .5, .75, 1]" :key="ring" :points="ringPoints(ring)" class="radar-grid" />
      <line v-for="(_, index) in values" :key="index" x1="200" y1="180" :x2="position(index).x" :y2="position(index).y" class="radar-grid" />
      <polygon v-if="known >= 3" class="radar-area" :points="points" fill="var(--accent)" fill-opacity=".14" stroke="var(--accent)" stroke-width="2" stroke-linejoin="round" />
      <polyline v-else-if="known === 2" class="radar-line" :points="points" fill="none" stroke="var(--accent)" stroke-width="2" />
      <g v-for="(axis, index) in values" :key="axis.key">
        <circle v-if="axis.value !== null" class="radar-point" :cx="position(index, scale(axis.value)).x" :cy="position(index, scale(axis.value)).y" r="4" :fill="axis.source === 'model_inferred' ? 'var(--info, var(--accent))' : 'var(--accent)'">
          <title>{{ axis.label }}：{{ axis.value }}</title>
        </circle>
        <text :x="position(index, 1.2).x" :y="position(index, 1.2).y + 4" :text-anchor="anchor(index)">
          {{ axis.label.length > 6 ? `${axis.label.slice(0, 5)}…` : axis.label }}
          <title>{{ axis.label }}</title>
          <tspan v-if="axis.value === null" :x="position(index, 1.2).x" dy="15" class="radar-missing">（待补充）</tspan>
        </text>
      </g>
    </svg>
    <p v-else class="radar-empty">至少需要三个维度才能绘制雷达图。</p>
    <p v-if="axes.length >= 3 && !known" class="radar-empty">暂无可用数据，积累记录后显示连线与填充。</p>
  </div>
</template>

<style scoped>
.radar-chart { width: 100%; min-width: 0; }
.radar-chart svg { display: block; width: 100%; height: auto; max-width: 560px; max-height: none; margin: 0 auto; overflow: visible; }
.radar-grid { fill: none; stroke: var(--line, #dce4ef); stroke-width: 1; }
.radar-chart text { fill: var(--muted, #64748b); font-family: inherit; font-size: 11px; }
.radar-chart .radar-missing { font-size: 9px; }
.radar-empty { text-align: center; color: var(--muted, #64748b); font-size: 12px; line-height: 1.7; }
</style>
