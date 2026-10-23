/** 学习时长格式化：秒 → 人读得懂的时长，null 表示"未采集"而非 0。 */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return '—'
  if (seconds <= 0) return '0 分钟'
  if (seconds < 60) return `${Math.round(seconds)} 秒`
  const total = seconds / 60
  if (total < 60) return `${total < 10 ? round1(total) : Math.round(total)} 分钟`
  const hours = Math.floor(total / 60)
  const rest = Math.round(total % 60)
  return rest ? `${hours} 小时 ${rest} 分` : `${hours} 小时`
}

/** 图表标签用的紧凑写法，避免长文案挤掉柱子。 */
export function formatCompactDuration(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds) || seconds <= 0) return '0'
  if (seconds < 60) return `${Math.round(seconds)}秒`
  const total = seconds / 60
  return `${total < 10 ? round1(total) : Math.round(total)}分`
}

function round1(value: number): number {
  return Math.round(value * 10) / 10
}
