import fs from 'node:fs'
import path from 'node:path'
import assert from 'node:assert/strict'
import { loadPlaywright } from './lib/env.mjs'

const { chromium } = loadPlaywright().module
const teacher = JSON.parse(process.env.CHECKIN_TEACHER_AUTH)
const student = JSON.parse(process.env.CHECKIN_STUDENT_AUTH)
const out = process.env.CHECKIN_OUT
const browser = await chromium.launch({ headless: true })
const report = { checks: [], errors: [], screenshots: [] }
const context = await browser.newContext({ viewport: { width: 1440, height: 960 } })
await context.addInitScript(auth => {
  sessionStorage.setItem('learning-system-tab-auth', auth)
  localStorage.setItem('learning-system-auth', auth)
}, JSON.stringify(student))
const page = await context.newPage()
page.on('pageerror', e => report.errors.push(String(e)))
page.on('response', r => { if (r.status() >= 500) report.errors.push(`${r.status()} ${r.url()}`) })
const api = 'http://127.0.0.1:8005'
async function call(auth, method, url, data) {
  const res = await context.request.fetch(api + url, { method, data, headers: { Authorization: `Bearer ${auth.token}` } })
  assert.ok(res.ok(), `${method} ${url}: ${res.status()} ${await res.text()}`)
  return (await res.json()).data
}
function check(name, ok = true) { assert.ok(ok, name); report.checks.push(name) }
async function refresh() {
  await page.goto('http://127.0.0.1:5175/student/timetable', { waitUntil: 'networkidle' })
  await page.getByRole('heading', { name: '我的课程表', exact: true }).waitFor()
}
async function shot(name) {
  const file = path.join(out, name + '.png')
  await page.screenshot({ path: file, fullPage: true, animations: 'disabled' })
  report.screenshots.push(file)
}
async function save() {
  await page.getByRole('button', { name: '保存课程', exact: true }).click()
  await page.getByRole('dialog').waitFor({ state: 'hidden' })
  await page.waitForLoadState('networkidle')
}
try {
  fs.mkdirSync(out, { recursive: true })
  const classes = await call(teacher, 'GET', '/teacher/classes')
  const room = classes.find(r => r.name === process.env.CHECKIN_CLASS_NAME)
  assert.ok(room)
  const official = (await call(teacher, 'GET', `/learning/classes/${room.id}/schedule`)).sessions[0]
  await call(teacher, 'DELETE', `/learning/classes/${room.id}/schedule/${official.id}`)
  await refresh()
  await page.getByText('待安排：尚无上课时间，请补充或等待教师排课', { exact: false }).waitFor()
  check('enrolled class automatically imported without a teacher schedule')
  await shot('auto-import-pending')
  await page.getByRole('button', { name: '安排上课时间', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await dialog.locator('.el-form-item').filter({ hasText: '课程名称' }).getByRole('textbox').fill('学生自排课程验收')
  await save()
  await page.locator('.lesson p').filter({ hasText: '学生自排课程验收' }).waitFor()
  check('student arranges imported pending course through UI')
  await refresh()
  await page.locator('.lesson p').filter({ hasText: '学生自排课程验收' }).waitFor()
  check('personal course survives page reload and database reread')
  await page.locator('.lesson').filter({ hasText: '学生自排课程验收' }).getByRole('button', { name: '编辑', exact: true }).click()
  await dialog.locator('.el-form-item').filter({ hasText: '课程名称' }).getByRole('textbox').fill('学生修改课程验收')
  await save()
  await page.locator('.lesson p').filter({ hasText: '学生修改课程验收' }).waitFor()
  check('student edits own course through UI')
  await shot('personal-course-edited')
  await page.locator('.lesson').filter({ hasText: '学生修改课程验收' }).getByRole('button', { name: '删除', exact: true }).click()
  await page.locator('.el-message-box__btns .el-button--primary').click()
  await page.locator('.lesson p').filter({ hasText: '学生修改课程验收' }).waitFor({ state: 'hidden' })
  check('student deletes own course through UI')

  const source = await call(teacher, 'POST', `/learning/classes/${room.id}/schedule`, {
    topic: '自动同步教师课程', weekday: 1, start_time: '09:00', end_time: '10:00',
    week_start: official.week_start, week_end: official.week_end, location: '线上', mode: 'online',
  })
  await refresh()
  await page.locator('.lesson p').filter({ hasText: '自动同步教师课程' }).waitFor()
  check('teacher schedule automatically appears for enrolled student')
  await page.locator('.lesson').filter({ hasText: '自动同步教师课程' }).getByRole('button', { name: '编辑', exact: true }).click()
  await dialog.locator('.el-form-item').filter({ hasText: '课程名称' }).getByRole('textbox').fill('仅本人调整课程')
  await save()
  await page.locator('.lesson p').filter({ hasText: '仅本人调整课程' }).waitFor()
  const after = await call(teacher, 'GET', `/learning/classes/${room.id}/schedule`)
  check('private classroom edit does not change teacher source', after.sessions[0].topic === '自动同步教师课程')
  await page.getByRole('button', { name: '管理个人安排' }).click()
  await page.getByRole('button', { name: '恢复教师安排', exact: true }).click()
  await page.locator('.el-message-box__btns .el-button--primary').click()
  await page.locator('.lesson p').filter({ hasText: '自动同步教师课程' }).waitFor()
  await page.getByRole('dialog', { name: '管理个人安排', exact: true }).getByRole('button', { name: /Close/ }).click()
  check('student restores teacher schedule after personal edit')
  await page.locator('.lesson').filter({ hasText: '自动同步教师课程' }).getByRole('button', { name: '隐藏本次', exact: true }).click()
  await page.locator('.el-message-box__btns .el-button--primary').click()
  await page.locator('.lesson p').filter({ hasText: '自动同步教师课程' }).waitFor({ state: 'hidden' })
  check('student hides a classroom occurrence privately')
  const hidden = (await call(student, 'GET', '/learning/schedule/me')).personal.find(p => p.hidden)
  await call(student, 'DELETE', `/learning/schedule/me/personal/${hidden.id}`)
  const target = new Date(`${official.week_start}T12:00:00`)
  target.setDate(target.getDate() + 9)
  const destination = target.toISOString().slice(0, 10)
  await call(teacher, 'POST', `/learning/classes/${room.id}/schedule/${source.id}/exceptions`, {
    date: official.week_start, kind: 'reschedule', new_date: destination,
    new_start_time: '14:00', new_end_time: '15:00', reason: '跨周同步浏览器验收',
  })
  await refresh()
  check('cross-week move removes original occurrence', await page.locator('.lesson').count() === 0)
  await page.getByRole('button', { name: '下一周', exact: true }).click()
  await page.locator('.lesson').filter({ hasText: '已调课' }).waitFor()
  check('cross-week moved course appears in destination week')
  await shot('cross-week-course')
  await page.setViewportSize({ width: 390, height: 844 })
  check('mobile has no horizontal overflow', await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2))
  await page.getByRole('button', { name: '新增个人课程', exact: true }).click()
  await dialog.waitFor()
  check('mobile editor fits viewport', await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2))
  await shot('mobile-editor')
  check('no page errors or server failures', report.errors.length === 0)
} catch (e) { report.error = String(e.stack || e); process.exitCode = 1 }
finally {
  fs.writeFileSync(path.join(out, 'result.json'), JSON.stringify(report, null, 2))
  console.log(JSON.stringify(report, null, 2))
  await browser.close()
}
