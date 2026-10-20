/**
 * Diagnostic helper: prints the exact DOM targets for axe violations on the
 * three audited pages, so a violation can be mapped back to a source file.
 * Usage: node axe-detail.mjs   (requires the dev server + backends to be up)
 */
import fs from 'node:fs'
import path from 'node:path'

import { BASE_URL, DESKTOP, REPO_ROOT, loadAxeSource, loadPlaywright, parseDotEnv } from './lib/env.mjs'

const env = parseDotEnv(path.join(REPO_ROOT, '.env'))
const { module: pw } = loadPlaywright()
const axe = loadAxeSource()
const browser = await pw.chromium.launch({ headless: true })

async function audit(context, url, readySelector, label) {
  const page = await context.newPage()
  await page.goto(url, { waitUntil: 'domcontentloaded' })
  if (readySelector) await page.waitForSelector(readySelector, { timeout: 30000 })
  await page.waitForTimeout(1500)
  await page.addScriptTag({ content: axe.source })
  const res = await page.evaluate(async () =>
    window.axe.run(document, {
      resultTypes: ['violations'],
      runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'best-practice'] },
    }),
  )
  console.log(`\n=== ${label} :: ${url} ===`)
  for (const v of res.violations) {
    console.log(`- ${v.id} [${v.impact}] ${v.nodes.length} node(s) :: ${v.help}`)
    for (const n of v.nodes.slice(0, 6)) {
      console.log(`    target : ${JSON.stringify(n.target)}`)
      console.log(`    html   : ${String(n.html).slice(0, 220)}`)
      if (n.any?.[0]?.message) console.log(`    message: ${String(n.any[0].message).replace(/\n/g, ' ').slice(0, 240)}`)
    }
  }
  await page.close()
}

// public page
const anon = await browser.newContext({ viewport: DESKTOP, locale: 'zh-CN' })
await audit(anon, `${BASE_URL}/login`, 'button.auth-button', 'login')
await anon.close()

// authenticated pages: register a throwaway student through the API-backed UI
const ctx = await browser.newContext({ viewport: DESKTOP, locale: 'zh-CN' })
const p = await ctx.newPage()
const username = `e2eaxe_${Date.now()}`
await p.goto(`${BASE_URL}/register`, { waitUntil: 'domcontentloaded' })
await p.waitForSelector('input[autocomplete="username"]')
await p.fill('input[autocomplete="username"]', username)
await p.fill('input[autocomplete="new-password"]', `E2ePass_${username}`)
await p.click('button.auth-button')
await p.waitForURL(/\/(profile-setup|student)/, { timeout: 30000 })
await p.close()
const state = await ctx.storageState()
await ctx.close()

const auth = await browser.newContext({ viewport: DESKTOP, locale: 'zh-CN', storageState: state })
await audit(auth, `${BASE_URL}/student/dashboard`, '.student-dashboard', 'student-dashboard')
await audit(auth, `${BASE_URL}/student/resources`, '.resource-search input', 'student-resources')
await auth.close()

await browser.close()
