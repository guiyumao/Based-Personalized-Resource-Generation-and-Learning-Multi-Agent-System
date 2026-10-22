/** Offline typeset frames. Reuses the reader's Markdown/KaTeX parser. */
import fs from 'node:fs'
import path from 'node:path'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { renderLearningMarkdown } from '../web-app/src/utils/learningMarkdownCore.mjs'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const require = createRequire(path.join(root, 'workspace/package.json'))
const { chromium } = require('playwright')
const webRequire = createRequire(path.join(root, 'web-app/package.json'))
const katexCssPath = webRequire.resolve('katex/dist/katex.min.css')
// Embed local fonts; the renderer never needs a server or an external request.
const css = fs.readFileSync(katexCssPath, 'utf8').replace(/url\(([^)]+)\)/g, (_, file) => {
  const name = file.replace(/["']/g, '')
  const mime = name.endsWith('.woff2') ? 'font/woff2' : name.endsWith('.woff') ? 'font/woff' : 'font/ttf'
  return `url(data:${mime};base64,${fs.readFileSync(path.join(path.dirname(katexCssPath), name)).toString('base64')})`
})
const [sourcePath, output] = process.argv.slice(2)
const source = JSON.parse(fs.readFileSync(sourcePath, 'utf8'))
const browser = await chromium.launch({ headless: true })
try {
  const page = await browser.newPage({ viewport: { width: 960, height: 600 }, deviceScaleFactor: 1 })
  await page.route('**/*', route => route.abort())
  const html = renderLearningMarkdown(source.content.replace(/```mermaid[\s\S]*?```/g, ''))
  await page.setContent(`<style>${css}
    *{box-sizing:border-box}body{margin:0;background:#f5f8ff;color:#26344d;font:25px/1.65 "Microsoft YaHei","Noto Sans CJK SC",sans-serif}
    #source{position:absolute;top:0;left:42px;width:876px;overflow-wrap:anywhere}
    p,ul,ol,pre,blockquote,table{margin:0 0 18px}h1,h2,h3,h4{font-size:28px;margin:16px 0}
    .katex{font-size:1.12em}.katex-display{margin:14px 0}table{border-collapse:collapse;width:100%;font-size:22px}
    td,th{border:1px solid #bac7df;padding:8px}pre{white-space:pre-wrap}img{display:none}
    #title{position:absolute;top:22px;left:42px;width:876px;font-size:30px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:#152342}
    #window{position:absolute;top:92px;left:0;width:960px;overflow:hidden}#footer{position:absolute;top:554px;left:42px;font-size:20px;color:#52688a}
  </style><div id="source">${html}</div>`)
  await page.evaluate(() => document.fonts.ready)
  const layout = await page.evaluate(() => {
    const host = document.querySelector('#source')
    // Keep formulas and table rows atomic, and find actual wrapped text lines.
    for (const el of host.querySelectorAll('.katex')) {
      if (el.offsetWidth > 870) el.style.fontSize = `${25 * 1.12 * 870 / el.offsetWidth}px`
    }
    const bands = []
    for (const el of host.querySelectorAll('.katex, tr, pre')) {
      const r = el.getBoundingClientRect(); bands.push([r.top, r.bottom])
    }
    const walker = document.createTreeWalker(host, NodeFilter.SHOW_TEXT)
    while (walker.nextNode()) {
      const node = walker.currentNode
      if (!node.textContent.trim() || node.parentElement.closest('.katex,tr,pre')) continue
      const range = document.createRange(); range.selectNodeContents(node)
      for (const r of range.getClientRects()) bands.push([r.top, r.bottom])
    }
    const height = Math.ceil(host.getBoundingClientRect().height)
    const slices = []
    let start = 0
    while (start < height) {
      let end = Math.min(start + 440, height)
      let adjusted = true
      while (adjusted) {
        adjusted = false
        for (const [top, bottom] of bands) {
          if (top < end && bottom > end && top > start) { end = top; adjusted = true }
        }
      }
      if (bands.some(([top, bottom]) => top < end && bottom > end)) throw new Error('单个公式或表格行超出视频画面，请缩短内容')
      if (end <= start) throw new Error('视频分页失败')
      slices.push([start, end]); start = end
    }
    return { slices, formulas: host.querySelectorAll('.katex').length, errors: host.querySelectorAll('.katex-error').length }
  })
  if (layout.errors) throw new Error(`课件有 ${layout.errors} 个无效公式，请先修正公式语法`)
  if (!layout.slices.length) throw new Error('视频课件正文为空')
  await page.evaluate(title => {
    const content = document.querySelector('#source')
    const window = document.createElement('div'); window.id = 'window'
    content.replaceWith(window); window.append(content)
    const heading = document.createElement('div'); heading.id = 'title'; heading.textContent = title; document.body.append(heading)
    const footer = document.createElement('div'); footer.id = 'footer'; document.body.append(footer)
  }, source.title || '学习课件')
  fs.mkdirSync(output, { recursive: true })
  for (let i = 0; i < layout.slices.length; i++) {
    const [start, end] = layout.slices[i]
    await page.evaluate(({ start, end, i, total }) => {
      document.querySelector('#source').style.top = `${-start}px`
      document.querySelector('#window').style.height = `${end - start}px`
      document.querySelector('#footer').textContent = `字幕课件 · 无声 · ${i + 1}/${total}`
    }, { start, end, i, total: layout.slices.length })
    await page.screenshot({ path: path.join(output, `frame-${String(i).padStart(5, '0')}.png`) })
  }
  fs.writeFileSync(path.join(output, 'layout.json'), JSON.stringify(layout))
} finally {
  await browser.close()
}
