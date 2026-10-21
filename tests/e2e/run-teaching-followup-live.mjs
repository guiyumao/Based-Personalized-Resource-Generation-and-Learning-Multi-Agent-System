import fs from 'node:fs'
import path from 'node:path'
import assert from 'node:assert/strict'
import { loadPlaywright } from './lib/env.mjs'
const root = process.argv[2]
const { token } = JSON.parse(fs.readFileSync(0, 'utf8'))
const { chromium } = loadPlaywright().module
const browser = await chromium.launch({ headless: true })
const context = await browser.newContext({viewport:{width:1440,height:1000}})
const page = await context.newPage()
const errors=[]
const mutations=[]
page.on('pageerror',e=>errors.push(e.message))
page.on('request',r=>{if(r.method()==='POST')mutations.push(r.url())})
await context.addInitScript(({token})=>localStorage.setItem('learning-system-auth',JSON.stringify({token,user:{userId:6,username:'runtime-copy-owner',role:'student'}})),{token})
try {
  const response=await page.request.get('http://127.0.0.1:8003/resources/222',{headers:{Authorization:`Bearer ${token}`}})
  assert.equal(response.status(),200)
  const old=(await response.json()).data
  await context.addInitScript(({old})=>sessionStorage.setItem('student-workspace-courseware',JSON.stringify({subject:'数据结构',topic:'冒泡排序',goal:'学习排序',generatedAt:Date.now(),selectedVariantId:'',resourceResult:{id:old.id,user_id:6,knowledge_point:'冒泡排序',content:old.content,variants:[],personalization:{mastery_score:60,correct_rate:60,answered_count:5,basis:[],recent_mistakes:[]}}})),{old})
  await page.goto('http://127.0.0.1:5175/student/courseware')
  await page.getByRole('button',{name:/打开已生成的九章新版/}).waitFor({timeout:20000})
  assert.equal(await page.locator('.courseware-reader nav').count(),0)
  assert.ok(!(await page.locator('.reader-content').innerText()).includes('最近一道选择题你选了'))
  const legacyNav=page.locator('.reader-toc button')
  const target=legacyNav.filter({hasText:'示例讲解'})
  await target.click()
  await page.waitForTimeout(1000)
  const legacySection=page.locator('.courseware-reader main > details').filter({has:page.locator('summary',{hasText:'示例讲解'})}).first()
  const legacyTop=(await legacySection.boundingBox()).y
  assert.ok(legacyTop>=0&&legacyTop<150,`legacy target top=${legacyTop}`)
  await page.screenshot({path:path.join(root,'legacy-directory.png')})
  await page.getByRole('button',{name:/打开已生成的九章新版/}).click()
  await page.getByRole('button',{name:'核心原理',exact:true}).waitFor()
  assert.equal(await page.locator('.courseware-reader main > details[data-section]').count(),10)
  await page.getByRole('button',{name:'图解与可视化',exact:true}).click()
  await page.waitForTimeout(500)
  assert.equal(await page.locator('.courseware-reader .flowchart').count(),0)
  assert.ok(!(await page.locator('.courseware-reader main').innerText()).includes('用流程图看整体控制结构'))
  await page.getByRole('button',{name:'完整案例分析',exact:true}).click()
  await page.waitForTimeout(1000)
  const chapter=page.locator('.courseware-reader main > details').filter({has:page.locator('summary',{hasText:'完整案例分析'})}).first()
  const desktopTop=(await chapter.boundingBox()).y
  assert.ok(desktopTop>=0&&desktopTop<150,`new target top=${desktopTop}`)
  assert.equal(await chapter.evaluate(el=>el.open),true)
  await page.screenshot({path:path.join(root,'new-directory-desktop.png')})
  await page.setViewportSize({width:390,height:844})
  await page.getByRole('button',{name:'知识巩固练习',exact:true}).click()
  await page.waitForTimeout(1000)
  const practice=page.locator('.courseware-reader main > details').filter({has:page.locator('summary',{hasText:'知识巩固练习'})}).first()
  const mobileTop=(await practice.boundingBox()).y
  assert.ok(mobileTop>=0&&mobileTop<150,`mobile target top=${mobileTop}`)
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false)
  await page.screenshot({path:path.join(root,'new-directory-mobile.png')})
  const stored=await page.evaluate(()=>JSON.parse(sessionStorage.getItem('student-workspace-courseware')))
  assert.equal(stored.resourceResult.id,225)
  assert.ok(stored.resourceResult.content.length>12000)
  assert.deepEqual(errors,[])
  assert.deepEqual(mutations.filter(url=>!url.endsWith('/evaluation/activity/heartbeat') && !url.endsWith('/activity/heartbeat')),[])
  fs.writeFileSync(path.join(root,'result.json'),JSON.stringify({passed:true,actualOldResource:222,actualNewResource:225,characters:stored.resourceResult.content.length,legacyTop,desktopTop,mobileTop,staleClaimsHidden:true,duplicateNavigation:false,paidCalls:0,pageErrors:errors},null,2))
} catch(e) {
  await page.screenshot({path:path.join(root,'failure.png')})
  fs.writeFileSync(path.join(root,'result.json'),JSON.stringify({passed:false,error:String(e),errors},null,2))
  throw e
} finally {await browser.close()}
