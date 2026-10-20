/** Real-model path draft, user confirmation and refresh against an isolated DB. */
import path from 'node:path'
import { BASE_URL, DESKTOP, REPO_ROOT, ensureDirs, loadPlaywright, parseDotEnv, shot } from './lib/env.mjs'

function assert(condition, message) {
  if (!condition) throw new Error(message)
  process.stdout.write(`[ok] ${message}\n`)
}

const credentials = parseDotEnv(path.join(REPO_ROOT, '.env'))
const agentUrl = process.env.E2E_AGENT_URL || 'http://127.0.0.1:8002'
const { module: pw } = loadPlaywright()
const browser = await pw.chromium.launch({ headless: true })
const context = await browser.newContext({ viewport: DESKTOP })
const page = await context.newPage()
const errors = []
page.on('pageerror', (error) => errors.push(String(error)))

try {
  ensureDirs()
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'domcontentloaded' })
  await page.fill('input[autocomplete="username"]', credentials.DEFAULT_ADMIN_USERNAME || 'admin')
  await page.fill('input[autocomplete="current-password"]', credentials.DEFAULT_ADMIN_PASSWORD)
  await page.click('button.auth-button')
  await page.waitForURL('**/admin', { timeout: 15000 })
  const auth = await page.evaluate(() => JSON.parse(localStorage.getItem('learning-system-auth')))
  const headers = { Authorization: `Bearer ${auth.token}` }
  if (process.env.E2E_EXPECT_TASK_MODE) {
    const capabilities = await context.request.get(`${agentUrl}/assistant/capabilities`, { headers })
    assert((await capabilities.json()).task_execution_mode === process.env.E2E_EXPECT_TASK_MODE, 'API is configured for the expected task executor')
  }
  const getActivePath = async () => {
    const response = await context.request.get(`${agentUrl}/paths/${auth.user.userId}`, { headers })
    return { status: response.status(), body: await response.json() }
  }
  const before = await getActivePath()
  assert([200, 404].includes(before.status), 'active path baseline is readable')

  await page.getByRole('button', { name: '打开可拖动的 AI 学习助手' }).click()
  const assistant = page.locator('.assistant-pet-panel')
  await assistant.getByRole('button', { name: '制定学习计划', exact: true }).click()
  await assistant.locator('textarea').fill('制定 TCP 协议三天复习计划')
  const acceptedResponse = page.waitForResponse((response) => response.url().endsWith('/assistant/chat') && response.request().method() === 'POST')
  await assistant.getByRole('button', { name: '发送', exact: true }).click()
  const accepted = await acceptedResponse
  assert(accepted.status() === 200, 'path generation request accepted')
  const taskId = (await accepted.json()).task.id
  const draftButton = assistant.locator('.pet-result-cards button').filter({ hasText: '确认保存学习路径' })
  await draftButton.waitFor({ state: 'visible', timeout: 180000 })
  assert(await draftButton.isEnabled(), 'real model draft has an enabled confirmation card')
  assert(JSON.stringify(await getActivePath()) === JSON.stringify(before), 'draft generation keeps the current active plan')

  await page.reload({ waitUntil: 'domcontentloaded' })
  await page.getByRole('button', { name: '打开可拖动的 AI 学习助手' }).click()
  await draftButton.waitFor({ state: 'visible', timeout: 15000 })
  await draftButton.click()
  await page.getByRole('button', { name: '继续查看草案', exact: true }).click()
  assert(JSON.stringify(await getActivePath()) === JSON.stringify(before), 'cancelling confirmation leaves the active plan unchanged')
  await draftButton.click()
  const savedResponse = page.waitForResponse((response) => response.url().endsWith(`/assistant/tasks/${taskId}/confirm-path`) && response.request().method() === 'POST')
  await page.getByRole('button', { name: '确认保存', exact: true }).click()
  const saved = await savedResponse
  const savedTask = await saved.json()
  assert(saved.status() === 200 && savedTask.result.path_saved === true, 'owner confirmation saves the plan')
  const after = await getActivePath()
  assert(after.status === 200 && after.body.stages.length > 0, 'saved plan is readable through the existing learning-path API')
  const repeated = await context.request.post(`${agentUrl}/assistant/tasks/${taskId}/confirm-path`, { headers })
  assert(repeated.status() === 200 && JSON.stringify(await getActivePath()) === JSON.stringify(after), 'repeated confirmation preserves the same plan')
  await page.reload({ waitUntil: 'domcontentloaded' })
  await page.getByRole('button', { name: '打开可拖动的 AI 学习助手' }).click()
  const savedCard = assistant.locator('.pet-result-cards button').filter({ hasText: '查看学习路径' })
  await savedCard.waitFor({ timeout: 15000 })
  await savedCard.scrollIntoViewIfNeeded()
  await page.waitForTimeout(400) // Let the panel's enter transition finish before visual evidence.
  const panelBox = await assistant.boundingBox()
  assert(panelBox && panelBox.x >= 0 && panelBox.y >= 0 && panelBox.x + panelBox.width <= DESKTOP.width + 1 && panelBox.y + panelBox.height <= DESKTOP.height + 1, 'confirmed plan stays inside the visible assistant panel')
  assert(errors.length === 0, `no browser errors occurred (${errors.join('; ')})`)
  process.stdout.write(`screenshot=${await shot(page, 'assistant-plan-confirmed')}\n`)
} finally {
  await context.close()
  await browser.close()
}
