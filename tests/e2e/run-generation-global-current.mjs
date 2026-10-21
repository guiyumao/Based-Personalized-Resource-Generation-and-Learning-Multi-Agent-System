import fs from 'node:fs'
import path from 'node:path'
import assert from 'node:assert/strict'
import {loadPlaywright} from './lib/env.mjs'
const root=process.argv[2], token=process.env.CURRENT_RUNTIME_TOKEN
assert.ok(token)
const {chromium}=loadPlaywright().module
const browser=await chromium.launch({headless:true})
const context=await browser.newContext({viewport:{width:1600,height:1000}})
const page=await context.newPage();const errors=[],forbidden=[]
page.on('pageerror',e=>errors.push(e.message))
await context.addInitScript(({token})=>localStorage.setItem('learning-system-auth',JSON.stringify({token,user:{userId:6,username:'student',role:'student'}})),{token})
await page.route('**/*',async route=>{
 const req=route.request()
 if(req.method()==='POST' && !req.url().includes('/resources/229/video') && !req.url().includes('/activity/heartbeat') && !req.url().endsWith('/resources/229/interactions')) {forbidden.push(req.url()); await route.abort(); return}
 await route.continue()
})
try {
 await page.goto('http://127.0.0.1:5175/student/workspace/f5324f85-1bfe-45de-a02c-a8544ce052bc')
 await page.getByRole('button',{name:'打开已有课件',exact:true}).waitFor({timeout:20000})
 await page.locator('.outline-resource[aria-current]').waitFor()
 const create=page.getByRole('button',{name:'制作当前课件视频',exact:true})
 const existing=await page.request.get('http://127.0.0.1:8002/resources/229/video',{headers:{Authorization:`Bearer ${token}`}})
 if(existing.status()!==200) {await create.waitFor();await create.click()}
 const video=page.locator('.courseware-video video')
 await video.waitFor({timeout:90000})
 await page.waitForFunction(()=>document.querySelector('video')?.readyState>=2)
 await video.evaluate(async v=>{v.muted=true;await v.play()})
 await page.waitForFunction(()=>document.querySelector('video')?.currentTime>0)
 await video.evaluate(v=>v.pause())
 const info=await video.evaluate(v=>({width:v.videoWidth,height:v.videoHeight,duration:v.duration,time:v.currentTime}))
 await page.screenshot({path:path.join(root,'live-workspace.png')})
 await page.goto('http://127.0.0.1:5175/student/resources?resource=229')
 await page.locator('.courseware-video video').waitFor({timeout:20000})
 await page.screenshot({path:path.join(root,'live-resource-center.png')})
 await page.setViewportSize({width:390,height:844})
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false)
 assert.deepEqual(errors,[]);assert.deepEqual(forbidden,[])
 fs.writeFileSync(path.join(root,'result.json'),JSON.stringify({passed:true,actualPlatform:5175,resource:229,video:info,pageErrors:errors,forbidden,realModelCalls:0},null,2))
} finally {await browser.close()}
