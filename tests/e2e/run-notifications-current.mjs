import fs from 'node:fs'
import path from 'node:path'
import assert from 'node:assert/strict'
import { loadPlaywright } from './lib/env.mjs'
const root=process.argv[2],auth=JSON.parse(fs.readFileSync(path.join(root,'auth.json'),'utf8'))
const {chromium}=loadPlaywright().module,browser=await chromium.launch({headless:true}),contexts=[],errors=[],checks=[]
const api='http://127.0.0.1:8005'
async function account(role){const context=await browser.newContext({viewport:{width:1440,height:900}});contexts.push(context);await context.addInitScript(a=>localStorage.setItem('learning-system-auth',JSON.stringify(a)),auth[role]);const p=await context.newPage();p.on('pageerror',e=>errors.push(e.message));return p}
async function req(p,role,method,url,data){const r=await p.request[method](api+url,{headers:{Authorization:`Bearer ${auth[role].token}`},data});assert.ok(r.ok(),`${url} ${r.status()} ${await r.text()}`);return(await r.json()).data}
try{
const student=await account('student'),teacher=await account('teacher')
for(const [role,title] of [['student','学生账号通知'],['teacher','教师工作通知']])await req(student,'admin','post','/learning/notifications/publish',{request_key:crypto.randomUUID(),scope:role,target_id:auth[role].user.userId,title,content:'当前5175平台专用验收通知，接收范围仅限本轮验收账号。'})
assert.equal((await req(student,'outsider','get','/learning/notifications/inbox')).total,0)
await student.goto('http://127.0.0.1:5175/student/notifications')
const card=student.locator('.notification-trigger');await card.waitFor();assert.equal(await card.getAttribute('aria-expanded'),'false');await card.locator('b').waitFor()
await card.click();await student.locator('.notification-panel .notification-item').filter({hasText:'学生账号通知'}).waitFor()
await student.screenshot({path:path.join(root,'student-desktop.png'),fullPage:true})
await student.keyboard.press('Escape');await student.locator('.notification-panel').waitFor({state:'detached'})
checks.push('current 5175 student default collapsed and real targeted admin publication')
const cls=await req(teacher,'teacher','post','/teacher/classes',{name:'通知功能专用验收班',subject:'数学',teacher_name:'验收教师'})
await req(teacher,'teacher','post',`/teacher/classes/${cls.id}/enrollments`,{student_user_id:auth.student.user.userId})
const assignment=await req(teacher,'teacher','post','/teacher/homework/assign',{class_id:cls.id,title:'专用验收作业',description:'只用于本轮通知闭环验收'})
const submission=await req(student,'student','post',`/teacher/students/me/homework/${assignment.id}/submit`,{content:'专用验收作业答案'})
await teacher.goto('http://127.0.0.1:5175/teacher/notifications');await teacher.locator('.notification-trigger b').waitFor();await teacher.locator('.notification-trigger').click()
await teacher.locator('.notification-panel .notification-item').filter({hasText:'学生提交作业'}).click();await teacher.getByRole('dialog').getByRole('button',{name:'前往关联业务'}).click();await teacher.waitForURL(`**/teacher/homework?assignment=${assignment.id}`);await teacher.getByText('专用验收作业答案',{exact:true}).waitFor()
await req(teacher,'teacher','post',`/teacher/homework/${submission.id}/review`,{score:93,comment:'专用验收批改'})
await student.evaluate(()=>window.dispatchEvent(new Event('online')));await card.click();await student.locator('.notification-panel .notification-item').filter({hasText:'作业已批改'}).waitFor()
await student.locator('.notification-panel .notification-item').filter({hasText:'作业已批改'}).click();await student.getByRole('dialog').getByText('得分 93。专用验收批改',{exact:true}).waitFor();await student.getByRole('dialog').getByRole('button',{name:'前往关联业务'}).click();await student.waitForURL(`**/student/classroom?assignment=${assignment.id}`);await student.locator(`#assignment-${assignment.id}`).waitFor()
checks.push('current real assignment submission review notifications and exact authorized destinations')
await req(student,'student','post','/learning/discussions',{class_id:cls.id,title:'递归课程提问',content:'如何确定递归的终止条件？'})
await teacher.goto('http://127.0.0.1:5175/teacher/notifications');await teacher.locator('.notification-trigger').click();await teacher.locator('.notification-panel .notification-item').filter({hasText:'学生课程提问'}).click();await teacher.getByRole('dialog').getByPlaceholder('回复课程讨论').fill('先找到不再分解的基础情况');await teacher.getByRole('dialog').getByRole('button',{name:'发送回复'}).click();await teacher.getByRole('dialog').getByText('先找到不再分解的基础情况',{exact:false}).waitFor();await teacher.getByRole('dialog').getByRole('button',{name:'Close this dialog'}).click()
checks.push('course question teacher notice and real reply inside authorized detail')

const second=await student.context().newPage();await second.goto('http://127.0.0.1:5175/student/notifications');await second.locator('.notification-trigger b').waitFor()
await student.locator('.notification-trigger').click();await student.locator('.notification-panel').getByRole('button',{name:'全部已读'}).click();await second.locator('.notification-trigger b').waitFor({state:'detached'})
await second.reload();await second.locator('.notification-trigger').waitFor();await second.waitForTimeout(300);assert.equal(await second.locator('.notification-trigger b').count(),0)
checks.push('cross-tab read state and reload persistence')
await second.context().setOffline(true);await second.locator('.notification-trigger').click();await second.locator('.notification-panel .retry').waitFor();await second.context().setOffline(false);await second.locator('.notification-panel .notification-item').first().waitFor();checks.push('offline error and online persistent inbox recovery')
await teacher.goto('http://127.0.0.1:5175/teacher/notifications');await teacher.locator('.notification-trigger').click();await teacher.locator('.notification-panel').waitFor();await teacher.setViewportSize({width:390,height:844});await teacher.waitForTimeout(600)
await teacher.screenshot({path:path.join(root,'teacher-mobile.png'),fullPage:true});const box=await teacher.locator('.notification-panel').boundingBox();assert.ok(box.x>=0&&box.x+box.width<=390)
assert.ok(await teacher.evaluate(()=>document.documentElement.scrollWidth<=innerWidth))
await second.setViewportSize({width:390,height:844});await second.waitForTimeout(600);await second.screenshot({path:path.join(root,'student-mobile.png'),fullPage:true})
checks.push('current 390px shared card and panel without overflow')
assert.deepEqual(errors,[])
fs.writeFileSync(path.join(root,'result.json'),JSON.stringify({checks,pageErrors:errors,mocked:false,runtime:'5175 / 8005'},null,2));console.log(JSON.stringify({checks,pageErrors:errors}))
}finally{for(const c of contexts)await c.close();await browser.close()}
