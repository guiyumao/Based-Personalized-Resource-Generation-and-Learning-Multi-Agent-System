import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { loadPlaywright } from './lib/env.mjs'
const out = process.argv[2], accounts = JSON.parse(process.env.CURRENT_ROLE_AUTH)
const { chromium } = loadPlaywright().module
const browser = await chromium.launch({ headless: true })
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
const errors = [], failures = [], classes = []
async function open(name, route) {
  const page = await context.newPage()
  await page.addInitScript(auth => {
    if (!sessionStorage.getItem('learning-system-tab-auth')) {
      localStorage.setItem('learning-system-auth', JSON.stringify(auth))
      sessionStorage.setItem('learning-system-tab-auth', JSON.stringify(auth))
    }
  }, accounts[name])
  page.on('pageerror', e => errors.push(e.message))
  page.on('response', r => { if (r.status() >= 400 && /:8005\//.test(r.url())) failures.push({ path: new URL(r.url()).pathname, status: r.status() }) })
  await page.goto('http://127.0.0.1:5175' + route)
  await page.locator('.user-copy strong').filter({ hasText: name }).waitFor()
  return page
}
try {
  const teacher = await open('teacher111', '/teacher/classes')
  const student = await open('student', '/student/classroom')
  await student.getByRole('button', { name: '刷新班级与作业', exact: true }).click()
  await student.getByRole('heading', { name: '我的班级', exact: true }).waitFor()
  await teacher.getByRole('button', { name: '刷新列表', exact: true }).click()
  const response = await teacher.request.get('http://127.0.0.1:8005/teacher/classes', { headers: { Authorization: `Bearer ${accounts.teacher111.token}` } })
  assert.equal(response.status(), 200)
  const rows = (await response.json()).data
  for (const row of rows) {
    await teacher.locator('button.list-card').filter({ hasText: `班级 #${row.id} /` }).click()
    await teacher.locator('.class-detail').getByRole('button', { name: '刷新成员', exact: true }).click()
    await teacher.waitForFunction(() => !document.querySelector('.class-detail .el-loading-mask'))
    const members = await teacher.request.get(`http://127.0.0.1:8005/teacher/classes/${row.id}/members`, { headers: { Authorization: `Bearer ${accounts.teacher111.token}` } })
    assert.equal(members.status(), 200)
    const list = (await members.json()).data
    for (const item of list) await teacher.locator('.class-detail').getByText(item.username, { exact: true }).waitFor()
    classes.push({ classId: row.id, studentCount: row.student_count, memberCount: list.length })
    assert.equal(row.student_count, list.length)
  }
  const populated = rows.find(r => r.student_count > 0)
  if (populated) {
    await teacher.locator('button.list-card').filter({ hasText: `班级 #${populated.id} /` }).click()
    await teacher.locator('.app-sidebar').getByRole('button', { name: '学生洞察', exact: true }).click()
    await teacher.locator('.report-grid article h3').first().waitFor()
    await teacher.screenshot({ path: path.join(out, 'teacher-insights-current.png'), fullPage: true })
  }
  await student.reload()
  await student.getByRole('heading', { name: '我的班级', exact: true }).waitFor()
  await teacher.reload()
  await teacher.locator('.user-copy strong').filter({ hasText: 'teacher111' }).waitFor()
  await student.getByRole('button', { name: '刷新班级与作业', exact: true }).click()
  assert.deepEqual(errors, []); assert.deepEqual(failures, [])
  fs.writeFileSync(path.join(out, 'result.json'), JSON.stringify({ classes, errors, failures, apiMocked: false, current5175: true, businessDataChanged: false, loginMethod: 'existing-user signed tokens; password login separately verified in same-browser test' }, null, 2))
  console.log(JSON.stringify({ classes, errors, failures }))
} finally { await context.close(); await browser.close() }
