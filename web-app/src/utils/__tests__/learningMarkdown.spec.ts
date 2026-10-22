import { describe, expect, it } from 'vitest'
import { renderLearningMarkdown } from '../learningMarkdownCore.mjs'

describe('renderLearningMarkdown 全局格式规范', () => {
  it('renders inline $...$ as KaTeX', () => {
    const html = renderLearningMarkdown('设 $f(x)=\\frac{x^2-1}{x-1}$，则极限为（）')
    expect(html).toContain('class="katex"')
    expect(html).not.toContain('\\frac{x^2-1}{x-1}')
  })

  it('renders display $$ blocks on their own lines', () => {
    const html = renderLearningMarkdown('结果如下\n\n$$\n\\lim_{x\\to 1} f(x) = 2\n$$\n')
    expect(html).toContain('learning-math-block')
    expect(html).toContain('katex-display')
    expect(html).not.toContain('\\lim_{x\\to 1}')
  })

  it('accepts \\(...\\) and \\[...\\] delimiters', () => {
    expect(renderLearningMarkdown('值 \\(x^2\\) 为正', true)).toContain('katex')
    expect(renderLearningMarkdown('\\[a^2+b^2=c^2\\]')).toContain('katex-display')
  })

  it('treats a single line break inside $...$ as a space instead of leaking source', () => {
    const html = renderLearningMarkdown('$a +\nb$')
    expect(html).toContain('katex')
    expect(html).not.toContain('$a +')
  })

  it('does not pair `$` across a blank line', () => {
    const html = renderLearningMarkdown('价格 $5 起\n\n第二段 $6 止')
    expect(html).not.toContain('class="katex"')
  })

  it('keeps raw HTML disabled', () => {
    const html = renderLearningMarkdown('<script>alert(1)</script><img src=x onerror=alert(1)>')
    expect(html).not.toContain('<script>')
    expect(html).not.toContain('<img')
    expect(html).toContain('&lt;script&gt;')
  })

  it('renders markdown structure for generated analysis text', () => {
    const html = renderLearningMarkdown('**要点**\n\n- 第一条\n- 第二条')
    expect(html).toContain('<strong>要点</strong>')
    expect(html).toContain('<li>第一条</li>')
  })

  it('returns an empty string for empty input', () => {
    expect(renderLearningMarkdown('')).toBe('')
    expect(renderLearningMarkdown(undefined as unknown as string)).toBe('')
  })
})
