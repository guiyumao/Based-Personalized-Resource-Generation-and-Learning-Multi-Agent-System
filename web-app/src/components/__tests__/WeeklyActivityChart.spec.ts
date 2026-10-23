import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import WeeklyActivityChart from '../WeeklyActivityChart.vue'

type Day = { date: string; study_seconds: number | null; answers?: number }

function week(values: Array<number | null>): Day[] {
  return values.map((study_seconds, index) => ({ date: `2026-10-${17 + index}`, study_seconds, answers: 0 }))
}

describe('近七日有效活动柱状图', () => {
  it('七天数据绘制七根柱，零时长日保留基线短柱而不是整条空轨道', () => {
    const wrapper = mount(WeeklyActivityChart, { props: { days: week([0, 0, 0, 0, 0, 0, 240]) } })
    const bars = wrapper.findAll('.weekly-bar')
    expect(bars).toHaveLength(7)
    expect(bars.filter(bar => bar.classes().includes('is-zero'))).toHaveLength(6)
    expect(bars[0]!.attributes('style')).toContain('height: 8px')
    expect(wrapper.findAll('.weekly-bar.is-today')).toHaveLength(1)
    wrapper.unmount()
  })

  it('唯一非零日按真实比例落地，不被拉满成"完成度"', () => {
    const wrapper = mount(WeeklyActivityChart, { props: { days: week([0, 0, 0, 0, 0, 0, 240]) } })
    const bar = wrapper.findAll('.weekly-bar').at(6)!
    expect(bar.attributes('style')).toContain('66.67%')
    expect(wrapper.text()).toContain('近 7 日合计')
    expect(wrapper.text()).toContain('4 分钟')
    expect(wrapper.text()).toContain('1 / 7 天')
    wrapper.unmount()
  })

  it('横轴标注星期与日期，今天单独标记', () => {
    const wrapper = mount(WeeklyActivityChart, { props: { days: week([0, 0, 0, 0, 0, 0, 240]) } })
    const labels = wrapper.findAll('.weekly-x').map(node => node.text())
    expect(labels[0]).toContain('周六')
    expect(labels[0]).toContain('10/17')
    expect(labels.at(-1)).toContain('今天')
    expect(labels.at(-1)).toContain('10/23')
    wrapper.unmount()
  })

  it('全零给出空状态，不画一张只有刻度的图', () => {
    const wrapper = mount(WeeklyActivityChart, { props: { days: week([0, 0, 0, 0, 0, 0, 0]) } })
    expect(wrapper.find('.weekly-plot').exists()).toBe(false)
    expect(wrapper.text()).toContain('暂无有效活动')
    wrapper.unmount()
  })

  it('全为 null 视为采集未启用，与 0 分钟区分', () => {
    const wrapper = mount(WeeklyActivityChart, { props: { days: week([null, null, null, null, null, null, null]) } })
    expect(wrapper.find('.weekly-plot').exists()).toBe(false)
    expect(wrapper.text()).toContain('采集尚未启用')
    wrapper.unmount()
  })

  it('每根柱都有悬停说明，读屏另有完整清单', () => {
    const wrapper = mount(WeeklyActivityChart, { props: { days: week([60, null, 0, 0, 0, 0, 240]) } })
    const bars = wrapper.findAll('.weekly-bar')
    expect(bars[0]!.attributes('title')).toContain('1 分钟')
    expect(bars[1]!.attributes('title')).toContain('采集未启用')
    expect(wrapper.get('.weekly-sr').text()).toContain('有效活动 4 分钟')
    wrapper.unmount()
  })
})
