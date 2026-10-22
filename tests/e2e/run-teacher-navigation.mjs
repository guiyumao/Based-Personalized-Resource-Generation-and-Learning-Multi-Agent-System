import fs from 'node:fs'
import path from 'node:path'
import assert from 'node:assert/strict'
import { loadPlaywright } from './lib/env.mjs'

const out = process.argv[2]
const auth = JSON.parse(process.env.TEACHER_VERIFY_AUTH)
const { chromium } = loadPlaywright().module
const browser = await chromium.launch({ headless: true })
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
await context.addInitScript(value => localStorage.setItem('learning-system-auth', JSON.stringify(value)), auth)
const page = await context.newPage()
const errors = [], warnings = [], failures = [], checks = []
page.on('pageerror', error => errors.push(error.message))
page.on('console', message => {
  if (/non-element root|cannot be animated|Unhandled error/.test(message.text())) warnings.push(message.text())
})
page.on('response', response => {
  if (response.status() >= 400 && /\/teacher\/|\/knowledge-base/.test(response.url())) failures.push({ url: response.url(), status: response.status() })
})
const pages = [
  ['overview', '教师管理系统'], ['classes', '班级管理'],
  ['knowledge-base', '大学课程知识库'], ['scopes', '学习范围与课件投放'],
  ['students', '学生洞察'], ['analytics', '教学统计与建议'],
  ['transcripts', ''], ['homework', '作业管理'],
]
const labels = ['教师总览', '班级管理', '课程知识库', '学习范围', '学生洞察', '教学分析', '成绩单分析', '作业管理']
async function visibleContent(key, title) {
  await page.waitForFunction(() => {
    const heading = document.querySelector('.app-content h1')
    return heading && heading.getBoundingClientRect().height > 0 &&
      !document.querySelector('.page-enter-active,.page-leave-active')
  })
  if (title) assert.equal(await page.locator('.app-content h1').innerText(), title)
  assert.ok((await page.locator('.app-content').innerText()).trim().length > 40, key)
}
try {
  await page.goto('http://127.0.0.1:5175/teacher/overview')
  await visibleContent('overview', '教师管理系统')
  for (let cycle = 0; cycle < 2; cycle++) {
    for (const [index, [key, title]] of pages.entries()) {
      await page.locator('.app-sidebar').getByRole('button', { name: labels[index], exact: true }).click()
      await page.waitForURL(`**/teacher/${key}`)
      await visibleContent(key, title)
      checks.push(`navigation ${cycle + 1}: ${key}`)
    }
  }
  await page.goto('http://127.0.0.1:5175/teacher/analytics')
  await visibleContent('analytics', '教学统计与建议')
  await page.reload()
  await visibleContent('analytics reload', '教学统计与建议')
  await page.screenshot({ path: path.join(out, 'analytics-desktop.png'), fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  await visibleContent('analytics mobile', '教学统计与建议')
  await page.screenshot({ path: path.join(out, 'analytics-mobile.png'), fullPage: true })
  checks.push('analytics direct entry, reload and mobile rendering')
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.evaluate(() => localStorage.setItem('app-theme', ''))
  await page.reload()
  await visibleContent('analytics light theme', '教学统计与建议')
  assert.equal(await page.locator('html').getAttribute('data-theme'), null)
  await page.screenshot({ path: path.join(out, 'analytics-light.png'), fullPage: true })
  checks.push('analytics light theme rendering')
  assert.deepEqual(errors, [])
  assert.deepEqual(warnings, [])
  assert.deepEqual(failures, [])
  fs.writeFileSync(path.join(out, 'result.json'), JSON.stringify({ checks, errors, warnings, failures, apiMocked: false, generationRequests: 0 }, null, 2))
  console.log(JSON.stringify({ checks, errors, warnings, failures }))
} finally {
  await context.close()
  await browser.close()
}
