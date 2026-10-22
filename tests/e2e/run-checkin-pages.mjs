import fs from 'node:fs'
import path from 'node:path'
import assert from 'node:assert/strict'
import { loadPlaywright } from './lib/env.mjs'

const out = process.env.CHECKIN_OUT
const teacherAuth = JSON.parse(process.env.CHECKIN_TEACHER_AUTH)
const studentAuth = JSON.parse(process.env.CHECKIN_STUDENT_AUTH)
const className = process.env.CHECKIN_CLASS_NAME
const studentName = process.env.CHECKIN_STUDENT_NAME
const base = process.env.E2E_BASE_URL || 'http://127.0.0.1:5175'

const { chromium } = loadPlaywright().module
const browser = await chromium.launch({ headless: true })
const report = { base, checks: [], pageErrors: [], apiErrors: [], screenshots: [] }

async function contextFor(auth, viewport = { width: 1440, height: 960 }) {
  const context = await browser.newContext({ viewport })
  const payload = JSON.stringify(auth)
  await context.addInitScript((value) => {
    sessionStorage.setItem('learning-system-tab-auth', value)
    localStorage.setItem('learning-system-auth', value)
  }, payload)
  return context
}

async function watch(page) {
  page.on('pageerror', (error) => report.pageErrors.push(String(error)))
  page.on('console', (message) => {
    if (message.type() === 'error') report.apiErrors.push(message.text().slice(0, 400))
  })
  page.on('response', (response) => {
    if (response.status() >= 500) {
      report.apiErrors.push(`${response.status()} ${response.url()}`)
    }
  })
}

async function shot(page, name) {
  const file = path.join(out, `${name}.png`)
  await page.screenshot({ path: file, fullPage: true })
  report.screenshots.push(file)
}

function check(name, condition) {
  report.checks.push({ name, ok: Boolean(condition) })
  assert.ok(condition, name)
}

