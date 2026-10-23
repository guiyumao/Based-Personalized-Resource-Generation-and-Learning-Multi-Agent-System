// Browser navigation regression. All HTTP APIs are intercepted; no model/DB writes.
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { loadPlaywright } from './lib/env.mjs'
const out = path.resolve('artifacts/workspace-background-20261023/browser')
fs.mkdirSync(out, { recursive: true })
const { chromium } = loadPlaywright().module
const browser = await chromium.launch({ headless: true })
const report = { mockedBackends: true, realModelCalls: 0, databaseWrites: 0, cases: [] }
try {
  for (const reload of [false, true]) {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
    const state = { submitted: 0, done: false, polls: 0 }
    const errors = []
    const snapshot = id => ({ id, plan_id: 369, module_id: 's1', task_id: 't1', subject: 'C++', knowledge_point: '链表', plan_revision: 0,
      resource_candidates: [], exercises: [], resource: id === 'linked' ? { id: 901, version: 'a'.repeat(64), type: 'article', title: '链表课件已完成', content: '# 链表后台生成结果' } : null })
    await context.addInitScript(() => {
      const auth = JSON.stringify({ token: 'mock', user: { userId: 104, username: 'student', role: 'student' } })
      localStorage.setItem('learning-system-auth', auth); sessionStorage.setItem('learning-system-tab-auth', auth)
    })
    await context.route(/http:\/\/(?:127\.0\.0\.1|localhost):800[1-7]\//, async route => {
      const url = new URL(route.request().url()); const p = url.pathname
      const json = data => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(data) })
      if (p === '/users/me') return json({ id: 104, username: 'student', role: 'student' })
      if (p === '/learning/contexts/catalog') return json({ plans: [{ id: 369, data: { subject: 'C++', knowledge_point: '链表', stages: [{ stage_id: 's1', title: '基础', tasks: [{ task_id: 't1', title: '学习链表', knowledge_point: '链表' }] }] } }], task_resources: [] })
      if (p.startsWith('/learning/contexts/')) return json(snapshot(p.split('/').at(-1)))
      if (p === '/assistant/chat') {
        state.submitted++
        await new Promise(resolve => setTimeout(resolve, 1500))
        return json({ task: { id: 16, status: 'PENDING', current_step: '等待执行' } })
      }
      const task = () => ({ id: 16, status: state.done ? 'SUCCEEDED' : 'RUNNING', current_step: '生成课件', result: state.done ? { cards: [{ learning_context_id: 'linked' }] } : {} })
      if (p === '/assistant/tasks') return json(state.submitted ? [task()] : [])
      if (p === '/assistant/tasks/16') { state.polls++; return json(task()) }
      if (p === '/evaluation/overview/me') return json({ data: { active_plans: [], due_cards: 0, suggestions: [], recent_resources: [], weak_points: [], analytics: { daily: [], summary: {}, week_comparison: {} } } })
      if (p.includes('dashboard')) return json({ heatmap: [], radar_metrics: [], knowledge_graph: [], suggestions: [], ability_summary: '', learning_style: '' })
      return json({ data: [] })
    })
    const page = await context.newPage(); page.on('pageerror', e => { if (!errors.length) console.log(e.stack); errors.push(e.message) })
    await page.goto('http://127.0.0.1:5175/student/workspace/origin')
    const submission = page.waitForRequest(r => r.url().includes('/assistant/chat'))
    await page.getByRole('button', { name: '生成课件', exact: true }).click()
    await submission
    if (reload) {
      // Reload after receipt persistence; case A exercises leaving before receipt.
      await page.getByRole('status').filter({ hasText: '任务已交给后台' }).waitFor()
      await page.waitForFunction(() => localStorage.getItem('workspace-job:104:origin') === '16')
      await page.reload()
    } else {
      await page.locator('.app-sidebar .nav-item').filter({ hasText: '学习概览' }).first().click()
      await page.waitForURL('**/student/dashboard')
    }
    state.done = true
    await page.waitForTimeout(4500)
    if (!reload) await page.goBack()
    await page.waitForURL('**/student/workspace/linked')
    await page.getByText('链表后台生成结果', { exact: true }).waitFor({ timeout: 8000 }).catch(async error => {
      await page.screenshot({ path: path.join(out, 'failure.png') })
      console.log(await page.locator('main').allTextContents(), errors)
      throw error
    })
    assert.equal(state.submitted, 1); assert.deepEqual(errors, [])
    await page.screenshot({ path: path.join(out, reload ? 'reload.png' : 'return.png') })
    report.cases.push({ reload, passed: true, ...state, pageErrors: errors })
    await context.close()
  }
} finally { await browser.close(); fs.writeFileSync(path.join(out, 'result.json'), JSON.stringify(report, null, 2)) }
console.log(JSON.stringify(report))
