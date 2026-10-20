/** Real UI + local backends + local provider. No dotenv or production accounts. */
import fs from 'node:fs'
import path from 'node:path'
import { loadPlaywright } from './lib/env.mjs'

const config = JSON.parse(process.env.NO_COST_E2E_CONFIG || 'null')
if (!config || !process.env.NO_COST_TEST) throw new Error('Run only through scripts/verify_no_cost_e2e.py')
const origins = new Set([config.frontend, ...Object.values(config.services)])
for (const origin of origins) if (new URL(origin).hostname !== '127.0.0.1') throw new Error('Only explicit loopback origins allowed')
const { module: pw } = loadPlaywright()
const browser = await pw.chromium.launch({ headless: true, args: ['--disable-background-networking', '--disable-component-update', '--disable-sync', '--no-first-run'] })
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true })
const results = { externalProvider: 'LOCAL_MOCK', steps: [], pageErrors: [], blockedRequests: [] }
await context.route('**/*', route => {
  const url = new URL(route.request().url())
  if (origins.has(url.origin)) return route.continue()
  results.blockedRequests.push(url.origin)
  return route.abort('blockedbyclient')
})
const page = await context.newPage()
page.on('pageerror', error => results.pageErrors.push(error.message))
function check(value, message) { if (!value) throw new Error(message); results.steps.push(message) }
try {
  await page.goto(`${config.frontend}/login`, { waitUntil: 'networkidle' })
  await page.getByPlaceholder('请输入用户名').fill(config.username)
  await page.getByPlaceholder('请输入密码', { exact: true }).fill(config.password)
  await page.locator('button.auth-button').click()
  await page.waitForURL(url => !url.pathname.startsWith('/login'), { timeout: 20000 })
  check(true, 'real UI login through isolated user service')
  await page.goto(`${config.frontend}/student/qa`, { waitUntil: 'networkidle' })
  await page.getByPlaceholder('输入你的问题，Enter 发送，Shift + Enter 换行').fill('请解释TCP确认和重传机制')
  const pending = page.waitForResponse(response => response.url().endsWith('/qa/analyze') && response.request().method() === 'POST')
  await page.getByRole('button', { name: '发送消息', exact: true }).click()
  const qa = await pending
  check(qa.status() === 200, 'QA API succeeded with local model')
  await page.getByText(/NC-QA-001/).first().waitFor({ timeout: 20000 })
  await page.reload({ waitUntil: 'networkidle' })
  await page.getByText(/NC-QA-001/).first().waitFor({ timeout: 15000 })
  check(true, 'QA answer persisted and restored after browser refresh')
  await page.screenshot({ path: path.join(config.output, 'qa-browser.png'), fullPage: true })

  await page.goto(`${config.frontend}/student/resources`, { waitUntil: 'networkidle' })
  await page.getByRole('button', { name: '打开可拖动的 AI 学习助手' }).click()
  const assistant = page.locator('.assistant-pet-panel')
  await assistant.getByRole('button', { name: '生成学习课件', exact: true }).click()
  await assistant.locator('textarea').fill('生成 TCP 可靠传输学习课件')
  const acceptedPromise = page.waitForResponse(response => response.url().endsWith('/assistant/chat') && response.request().method() === 'POST')
  await assistant.getByRole('button', { name: '发送', exact: true }).click()
  const accepted = await acceptedPromise
  check(accepted.status() === 200, 'assistant accepted persistent courseware task')
  results.taskId = (await accepted.json()).task.id
  const resourceCard = assistant.locator('.pet-result-cards button').filter({ hasText: '查看资源' }).first()
  await resourceCard.waitFor({ state: 'visible', timeout: 60000 })
  await resourceCard.click()
  const preview = page.getByTestId('generated-resource-content')
  await preview.waitFor({ state: 'visible', timeout: 15000 })
  check((await preview.innerText()).includes('NC-RESOURCE-001'), 'independent Worker resource persisted and rendered in UI')
  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('button', { name: '下载 Word 文档', exact: true }).click()
  const download = await downloadPromise
  await download.saveAs(path.join(config.output, 'courseware.docx'))
  check(fs.readFileSync(path.join(config.output, 'courseware.docx')).subarray(0, 2).toString() === 'PK', 'real browser DOCX download')
  await page.screenshot({ path: path.join(config.output, 'resource-browser.png'), fullPage: true })
  await page.goto(`${config.frontend}/student/transcripts`, { waitUntil: 'networkidle' })
  const parsedPromise = page.waitForResponse(response => response.url().endsWith('/transcripts/parse') && response.request().method() === 'POST')
  await page.locator('input[type="file"]').setInputFiles({
    name: 'no-cost-grades.csv', mimeType: 'text/csv',
    buffer: Buffer.from('\ufeff学号,姓名,科目,分数,满分\nNC001,测试学生,数学,72,100\nNC001,测试学生,英语,85,100\n', 'utf8'),
  })
  check((await parsedPromise).status() === 200, 'real CSV transcript uploaded and parsed in browser')
  const analysisPromise = page.waitForResponse(response => response.url().endsWith('/transcripts/analyze') && response.request().method() === 'POST')
  await page.getByRole('button', { name: '生成分析方案', exact: true }).click()
  check((await analysisPromise).status() === 200, 'real transcript analysis persisted through browser workflow')
  await page.getByRole('heading', { name: '7天学习路径', exact: true }).waitFor({ timeout: 15000 })
  await page.screenshot({ path: path.join(config.output, 'transcript-browser.png'), fullPage: true })
  check(results.pageErrors.length === 0, 'no browser page errors')
  results.passed = true
} catch (error) {
  results.passed = false
  results.error = String(error)
  fs.writeFileSync(path.join(config.output, 'failure-dom.txt'), await page.locator('body').innerText())
  await page.screenshot({ path: path.join(config.output, 'failure-browser.png'), fullPage: true })
  throw error
} finally {
  fs.writeFileSync(path.join(config.output, 'browser-report.json'), JSON.stringify(results, null, 2))
  await browser.close()
}