try {
  fs.mkdirSync(out, { recursive: true })

  const teacherContext = await contextFor(teacherAuth)
  const teacherPage = await teacherContext.newPage()
  await watch(teacherPage)
  await teacherPage.goto(`${base}/teacher/checkin`, { waitUntil: 'networkidle' })
  await teacherPage.getByText('学习打卡与课堂签到管理').first().waitFor({ timeout: 20000 })
  check('teacher page renders heading', true)
  await teacherPage.getByText(className).first().waitFor({ timeout: 20000 })
  check('teacher page shows real class name', true)
  await shot(teacherPage, 'teacher-tasks')

  await teacherPage.getByRole('tab', { name: '完成与审核' }).click()
  await teacherPage.getByText(studentName).first().waitFor({ timeout: 20000 })
  check('teacher completion table shows real student', true)
  await shot(teacherPage, 'teacher-review')

  await teacherPage.getByRole('tab', { name: '课堂签到' }).click()
  await teacherPage.getByText('界面验收现场签到').first().waitFor({ timeout: 20000 })
  check('teacher attendance list shows live session', true)
  await teacherPage.getByText('实时出勤').first().click()
  await teacherPage.getByText('签到码').first().waitFor({ timeout: 20000 })
  await teacherPage.waitForFunction((name) => document.body.innerText.includes(name), studentName, {
    timeout: 20000,
  })
  check('teacher live attendance shows student', true)
  await shot(teacherPage, 'teacher-live')

  await teacherPage.goto(`${base}/teacher/schedule`, { waitUntil: 'networkidle' })
  await teacherPage.getByText('课程安排与教学日历').first().waitFor({ timeout: 20000 })
  await teacherPage.waitForFunction(
    () => document.body.innerText.includes('界面验收 · 图论'),
    { timeout: 20000 },
  )
  check('teacher schedule page shows real session', true)
  await shot(teacherPage, 'teacher-schedule')
  await teacherContext.close()

  const studentContext = await contextFor(studentAuth)
  const studentPage = await studentContext.newPage()
  await watch(studentPage)
  await studentPage.goto(`${base}/student/checkin`, { waitUntil: 'networkidle' })
  await studentPage.getByText('平台学习打卡').first().waitFor({ timeout: 20000 })
  await studentPage.getByText('今天还没有打卡').first().waitFor({ timeout: 20000 })
  check('platform check-in page renders unchecked', true)
  await shot(studentPage, 'student-overview')

  await studentPage.getByRole('button', { name: '立即打卡' }).click()
  await studentPage.getByPlaceholder('例如：完成数据结构第三章复习').fill('界面验收学习目标')
  await studentPage.getByRole('button', { name: '确认打卡' }).click()
  await studentPage.getByText('今天已完成平台学习打卡').first().waitFor({ timeout: 20000 })
  check('one-click platform check-in succeeds', true)
  await studentPage.waitForFunction(
    () => document.body.innerText.includes('打卡历史') && document.body.innerText.includes('界面验收学习目标'),
    { timeout: 20000 },
  )
  check('check-in history shows the real record', true)
  await shot(studentPage, 'student-checked-in')

  await studentPage.getByRole('tab', { name: '课堂任务' }).click()
  await studentPage.waitForFunction(() => document.body.innerText.includes('界面验收 · 二叉树遍历'), { timeout: 20000 })
  check('student sees published classroom task', true)
  await shot(studentPage, 'student-tasks')
  await studentPage.getByRole('tab', { name: '课堂签到' }).click()
  await studentPage.waitForFunction(
    () => document.body.innerText.includes('界面验收现场签到'),
    { timeout: 20000 },
  )
  check('student attendance history renders', true)
  await studentContext.close()

  const timetableContext = await contextFor(studentAuth)
  const timetablePage = await timetableContext.newPage()
  await watch(timetablePage)
  await timetablePage.goto(`${base}/student/timetable`, { waitUntil: 'networkidle' })
  await timetablePage.getByText('我的课程表').first().waitFor({ timeout: 20000 })
  await timetablePage.waitForFunction(
    () => document.body.innerText.includes('界面验收 · 图论'),
    { timeout: 20000 },
  )
  check('student timetable syncs the joined classroom', true)
  await shot(timetablePage, 'student-timetable')
  await timetableContext.close()

  const plazaContext = await contextFor(studentAuth)
  const plazaPage = await plazaContext.newPage()
  await watch(plazaPage)
  await plazaPage.goto(`${base}/student/classroom-plaza`, { waitUntil: 'networkidle' })
  await plazaPage.getByText('课堂广场').first().waitFor({ timeout: 20000 })
  await plazaPage.waitForFunction(
    (name) => document.body.innerText.includes(name) && document.body.innerText.includes('已加入 · 进入我的课堂'),
    className,
    { timeout: 20000 },
  )
  check('classroom plaza renders joined open class', true)
  await shot(plazaPage, 'student-plaza')
  await plazaContext.close()

  const mobileContext = await contextFor(studentAuth, { width: 390, height: 844 })
  const mobilePage = await mobileContext.newPage()
  await watch(mobilePage)
  await mobilePage.goto(`${base}/student/checkin`, { waitUntil: 'networkidle' })
  await mobilePage.getByText('学习打卡').first().waitFor({ timeout: 20000 })
  const overflow = await mobilePage.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
  check('mobile layout has no horizontal overflow', overflow <= 2)
  await shot(mobilePage, 'student-mobile')
  await mobileContext.close()

  check('no page errors', report.pageErrors.length === 0)
  check('no 5xx api responses', report.apiErrors.length === 0)
} catch (error) {
  report.error = String(error?.stack || error)
  process.exitCode = 1
} finally {
  fs.writeFileSync(path.join(out, 'result.json'), JSON.stringify(report, null, 2), 'utf8')
  await browser.close()
  console.log(JSON.stringify(report, null, 2))
}
