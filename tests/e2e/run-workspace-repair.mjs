import fs from 'node:fs'
import path from 'node:path'
import assert from 'node:assert/strict'
import { loadPlaywright } from './lib/env.mjs'
const root = process.argv[2]
const {token} = JSON.parse(fs.readFileSync(path.join(root,'auth.json'),'utf8'))
const {chromium} = loadPlaywright().module
const browser = await chromium.launch({headless:true})
const context = await browser.newContext({viewport:{width:1600,height:1000}})
const page = await context.newPage()
const errors=[]; page.on('pageerror',e=>errors.push(e.message))
await context.addInitScript(({token})=>localStorage.setItem('learning-system-auth',JSON.stringify({token,user:{userId:6,username:'owner',role:'student'}})),{token})
const base='http://127.0.0.1:18221/agent'
const headers={Authorization:`Bearer ${token}`}
try {
  await page.goto('http://127.0.0.1:15189/student/workspace/5ea022ee-fdb3-4541-a97e-9c1f50614a9b')
  await page.locator('.workspace-quiz .katex').first().waitFor({timeout:20000})
  await page.goto('http://127.0.0.1:15189/student/workspace/f313f2a1-7ece-4e7a-bc34-f960d0cb9087')
  await page.getByRole('button',{name:'打开已有课件',exact:true}).waitFor({timeout:20000})
  await page.getByRole('button',{name:'打开已有课件',exact:true}).click()
  await page.locator('.courseware-reader').first().waitFor()
  assert.ok(await page.locator('.workspace-quiz .quiz-prompt p').count()>0,'real saved quiz renders paragraphs')
  assert.ok(await page.locator('.outline-task .outline-resource').count()>0)
  assert.ok((await page.locator('.outline-resource[aria-current]').count())>0)
  const selected=page.url().split('/').pop()
  const snapshot=(await (await page.request.get(`${base}/learning/contexts/${selected}`,{headers})).json())
  assert.equal(snapshot.resource.id,229)
  assert.ok(snapshot.exercises.length>=3,'exercise bindings survive selecting generated resource')
  await page.getByRole('button',{name:'生成字幕视频',exact:true}).click()
  await page.getByRole('button',{name:'加载预览',exact:true}).last().waitFor({timeout:90000})
  await page.getByRole('button',{name:'加载预览',exact:true}).last().click()
  const video=page.locator('video')
  await video.waitFor()
  await page.waitForFunction(()=>{const v=document.querySelector('video'); return v && v.readyState>=2 && v.videoWidth>0})
  await video.evaluate(async v=>{v.muted=true; await v.play()})
  await page.waitForFunction(()=>document.querySelector('video')?.currentTime>0)
  await video.evaluate(v=>v.pause())
  const videoInfo=await video.evaluate(v=>({duration:v.duration,width:v.videoWidth,height:v.videoHeight,currentTime:v.currentTime}))
  await page.screenshot({path:path.join(root,'workspace-desktop.png')})
  let submitted=0
  await page.route('**/assistant/chat',async route=>{
    submitted++
    const request=route.request().postDataJSON()
    assert.equal(request.course_key,'数据结构'); assert.equal(request.allow_web_knowledge,true)
    await route.fulfill({json:{task:{id:98765,status:'PENDING',current_step:'等待执行'}}})
  })
  let polls=0
  await page.route('**/assistant/tasks/98765',async route=>{
    polls++
    await route.fulfill({json:polls===1?{id:98765,status:'RUNNING',current_step:'课件章节 1/9',partial_resource:{id:999,title:'部分课件',content:'# 冒泡排序\n\n## 核心概念\n已完成的章节可阅读。',structured_json:'{}'}}:{id:98765,status:'SUCCEEDED',current_step:'完成',result:{cards:[{learning_context_id:selected}],content:'课件已保存',evidence:{knowledge_supplementation:{status:'SAVED_PENDING_REVIEW',candidate_ids:[42],reused:true}}}}})
  })
  await page.getByRole('button',{name:'重新生成课件',exact:true}).click()
  assert.equal(await page.getByRole('button',{name:'重新生成课件',exact:true}).isDisabled(),true)
  await page.locator('.partial-courseware').waitFor({timeout:15000})
  await page.getByText('复用已入库资料：候选 #42，待审核后进入公共知识库').waitFor({timeout:15000})
  assert.equal(submitted,1)
  await page.setViewportSize({width:390,height:844})
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false)
  await page.screenshot({path:path.join(root,'workspace-mobile.png')})
  assert.deepEqual(errors,[])
  fs.writeFileSync(path.join(root,'result.json'),JSON.stringify({passed:true,actualResource:229,exerciseCount:snapshot.exercises.length,videoInfo,taskBinding:true,formulas:true,partialPreview:true,automaticOpen:true,duplicateSubmissionBlocked:true,pageErrors:errors,paidCalls:0,completionSimulation:true},null,2))
} catch(e) {await page.screenshot({path:path.join(root,'failure.png')}); throw e}
finally {await browser.close()}
