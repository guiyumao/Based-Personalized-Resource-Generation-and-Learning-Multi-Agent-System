import fs from 'node:fs'
import path from 'node:path'
import assert from 'node:assert/strict'
import { loadPlaywright } from './lib/env.mjs'

const root = process.argv[2]
const fixture = JSON.parse(fs.readFileSync(path.join(root, 'browser-fixture.json'), 'utf8'))
const { chromium } = loadPlaywright().module
const browser = await chromium.launch({ headless: true })
const results = []; const errors = []
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
await context.addInitScript(({ token }) => localStorage.setItem('learning-system-auth', JSON.stringify({ token, user: { userId: 1, username: 'teaching-live-isolated', role: 'student' } })), fixture)
const page = await context.newPage()
page.on('pageerror', error => errors.push(error.message))
try {
  for (const item of fixture.contexts) {
    await page.goto(`http://127.0.0.1:15189/student/workspace/${item.id}`)
    await page.getByRole('navigation', { name: '课件章节目录' }).waitFor()
    await page.getByText('总结与知识拓展', { exact: true }).first().waitFor()
    await page.waitForTimeout(1000)
    const chapters = await page.locator('.courseware-reader main > details[data-section]').count()
    assert.ok(chapters >= 9)
    const answers = page.locator('.courseware-answer')
    assert.ok(await answers.count() >= 3)
    assert.equal(await answers.first().evaluate(el => el.open), false)
    await answers.first().locator('summary').click()
    assert.equal(await answers.first().evaluate(el => el.open), true)
    await page.getByRole('button', { name: '本章已读', exact: true }).first().click()
    const progress = await page.locator('.courseware-reader progress').evaluate(el => el.value)
    assert.ok(progress > 0 && progress < 100)
    await page.reload()
    await page.getByRole('navigation', { name: '课件章节目录' }).waitFor()
    assert.equal(await page.locator('.courseware-reader progress').evaluate(el => el.value), progress)
    await page.locator('.courseware-diagram').first().waitFor({ timeout: 20000 })
    await page.getByText('提交配套练习并更新学情', { exact: true }).click()
    assert.equal(await page.locator('.courseware-reader textarea').count(), 3)
    const diagrams = await page.locator('.courseware-diagram svg').count()
    const formulas = await page.locator('.katex').count()
    const highlighted = await page.locator('pre code .hljs-keyword').count()
    if (item.topic.includes('公式')) assert.ok(formulas > 0)
    if (item.topic === '链表') assert.ok(highlighted > 0)
    await page.locator('.courseware-reader main details[data-section="3"] > summary').scrollIntoViewIfNeeded()
    await page.screenshot({ path: path.join(root, `reader-${item.resource_id}-desktop.png`) })
    await page.setViewportSize({ width: 390, height: 844 })
    await page.waitForTimeout(400)
    await page.locator('.courseware-reader main details[data-section="3"] > summary').scrollIntoViewIfNeeded()
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)
    assert.equal(overflow, false)
    await page.screenshot({ path: path.join(root, `reader-${item.resource_id}-mobile.png`), fullPage: false })
    await page.setViewportSize({ width: 1440, height: 1000 })
    results.push({ topic: item.topic, chapters, persistedCharacters: item.characters, readingProgress: progress,
      formulas, highlighted, diagrams, overflow, answerToggle: true, reload: true, savedExercises: 3 })
  }
  // Two actual create-context HTTP requests return out of order.
  const [firstContext, secondContext] = fixture.contexts
  await page.goto(`http://127.0.0.1:15189/student/workspace/${firstContext.id}`)
  await page.getByRole('navigation', { name: '课件章节目录' }).waitFor()
  const createdContexts = []
  await page.route('**/agent/learning/contexts', async route => {
    if (route.request().method() !== 'POST') return route.continue()
    const response = await route.fetch()
    const data = await response.json()
    createdContexts.push(data)
    if (createdContexts.length === 1) await new Promise(resolve => setTimeout(resolve, 1400))
    await route.fulfill({ response })
  })
  await page.locator('.workspace-outline section button').first().click()
  await page.waitForTimeout(100)
  await page.locator('.workspace-outline .el-select__wrapper').click()
  await page.getByRole('option', { name: new RegExp(secondContext.topic) }).click()
  await page.locator('.workspace-outline section button').first().click()
  await page.waitForTimeout(2200)
  assert.equal(createdContexts.length, 2)
  assert.ok(page.url().endsWith(createdContexts[1].id))
  assert.equal(await page.locator('.workspace-content > h2').textContent(), secondContext.topic)
  await page.unroute('**/agent/learning/contexts')
  const auth = { Authorization: `Bearer ${fixture.token}` }
  const other = { Authorization: `Bearer ${fixture.other_token}` }
  const first = fixture.contexts[0]
  assert.equal((await page.request.get(`http://127.0.0.1:18221/agent/learning/contexts/${first.id}`, { headers: other })).status(), 404)
  assert.ok([403, 404].includes((await page.request.get(`http://127.0.0.1:18221/resource/resources/${first.resource_id}`, { headers: other })).status()))
  const revisionUrl = `http://127.0.0.1:18221/agent/resources/${first.resource_id}/chapters/case/regenerate`
  const payload = { expected_version: first.version, client_request_id: 'teaching-browser-chapter-revision' }
  const revision = await page.request.post(revisionUrl, { headers: auth, data: payload })
  assert.equal(revision.status(), 202, await revision.text())
  const task = await revision.json()
  const replay = await page.request.post(revisionUrl, { headers: auth, data: payload })
  assert.equal((await replay.json()).id, task.id)
  assert.equal((await page.request.post(revisionUrl, { headers: other, data: payload })).status(), 404)
  // Standalone courseware creation queues a real durable task and resumes
  // the same task after reload. No Worker/provider is run in this UI check.
  await page.goto('http://127.0.0.1:15189/student/courseware')
  await page.getByText('等待执行', { exact: true }).waitFor({ timeout: 20000 })
  const queuedBefore = (await (await page.request.get('http://127.0.0.1:18221/agent/assistant/tasks', { headers: auth })).json()).filter(item => item.task_type === 'courseware')
  assert.equal(queuedBefore.length, 1)
  await page.reload()
  await page.getByText('等待执行', { exact: true }).waitFor({ timeout: 20000 })
  const queuedAfter = (await (await page.request.get('http://127.0.0.1:18221/agent/assistant/tasks', { headers: auth })).json()).filter(item => item.task_type === 'courseware')
  assert.equal(queuedAfter.length, 1)
  assert.equal(queuedAfter[0].id, queuedBefore[0].id)
  assert.deepEqual(errors, [])
  fs.writeFileSync(path.join(root, 'browser-result.json'), JSON.stringify({ passed: true, results,
    pageErrors: errors, privacy: true, rapidSwitch: true, revisionTask: task.id, revisionIdempotency: true, standaloneTaskReload: true,
    note: 'Real generated bodies, real SQL/API; chapter revision queued only; no model calls.' }, null, 2))
} catch (error) {
  await page.screenshot({ path: path.join(root, 'failure.png'), fullPage: true })
  fs.writeFileSync(path.join(root, 'browser-result.json'), JSON.stringify({ passed: false, results, pageErrors: errors, error: String(error) }, null, 2))
  throw error
} finally { await browser.close() }
