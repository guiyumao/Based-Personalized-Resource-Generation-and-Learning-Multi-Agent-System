/** Real provider stream through the XiaoZhi browser UI and authenticated API. */
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
  await assistant.getByRole('button', { name: '开始新对话' }).click()
  await assistant.locator('textarea').fill('用简单例子解释二叉树前序遍历')
  const pending = page.waitForResponse((response) => response.url().endsWith('/assistant/chat/stream') && response.request().method() === 'POST')
  await assistant.getByRole('button', { name: '发送' }).click()
  const response = await pending
  const streamBody = await response.text()
  assert(response.status() === 200, 'authenticated stream endpoint returns HTTP 200')
  assert(streamBody.includes('event: start') && streamBody.includes('event: final'), 'SSE has start and final events')
  assert(streamBody.match(/event: delta/g)?.length > 2, 'provider emitted multiple real token deltas')
  await page.waitForFunction(() => {
    const nodes = document.querySelectorAll('.pet-message.assistant .pet-message-content')
    const last = nodes[nodes.length - 1]
    return Boolean(last && (last.textContent || '').length > 40 && (last.textContent || '').includes('前序遍历'))
  }, { timeout: 15000 })
  assert(await assistant.getByRole('button', { name: '停止生成' }).count() === 0, 'stream exits the thinking state')
  await page.reload({ waitUntil: 'domcontentloaded' })
  await page.getByRole('button', { name: '打开可拖动的 AI 学习助手' }).click()
  await page.getByText(/前序遍历/).first().waitFor({ timeout: 10000 })
  assert(await page.locator('.pet-message.assistant').count() > 0, 'streamed answer is restored from database')
  const restoredAssistant = page.locator('.assistant-pet-panel')
  await restoredAssistant.getByRole('button', { name: '助手设置' }).click()
  assert(!(await restoredAssistant.getByLabel('使用学习上下文').isChecked()), 'learning memory is opt-in')
  await restoredAssistant.locator('.pet-memory-manager summary').click()
  await restoredAssistant.getByPlaceholder('输入并确认要保存的内容').fill('喜欢图解二叉树')
  await restoredAssistant.getByRole('button', { name: '保存记忆' }).click()
  await restoredAssistant.getByText('喜欢图解二叉树', { exact: true }).waitFor({ timeout: 10000 })
  const savedMemory = restoredAssistant.locator('.pet-memory-item').filter({ hasText: '喜欢图解二叉树' })
  await savedMemory.getByRole('button', { name: '修正' }).click()
  await restoredAssistant.getByPlaceholder('输入并确认要保存的内容').fill('喜欢画图理解二叉树')
  await restoredAssistant.getByRole('button', { name: '保存修正' }).click()
  await restoredAssistant.getByText('喜欢画图理解二叉树', { exact: true }).waitFor({ timeout: 10000 })
  await restoredAssistant.locator('.pet-memory-item').filter({ hasText: '喜欢画图理解二叉树' }).getByRole('button', { name: '删除' }).click()
  await restoredAssistant.getByText('喜欢画图理解二叉树', { exact: true }).waitFor({ state: 'detached', timeout: 10000 })
  assert(true, 'memory create, correction and deletion work through the UI')
  assert(errors.length === 0, `no browser errors occurred (${errors.join('; ')})`)
} finally {
  await context.close()
  await browser.close()
}
