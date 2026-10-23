import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import RadarChart from '../RadarChart.vue'

function axes(values: Array<number | null>) {
  return values.map((value, index) => ({ key: `axis-${index}`, label: `维度${index + 1}`, value }))
}

describe('全站共享雷达绘制', () => {
  it.each([3, 4, 5, 7])('%s个维度统一连线并填充', (count) => {
    const wrapper = mount(RadarChart, { props: { axes: axes(Array(count).fill(70)) } })
    expect(wrapper.get('.radar-area').attributes('points')?.split(' ')).toHaveLength(count)
    expect(wrapper.findAll('.radar-point')).toHaveLength(count)
    wrapper.unmount()
  })

  it('百分制的零是真实数据，null与非有限数值保持缺失', () => {
    const wrapper = mount(RadarChart, { props: { axes: axes([0, null, NaN, Infinity, 90]) } })
    expect(wrapper.findAll('.radar-point')).toHaveLength(2)
    expect(wrapper.findAll('.radar-missing')).toHaveLength(3)
    expect(wrapper.find('.radar-area').exists()).toBe(false)
    expect(wrapper.find('.radar-line').exists()).toBe(true)
    expect(wrapper.find('.radar-point').attributes('cy')).toBe('180')
    wrapper.unmount()
  })

  it('偏好量表使用-1到1，零位于半径中间', () => {
    const wrapper = mount(RadarChart, { props: { axes: axes([0, 1, -1, null]), min: -1, max: 1 } })
    expect(wrapper.find('.radar-point').attributes('cy')).toBe('126')
    expect(wrapper.findAll('.radar-point')).toHaveLength(3)
    expect(wrapper.findAll('.radar-missing')).toHaveLength(1)
    wrapper.unmount()
  })

  it('补齐或清空数据后实时更新图形，不残留旧面', async () => {
    const wrapper = mount(RadarChart, { props: { axes: axes([80, null, 70, null]) } })
    expect(wrapper.find('.radar-line').exists()).toBe(true)
    await wrapper.setProps({ axes: axes([80, 65, 70, null]) })
    expect(wrapper.find('.radar-area').exists()).toBe(true)
    await wrapper.setProps({ axes: axes([null, null, null, null]) })
    expect(wrapper.find('.radar-area').exists()).toBe(false)
    expect(wrapper.find('.radar-line').exists()).toBe(false)
    expect(wrapper.findAll('.radar-point')).toHaveLength(0)
    expect(wrapper.text()).toContain('暂无可用数据')
    wrapper.unmount()
  })
})
