import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import LearningContent from '../LearningContent.vue'

describe('LearningContent 全局格式规范化', () => {
  it('renders inline math inside option text', () => {
    const wrapper = mount(LearningContent, {
      props: { content: 'A. $x=1$', inline: true },
    })
    expect(wrapper.classes()).toContain('learning-markdown')
    expect(wrapper.classes()).toContain('is-inline')
    expect(wrapper.find('.katex').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('$x=1$')
  })

  it('renders block markdown with headings, lists and display math', () => {
    const wrapper = mount(LearningContent, {
      props: { content: '### 解析\n\n- 要点一\n\n$$\n\\lim_{x\\to 0}\\frac{\\sin x}{x}=1\n$$' },
    })
    expect(wrapper.find('h3').exists()).toBe(true)
    expect(wrapper.find('li').exists()).toBe(true)
    expect(wrapper.find('.learning-math-block .katex-display').exists()).toBe(true)
  })

  it('honours the container tag', () => {
    const wrapper = mount(LearningContent, { props: { content: '题干', tag: 'h3' } })
    expect(wrapper.element.tagName).toBe('H3')
  })

  it('applies line clamping for list previews without cutting formula source', () => {
    const wrapper = mount(LearningContent, {
      props: { content: '设 $f(x)=\\frac{x^2-1}{x-1}$，求极限并说明理由。', clampLines: 2 },
    })
    expect(wrapper.classes()).toContain('is-clamped')
    expect(wrapper.attributes('style')).toContain('-webkit-line-clamp: 2')
    expect(wrapper.find('.katex').exists()).toBe(true)
  })

  it('falls back to the empty text when content is blank', () => {
    const wrapper = mount(LearningContent, { props: { content: '   ', empty: '(未作答)' } })
    expect(wrapper.text()).toBe('(未作答)')
    expect(wrapper.classes()).toContain('learning-content-empty')
  })

  it('renders nothing when content is blank and no empty text is given', () => {
    const wrapper = mount(LearningContent, { props: { content: '' } })
    expect(wrapper.html()).toBe('<!--v-if-->')
  })
})
