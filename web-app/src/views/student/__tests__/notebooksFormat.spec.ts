import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../../api', () => ({
  evaluationApi: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
}))

vi.mock('../../../stores/auth', () => ({
  useAuthStore: () => ({ user: { userId: 1, username: 'learner' } }),
}))

vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))

import { evaluationApi } from '../../../api'
import MistakeNotebookView from '../../MistakeNotebookView.vue'
import FavoriteNotebookView from '../FavoriteNotebookView.vue'

const evaluationGet = vi.mocked(evaluationApi.get)

const latexPrompt = '设 $f(x)=\\frac{x^2-1}{x-1}$（$x\\ne 1$），则 $\\lim_{x\\to 1}f(x)$ 的值为（ ）。'
const latexAnalysis = '因为 $\\frac{x^2-1}{x-1}=x+1$，所以极限为 **2**。'

const notebook = {
  user_id: 1,
  mistake_count: 1,
  items: [
    {
      exercise_id: 11,
      knowledge_point: '函数极限',
      question_type: 'choice',
      prompt: latexPrompt,
      options: 'A. 0|B. 1|C. 2|D. 不存在',
      user_answer: 'B',
      correct_answer: 'C',
      analysis: latexAnalysis,
      suggested_action: '回看**等价无穷小**替换',
    },
  ],
}

beforeEach(() => {
  vi.clearAllMocks()
  window.sessionStorage.clear()
  window.sessionStorage.setItem(
    'student-workspace-mistakes',
    JSON.stringify({ userId: 1, generatedAt: Date.now(), mistakeNotebook: notebook, remedialExerciseSet: null }),
  )
  evaluationGet.mockResolvedValue({ data: { data: notebook } })
})

describe('错题本 / 收藏本 全局格式规范化', () => {
  it('错题本卡片预览渲染公式而不是原始 LaTeX 源码', () => {
    const wrapper = mount(MistakeNotebookView, { global: { plugins: [ElementPlus] } })
    const preview = wrapper.find('.mistake-card-preview')
    expect(preview.exists()).toBe(true)
    expect(preview.classes()).toContain('is-clamped')
    expect(preview.find('.katex').exists()).toBe(true)
    expect(preview.text()).not.toContain('\\frac')
  })

  it('错题详情弹窗的题干、选项与解析都渲染公式', async () => {
    const wrapper = mount(MistakeNotebookView, {
      global: { plugins: [ElementPlus] },
      attachTo: document.body,
    })
    await wrapper.find('.subject-mistake-card').trigger('click')
    await wrapper.vm.$nextTick()
    await new Promise((resolve) => setTimeout(resolve, 0))

    const dialog = document.body.querySelector('.el-dialog')
    expect(dialog).not.toBeNull()
    const dialogText = dialog?.textContent ?? ''
    expect(dialogText).not.toContain('\\frac')
    expect(dialogText).not.toContain('$')
    // 题干 + 选项 C + 正确答案 C + 解析，均应由 KaTeX 渲染
    expect(dialog?.querySelectorAll('.katex').length).toBeGreaterThanOrEqual(2)
    wrapper.unmount()
  })

  it('收藏本的题干、选项、答案与解析都渲染公式', async () => {
    evaluationGet.mockResolvedValue({
      data: {
        data: {
          user_id: 1,
          favorite_count: 1,
          items: [
            {
              id: 1,
              exercise_id: 21,
              question_type: 'choice',
              difficulty: 'intermediate',
              knowledge_point: '函数极限',
              prompt: latexPrompt,
              options: ['A. $0$', 'B. $1$', 'C. $2$', 'D. 不存在'],
              answer: '$2$',
              analysis: latexAnalysis,
              created_at: new Date().toISOString(),
            },
          ],
        },
      },
    })

    const wrapper = mount(FavoriteNotebookView, { global: { plugins: [ElementPlus] } })
    await new Promise((resolve) => setTimeout(resolve, 0))
    await wrapper.vm.$nextTick()

    const prompt = wrapper.find('.favorite-prompt')
    expect(prompt.exists()).toBe(true)
    expect(prompt.find('.katex').exists()).toBe(true)
    expect(prompt.text()).not.toContain('\\frac')

    const option = wrapper.find('.option-item')
    expect(option.find('.katex').exists()).toBe(true)

    const revealButton = wrapper.findAll('button').find((button) => button.text().includes('查看答案与解析'))
    expect(revealButton).toBeTruthy()
    await revealButton!.trigger('click')
    await wrapper.vm.$nextTick()

    const answerPanel = wrapper.find('.answer-panel')
    expect(answerPanel.exists()).toBe(true)
    expect(answerPanel.findAll('.katex').length).toBeGreaterThanOrEqual(2)
    expect(answerPanel.text()).not.toContain('\\frac')
  })
})
