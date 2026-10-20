/** Browser acceptance check for the draggable animated learning assistant. */
import path from 'node:path'

import {
  BASE_URL,
  DESKTOP,
  MOBILE,
  REPO_ROOT,
  ensureDirs,
  loadPlaywright,
  parseDotEnv,
  shot,
} from './lib/env.mjs'

function assert(condition, message) {
  if (!condition) throw new Error(message)
  process.stdout.write(`[ok] ${message}\n`)
}

function moved(before, after, minimum = 30) {
  if (!before || !after) return false
  return Math.hypot(after.x - before.x, after.y - before.y) >= minimum
}

async function drag(page, box, deltaX, deltaY) {
  assert(Boolean(box), 'draggable element has a measurable box')
  const startX = box.x + box.width / 2
  const startY = box.y + box.height / 2
  await page.mouse.move(startX, startY)
  await page.mouse.down()
  await page.mouse.move(startX + deltaX, startY + deltaY, { steps: 8 })
  await page.mouse.up()
}

async function main() {
  ensureDirs()
  const rootEnv = parseDotEnv(path.join(REPO_ROOT, '.env'))
  const adminUser = rootEnv.DEFAULT_ADMIN_USERNAME || 'admin'
  const adminPass = rootEnv.DEFAULT_ADMIN_PASSWORD
  if (!adminPass) throw new Error('DEFAULT_ADMIN_PASSWORD is required for assistant E2E login')

  const { module: pw } = loadPlaywright()
  const browser = await pw.chromium.launch({ headless: true })
  const context = await browser.newContext({ viewport: DESKTOP })
  const page = await context.newPage()
  const pageErrors = []
  page.on('pageerror', (error) => pageErrors.push(String(error)))

  try {
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'domcontentloaded' })
    await page.fill('input[autocomplete="username"]', adminUser)
    await page.fill('input[autocomplete="current-password"]', adminPass)
    await page.click('button.auth-button')
    await page.waitForTimeout(1500)
    process.stdout.write(`login_state=${JSON.stringify({url: page.url(), errors: pageErrors, messages: await page.locator('.el-message').allTextContents()})}\n`)
    await page.waitForURL('**/admin', { timeout: 8000 }).catch(async () => {
      throw new Error(`Login did not reach /admin; URL=${page.url()}, feedback=${(await page.locator('.el-message, .auth-error, .error-message').allTextContents()).join(' | ')}`)
    })

    const pet = page.locator('.assistant-pet-button')
    await pet.waitFor({ state: 'visible', timeout: 20000 })
    assert(await pet.isVisible(), 'assistant is visible after login')
    assert(await pet.locator('.xiaozhi-avatar svg').isVisible(), 'new XiaoZhi SVG is rendered')
    const animationName = await page.locator('.pet-character').evaluate((el) => getComputedStyle(el).animationName)
    assert(animationName.includes('xz-float'), `avatar uses the floating animation (${animationName})`)
    assert((await page.getByText('生成 Prompt', { exact: true }).count()) === 0, 'Prompt mode is absent')

    const petBefore = await pet.boundingBox()
    await drag(page, petBefore, -180, -120)
    const petAfter = await pet.boundingBox()
    assert(moved(petBefore, petAfter), 'collapsed pet can be dragged')
    const savedPosition = await page.evaluate(() => localStorage.getItem('learning-assistant-pet-position'))
    assert(Boolean(savedPosition), 'dragged pet position is persisted')
    const collapsedScreenshot = await shot(page, 'assistant-pet-collapsed-dragged')
    process.stdout.write(`collapsed_screenshot=${collapsedScreenshot}\n`)

    await pet.click()
    const panel = page.locator('.assistant-pet-panel')
    await panel.waitFor({ state: 'visible' })
    assert(await panel.getByText('你好，我是小智', { exact: true }).isVisible(), 'welcome state is visible')
    assert(await panel.getByRole('button', { name: '生成针对性练习' }).isVisible(), 'real task shortcut is visible')
    await panel.getByRole('button', { name: '打开学习工作台' }).click()
    assert(await panel.locator('.pet-context').isVisible(), 'workspace context column is visible')
    await panel.getByRole('button', { name: '返回聊天窗口' }).click()
    await panel.getByRole('button', { name: '助手设置' }).click()
    const rendered = await page.evaluate(async () => {
      const { renderLearningMarkdown } = await import('/src/utils/renderLearningMarkdown.ts')
      return renderLearningMarkdown('公式 $x^2+1$，链接 [资料](https://example.com) <img src=x onerror=alert(1)>')
    })
    assert(rendered.includes('class="katex"'), 'inline KaTeX renders')
    assert(!rendered.includes('<img'), 'untrusted HTML is escaped')
    assert(rendered.includes('noopener noreferrer'), 'external links use safe attributes')
    await panel.getByLabel('动态效果').uncheck()
    assert(await page.locator('.pet-title-row .xiaozhi-avatar.has-motion').count() === 0, 'motion preference disables avatar animation')
    await panel.getByRole('button', { name: '助手设置' }).click()

    const panelBefore = await panel.boundingBox()
    const header = page.locator('.pet-panel-header')
    await drag(page, await header.boundingBox(), 100, 70)
    const panelAfter = await panel.boundingBox()
    assert(moved(panelBefore, panelAfter), 'expanded assistant panel can be dragged by its header')
    const desktopScreenshot = await shot(page, 'assistant-pet-desktop-chat')
    process.stdout.write(`desktop_screenshot=${desktopScreenshot}\n`)

    await page.setViewportSize(MOBILE)
    await page.waitForTimeout(120)
    const mobilePanel = await panel.boundingBox()
    assert(
      Boolean(mobilePanel)
        && mobilePanel.x >= 0
        && mobilePanel.y >= 0
        && mobilePanel.x + mobilePanel.width <= MOBILE.width + 1
        && mobilePanel.y + mobilePanel.height <= MOBILE.height + 1,
      'assistant panel stays inside the 390x844 viewport',
    )
    const mobileScreenshot = await shot(page, 'assistant-pet-mobile')
    process.stdout.write(`mobile_screenshot=${mobileScreenshot}\n`)
    assert(pageErrors.length === 0, `no page errors occurred (${pageErrors.join('; ')})`)
    const screenshot = await shot(page, 'assistant-pet-dragged')
    process.stdout.write(`screenshot=${screenshot}\n`)
  } finally {
    await context.close()
    await browser.close()
  }
}

main().catch((error) => {
  process.stderr.write(`${error.stack || error}\n`)
  process.exitCode = 1
})
