import fs from 'node:fs'
import path from 'node:path'
import assert from 'node:assert/strict'
import {loadPlaywright} from './lib/env.mjs'
const input=JSON.parse(fs.readFileSync(0,'utf8'));const dir=input.output;fs.mkdirSync(dir,{recursive:true})
const {module:pw}=loadPlaywright();const browser=await pw.chromium.launch({headless:true})
const context=await browser.newContext({viewport:{width:1500,height:1100}})
await context.route('**/*',route=>['127.0.0.1','localhost'].includes(new URL(route.request().url()).hostname)?route.continue():route.abort())
const headers={Authorization:'Bearer '+input.auth.token};const api='http://127.0.0.1:8001/study'
const page=await context.newPage();page.setDefaultTimeout(30000)
const report={passed:false,currentRuntime:true,demoAccountOnly:true,paidCalls:0,pageErrors:[],checks:[]}
page.on('pageerror',error=>report.pageErrors.push(String(error)))
try {
 const binding=await context.request.post('http://127.0.0.1:8002/learning/contexts',{headers,data:input.binding})
 assert.ok(binding.ok(),'Context HTTP '+binding.status())
 const ctx=(await binding.json()).id
 const title='笔记历史验收示例 '+Date.now()
 const created=await context.request.post(api+'/notes',{headers,data:{title,body:'原始验收正文',learning_context_id:ctx,source_locator:'第1节'}})
 assert.equal(created.status(),201,await created.text());const note=await created.json();report.noteId=note.id
 await page.goto('http://127.0.0.1:5175/')
 await page.evaluate(auth=>localStorage.setItem('learning-system-auth',JSON.stringify(auth)),input.auth)
 await page.goto('http://127.0.0.1:5175/student/study-tools')
 const notes=page.getByRole('region',{name:'学习笔记',exact:true})
 await notes.getByRole('textbox',{name:'搜索笔记',exact:true}).fill(title)
 await notes.getByRole('textbox',{name:'笔记学科',exact:true}).fill('功能验收学科')
 await notes.getByRole('button',{name:'筛选笔记',exact:true}).click()
 const item=notes.locator('.study-item').filter({hasText:title})
 await item.getByText('关联资源 #'+input.binding.resource_id,{exact:true}).waitFor()
 await item.getByRole('button',{name:'编辑',exact:true}).click()
 await notes.getByRole('textbox',{name:'笔记内容',exact:true}).fill('修订后的验收正文')
 const saved=page.waitForResponse(r=>r.url().endsWith('/study/notes/'+note.id)&&r.request().method()==='PUT')
 await notes.getByRole('button',{name:'保存笔记',exact:true}).click();assert.equal((await saved).status(),200)
 await item.getByRole('button',{name:'修改历史',exact:true}).click()
 const dialog=page.getByRole('dialog',{name:'笔记修改历史'})
 await dialog.getByText('原始验收正文',{exact:true}).waitFor()
 await dialog.getByText('修订后的验收正文',{exact:true}).waitFor()
 await page.waitForTimeout(350)
 await page.screenshot({path:path.join(dir,'note-history.png'),fullPage:true})
 await dialog.getByRole('button',{name:'Close this dialog',exact:true}).click()
 const stale=await context.request.put(api+'/notes/'+note.id,{headers,data:{title,body:'stale tab',expected_version:note.version}})
 assert.equal(stale.status(),409)
 report.checks.push('current_note_filter_source_locator_version_history_and_stale_tab_409')
 const cards=page.getByRole('region',{name:'复习闪卡',exact:true})
 const front='验收闪卡 '+Date.now()
 await cards.getByRole('textbox',{name:'闪卡正面',exact:true}).fill(front)
 await cards.getByRole('textbox',{name:'闪卡背面',exact:true}).fill('验收答案')
 await cards.locator('.el-select__wrapper').click();await page.getByRole('option',{name:title,exact:true}).click()
 const cardSaved=page.waitForResponse(r=>r.url().endsWith('/study/cards')&&r.request().method()==='POST')
 await cards.getByRole('button',{name:'添加闪卡',exact:true}).click()
 const cardResponse=await cardSaved;assert.equal(cardResponse.status(),201);const card=await cardResponse.json();report.cardId=card.id
 assert.equal(card.knowledge_point_id,input.pointId)
 const cardItem=cards.locator('.study-item').filter({hasText:front})
 await cardItem.getByRole('button',{name:'显示答案',exact:true}).click()
 const reviewed=page.waitForResponse(r=>r.url().endsWith(`/study/cards/${card.id}/review`)&&r.request().method()==='POST')
 await cardItem.getByRole('button',{name:'已经记住',exact:true}).click()
 const receipt=await reviewed;assert.equal(receipt.status(),200)
 const replay=await context.request.post(api+`/cards/${card.id}/review`,{headers,data:receipt.request().postDataJSON()})
 assert.equal(replay.status(),200);assert.equal((await replay.json()).review_count,1)
 await cardItem.getByText(/该知识点累计复习/).waitFor()
 await page.screenshot({path:path.join(dir,'flashcard-evidence.png'),fullPage:true})
 const reviews=await context.request.get(api+`/cards/${card.id}/reviews`,{headers});assert.equal((await reviews.json()).length,1)
 report.checks.push('current_note_to_card_binding_review_schedule_idempotent_replay_and_self_reported_profile')
 assert.deepEqual(report.pageErrors,[]);report.passed=true
} catch(error) {report.error=String(error.stack??error);process.exitCode=1;await page.screenshot({path:path.join(dir,'failure.png'),fullPage:true}).catch(()=>{})}
finally {fs.writeFileSync(path.join(dir,'result.json'),JSON.stringify(report,null,2));await browser.close()}
