<script setup lang="ts">
import { computed } from 'vue'
import { formatCompactDuration, formatDuration } from '../utils/duration'

export type ActivityDay = { date: string; study_seconds: number | null; answers?: number }

const props = withDefaults(defineProps<{ days: ActivityDay[]; label?: string }>(), { label: '近七日有效活动' })

const WEEKDAYS = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
/** 刻度阶梯全为偶数，保证中值刻度不出现半格小数。 */
const SCALE_LADDER = [6, 10, 16, 20, 30, 40, 60, 90, 120, 180, 240, 300, 420, 600, 900, 1200]

function normalizeSeconds(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : null
}
function localDateKey(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}
const todayKey = localDateKey(new Date())

const points = computed(() => props.days.map((day) => {
  const seconds = normalizeSeconds(day.study_seconds)
  const parsed = new Date(`${day.date}T00:00:00`)
  const valid = !Number.isNaN(parsed.getTime())
  return {
    date: day.date,
    seconds,
    minutes: seconds == null ? null : seconds / 60,
    weekday: valid ? WEEKDAYS[parsed.getDay()] : '',
    dayLabel: valid ? `${parsed.getMonth() + 1}/${parsed.getDate()}` : day.date.slice(5),
    answers: normalizeSeconds(day.answers),
    isToday: day.date === todayKey,
  }
}))

/** null 表示"未采集"，不当作 0 分钟参与合计。 */
const tracked = computed(() => points.value.filter((point) => point.seconds !== null))
const collectionDisabled = computed(() => points.value.length > 0 && tracked.value.length === 0)
const totalSeconds = computed(() => tracked.value.reduce((sum, point) => sum + (point.seconds ?? 0), 0))
const activeDays = computed(() => tracked.value.filter((point) => (point.seconds ?? 0) > 0).length)
const emptyWeek = computed(() => !collectionDisabled.value && points.value.length > 0 && totalSeconds.value === 0)
const peak = computed(() => tracked.value.reduce<(typeof tracked.value)[number] | undefined>(
  (best, point) => ((point.seconds ?? 0) > (best?.seconds ?? 0) ? point : best),
  tracked.value[0],
))
const peakLabel = computed(() => peak.value && (peak.value.seconds ?? 0) > 0 ? `${peak.value.dayLabel} · ${formatDuration(peak.value.seconds)}` : '—')

const maxMinutes = computed(() => {
  const peakMinutes = Math.max(0, ...tracked.value.map((point) => point.minutes ?? 0))
  return SCALE_LADDER.find((step) => peakMinutes <= step) ?? Math.ceil(peakMinutes / 600) * 600
})
const ticks = computed(() => [0, maxMinutes.value / 2, maxMinutes.value].map((value) => ({
  value,
  label: Number.isInteger(value) ? String(value) : value.toFixed(1),
  percent: maxMinutes.value ? (value / maxMinutes.value) * 100 : 0,
})))

const bars = computed(() => points.value.map((point, index) => {
  const percent = point.seconds == null || !maxMinutes.value
    ? 0
    : Math.min(1, (point.minutes ?? 0) / maxMinutes.value) * 100
  return {
    ...point,
    key: point.date || String(index),
    percent: Math.round(percent * 100) / 100,
    zero: percent <= 0,
  }
}))

const summary = computed(() => {
  if (collectionDisabled.value) return '活动采集尚未启用，暂无近七日数据。'
  const perDay = bars.value
    .map((bar) => `${bar.dayLabel}${bar.isToday ? '（今天）' : bar.weekday ? `（${bar.weekday}）` : ''}${bar.seconds == null ? '未采集' : formatDuration(bar.seconds)}`)
    .join('；')
  return `${perDay}。合计 ${formatDuration(totalSeconds.value)}，${activeDays.value} 天有活动记录。`
})

function barTitle(bar: { date: string; weekday: string; isToday: boolean; seconds: number | null; answers: number | null }): string {
  const head = `${bar.isToday ? '今天' : bar.weekday} ${bar.date}`
  const time = bar.seconds == null ? '采集未启用' : `有效活动 ${formatDuration(bar.seconds)}`
  return bar.answers == null ? `${head}：${time}` : `${head}：${time} · ${bar.answers} 次作答`
}
</script>

