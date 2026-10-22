import fs from 'node:fs'
import path from 'node:path'
import assert from 'node:assert/strict'
import { loadPlaywright } from './lib/env.mjs'

const { chromium } = loadPlaywright().module
const teacher = JSON.parse(process.env.SUPPORT_TEACHER_AUTH)
const student = JSON.parse(process.env.SUPPORT_STUDENT_AUTH)
const peer = JSON.parse(process.env.SUPPORT_PEER_AUTH)
const room = JSON.parse(process.env.SUPPORT_CLASS)
const out = process.env.SUPPORT_OUT
const browser = await chromium.launch({ headless: true })
const report = { checks: [], errors: [], screenshots: [], real_model: true }
function check(name, condition = true) { assert.ok(condition, name); report.checks.push(name); console.log('PASS', name) }
async function contextFor(auth) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
  await context.addInitScript(({ auth, classId }) => {
    sessionStorage.setItem('learning-system-tab-auth', JSON.stringify(auth))
    localStorage.setItem('learning-system-auth', JSON.stringify(auth))
    sessionStorage.setItem(`teacher-class-${auth.user.userId}`, String(classId))
  }, { auth, classId: room.id })
  return context
}
const tc = await contextFor(teacher)
const sc = await contextFor(student)
const pc = await contextFor(peer)
const tp = await tc.newPage()
const sp = await sc.newPage()
for (const p of [tp, sp]) {
  p.on('pageerror', e => report.errors.push(String(e)))
  p.on('response', r => { if (r.status() >= 500) report.errors.push(`${r.status()} ${r.url().split('?')[0]}`) })
}
async function call(context, auth, method, route, data) {
  const res = await context.request.fetch('http://127.0.0.1:8005' + route, {
    method, data, headers: { Authorization: `Bearer ${auth.token}` }, timeout: 240000,
  })
  assert.ok(res.ok(), `${method} ${route}: ${res.status()} ${await res.text()}`)
  return (await res.json()).data
}
async function shot(page, name) {
  const file = path.join(out, name + '.png')
  await page.screenshot({ path: file, fullPage: true, animations: 'disabled' })
  report.screenshots.push(file)
}
try {
  fs.mkdirSync(out, { recursive: true })
  await tp.goto('http://127.0.0.1:5175/teacher/homework', { waitUntil: 'networkidle' })
  const support = tp.locator('.course-support')
  await support.getByRole('heading', { name: '课程资源与个性化补强' }).waitFor()
  await support.getByText(room.name + '：', { exact: false }).waitFor()
  const form = support.locator('.support-form').first()
  await form.locator('.el-form-item').filter({ hasText: '资源标题' }).getByRole('textbox').fill('教师专属二叉树遍历讲义')
  await form.locator('.el-form-item').filter({ hasText: '课程资源正文' }).getByRole('textbox').fill('中序遍历：先访问左子树，再访问根节点，最后访问右子树。前序遍历：根、左、右。对于根为2，左孩子为1，右孩子为3的树，中序为1、2、3。')
  await form.locator('.el-form-item').filter({ hasText: '课程知识点' }).getByRole('textbox').fill('二叉树遍历')
  await support.getByRole('button', { name: '发送课程资源', exact: true }).click()
  await support.locator('.support-card').filter({ hasText: '教师专属二叉树遍历讲义' }).waitFor()
  check('teacher sends course material through the real UI')
  const materials = await call(tc, teacher, 'GET', `/teacher/classes/${room.id}/course-resources`)
  await sp.goto('http://127.0.0.1:5175/student/classroom', { waitUntil: 'networkidle' })
  await sp.getByRole('heading', { name: '教师专属二叉树遍历讲义', exact: true }).waitFor()
  check('enrolled student receives and reads the teacher material')
  console.log('Starting one real generation call')
  const draft = await call(tc, teacher, 'POST', `/teacher/classes/${room.id}/reinforcements`, {
    request_id: crypto.randomUUID(), student_user_id: student.user.userId,
    delivery_ids: [materials[0].id], question_count: 2,
    teacher_note: '恰好生成一道选择题与一道简答题，围绕中序遍历与前序遍历易混淆处设计简单变式题。',
  })
  assert.equal(draft.status, 'ready', JSON.stringify({ status: draft.status, error: draft.error }))
  report.model_name = draft.model_name
  check('real configured model generates a valid evidence-bound draft')
  check('generation includes course-specific wrong-answer evidence', draft.evidence_json.mistake_count === 1)
  check('measured platform duration has an explicit non-course attribution', draft.evidence_json.study_time_scope === 'platform_total_not_course_specific')
  await support.getByRole('button', { name: '刷新资源与草稿' }).click()
  await support.getByRole('tab', { name: '生成补强作业', exact: true }).click()
  await support.getByRole('button', { name: '审阅题目', exact: true }).click()
  const dialog = tp.getByRole('dialog', { name: '教师审阅补强题', exact: true })
  await dialog.getByText('参考答案（学生提交后立即展示）', { exact: true }).first().waitFor()
  await shot(tp, 'teacher-review-real-model')
  await dialog.getByRole('button', { name: '审阅通过并发送作业', exact: true }).click()
  await tp.locator('.el-message-box__btns .el-button--primary').click()
  await dialog.waitFor({ state: 'hidden' })
  check('teacher reviews and publishes personalized homework from the UI')
  const own = (await call(sc, student, 'GET', '/teacher/students/me/homework')).find(a => a.target_student_id === student.user.userId)
  assert.ok(own)
  report.assignment_id = own.id
  check('answers and analyses are withheld before submission', own.practice_questions.every(q => !('answer' in q) && !('analysis' in q)))
  check('same-class peer cannot see targeted homework', !(await call(pc, peer, 'GET', '/teacher/students/me/homework')).some(a => a.id === own.id))
  await sp.reload({ waitUntil: 'networkidle' })
  const card = sp.locator(`#assignment-${own.id}`)
  await card.locator('.practice-question').first().waitFor()
  for (const [index, q] of draft.questions.entries()) {
    const question = card.locator('.practice-question').nth(index)
    if (q.question_type === 'choice') {
      const correct = q.options.findIndex((option, i) => option === q.answer || option.replace(/^[A-F][.、\s]+/, '') === q.answer || String.fromCharCode(65 + i) === q.answer.trim())
      assert.ok(correct >= 0, 'reference matches a choice option')
      await question.locator('.el-radio').nth((correct + 1) % q.options.length).click()
    } else await question.getByRole('textbox').fill('我认为中序遍历是先根节点，再左子树，最后右子树。')
  }
  await card.getByRole('button', { name: '提交作业', exact: true }).click()
  await card.getByRole('heading', { name: '逐题结果与错题反馈', exact: true }).waitFor()
  await card.getByText('参考答案', { exact: true }).first().waitFor()
  check('student immediately sees reference answers without teacher review')
  await shot(sp, 'student-immediate-reference')
  for (let retry = 0; retry < 90; retry++) {
    const current = (await call(sc, student, 'GET', '/teacher/students/me/homework')).find(a => a.id === own.id).my_submission.practice_result
    if (current.status === 'failed') throw new Error(current.error)
    if (current.status === 'completed') break
    await new Promise(resolve => setTimeout(resolve, 2000))
  }
  await card.getByRole('heading', { name: '模型辅助分析', exact: true }).waitFor({ timeout: 15000 })
  check('model analysis and subjective scoring arrive after submission')
  const completed = (await call(sc, student, 'GET', '/teacher/students/me/homework')).find(a => a.id === own.id)
  const result = completed.my_submission.practice_result
  report.attempt_id = result.id
  report.model_feedback_name = result.model_name
  check('all questions have completed judgments', result.status === 'completed' && result.results.every(r => r.is_correct !== null))
  check('intentional wrong responses are identified', result.results.some(r => r.is_correct === false))
  await shot(sp, 'student-wrong-results')
  await support.getByRole('tab', { name: '学生错题与模型分析', exact: true }).click()
  await support.getByRole('heading', { name: '模型辅助分析', exact: true }).waitFor({ timeout: 20000 })
  check('teacher receives per-question wrong answers and model recommendations')
  await shot(tp, 'teacher-mistakes-and-analysis')
  await sp.goto('http://127.0.0.1:5175/student/mistakes', { waitUntil: 'networkidle' })
  await sp.getByText('二叉树遍历', { exact: false }).first().waitFor({ timeout: 20000 })
  const notebookRes = await sc.request.get(`http://127.0.0.1:8004/evaluation/mistakes/${student.user.userId}/detail`, { headers: { Authorization: `Bearer ${student.token}` } })
  assert.ok(notebookRes.ok(), `mistake endpoint ${notebookRes.status()}`)
  const notebook = (await notebookRes.json()).data
  check('new homework mistakes enter existing student mistake notebook', result.results.filter(r => r.is_correct === false).every(r => notebook.items.some(m => Number(m.exercise_id) === r.exercise_id)))
  await shot(sp, 'existing-mistake-notebook')
  await sp.setViewportSize({ width: 390, height: 844 })
  await sp.goto('http://127.0.0.1:5175/student/classroom', { waitUntil: 'networkidle' })
  check('mobile student feedback has no horizontal overflow', await sp.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2))
  await shot(sp, 'mobile-feedback')
  check('no page exceptions or server failures', report.errors.length === 0)
} catch (e) { report.error = String(e.stack || e); process.exitCode = 1 }
finally {
  fs.writeFileSync(path.join(out, 'result.json'), JSON.stringify(report, null, 2))
  console.log(JSON.stringify(report, null, 2))
  await browser.close()
}
