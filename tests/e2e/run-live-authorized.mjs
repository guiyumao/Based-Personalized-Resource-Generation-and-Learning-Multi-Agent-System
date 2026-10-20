import fs from 'node:fs'
import path from 'node:path'
import { loadPlaywright } from './lib/env.mjs'
const config = JSON.parse(process.env.LIVE_E2E_CONFIG || 'null')
if (!config) throw new Error('Dedicated authorized live runner required')
const allowed = new Set([config.frontend, ...Object.values(config.services)])
if ([...allowed].some(url => new URL(url).hostname !== '127.0.0.1')) throw new Error('Nonlocal UI endpoint')
const { module: pw } = loadPlaywright()
const browser = await pw.chromium.launch({headless:true,args:['--disable-background-networking','--disable-component-update','--disable-sync']})
const context = await browser.newContext({viewport:{width:1440,height:1000}})
await context.route('**/*',route => allowed.has(new URL(route.request().url()).origin) ? route.continue() : route.abort())
const page = await context.newPage()
const report = {source:'LIVE_AUTHORIZED_VIA_LOCAL_GATEWAY',steps:[],errors:[]}
page.on('pageerror',e=>report.errors.push(e.message))
try {
 await page.goto(config.frontend+'/login',{waitUntil:'networkidle'})
 await page.getByPlaceholder('请输入用户名').fill(config.username)
 await page.getByPlaceholder('请输入密码',{exact:true}).fill(config.password)
 await page.locator('button.auth-button').click()
 await page.waitForURL(u=>!u.pathname.startsWith('/login'))
 report.steps.push('real UI login')
 await page.goto(config.frontend+'/student/qa',{waitUntil:'networkidle'})
 await page.getByPlaceholder('输入你的问题，Enter 发送，Shift + Enter 换行').fill('请解释TCP确认和超时重传的关系，用简单中文回答')
 const pending=page.waitForResponse(r=>r.url().endsWith('/qa/analyze')&&r.request().method()==='POST',{timeout:90000})
 await page.getByRole('button',{name:'发送消息',exact:true}).click()
 const response=await pending
 if(response.status()!==200)throw new Error('QA HTTP '+response.status())
 const data=await response.json()
 if(!data.student_response || data.student_response.length<30)throw new Error('QA answer missing')
 const marker=data.student_response.slice(0,35)
 await page.reload({waitUntil:'networkidle'})
 await page.getByText(marker,{exact:false}).first().waitFor({timeout:15000})
 report.steps.push('authorized real-provider QA saved and restored')
 fs.writeFileSync(path.join(config.output,'live-qa-response.json'),JSON.stringify(data,null,2))
 await page.screenshot({path:path.join(config.output,'live-qa-browser.png'),fullPage:true})
 await page.goto(config.frontend+'/student/resources',{waitUntil:'networkidle'})
 await page.getByText(/TCP/).first().waitFor({timeout:15000})
 report.steps.push('saved real-generated courseware visible in resource catalog')
 await page.screenshot({path:path.join(config.output,'live-resource-browser.png'),fullPage:true})
 report.passed=report.errors.length===0
}catch(e){report.passed=false;report.error=String(e);await page.screenshot({path:path.join(config.output,'live-browser-failure.png'),fullPage:true});throw e}
finally{fs.writeFileSync(path.join(config.output,'live-browser-report.json'),JSON.stringify(report,null,2));await browser.close()}
