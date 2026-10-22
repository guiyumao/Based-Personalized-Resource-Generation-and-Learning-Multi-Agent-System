import fs from 'node:fs'
import path from 'node:path'
import assert from 'node:assert/strict'
import { loadPlaywright } from './lib/env.mjs'
const root=process.argv[2],auth=JSON.parse(fs.readFileSync(path.join(root,'auth.json'),'utf8'))
const {chromium}=loadPlaywright().module,browser=await chromium.launch({headless:true})
const checks=[],errors=[],contexts=[],payloads=[],responses=[]
async function create(uid){const c=await browser.newContext({viewport:{width:1440,height:900}});contexts.push(c);await c.addInitScript(a=>{localStorage.setItem('learning-system-auth',JSON.stringify(a));if(!sessionStorage.getItem('student-workspace-context'))sessionStorage.setItem('student-workspace-context',JSON.stringify({userId:a.user.userId,subject:'计算机网络',topic:'TCP',generatedAt:Date.now()}));},auth[uid]);const p=await c.newPage();p.on('pageerror',e=>errors.push(e.message));p.on('request',r=>{if(r.url().endsWith('/exercises/generate'))payloads.push(r.postDataJSON())});return p}
try{
const page=await create(903)
await page.goto('http://127.0.0.1:15205/student/exercise')
const count=page.getByRole('spinbutton',{name:'练习题数量，范围 1 到 25'})
await count.waitFor();assert.equal(await count.inputValue(),'10')
for(const n of [1,7,25]){
 await count.fill(String(n));await count.blur()
 const responsePromise=page.waitForResponse(r=>r.url().endsWith('/exercises/generate'))
 await page.getByRole('button',{name:'生成练习题',exact:true}).click()
 const r=await responsePromise;assert.equal(r.status(),200,await r.text());const data=await r.json();assert.equal(data.exercises.length,n);responses.push({requested:n,received:data.exercises.length,ids:data.exercises.map(e=>e.exercise_id)})
 await page.getByText(new RegExp(`第 1 题 / 共 ${n} 题`)).waitFor()
 assert.equal(payloads.at(-1).exercise_count,n)
}
checks.push('1 / 7 / 25 question UI requests real API exact count persistence')
await count.fill('99');await count.blur();assert.equal(await count.inputValue(),'25');assert.ok(await page.getByRole('button',{name:'增加题量',exact:true}).isDisabled())
await count.fill('0');await count.blur();assert.equal(await count.inputValue(),'1');assert.ok(await page.getByRole('button',{name:'减少题量',exact:true}).isDisabled())
await count.fill('7');await count.blur();await page.reload();await count.waitFor();assert.equal(await count.inputValue(),'7');await page.getByText(/第 1 题 \/ 共 25 题/).waitFor()
checks.push('range normalization and saved future count survives previous set reload')
await page.screenshot({path:path.join(root,'exercise-desktop.png'),fullPage:true})
await page.setViewportSize({width:390,height:844});await page.waitForTimeout(500);await page.screenshot({path:path.join(root,'exercise-mobile.png'),fullPage:true});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth && document.querySelector('.app-content').scrollWidth<=document.querySelector('.app-content').clientWidth))
checks.push('390px exercise controls and question layout')
const other=await create(904);await other.goto('http://127.0.0.1:15205/student/exercise');assert.equal(await other.getByRole('spinbutton',{name:'练习题数量，范围 1 到 25'}).inputValue(),'10')
checks.push('separate account exercise count preference')
await page.setViewportSize({width:1440,height:900});await page.goto('http://127.0.0.1:15205/student/knowledge-graph')
const responsePromise=page.waitForResponse(r=>r.url().endsWith('/graph/visualization'))
await page.getByRole('button',{name:'查询图谱',exact:true}).click()
const graphResponse=await responsePromise;assert.equal(graphResponse.status(),200,await graphResponse.text());const graph=await graphResponse.json()
const publicLinks=graph.nodes.filter(n=>n.category==='resource'&&n.url)
assert.ok(publicLinks.length>0)
const links=page.locator('a.graph-resource-item--link');await links.first().waitFor();assert.equal(await links.count(),publicLinks.length)
for(const link of await links.all()){assert.match(await link.getAttribute('href'),/^https?:\/\//);assert.equal(await link.getAttribute('target'),'_blank');assert.equal(await link.getAttribute('rel'),'noopener noreferrer')}
await page.screenshot({path:path.join(root,'graph-desktop.png'),fullPage:true});await page.setViewportSize({width:390,height:844});await page.waitForTimeout(500);await page.screenshot({path:path.join(root,'graph-mobile.png'),fullPage:true});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth && document.querySelector('.app-content').scrollWidth<=document.querySelector('.app-content').clientWidth))
checks.push('real graph article references survive API and render safe links desktop/mobile')
assert.deepEqual(errors,[])
fs.writeFileSync(path.join(root,'result.json'),JSON.stringify({checks,pageErrors:errors,payloads,responses,model:'controlled fixture',api:'real services',graph:'real repository and curated references',database:'isolated SQLite',paidCalls:0},null,2));console.log(JSON.stringify({checks,pageErrors:errors}))
}finally{for(const c of contexts)await c.close();await browser.close()}
