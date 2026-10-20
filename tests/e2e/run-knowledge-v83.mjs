/** Real login and reviewed publication/rollback against an isolated V8.3 runtime. */
import fs from 'node:fs'
import path from 'node:path'
import { loadPlaywright } from './lib/env.mjs'

const { module: pw } = loadPlaywright()
const runtime = process.env.V83_RUNTIME
const origin = process.env.E2E_BASE_URL
if (!runtime || !origin || !process.env.V83_BROWSER_PASSWORD) throw new Error('Isolated browser environment is required')
const browser = await pw.chromium.launch({ headless: true })
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
const errors = []
page.on('pageerror', error => errors.push(String(error)))
const result = { passed: false, mocked: false, steps: [] }
try {
  await page.goto(`${origin}/login`, { waitUntil: 'domcontentloaded' })
  fs.writeFileSync(path.join(runtime, 'browser-login-snapshot.yml'), await page.locator('body').ariaSnapshot())
  await page.locator('input[autocomplete="username"]').fill('v83-verifier')
  await page.locator('input[autocomplete="current-password"]').fill(process.env.V83_BROWSER_PASSWORD)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await page.waitForURL('**/admin', { timeout: 20000 })
  await page.getByRole('heading', { name: 'AI 学科规划与分批建设' }).waitFor()
  result.steps.push('real_user_service_login')
  fs.writeFileSync(path.join(runtime, 'browser-admin-snapshot.yml'), await page.locator('body').ariaSnapshot())
  let candidate = page.locator(`[data-candidate-id="${process.env.V83_BROWSER_CANDIDATE_ID}"]`)
  const revisionButton = candidate.getByRole('button', { name: '创建修订草稿', exact: true })
  await revisionButton.waitFor()
  await revisionButton.click()
  const editor = candidate.locator('textarea')
  await editor.waitFor()
  await editor.fill((await editor.inputValue()) + '\n\n## Browser acceptance revision\n\nIsolated browser acceptance test marker.\n')
  await candidate.getByPlaceholder('许可证标识').fill('INTERNAL_TEST_ONLY')
  await candidate.getByPlaceholder('许可依据 URL').fill('https://datatracker.ietf.org/doc/draft-ietf-ccwg-bbr/')
  if (!await candidate.getByRole('checkbox', { name: '已核验全文发布许可' }).isChecked()) {
    await candidate.getByText('已核验全文发布许可', { exact: true }).click()
  }
  await candidate.getByRole('button', { name: '提交审核', exact: true }).click()
  await candidate.getByRole('button', { name: '批准', exact: true }).click()
  await candidate.getByRole('button', { name: '发布并验证检索', exact: true }).click()
  fs.writeFileSync(path.join(runtime, 'browser-publish-dialog.yml'), await page.locator('.el-message-box').ariaSnapshot())
  const publicationResponse = page.waitForResponse(response => response.url().includes(`/knowledge-base/candidates/${process.env.V83_BROWSER_CANDIDATE_ID}/publish`) && response.request().method() === 'POST')
  await page.locator('.el-message-box').getByRole('button').last().click()
  const publication = await (await publicationResponse).json()
  result.publication = { version_id: publication.version_id, corpus_path: publication.corpus_path, retrieval_matches: publication.retrieval_matches }
  await page.getByText(/发布成功，检索验证命中/).waitFor({ timeout: 120000 })
  result.steps.push('edit_submit_approve_publish_real_chroma')
  const originalCard = page.locator(`[data-version-id="${process.env.V83_ORIGINAL_VERSION_ID}"]`)
  await originalCard.getByRole('button', { name: '恢复此版本', exact: true }).click()
  const rollbackResponse = page.waitForResponse(response => response.url().includes(`/knowledge-base/versions/${process.env.V83_ORIGINAL_VERSION_ID}/rollback`) && response.request().method() === 'POST')
  await page.locator('.el-message-box').getByRole('button').last().click()
  const restored = await (await rollbackResponse).json()
  result.rollback = { version_id: restored.version_id, retrieval_matches: restored.retrieval_matches, affected: restored.affected }
  await page.getByText('知识版本与索引已恢复', { exact: true }).waitFor({ timeout: 120000 })
  result.steps.push('rollback_to_original_version_and_verify_retrieval')
  await page.getByRole('heading', { name: '比较与恢复' }).scrollIntoViewIfNeeded()
  await page.screenshot({ path: path.join(runtime, 'browser-versions.png') })
  result.pageErrors = errors
  if (errors.length) throw new Error(errors.join('\n'))
  result.passed = true
} catch (error) {
  result.error = String(error)
  fs.writeFileSync(path.join(runtime, 'browser-failure.yml'), await page.locator('body').ariaSnapshot())
  await page.screenshot({ path: path.join(runtime, 'browser-failure.png') })
  throw error
} finally {
  fs.writeFileSync(path.join(runtime, 'browser-report.json'), JSON.stringify(result, null, 2))
  await browser.close()
}
console.log(JSON.stringify(result))
