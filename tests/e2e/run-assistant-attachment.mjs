/** Real browser upload and model answer using a private text attachment. */
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
  const uploadResponse = page.waitForResponse((response) => response.url().endsWith('/assistant/attachments') && response.request().method() === 'POST')
  await assistant.locator('input[type="file"]').setInputFiles({
    name: 'lesson.txt', mimeType: 'text/plain',
    buffer: Buffer.from('课程资料：二叉树前序遍历先访问根节点，再访问左子树，最后访问右子树。', 'utf8'),
  })
  const uploaded = await uploadResponse
  if (uploaded.status() !== 201 || !(await uploaded.json()).id) throw new Error(`Upload failed: ${uploaded.status()}`)
  await assistant.getByText('lesson.txt').first().waitFor({ timeout: 10000 })
  process.stdout.write('[ok] text attachment uploaded and displayed\n')

  await assistant.locator('textarea').fill('根据我上传的资料，解释二叉树前序遍历的步骤。')
  await assistant.getByRole('button', { name: '发送' }).click()
  await assistant.locator('.pet-message.assistant .pet-message-content').last().getByText(/根节点|左子树/).first().waitFor({ timeout: 60000 })
  if (await assistant.locator('.pet-message.user .pet-message-attachments').filter({ hasText: 'lesson.txt' }).count() < 1) throw new Error('User message lost its attachment label')
  process.stdout.write('[ok] model response and user attachment label rendered\n')

  await page.reload({ waitUntil: 'domcontentloaded' })
  await page.getByRole('button', { name: '打开可拖动的 AI 学习助手' }).click()
  await assistant.locator('.pet-message.user .pet-message-attachments').filter({ hasText: 'lesson.txt' }).waitFor({ timeout: 15000 })
  await assistant.getByRole('button', { name: '助手设置' }).click()
  const storedFiles = assistant.locator('details.pet-memory-manager').filter({ hasText: '已提取的资料' })
  await storedFiles.locator('summary').click()
  await storedFiles.getByText('lesson.txt').waitFor({ timeout: 10000 })
  const deleteResponse = page.waitForResponse((response) => response.url().includes('/assistant/attachments/') && response.request().method() === 'DELETE')
  await storedFiles.getByRole('button', { name: '删除' }).click()
  if ((await deleteResponse).status() !== 200) throw new Error('Attachment delete failed')
  await storedFiles.getByText('lesson.txt').waitFor({ state: 'detached', timeout: 10000 })
  if (errors.length) throw new Error(`Browser errors: ${errors.join('; ')}`)
  process.stdout.write('[ok] attachment label survives refresh and stored text can be deleted without browser errors\n')
} finally {
  await context.close()
  await browser.close()
}
