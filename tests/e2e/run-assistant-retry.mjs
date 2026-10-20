/** Failed assistant tasks stay visible and can be retried through the real API. */
import path from 'node:path'
import { BASE_URL, DESKTOP, REPO_ROOT, loadPlaywright, parseDotEnv } from './lib/env.mjs'

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
  await assistant.locator('textarea').fill('根据我的薄弱知识点生成十道练习题')
  const createdResponse = page.waitForResponse((response) => response.url().endsWith('/assistant/chat') && response.request().method() === 'POST')
  await assistant.getByRole('button', { name: '发送' }).click()
  const created = await (await createdResponse).json()
  if (created.kind !== 'task' || !created.task.id) throw new Error('Assistant did not create a task')
  await assistant.getByRole('button', { name: '重试任务' }).waitFor({ timeout: 15000 })
  process.stdout.write('[ok] failed task offers a retry action\n')

  const retryResponse = page.waitForResponse((response) => response.url().endsWith(`/assistant/tasks/${created.task.id}/retry`) && response.request().method() === 'POST')
  await assistant.getByRole('button', { name: '重试任务' }).click()
  const retried = await (await retryResponse).json()
  if (retried.kind !== 'task' || retried.task.id === created.task.id) throw new Error('Retry did not create a new task')
  await assistant.getByRole('button', { name: '重试任务' }).last().waitFor({ timeout: 15000 })
  process.stdout.write('[ok] retry created a separately persisted task\n')

  await page.reload({ waitUntil: 'domcontentloaded' })
  await page.getByRole('button', { name: '打开可拖动的 AI 学习助手' }).click()
  await assistant.getByRole('button', { name: '重试任务' }).first().waitFor({ timeout: 15000 })
  if (await assistant.getByRole('button', { name: '重试任务' }).count() < 2) throw new Error('Failed tasks did not survive refresh')
  if (errors.length) throw new Error(`Browser errors: ${errors.join('; ')}`)
  process.stdout.write('[ok] failed tasks and retry actions survive refresh without browser errors\n')
} finally {
  await context.close()
  await browser.close()
}
