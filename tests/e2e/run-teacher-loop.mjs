import fs from 'node:fs'
import path from 'node:path'
import assert from 'node:assert/strict'
import { loadPlaywright } from './lib/env.mjs'
const out = process.argv[2], origin = 'http://127.0.0.1:15196', api = 'http://127.0.0.1:18226'
const { chromium } = loadPlaywright().module
const browser = await chromium.launch({ headless: true })
const errors = [], checks = [], requests = [], contexts = []
const sameBrowser = process.argv.includes('--same-browser')
const withFiles = process.argv.includes('--files')
const preparedPages = []
if (sameBrowser) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } }); contexts.push(context)
  for (let i = 0; i < 4; i++) {
    const page = await context.newPage(); await page.goto(origin + '/login')
    await page.getByPlaceholder('请输入用户名').waitFor(); preparedPages.push(page)
  }
}
async function login(name) {
  let page
  if (sameBrowser) page = preparedPages.shift()
  else {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } }); contexts.push(context)
    page = await context.newPage(); await page.goto(origin + '/login')
  }
  page.on('pageerror', e => errors.push(e.message))
  page.on('response', async r => {
    if (r.url().includes('/teacher-api/teacher/') && ['POST', 'PATCH', 'DELETE'].includes(r.request().method()))
      requests.push({ path: new URL(r.url()).pathname, method: r.request().method(), status: r.status() })
  })
  await page.getByPlaceholder('请输入用户名').fill(name)
  await page.getByPlaceholder('请输入密码', { exact: true }).fill('Loop-test-123')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await page.waitForURL(url => url.pathname !== '/login')
  return page
}
async function auth(page) { return JSON.parse(await page.evaluate(() => sessionStorage.getItem('learning-system-tab-auth') || localStorage.getItem('learning-system-auth'))) }
async function request(page, method, url, data, expected = 200) {
  const a = await auth(page)
  const r = await page.request[method](api + '/teacher-api' + url, { headers: { Authorization: `Bearer ${a.token}` }, data })
  assert.equal(r.status(), expected, await r.text())
  return (await r.json()).data
}
try {
  const teacher = await login('loop-teacher'), student = await login('loop-student')
  checks.push(sameBrowser ? 'same browser context, independent teacher/student tabs, real password login' : 'two independent browser contexts log in through actual user-service password authentication')
  await teacher.locator('.app-sidebar').getByRole('button', { name: '班级管理', exact: true }).click()
  await teacher.getByPlaceholder('请输入班级名称').fill('师生联合验收班')
  await teacher.getByPlaceholder('请输入学科', { exact: true }).fill('数学')
  await teacher.getByRole('button', { name: '创建班级', exact: true }).click()
  const invite = teacher.getByTestId('class-invite'); await invite.waitFor()
  const code = (await invite.innerText()).trim(); assert.ok(code.length >= 8)
  const cls = (await request(teacher, 'get', '/teacher/classes'))[0]
  await teacher.reload(); await invite.waitFor(); assert.equal((await invite.innerText()).trim(), code)
  checks.push('teacher creates persistent class through UI; reload preserves invitation')
  await student.goto(origin + '/student/classroom')
  await student.getByPlaceholder('输入班级邀请码').fill(code)
  await student.getByRole('button', { name: '查找班级', exact: true }).click()
  await student.getByRole('button', { name: '确认加入班级', exact: true }).click()
  await student.getByText('已加入', { exact: false }).first().waitFor()
  await teacher.getByRole('button', { name: '刷新成员', exact: true }).click()
  await teacher.locator('.class-detail').getByText('loop-student', { exact: true }).waitFor()
  checks.push('student joins by invitation in UI; teacher sees the same persisted member')
  await teacher.locator('.app-sidebar').getByRole('button', { name: '学生洞察', exact: true }).click()
  await teacher.locator('.report-grid article h3').filter({ hasText: 'loop-student' }).waitFor()
  assert.equal(await teacher.getByText('暂无学生洞察', { exact: true }).count(), 0)
  await teacher.screenshot({ path: path.join(out, 'teacher-student-insights.png'), fullPage: true })
  checks.push('same browser teacher insights reads the joined student while student tab stays logged in')
  await request(teacher, 'post', '/teacher/teaching-scopes', {
    class_id: cls.id, knowledge_points: ['一元一次方程'], learning_direction: '掌握等式变形与检验',
    courseware_title: '本班方程课件', courseware_content: '先移项，再合并同类项，最后代回检验。',
  })
  await student.getByRole('button', { name: '刷新班级与作业', exact: true }).click()
  await student.getByRole('heading', { name: '本班方程课件', exact: true }).waitFor()
  await student.getByText('先移项，再合并同类项，最后代回检验。', { exact: true }).waitFor()
  checks.push('real class teaching scope reaches enrolled student courseware UI and active learning path')
  await teacher.goto(origin + '/teacher/homework')
  assert.equal(await teacher.getByText('提交记录 ID', { exact: true }).count(), 0)
  await teacher.getByPlaceholder('请输入作业标题').fill('联合验收作业')
  await teacher.getByPlaceholder('请输入作业要求、范围和提交说明').fill('证明并解释你的解题过程。')
  await teacher.getByRole('button', { name: '布置作业', exact: true }).click()
  await teacher.getByRole('button').filter({ hasText: '联合验收作业' }).waitFor()
  await student.getByRole('button', { name: '刷新班级与作业', exact: true }).click()
  const task = student.locator('.task-card').filter({ hasText: '联合验收作业' })
  if (withFiles) {
    await task.getByLabel('选择作业附件').setInputFiles(['手写解答.png', '作业文档.docx', '推导.pdf'].map(name => path.join(out, 'fixtures', name)))
    await task.locator('[data-testid="homework-file"]').filter({hasText:'推导.pdf'}).waitFor()
    await task.getByRole('textbox').fill('')
  } else await task.getByRole('textbox').fill('由已知条件得到 x = 2，代回原式验证成立。')
  await task.getByRole('button', { name: '提交作业', exact: true }).click()
  await task.getByText('已提交，等待批改', { exact: true }).waitFor()
  await teacher.getByRole('button').filter({ hasText: '联合验收作业' }).click()
  await teacher.getByRole('heading', { name: '正在批改：loop-student', exact: true }).waitFor()
  if (withFiles) {
    const review = teacher.getByRole('heading', { name: '正在批改：loop-student', exact: true }).locator('..')
    assert.equal(await review.locator('[data-testid="homework-file"]').count(), 3)
    for (const name of ['手写解答.png', '作业文档.docx', '推导.pdf']) {
      await review.locator('[data-testid="homework-file"]').filter({hasText:name}).getByRole('button', {name:'预览',exact:true}).click()
      const dialog = teacher.getByRole('dialog', {name,exact:true}); await dialog.waitFor()
      if (name.endsWith('.png')) await dialog.locator('img').evaluate(img => img.complete && img.naturalWidth > 0 ? true : new Promise(resolve => {img.onload=resolve}))
      if (name.endsWith('.docx')) await dialog.getByText('作业原文：SQL事务分析与证明。', {exact:true}).waitFor()
      if (name.endsWith('.pdf')) await dialog.locator('iframe[src^="blob:"]').waitFor()
      await teacher.screenshot({path:path.join(out, `preview-${path.extname(name).slice(1)}.png`),fullPage:true})
      await dialog.getByRole('button', {name:'关闭预览',exact:true}).click()
    }
    const downloadWait = teacher.waitForEvent('download')
    await review.locator('[data-testid="homework-file"]').filter({hasText:'作业文档.docx'}).getByRole('button', {name:'下载',exact:true}).click()
    const download = await downloadWait; await download.saveAs(path.join(out, 'teacher-downloaded.docx'))
    assert.deepEqual(fs.readFileSync(path.join(out,'teacher-downloaded.docx')), fs.readFileSync(path.join(out,'fixtures','作业文档.docx')))
    checks.push('student submits only PNG/DOCX/PDF originals; teacher previews all three and downloads byte-identical Word original')
  }
  await teacher.locator('.el-form-item').filter({ has: teacher.getByText('分数', { exact: true }) }).getByRole('spinbutton').fill('94')
  await teacher.getByPlaceholder('请输入批改评语和后续建议').fill('推理完整，注意书写规范。')
  await teacher.getByRole('button', { name: '提交批改', exact: true }).click()
  await teacher.getByText('批改已保存，学生可在班级空间查看成绩和评语', { exact: true }).waitFor()
  await student.getByRole('button', { name: '刷新班级与作业', exact: true }).click()
  await task.getByText('成绩：94 分', { exact: true }).waitFor()
  await task.getByText('推理完整，注意书写规范。', { exact: true }).waitFor()
  checks.push('same assignment flows UI publish -> student answer -> teacher selects submission and grades -> student reads score/comment')
  const t = await auth(teacher), s = await auth(student)
  const a = (await request(teacher, 'get', '/teacher/homework'))[0]
  const submission = (await request(teacher, 'get', `/teacher/homework/${a.id}/submissions`))[0]
  assert.equal(submission.student_user_id, s.user.userId)
  assert.equal(a.class_id, cls.id)
  if (withFiles) assert.equal(submission.attachments.length, 3)
  await teacher.getByRole('heading', { name: '正在批改：loop-student', exact: true }).scrollIntoViewIfNeeded()
  await teacher.screenshot({ path: path.join(out, 'teacher-review.png'), fullPage: true })
  await task.scrollIntoViewIfNeeded()
  await student.screenshot({ path: path.join(out, 'student-grade.png'), fullPage: true })
  for (const [page, text] of [[teacher, '学生提交作业'], [student, '作业已批改']]) {
    await page.locator('.notification-trigger').click()
    const item = page.locator('.notification-panel .notification-item').filter({ hasText: text }); await item.waitFor(); await item.click()
    await page.getByRole('dialog', { name: '消息详情' }).waitFor()
    await page.getByRole('dialog').getByRole('button', { name: 'Close this dialog' }).click()
    const notifications = await request(page, 'get', '/learning/notifications/inbox?page=1&size=20')
    assert.ok(notifications.items.some(n => n.title.includes(text) && n.is_read))
  }
  checks.push('real event notifications delivered to correct roles; opening details persists read state')
  const outsider = await login('loop-outsider'), otherTeacher = await login('loop-other-teacher')
  assert.deepEqual(await request(outsider, 'get', '/teacher/students/me/homework'), [])
  await request(outsider, 'post', `/teacher/students/me/homework/${a.id}/submit`, { content: '越权' }, 403)
  await request(student, 'post', `/teacher/homework/${submission.id}/review`, { score: 100, comment: '越权' }, 403)
  await request(otherTeacher, 'get', `/teacher/homework/${a.id}/submissions`, undefined, 404)
  await request(otherTeacher, 'get', `/teacher/classes/${cls.id}/members`, undefined, 403)
  if (withFiles) {
    await request(outsider, 'get', `/teacher/homework/attachments/${submission.attachments[0].id}`, undefined, 403)
    await request(otherTeacher, 'get', `/teacher/homework/attachments/${submission.attachments[0].id}/preview`, undefined, 403)
  }
  checks.push('second teacher/student cannot access private class, submission, or grading')
  // Real network failure, not a mocked successful business response.
  await teacher.route('**/teacher-api/teacher/classes', route => route.abort('connectionfailed'))
  await teacher.goto(origin + '/teacher/classes')
  await teacher.getByText('重试班级列表', { exact: true }).waitFor()
  assert.equal(await teacher.getByText('还没有班级', { exact: true }).count(), 0)
  await teacher.unroute('**/teacher-api/teacher/classes')
  await teacher.getByRole('button', { name: '重试班级列表', exact: true }).click()
  await teacher.getByTestId('class-invite').waitFor()
  checks.push('network failure shows retry instead of an empty-list claim; retry restores real data')
  fs.writeFileSync(path.join(out, 'restart-request'), 'ready')
  for (let i = 0; i < 200 && !fs.existsSync(path.join(out, 'restart-complete')); i++) await new Promise(resolve => setTimeout(resolve, 300))
  assert.ok(fs.existsSync(path.join(out, 'restart-complete')))
  await student.reload(); await task.getByText('成绩：94 分', { exact: true }).waitFor()
  await teacher.reload(); await teacher.getByTestId('class-invite').waitFor()
  await student.locator('.user-button').click()
  await student.getByRole('button', { name: '退出登录', exact: true }).click()
  await student.waitForURL('**/login')
  await student.getByPlaceholder('请输入用户名').fill('loop-student')
  await student.getByPlaceholder('请输入密码', { exact: true }).fill('Loop-test-123')
  await student.getByRole('button', { name: '登录', exact: true }).click(); await student.waitForURL(url => url.pathname !== '/login')
  await student.goto(origin + '/student/classroom'); await task.getByText('成绩：94 分', { exact: true }).waitFor()
  for (const [page, text] of [[teacher, '学生提交作业'], [student, '作业已批改']]) {
    const inbox = await request(page, 'get', '/learning/notifications/inbox?page=1&size=20')
    assert.ok(inbox.items.some(item => item.title.includes(text) && item.is_read))
    const count = await request(page, 'get', '/learning/notifications/unread-count')
    assert.equal(count.unread_count, inbox.unread_count)
  }
  checks.push('API process restart + page refresh + fresh password login preserve class/member/assignment/submission/grade')
  fs.writeFileSync(path.join(out, 'ids.json'), JSON.stringify({ teacherId: t.user.userId, studentId: s.user.userId, classId: cls.id, assignmentId: a.id, submissionId: submission.id }))
  assert.deepEqual(errors, [])
  fs.writeFileSync(path.join(out, 'result.json'), JSON.stringify({ checks, errors, requests, mockedBusinessResponses: false, paidModelRequests: 0 }, null, 2))
  console.log(JSON.stringify({ checks, errors }))
} catch (e) {
  for (let i = 0; i < contexts.length; i++) for (const p of contexts[i].pages()) await p.screenshot({ path: path.join(out, `failure-${i}.png`), fullPage: true }).catch(() => {})
  fs.writeFileSync(path.join(out, 'failure.json'), JSON.stringify({ message: e.message, checks, requests, errors }, null, 2))
  throw e
} finally { for (const context of contexts) await context.close(); await browser.close() }
