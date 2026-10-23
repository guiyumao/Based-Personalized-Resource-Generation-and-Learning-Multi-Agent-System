import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import GenerationProgress from '../GenerationProgress.vue'

const job = (overrides: Record<string, unknown> = {}) => ({
  id: 1, status: 'RUNNING', current_step: '正在执行 knowledge_base_agent',
  created_at: '2026-10-23T02:00:00', ...overrides,
})

describe('资源生成进度反馈', () => {
  it('把智能体步骤翻译成中文进度说明', async () => {
    const wrapper = mount(GenerationProgress, { props: { job: job(), label: '课件' } })
    expect(wrapper.text()).toContain('课件生成进度')
    expect(wrapper.get('.generation-progress-step').text()).toBe('正在知识库资料检索')
    expect(wrapper.text()).toContain('生成中')
    wrapper.unmount()
  })

  it('课件只显示真实保存章节数，不冒充总体百分比', async () => {
    const wrapper = mount(GenerationProgress, { props: { job: job({ current_step: '课件章节 4/9 · 正在生成 x' }) } })
    expect(wrapper.get('.generation-progress-step').text()).toBe('已保存 4/9 章 · 正在生成 x')
    expect(wrapper.get('progress').attributes('value')).toBe('4')
    expect(wrapper.text()).not.toContain('%')
    wrapper.unmount()
  })

  it('阶段未知显示不定进度，不伪造百分比', () => {
    const wrapper = mount(GenerationProgress, { props: { job: job() } })
    expect(wrapper.find('progress').exists()).toBe(false)
    expect(wrapper.get('[role="progressbar"]').attributes('aria-valuenow')).toBeUndefined()
    expect(wrapper.text()).not.toContain('%')
    wrapper.unmount()
  })

  it('提交中但尚未拿到任务时显示提交态', () => {
    const wrapper = mount(GenerationProgress, { props: { job: null, submitting: true } })
    expect(wrapper.get('.generation-progress-step').text()).toBe('正在提交生成任务…')
    expect(wrapper.get('.generation-progress-status').text()).toBe('提交中')
    wrapper.unmount()
  })

  it('失败状态标记为异常而不是继续假装进行中', () => {
    const wrapper = mount(GenerationProgress, { props: { job: job({ status: 'FAILED', current_step: '任务未完成' }) } })
    expect(wrapper.get('.generation-progress-status').text()).toBe('生成失败')
    expect(wrapper.find('[role=progressbar]').exists()).toBe(false)
    wrapper.unmount()
  })
})
