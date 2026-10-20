/** Authenticated XiaoZhi profile task against a running agent service. */
import path from 'node:path'
import { BASE_URL, DESKTOP, REPO_ROOT, loadPlaywright, parseDotEnv } from './lib/env.mjs'

function assert(condition, message) {
  if (!condition) throw new Error(message)
  process.stdout.write(`[ok] ${message}\n`)
}

const credentials = parseDotEnv(path.join(REPO_ROOT, '.env'))
const { module: pw } = loadPlaywright()
const browser = await pw.chromium.launch({ headless: true })
const context = await browser.newContext({ viewport: DESKTOP })
const page = await context.newPage()
const errors = []
page.on('pageerror', (error) => errors.push(String(error)))

try {
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'domcontentloaded' })
  await page.fill('input[autocomplete="username"]', credentials.DEFAULT_ADMIN_USERNAME || 'admin')
  await page.fill('input[autocomplete="current-password"]', credentials.DEFAULT_ADMIN_PASSWORD)
  await page.click('button.auth-button')
  await page.waitForURL('**/admin', { timeout: 15000 })
  await page.getByRole('button', { name: '打开可拖动的 AI 学习助手' }).click()
  const assistant = page.locator('.assistant-pet-panel')
  await assistant.getByRole('button', { name: '分析我的学情' }).click()
  assert(await assistant.locator('textarea').inputValue() === '分析我的学情和薄弱知识点', 'shortcut prepares a real profile request')
  const pendingResponse = page.waitForResponse((response) => response.url().endsWith('/assistant/chat') && response.request().method() === 'POST')
  await assistant.getByRole('button', { name: '发送' }).click()
  const response = await pendingResponse
  assert(response.status() === 200, 'assistant task accepted by authenticated API')
  const body = await response.json()
  assert(body.kind === 'task' && body.task.id > 0, 'server returned a persistent task ID')
  await assistant.locator('.pet-message.task').getByText(/没有可用于分析的练习/).waitFor({ timeout: 15000 })
  assert(await assistant.getByText(/没有可用于分析的练习/).isVisible(), 'no-data profile response is grounded in the empty database')
  await page.reload({ waitUntil: 'domcontentloaded' })
  await page.getByRole('button', { name: '打开可拖动的 AI 学习助手' }).click()
  assert(await page.getByText(/没有可用于分析的练习/).isVisible(), 'task result survives a page refresh')
  assert(errors.length === 0, `no browser errors occurred (${errors.join('; ')})`)
} finally {
  await context.close()
  await browser.close()
}
