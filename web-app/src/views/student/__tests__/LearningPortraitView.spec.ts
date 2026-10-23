import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../../api/http', () => ({
  userApi: { get: vi.fn(), post: vi.fn(), put: vi.fn() },
}))

vi.mock('../../../stores/auth', () => ({
  useAuthStore: () => ({ user: { userId: 1, username: 'learner' }, token: 't' }),
}))

import { userApi } from '../../../api/http'
import LearningPortraitView from '../LearningPortraitView.vue'

const userGet = vi.mocked(userApi.get)
const userPost = vi.mocked(userApi.post)
const userPut = vi.mocked(userApi.put)

const portrait = {
  user_id: 1,
  updated_at: '2026-10-23T00:00:00',
  axes: [
    { key: 'processing', label: '信息加工', negative: '沉思', positive: '活跃', value: 0.5, source: 'model_inferred', confidence: 0.8, evidence: '多次先动手试错' },
    { key: 'perception', label: '信息感知', negative: '直觉', positive: '感知', value: 0.6, source: 'model_inferred', confidence: 0.7, evidence: '偏好具体例子' },
    { key: 'input', label: '信息输入', negative: '言语', positive: '视觉', value: 0.7, source: 'user_reported', confidence: null, evidence: '' },
    { key: 'understanding', label: '理解方式', negative: '全局', positive: '序列', value: -0.4, source: 'model_inferred', confidence: 0.5, evidence: '先看整体框架' },
  ],
  dimensions: {},
  dimension_sources: {},
  style_source: '1 项本人自述，3 项由模型根据已收集的学习记录推断；推断是可覆盖的假设。',
  inference: {
    status: 'completed',
    generated_at: '2026-10-23T00:00:00',
    model: 'deepseek-chat',
    stale: false,
    summary: '偏活跃与视觉，理解偏全局',
    evidence: { answers: 3, resources: 2, conversations: 1, notes: 0, reviews: 0 },
  },
  behavior_profile: {
    algorithm_version: 'test',
    dimensions: {},
    evidence: { answer_record_count: 3 },
  },
}

function mountView() {
  return mount(LearningPortraitView, {
    global: { plugins: [ElementPlus], stubs: { RouterLink: true } },
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  userGet.mockResolvedValue({ data: portrait })
  userPost.mockResolvedValue({ data: { status: 'completed', message: '已生成', snapshot: portrait } })
  userPut.mockResolvedValue({ data: portrait })
})

describe('学习画像由模型生成', () => {
  it('三项已有偏好连成填充区域，缺失维度不补造顶点', async () => {
    userGet.mockResolvedValue({ data: { ...portrait, axes: portrait.axes.map((axis) => axis.key === 'input' ? { ...axis, value: null } : axis) } })
    const wrapper = mountView()
    await flushPromises()
    const area = wrapper.get('.radar-area')
    expect((area.attributes('points') || '').split(' ')).toHaveLength(3)
    expect(wrapper.findAll('.portrait-radar circle')).toHaveLength(3)
    expect(wrapper.get('.portrait-radar').text()).toContain('3/4项已获得')
    expect(wrapper.get('svg').text()).toContain('信息输入（待补充）')
    wrapper.unmount()
  })

  it.each([0, 1, 2])('仅有%s项偏好时不绘制虚构的填充面', async (count) => {
    userGet.mockResolvedValue({ data: { ...portrait, axes: portrait.axes.map((axis, index) => index < count ? axis : { ...axis, value: null }) } })
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.find('.radar-area').exists()).toBe(false)
    expect(wrapper.find('.radar-line').exists()).toBe(count === 2)
    expect(wrapper.findAll('.portrait-radar circle')).toHaveLength(count)
    wrapper.unmount()
  })

  it('雷达与维度展示模型推断值、依据和来源', async () => {
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.get('.portrait-radar').text()).toContain('4/4项已获得')
    expect(wrapper.text()).toContain('模型依据：3 条作答、2 条资源浏览、1 条画像对话')
    expect(wrapper.text()).toContain('偏活跃与视觉，理解偏全局')
    const sources = wrapper.findAll('.axis-source')
    expect(sources.filter((item) => item.classes().includes('model_inferred'))).toHaveLength(3)
    expect(sources.filter((item) => item.classes().includes('user_reported'))).toHaveLength(1)
    expect(wrapper.text()).toContain('依据：多次先动手试错 · 置信度 80%')
    expect(wrapper.find('.portrait-radar polygon.radar-area').exists()).toBe(true)
  })

  it('点击 AI 更新画像调用推断接口并用返回快照刷新', async () => {
    const wrapper = mountView()
    await flushPromises()
    const button = wrapper.findAll('button').find((item) => item.text() === 'AI 更新画像')
    expect(button).toBeTruthy()
    await button!.trigger('click')
    await flushPromises()
    expect(userPost).toHaveBeenCalledWith('/users/1/learning-portrait/infer', { force: false })
    expect(wrapper.text()).toContain('已生成')
  })

  it('进入编辑时模型推断项不自动变成本人填写', async () => {
    const wrapper = mountView()
    await flushPromises()
    await wrapper.findAll('button').find((item) => item.text() === '编辑画像')!.trigger('click')
    const checkboxes = wrapper.findAll('.axis-editor input[type=checkbox]')
    expect(checkboxes).toHaveLength(4)
    expect((checkboxes[0].element as HTMLInputElement).checked).toBe(false)
    expect((checkboxes[2].element as HTMLInputElement).checked).toBe(true)

    await wrapper.findAll('button').find((item) => item.text() === '保存画像')!.trigger('click')
    await flushPromises()
    const payload = vi.mocked(userApi.put).mock.calls[0][1] as { axes: Record<string, number | null> }
    expect(payload.axes).toEqual({
      processing: null,
      perception: null,
      input: 0.7,
      understanding: null,
    })
  })
})
