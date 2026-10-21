import fs from 'node:fs'
import path from 'node:path'
import assert from 'node:assert/strict'
import {loadPlaywright} from './lib/env.mjs'
const {module:pw}=loadPlaywright(),root=process.env.LIVE_INSIGHTS_OUTPUT,user=JSON.parse(process.env.LIVE_INSIGHTS_USER)
assert.ok(root&&process.env.LIVE_INSIGHTS_TOKEN)
const browser=await pw.chromium.launch({headless:true})
const context=await browser.newContext({viewport:{width:1440,height:1000}})
const allowed=new Set(['http://127.0.0.1:5175','http://127.0.0.1:8001','http://127.0.0.1:8004'])
await context.route('**/*',route=>allowed.has(new URL(route.request().url()).origin)&&['GET','OPTIONS'].includes(route.request().method())?route.continue():route.abort())
const page=await context.newPage();page.setDefaultTimeout(20000)
const result={passed:false,live:true,readOnly:true,learner_id:user.userId,steps:[],pageErrors:[],newEndpointErrors:[]}
page.on('pageerror',e=>result.pageErrors.push(String(e)))
page.on('response',r=>{if((r.url().includes('/learning-portrait')||r.url().includes('/insights'))&&r.status()>=400)result.newEndpointErrors.push(r.status())})
try {
  await page.goto('http://127.0.0.1:5175/login')
  await page.evaluate(({token,user})=>localStorage.setItem('learning-system-auth',JSON.stringify({token,user})),{token:process.env.LIVE_INSIGHTS_TOKEN,user})
  const analytics=page.waitForResponse(r=>r.url().includes(`/evaluation/analytics/${user.userId}/insights`)&&r.status()===200)
  await page.goto('http://127.0.0.1:5175/student/analytics')
  const data=await(await analytics).json()
  await page.getByRole('heading',{name:'学习分析仪表盘',exact:true}).waitFor()
  await page.locator('.insight-stats strong').first().waitFor()
  assert.equal(data.data.daily.length,30)
  await page.screenshot({path:path.join(root,'live-analytics.png'),fullPage:true})
  result.steps.push('live_5175_analytics_8004_real_data')
  const [portrait]=await Promise.all([
    page.waitForResponse(r=>r.url().includes(`/users/${user.userId}/learning-portrait`)&&r.status()===200),
    page.getByRole('button',{name:'学习画像',exact:true}).click(),
  ])
  const saved=await portrait.json()
  assert.equal(saved.axes.length,4)
  await page.getByRole('heading',{name:'我的学习画像',exact:true}).waitFor()
  await page.getByRole('button',{name:'编辑画像',exact:true}).click()
  await page.getByRole('button',{name:'保存画像',exact:true}).waitFor()
  await page.getByRole('button',{name:'取消',exact:true}).click()
  await page.screenshot({path:path.join(root,'live-portrait.png'),fullPage:true})
  result.steps.push('live_5175_portrait_8001_editor_and_cancel')
  await page.reload()
  await page.getByRole('button',{name:'编辑画像',exact:true}).waitFor()
  result.steps.push('live_refresh_readback')
  assert.deepEqual(result.pageErrors,[]);assert.deepEqual(result.newEndpointErrors,[])
  result.passed=true
}catch(e){result.error=String(e);await page.screenshot({path:path.join(root,'live-failure.png'),fullPage:true});throw e}finally{fs.writeFileSync(path.join(root,'live-browser-result.json'),JSON.stringify(result,null,2));await browser.close()}
