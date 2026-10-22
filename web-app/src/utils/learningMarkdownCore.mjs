import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js/lib/common'
import katex from 'katex'

const markdown = new MarkdownIt({ html: false, linkify: true, breaks: true, highlight: (code, language) => language !== "mermaid" && hljs.getLanguage(language) ? hljs.highlight(code, { language, ignoreIllegals: true }).value : "" })
const defaultLinkOpen = markdown.renderer.rules.link_open
markdown.renderer.rules.link_open = (tokens, index, options, env, self) => {
  tokens[index].attrSet('target', '_blank')
  tokens[index].attrSet('rel', 'noopener noreferrer')
  return defaultLinkOpen ? defaultLinkOpen(tokens, index, options, env, self) : self.renderToken(tokens, index, options)
}

function renderFormula(formula, displayMode) {
  return katex.renderToString(formula, {
    displayMode,
    throwOnError: false,
    trust: false,
    strict: 'ignore',
    output: 'html',
  })
}

// Parse formulas before Markdown processes backslashes and underscores.
markdown.inline.ruler.before('escape', 'learning_math', (state, silent) => {
  const source = state.src
  const position = state.pos
  const opening = source.startsWith('\\(', position) ? '\\('
    : source.startsWith('\\[', position) ? '\\['
      : source.startsWith('$$', position) ? '$$'
        : source[position] === '$' ? '$' : ''
  if (!opening || (opening === '$' && source[position + 1] === ' ')) return false

  const closing = opening === '\\(' ? '\\)' : opening === '\\[' ? '\\]' : opening
  let end = source.indexOf(closing, position + opening.length)
  while (end > position && source[end - 1] === '\\' && opening.startsWith('$')) {
    end = source.indexOf(closing, end + closing.length)
  }
  if (end < 0 || end === position + opening.length) return false
  let formula = source.slice(position + opening.length, end)
  if (opening === '$') {
    if (formula.endsWith(' ')) return false
    if (formula.includes('\n')) {
      // Model output frequently wraps one long inline formula across lines. A single
      // line break becomes a space; a blank line means the two `$` are not a pair.
      if (/\n[ \t]*\n/.test(formula) || formula.length > 400) return false
      formula = formula.replace(/[ \t]*\n[ \t]*/g, ' ')
    }
  }

  if (!silent) {
    const token = state.push('learning_math', '', 0)
    token.content = formula
    token.meta = { displayMode: opening === '$$' || opening === '\\[' }
  }
  state.pos = end + closing.length
  return true
})

markdown.block.ruler.before('fence', 'learning_math_block', (state, startLine, endLine, silent) => {
  const line = state.src.slice(state.bMarks[startLine] + state.tShift[startLine], state.eMarks[startLine]).trim()
  if (line !== '$$' && line !== '\\[') return false
  const closing = line === '$$' ? '$$' : '\\]'
  let nextLine = startLine + 1
  while (nextLine < endLine) {
    const next = state.src.slice(state.bMarks[nextLine] + state.tShift[nextLine], state.eMarks[nextLine]).trim()
    if (next === closing) break
    nextLine += 1
  }
  if (nextLine >= endLine) return false
  if (!silent) {
    const token = state.push('learning_math_block', '', 0)
    token.content = state.getLines(startLine + 1, nextLine, 0, false).trim()
    token.map = [startLine, nextLine + 1]
  }
  state.line = nextLine + 1
  return true
})

markdown.renderer.rules.learning_math = (tokens, index) =>
  renderFormula(tokens[index].content, Boolean(tokens[index].meta?.displayMode))
markdown.renderer.rules.learning_math_block = (tokens, index) =>
  `<div class="learning-math-block">${renderFormula(tokens[index].content, true)}</div>`

/** Markdown HTML is disabled; KaTeX also runs with trust disabled. */
export function renderLearningMarkdown(source, inline = false) {
  return inline ? markdown.renderInline(source ?? '') : markdown.render(source ?? '')
}
