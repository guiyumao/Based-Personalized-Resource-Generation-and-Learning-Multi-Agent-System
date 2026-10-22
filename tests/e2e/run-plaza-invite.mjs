import fs from 'node:fs'
import path from 'node:path'
import assert from 'node:assert/strict'
import { loadPlaywright } from './lib/env.mjs'

const { chromium } = loadPlaywright().module
const teacher = JSON.parse(process.env.CHECKIN_TEACHER_AUTH)
const student = JSON.parse(process.env.CHECKIN_STUDENT_AUTH)
const out = process.env.CHECKIN_OUT
const browser = await chromium.launch({ headless: true })
const context = await browser.newContext({ viewport: { width: 1440, height: 960 } })
await context.addInitScript(auth => {
  sessionStorage.setItem('learning-system-tab-auth', auth)
  localStorage.setItem('learning-system-auth', auth)
}, JSON.stringify(student))
const page = await context.newPage()
const report = { checks: [], errors: [], screenshots: [] }
page.on('pageerror', e => report.errors.push(String(e)))
page.on('response', r => { if (r.status() >= 500) report.errors.push(`${r.status()} ${r.url().split('?')[0]}`) })
async function call(auth, method, url, data) {
  const res = await context.request.fetch('http://127.0.0.1:8005' + url, {
    method, data, headers: { Authorization: `Bearer ${auth.token}` },
  })
  assert.ok(res.ok(), `${method} ${url}: ${res.status()}`)
  return (await res.json()).data
}
function check(name, condition = true) { assert.ok(condition, name); report.checks.push(name) }
async function shot(name) {
  const file = path.join(out, name + '.png')
  await page.screenshot({ path: file, fullPage: true, animations: 'disabled' })
  report.screenshots.push(file)
}
const searchInput = page.getByPlaceholder('搜索课堂、学科、教师或完整邀请码')
async function search(value) {
  await searchInput.fill(value)
  const response = page.waitForResponse(r => r.url().includes('/learning/classrooms/plaza?') && r.request().method() === 'GET')
  await searchInput.press('Enter')
  const res = await response
  assert.equal(res.status(), 200)
  const payload = (await res.json()).data
  check('search response never exposes classroom invite codes', payload.every(c => !('invite_code' in c)))
  await page.waitForLoadState('networkidle')
  return payload
}
try {
  fs.mkdirSync(out, { recursive: true })
  const room = (await call(teacher, 'GET', '/teacher/classes')).find(r => r.name === process.env.CHECKIN_CLASS_NAME)
  await call(student, 'POST', `/learning/classrooms/${room.id}/leave`)
  await call(teacher, 'PATCH', `/teacher/classes/${room.id}`, {
    name: room.name, subject: room.subject, join_mode: 'invite', is_public: false, capacity: 1,
  })
  let code = (await call(teacher, 'POST', `/teacher/classes/${room.id}/invite`)).invite_code
  await page.goto('http://127.0.0.1:5175/student/classroom-plaza', { waitUntil: 'networkidle' })
  check('private class absent from ordinary plaza', await page.locator('.plaza-card').filter({ hasText: room.name }).count() === 0)
  const partial = await search(code.slice(0, 8))
  check('partial invitation does not find private class', !partial.some(c => c.id === room.id))
  const matched = await search(' ' + code.toLowerCase() + ' ')
  check('complete lowercase invitation finds the correct private class', matched.length === 1 && matched[0].id === room.id && matched[0].invite_matched)
  await page.getByRole('button', { name: '使用邀请码加入', exact: true }).waitFor()
  // Do not include the supplied invite in a screenshot artifact.
  await searchInput.fill('未提交的新搜索文字')
  await shot('invite-found')
  const joined = page.waitForResponse(r => r.url().endsWith('/teacher/students/me/classes/join') && r.request().method() === 'POST')
  await page.getByRole('button', { name: '使用邀请码加入', exact: true }).click()
  assert.equal((await joined).status(), 200)
  check('join uses displayed result invitation despite unsubmitted input changes')
  await page.waitForLoadState('networkidle')
  await search(code)
  await page.getByRole('button', { name: '已加入 · 进入我的课堂', exact: true }).waitFor()
  check('search after joining reports joined instead of another join button')
  await searchInput.fill('已加入课堂')
  await shot('invite-joined')
  await page.getByRole('button', { name: '已加入 · 进入我的课堂', exact: true }).click()
  await page.getByText(room.name, { exact: true }).first().waitFor()
  check('joined classroom appears in my classrooms')
  await page.goto('http://127.0.0.1:5175/student/timetable', { waitUntil: 'networkidle' })
  await page.getByText(room.name, { exact: true }).first().waitFor()
  await page.locator('.lesson').filter({ hasText: '界面验收 · 图论' }).waitFor()
  check('invite enrollment imports classroom and teacher lesson into timetable')

  await call(student, 'POST', `/learning/classrooms/${room.id}/leave`)
  const oldCode = code
  code = (await call(teacher, 'POST', `/teacher/classes/${room.id}/invite`)).invite_code
  await page.goto('http://127.0.0.1:5175/student/classroom-plaza', { waitUntil: 'networkidle' })
  check('rotated old invitation no longer finds class', !(await search(oldCode)).some(c => c.id === room.id))
  await search(code)
  await page.getByRole('button', { name: '使用邀请码加入', exact: true }).waitFor()
  check('new invitation finds class after rotation')
  await searchInput.fill('已验证邀请码')
  await page.setViewportSize({ width: 390, height: 844 })
  check('mobile search and course card have no horizontal overflow', await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2))
  await shot('mobile-invite-search')
  check('no page exceptions or server errors', report.errors.length === 0)
} catch (e) { report.error = String(e.stack || e); process.exitCode = 1 }
finally {
  fs.writeFileSync(path.join(out, 'result.json'), JSON.stringify(report, null, 2))
  console.log(JSON.stringify(report, null, 2))
  await browser.close()
}
