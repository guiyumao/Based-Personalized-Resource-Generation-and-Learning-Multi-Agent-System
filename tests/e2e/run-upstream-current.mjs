import fs from 'node:fs'
import path from 'node:path'
import assert from 'node:assert/strict'
import { loadPlaywright } from './lib/env.mjs'
const root=process.argv[2],auth=JSON.parse(fs.readFileSync(path.join(root,'auth.json'),'utf8'))
const {chromium}=loadPlaywright().module,browser=await chromium.launch({headless:true})
const context=await browser.newContext({viewport:{width:1440,height:900}}),errors=[],checks=[]
await context.addInitScript(a=>{localStorage.setItem('learning-system-auth',JSON.stringify(a));if(!sessionStorage.getItem('student-workspace-context'))sessionStorage.setItem('student-workspace-context',JSON.stringify({userId:a.user.userId,subject:'计算机网络',topic:'TCP',generatedAt:Date.now()}))},auth)
const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message))
try{
const spec=await(await page.request.get('http://127.0.0.1:8002/openapi.json')).json()
const limits=spec.components.schemas.ExerciseGenerationRequest.properties.exercise_count;assert.equal(limits.minimum,1);assert.equal(limits.maximum,25)
const headers={Authorization:`Bearer ${auth.token}`}
const caps=await(await page.request.get('http://127.0.0.1:8002/assistant/capabilities',{headers})).json();assert.equal(caps.max_exercise_count,25)
for(const exercise_count of [0,26]){const r=await page.request.post('http://127.0.0.1:8002/exercises/generate',{headers,data:{user_id:auth.user.userId,knowledge_point:'TCP',exercise_count}});assert.equal(r.status(),422)}
checks.push('current API schemas/capabilities 1-25 and invalid requests rejected before generation')
await page.goto('http://127.0.0.1:5175/student/exercise')
const count=page.getByRole('spinbutton',{name:'练习题数量，范围 1 到 25'});await count.waitFor();await count.fill('25');await count.blur();await page.reload();await count.waitFor();assert.equal(await count.inputValue(),'25')
assert.equal(await page.locator('.notification-trigger').getAttribute('aria-expanded'),'false')
await page.setViewportSize({width:390,height:844});await page.waitForTimeout(400);await page.screenshot({path:path.join(root,'exercise-mobile.png'),fullPage:true});assert.ok(await page.evaluate(()=>document.querySelector('.app-content').scrollWidth<=document.querySelector('.app-content').clientWidth))
checks.push('current 5175 selector persistence/mobile and existing notification card preserved')
await page.setViewportSize({width:1440,height:900});await page.goto('http://127.0.0.1:5175/student/knowledge-graph')
const promise=page.waitForResponse(r=>r.url().endsWith('/graph/visualization'));await page.getByRole('button',{name:'查询图谱',exact:true}).click();const response=await promise;assert.equal(response.status(),200,await response.text());const graph=await response.json()
assert.ok(graph.nodes.some(n=>n.category==='resource'&&n.url))
await page.locator('a.graph-resource-item--link').first().waitFor();await page.screenshot({path:path.join(root,'graph-desktop.png'),fullPage:true})
assert.equal(await page.locator('a.graph-resource-item--link').first().getAttribute('rel'),'noopener noreferrer')
checks.push('current real public graph hyperlinks reach 5175 UI')
assert.deepEqual(errors,[])
fs.writeFileSync(path.join(root,'result.json'),JSON.stringify({checks,pageErrors:errors,apiMocked:false,realPaidGenerationRun:false},null,2));console.log(JSON.stringify({checks,pageErrors:errors}))
}finally{await context.close();await browser.close()}