<template>
  <figure class="weekly-activity" :aria-label="label">
    <dl v-if="!collectionDisabled && !emptyWeek" class="weekly-summary">
      <div><dt>近 {{ points.length }} 日合计</dt><dd>{{ formatDuration(totalSeconds) }}</dd></div>
      <div><dt>有活动天数</dt><dd>{{ activeDays }} / {{ points.length }} 天</dd></div>
      <div><dt>单日最高</dt><dd>{{ peakLabel }}</dd></div>
    </dl>
    <p v-if="collectionDisabled" class="weekly-empty">活动采集尚未启用，暂无可视化数据。开启后会自动按天累计。</p>
    <p v-else-if="emptyWeek" class="weekly-empty">近 {{ points.length }} 日暂无有效活动。进入学习页并保持窗口可见，系统会自动累计时长。</p>
    <template v-else>
      <div class="weekly-body">
        <div class="weekly-scale" aria-hidden="true">
          <span v-for="tick in ticks" :key="`tick-${tick.value}`" :style="{ bottom: `${tick.percent}%` }">{{ tick.label }}</span>
        </div>
        <div class="weekly-plot" aria-hidden="true">
          <i v-for="tick in ticks.slice(1)" :key="`grid-${tick.value}`" class="weekly-gridline" :style="{ bottom: `${tick.percent}%` }" />
          <div class="weekly-columns">
            <div v-for="bar in bars" :key="bar.key" class="weekly-col">
              <span
                class="weekly-value"
                :class="{ 'is-today': bar.isToday }"
                :style="{ bottom: `calc(${bar.percent}% + 6px)` }"
                v-text="formatCompactDuration(bar.seconds)"
                v-show="!bar.zero"
              />
              <span
                class="weekly-bar"
                :class="{ 'is-today': bar.isToday, 'is-zero': bar.zero }"
                :style="{ height: bar.zero ? '8px' : `${bar.percent}%` }"
                :title="barTitle(bar)"
              />
            </div>
          </div>
        </div>
        <span class="weekly-unit" aria-hidden="true">单位：分钟</span>
      </div>
      <div class="weekly-xaxis">
        <div v-for="bar in bars" :key="`x-${bar.key}`" class="weekly-x" :class="{ 'is-today': bar.isToday }">
          <b>{{ bar.isToday ? '今天' : bar.weekday }}</b>
          <small>{{ bar.dayLabel }}</small>
        </div>
      </div>
      <figcaption>实色为今天，浅色为历史日期，空心点表示当天 0 分钟。</figcaption>
      <ul class="weekly-sr">
        <li v-for="bar in bars" :key="`sr-${bar.key}`">{{ barTitle(bar) }}</li>
      </ul>
    </template>
  </figure>
</template>

<style scoped>
.weekly-activity { margin: 0; min-width: 0; }
.weekly-summary { display: flex; flex-wrap: wrap; gap: 8px 22px; margin: 0 0 14px; padding: 0; }
.weekly-summary > div { display: grid; gap: 2px; }
.weekly-summary dt { color: var(--muted); font-size: 12px; }
.weekly-summary dd { margin: 0; color: var(--text); font-size: 16px; font-weight: 600; font-variant-numeric: tabular-nums; }
.weekly-body { position: relative; display: flex; gap: 8px; margin-top: 18px; min-width: 0; }
.weekly-scale { position: relative; flex: 0 0 30px; height: 132px; }
.weekly-scale span { position: absolute; right: 4px; transform: translateY(50%); color: var(--muted); font-size: 10.5px; font-variant-numeric: tabular-nums; }
.weekly-unit { position: absolute; top: -16px; right: 0; color: var(--muted); font-size: 10px; }
.weekly-plot { position: relative; flex: 1 1 auto; height: 132px; min-width: 0; }
.weekly-gridline { position: absolute; left: 0; right: 0; border-top: 1px dashed var(--line); }
.weekly-plot::after { content: ""; position: absolute; left: 0; right: 0; bottom: 0; border-top: 1.5px solid var(--line); }
.weekly-columns { position: absolute; inset: 0; display: flex; align-items: flex-end; }
.weekly-col { position: relative; flex: 1 1 0; display: flex; justify-content: center; align-items: flex-end; height: 100%; min-width: 0; }
.weekly-bar { display: block; width: min(26px, 58%); border-radius: 4px 4px 2px 2px; background: var(--accent); opacity: 0.5; transition: opacity 0.15s ease; }
.weekly-bar.is-today { opacity: 1; }
.weekly-bar.is-zero { width: 8px; background: transparent; box-shadow: inset 0 0 0 1.5px var(--muted); opacity: 0.55; border-radius: 50%; }
.weekly-col:hover .weekly-bar { opacity: 0.75; }
.weekly-col:hover .weekly-bar.is-today { opacity: 1; }
.weekly-value { position: absolute; color: var(--muted); font-size: 11px; font-weight: 600; white-space: nowrap; font-variant-numeric: tabular-nums; }
.weekly-value.is-today { color: var(--accent-deep); }
.weekly-xaxis { display: flex; margin: 8px 0 0 38px; }
.weekly-x { flex: 1 1 0; display: grid; justify-items: center; gap: 1px; min-width: 0; }
.weekly-x b { color: var(--muted); font-size: 11px; font-weight: 500; }
.weekly-x small { color: var(--muted); font-size: 10px; opacity: 0.75; font-variant-numeric: tabular-nums; }
.weekly-x.is-today b { color: var(--accent-deep); font-weight: 700; }
.weekly-x.is-today small { color: var(--accent-deep); opacity: 1; }
.weekly-activity figcaption { margin-top: 10px; color: var(--muted); font-size: 11px; line-height: 1.6; }
.weekly-empty { margin: 0; padding: 18px 16px; border: 1px dashed var(--line); border-radius: 12px; background: var(--surface-muted); color: var(--muted); font-size: 12px; line-height: 1.7; }
.weekly-sr { position: absolute; width: 1px; height: 1px; margin: -1px; padding: 0; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; border: 0; }
@media (max-width: 420px) {
  .weekly-scale { flex-basis: 24px; }
  .weekly-xaxis { margin-left: 32px; }
  .weekly-x small { display: none; }
}
</style>
