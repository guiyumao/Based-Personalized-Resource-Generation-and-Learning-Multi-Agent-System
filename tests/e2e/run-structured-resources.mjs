/**
 * Structured-resource E2E — mind_map / code_case / video_script in a real browser.
 *
 *   node tests/e2e/run-structured-resources.mjs
 *   E2E_BASE_URL=http://127.0.0.1:5175 node tests/e2e/run-structured-resources.mjs
 *
 * What this suite does and does NOT claim
 * ---------------------------------------
 * * Section `generation` records whether the three resources were produced by a
 *   **real LLM call through the live agent API**. It is reported separately from
 *   the browser assertions on purpose: "the page rendered" is never written up as
 *   "the model generated it".
 * * Section `ui` records the browser-level assertions (type label, structured
 *   body, validation status, empty state, failure state, unknown type, reload).
 *   Injected states (forced HTTP statuses, a hand-crafted empty payload) are
 *   labelled `injected: true` so they can never be mistaken for live data.
 *
 * Outputs (artifacts/upstream-integration/e2e-structured/):
 *   results.json            machine-readable record of both sections
 *   run.log                 raw console log
 *   screenshots/*.png       one screenshot per case
 */
import fs from 'node:fs'
import path from 'node:path'
import { createRequire } from 'node:module'

import { BASE_URL, DESKTOP, REPO_ROOT, ensureDirs, loadPlaywright, sleep } from './lib/env.mjs'

const OUT_DIR = path.join(REPO_ROOT, 'artifacts', 'upstream-integration', 'e2e-structured')
const SHOT_DIR = path.join(OUT_DIR, 'screenshots')

const USER_API = process.env.E2E_USER_API || 'http://127.0.0.1:8001'
const AGENT_API = process.env.E2E_AGENT_API || 'http://127.0.0.1:8002'
const RESOURCE_API = process.env.E2E_RESOURCE_API || 'http://127.0.0.1:8003'

const AUTH_KEY = 'learning-system-auth'

const LOG = []
function log(...parts) {
  const line = parts.map((p) => (typeof p === 'string' ? p : JSON.stringify(p))).join(' ')
  LOG.push(line)
  process.stdout.write(`${line}\n`)
}

const results = {
  generated_at: new Date().toISOString(),
  base_url: BASE_URL,
  apis: { user: USER_API, agent: AGENT_API, resource: RESOURCE_API },
  generation: { attempted: false, real_llm: false, resources: [], note: '' },
  ui: [],
  injected_states: [],
  console_errors: [],
  page_errors: [],
  network: [],
  screenshots: [],
}

class CaseContext {
  constructor(id) {
    this.id = id
    this.assertions = 0
    this.notes = []
  }

  assert(title, condition, detail = '') {
    this.assertions += 1
    if (condition) {
      log(`    [ok]   ${title}`)
      return true
    }
    throw new Error(detail ? `${title} — ${detail}` : title)
  }

  note(text) {
    this.notes.push(text)
    log(`    [note] ${text}`)
  }
}

async function shot(page, name) {
  const file = path.join(SHOT_DIR, `${name}.png`)
  try {
    await page.screenshot({ path: file, fullPage: false })
    const rel = path.relative(REPO_ROOT, file).replace(/\\/g, '/')
    results.screenshots.push(rel)
    return rel
  } catch {
    return null
  }
}

async function loginAs(page, username, password) {
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('input[autocomplete="username"]', { timeout: 20000 })
  await page.fill('input[autocomplete="username"]', username)
  await page.fill('input[autocomplete="current-password"]', password)
  await page.click('button.auth-button')
}

async function readAuth(page) {
  const raw = await page.evaluate((key) => window.localStorage.getItem(key), AUTH_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw)
  } catch {
    return null
  }
}

/** The library card is addressable by the persisted resource id. */
function cardById(page, resourceId) {
  return page.locator(`.library-card[data-resource-id="${resourceId}"]`).first()
}

/* ------------------------------------------------------------------ API calls */

async function apiGenerate(token, userId, resourceType, knowledgePoint) {
  const started = Date.now()
  const response = await fetch(`${AGENT_API}/resources/generate`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', authorization: `Bearer ${token}` },
    body: JSON.stringify({
      user_id: userId,
      knowledge_point: knowledgePoint,
      resource_type: resourceType,
      resource_style: 'concise',
      subject: '计算机基础',
      learner_profile: {},
    }),
  })
  const elapsedMs = Date.now() - started
  const text = await response.text()
  let body = null
  try {
    body = JSON.parse(text)
  } catch {
    body = { raw: text.slice(0, 400) }
  }
  return { status: response.status, elapsedMs, body }
}

/* ------------------------------------------------------------------ case list */

const CASES = []
const defineCase = (id, title, fn, options = {}) => CASES.push({ id, title, fn, options })

const GENERATION_TARGETS = [
  { resourceType: 'mind_map', knowledgePoint: '二分查找', label: '思维导图' },
  { resourceType: 'code_case', knowledgePoint: 'Python 循环结构', label: '代码实操' },
  { resourceType: 'video_script', knowledgePoint: 'HTTP 请求与响应', label: '讲解脚本' },
]
const generated = {}

/* --- S1: home page is not blank ------------------------------------------ */
defineCase('S1-home-not-blank', 'Home page opens without a blank screen', async (ctx) => {
  const { page } = ctx
  await page.goto(`${BASE_URL}/`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('#app', { timeout: 20000 })
  await sleep(1500)

  const appText = (await page.locator('#app').innerText()).trim()
  ctx.assert('app root has content', appText.length > 80, `${appText.length} chars`)
  ctx.assert('document body has content', (await page.innerText('body')).trim().length > 80)
  const rootHtml = await page.locator('#app').innerHTML()
  ctx.assert('app root is not an empty template', rootHtml.trim().length > 200)
}, { screenshot: true })

/* --- S2: register a throwaway student ------------------------------------ */
defineCase('S2-student-register', 'Throwaway student registers through the UI', async (ctx) => {
  const { page, ENV } = ctx
  const username = `e2es_${ENV.suffix}`
  await page.goto(`${BASE_URL}/register`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('input[autocomplete="username"]', { timeout: 20000 })
  await page.fill('input[autocomplete="username"]', username)
  await page.fill('input[autocomplete="new-password"]', ENV.studentPass)
  await page.click('button.auth-button')
  await page.waitForURL(/\/(profile-setup|student)/, { timeout: 30000 })

  const auth = await readAuth(page)
  ctx.assert('registration persisted a token', Boolean(auth?.token))
  ctx.assert('registered role is student', auth?.user?.role === 'student', String(auth?.user?.role))
  ctx.ENV.studentUsername = username
  ctx.ENV.studentUserId = auth?.user?.userId
  ctx.ENV.studentToken = auth?.token
  ctx.shared.studentState = await ctx.context.storageState()
  ctx.note(`student ${username} userId=${auth?.user?.userId} password=<redacted>`)
})

/* --- S3: real LLM generation through the live API ------------------------ */
defineCase('S3-real-llm-generation', 'Three structured resources are generated by the real LLM API', async (ctx) => {
  const { ENV } = ctx
  results.generation.attempted = true
  ctx.assert('student token available', Boolean(ENV.studentToken), 'registration must run first')

  for (const target of GENERATION_TARGETS) {
    const response = await apiGenerate(ENV.studentToken, ENV.studentUserId, target.resourceType, target.knowledgePoint)
    const record = {
      resource_type: target.resourceType,
      knowledge_point: target.knowledgePoint,
      http_status: response.status,
      elapsed_ms: response.elapsedMs,
      resource_id: response.body?.id ?? null,
      audit_status: response.body?.audit_status ?? null,
      audit_reason: response.body?.audit_reason ?? null,
      validation_verdict: response.body?.content_validation?.verdict ?? null,
      structure_passed: response.body?.content_validation?.structure_passed ?? null,
      title: response.body?.[target.resourceType]?.title ?? null,
    }
    results.generation.resources.push(record)
    log(`    [gen] ${target.resourceType} -> HTTP ${response.status} in ${response.elapsedMs}ms ${JSON.stringify(record)}`)

    ctx.assert(
      `${target.resourceType} generation returned HTTP 200`,
      response.status === 200,
      JSON.stringify(response.body).slice(0, 400),
    )
    ctx.assert(`${target.resourceType} returned a persisted id`, Number.isInteger(response.body?.id), String(response.body?.id))
    ctx.assert(
      `${target.resourceType} audit is not rejected`,
      response.body?.audit_status !== 'rejected',
      String(response.body?.audit_reason),
    )
    generated[target.resourceType] = record
  }

  results.generation.real_llm = true
  results.generation.note =
    'Each record below is a real HTTP call from this run to the live agent service, which calls the configured LLM provider.'
}, { screenshot: false })

/* --- S4..S6: the three resource types render their real content ---------- */
function structuredCase(id, resourceType, label) {
  defineCase(id, `${label} (${resourceType}) renders type, structure and validation status`, async (ctx) => {
    const { page } = ctx
    const record = generated[resourceType]
    ctx.assert('the resource was generated earlier in this run', Boolean(record?.resource_id), 'missing id')

    await page.goto(`${BASE_URL}/student/resources`, { waitUntil: 'domcontentloaded' })
    await page.waitForSelector('.resource-search input', { timeout: 30000 })

    const card = cardById(page, record.resource_id)
    await card.waitFor({ state: 'visible', timeout: 30000 })
    ctx.assert('the generated resource appears in the library', await card.isVisible())

    const cardLabel = (await card.locator('.meta-row span').first().innerText()).trim()
    ctx.assert(`card shows the ${label} type label`, cardLabel === label, cardLabel)

    await card.click()
    const panel = page.locator('[data-testid="structured-resource-panel"]')
    await panel.waitFor({ state: 'visible', timeout: 30000 })
    ctx.assert(
      'panel carries the resource type',
      (await panel.getAttribute('data-resource-type')) === resourceType,
      String(await panel.getAttribute('data-resource-type')),
    )

    const typeLabel = (await page.locator('[data-testid="structured-type-label"]').innerText()).trim()
    ctx.assert(`panel shows the ${label} type name`, typeLabel === label, typeLabel)

    // structured body
    if (resourceType === 'mind_map') {
      const nodes = await page.locator('[data-testid="structured-mind-map"] .mind-map-outline li').count()
      ctx.assert('mind map renders its nodes', nodes > 0, `${nodes} nodes`)
    } else if (resourceType === 'code_case') {
      await page.waitForSelector('[data-testid="structured-code-case"]', { timeout: 20000 })
      const code = (await page.locator('[data-testid="code-case-source"]').innerText()).trim()
      ctx.assert('code case renders its example code', code.length > 10, `${code.length} chars`)
    } else {
      const chapters = await page.locator('[data-testid="structured-video-script"] .chapter-list li').count()
      ctx.assert('video script renders its chapters', chapters > 0, `${chapters} chapters`)
      const bodyText = await page.locator('[data-testid="structured-video-script"]').innerText()
      ctx.assert('video script states it is a script, not a video', bodyText.includes('不产出视频文件'), bodyText.slice(0, 80))
    }

    // validation status
    await page.waitForSelector('[data-testid="validation-block"]', { timeout: 20000 })
    const verdict = (await page.locator('[data-testid="validation-verdict"]').innerText()).trim()
    ctx.assert('validation verdict is rendered', verdict.length > 0, verdict)
    ctx.note(`validation verdict: ${verdict}`)

    // read-back evidence from the detail API (not just what the DOM says)
    const detail = await fetch(`${RESOURCE_API}/resources/${record.resource_id}`)
    const payload = (await detail.json()).data
    ctx.assert('detail API returned the structured payload', Boolean(payload?.structured))
    ctx.assert('detail API returned the validation report', Boolean(payload?.content_validation))
    record.detail_readback = {
      http_status: detail.status,
      has_structured: Boolean(payload?.structured),
      has_content_validation: Boolean(payload?.content_validation),
      validation_verdict: payload?.content_validation?.verdict ?? null,
      audit_status: payload?.audit_status ?? null,
    }
  }, { screenshot: true })
}

structuredCase('S4-mind-map-renders', 'mind_map', '思维导图')
structuredCase('S5-code-case-renders', 'code_case', '代码实操')
structuredCase('S6-video-script-renders', 'video_script', '讲解脚本')

/* --- S7: injected empty structured payload ------------------------------- */
defineCase('S7-empty-structured-state', 'An empty structured payload shows a defined empty state (injected)', async (ctx) => {
  const { page } = ctx
  const record = generated['mind_map']
  ctx.assert('mind map generated earlier', Boolean(record?.resource_id))

  await page.route(`${RESOURCE_API}/resources/${record.resource_id}`, async (route) => {
    await route.fulfill({
      status: 200,
      headers: { 'content-type': 'application/json', 'access-control-allow-origin': '*' },
      body: JSON.stringify({
        data: {
          id: record.resource_id,
          title: record.title,
          type: 'mind_map',
          format: 'json',
          status: 'draft',
          knowledge_point: '二分查找',
          source_type: 'generated',
          is_downloadable: false,
          audit_status: 'passed',
          audit_reason: 'rule_audit_passed',
          content: '',
          structured: null,
          content_validation: null,
        },
        message: 'injected',
      }),
    })
  })
  results.injected_states.push({ case: 'S7', kind: 'empty_structured_payload', resource_id: record.resource_id })

  await page.goto(`${BASE_URL}/student/resources`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('.resource-search input', { timeout: 30000 })
  const card = cardById(page, record.resource_id)
  await card.waitFor({ state: 'visible', timeout: 30000 })
  await card.click()

  await page.waitForSelector('[data-testid="structured-resource-panel"]', { timeout: 30000 })
  await page.waitForSelector('[data-testid="structured-empty"]', { timeout: 20000 })
  const text = (await page.locator('[data-testid="structured-empty"]').innerText()).trim()
  ctx.assert('empty state explains there is no structured content', text.includes('暂无可展示的结构化内容'), text)
  ctx.assert('page did not white-screen', (await page.locator('#app').innerText()).trim().length > 100)
}, { screenshot: true })

/* --- S8: injected failure states (409 / 422 / 503) ----------------------- */
async function forceStatus(page, url, status, body) {
  await page.route(url, async (route) => {
    const request = route.request()
    const headers = {
      'access-control-allow-origin': '*',
      'access-control-allow-headers': '*',
      'access-control-allow-methods': '*',
      'content-type': 'application/json',
    }
    if (request.method() === 'OPTIONS') {
      await route.fulfill({ status: 204, headers, body: '' })
      return
    }
    await route.fulfill({ status, headers, body: JSON.stringify(body) })
  })
}

defineCase('S8-failure-states-detail', '409 / 422 / 503 on the detail API each show a comprehensible error', async (ctx) => {
  const { page } = ctx
  const record = generated['code_case']
  ctx.assert('code case generated earlier', Boolean(record?.resource_id))

  const messages = {
    409: '资源正在被其他操作占用，请稍后重试。',
    422: '请求参数不合法，无法加载该资源内容。',
    503: '资源服务暂不可用，请稍后重试。',
  }

  for (const [statusText, detail] of Object.entries(messages)) {
    const status = Number(statusText)
    const route = `${RESOURCE_API}/resources/${record.resource_id}`
    await page.unroute(route).catch(() => {})
    await forceStatus(page, route, status, { detail })
    results.injected_states.push({ case: 'S8', kind: 'detail_api_status', status, resource_id: record.resource_id })

    await page.goto(`${BASE_URL}/student/resources`, { waitUntil: 'domcontentloaded' })
    await page.waitForSelector('.resource-search input', { timeout: 30000 })
    const card = cardById(page, record.resource_id)
    await card.waitFor({ state: 'visible', timeout: 30000 })
    await card.click()

    const banner = page.locator('[data-testid="structured-detail-error"]')
    await banner.waitFor({ state: 'visible', timeout: 20000 })
    const text = (await banner.innerText()).trim()
    ctx.assert(`HTTP ${status} produces a visible error banner`, text.length > 0, text)
    ctx.assert(`HTTP ${status} is named in the message`, text.includes(String(status)), text)
    ctx.assert('the page did not white-screen', (await page.locator('#app').innerText()).trim().length > 100)
    ctx.assert('the base metadata is still shown', await page.locator('.modal-info').isVisible())
  }
  await page.unroute(`${RESOURCE_API}/resources/${record.resource_id}`).catch(() => {})
}, { screenshot: true })

defineCase('S9-failure-state-list-503', 'A 503 on the resource list shows the page-level error banner', async (ctx) => {
  const { page } = ctx
  await forceStatus(page, `${RESOURCE_API}/resources`, 503, {
    detail: '资源服务正在维护，请稍后重试。',
  })
  results.injected_states.push({ case: 'S9', kind: 'list_api_status', status: 503 })

  await page.goto(`${BASE_URL}/student/resources`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('.resource-error', { timeout: 40000 })
  const text = (await page.locator('.resource-error').innerText()).trim()
  ctx.assert('list error banner rendered', text.length > 0, text)
  ctx.assert('banner explains the failure', /失败/.test(text), text)
  ctx.assert('backend detail is surfaced', text.includes('资源服务正在维护'), text)
  ctx.assert('page did not white-screen', (await page.locator('#app').innerText()).trim().length > 100)
  await page.unroute(`${RESOURCE_API}/resources`).catch(() => {})
}, { screenshot: true })

/* --- S10: unknown resource type is never a blank panel ------------------- */
defineCase('S10-unknown-resource-type', 'An unknown resource type renders an explicit fallback (injected)', async (ctx) => {
  const { page } = ctx
  const unknownItem = {
    id: 987654,
    title: '未知类型资源（注入用例）',
    type: 'quantum_notes',
    format: 'json',
    status: 'draft',
    knowledge_point: '二分查找',
    source_type: 'generated',
    is_downloadable: false,
    audit_status: 'pending',
    audit_reason: '',
  }

  await page.route(`${RESOURCE_API}/resources`, async (route) => {
    const request = route.request()
    if (request.method() !== 'GET') return route.continue()
    const headers = {
      'access-control-allow-origin': '*',
      'access-control-allow-headers': '*',
      'access-control-allow-methods': '*',
      'content-type': 'application/json',
    }
    await route.fulfill({
      status: 200,
      headers,
      body: JSON.stringify({ data: [unknownItem], message: 'injected' }),
    })
  })
  await page.route(`${RESOURCE_API}/resources/987654`, async (route) => {
    const headers = {
      'access-control-allow-origin': '*',
      'access-control-allow-headers': '*',
      'access-control-allow-methods': '*',
      'content-type': 'application/json',
    }
    await route.fulfill({
      status: 200,
      headers,
      body: JSON.stringify({ data: { ...unknownItem, content: null, structured: null, content_validation: null }, message: 'injected' }),
    })
  })
  results.injected_states.push({ case: 'S10', kind: 'unknown_resource_type', type: unknownItem.type })

  await page.goto(`${BASE_URL}/student/resources`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('.resource-search input', { timeout: 30000 })
  const card = cardById(page, unknownItem.id)
  await card.waitFor({ state: 'visible', timeout: 30000 })

  const cardLabel = (await card.locator('.meta-row span').first().innerText()).trim()
  ctx.assert('the raw type is shown instead of a blank label', cardLabel === 'quantum_notes', cardLabel)

  await card.click()
  await page.waitForSelector('[data-testid="unknown-resource-type"]', { timeout: 20000 })
  const fallback = (await page.locator('[data-testid="unknown-resource-type"]').innerText()).trim()
  ctx.assert('fallback names the unknown type', fallback.includes('quantum_notes'), fallback)
  ctx.assert('modal still renders its metadata', await page.locator('.modal-info').isVisible())
  ctx.assert('page did not white-screen', (await page.locator('#app').innerText()).trim().length > 100)

  await page.unroute(`${RESOURCE_API}/resources`).catch(() => {})
  await page.unroute(`${RESOURCE_API}/resources/987654`).catch(() => {})
}, { screenshot: true })

/* --- S11: content survives a full page reload ---------------------------- */
defineCase('S11-refresh-persistence', 'Structured content is still readable after a full page reload', async (ctx) => {
  const { page } = ctx
  const record = generated['video_script']
  ctx.assert('video script generated earlier', Boolean(record?.resource_id))

  const open = async () => {
    await page.goto(`${BASE_URL}/student/resources`, { waitUntil: 'domcontentloaded' })
    await page.waitForSelector('.resource-search input', { timeout: 30000 })
    const card = cardById(page, record.resource_id)
    await card.waitFor({ state: 'visible', timeout: 30000 })
    await card.click()
    await page.waitForSelector('[data-testid="structured-video-script"]', { timeout: 30000 })
    return page.locator('[data-testid="structured-video-script"] .chapter-list li').count()
  }

  const before = await open()
  await page.reload({ waitUntil: 'domcontentloaded' })
  await page.waitForSelector('.resource-search input', { timeout: 30000 })
  ctx.assert('still authenticated after reload', !page.url().includes('/login'), page.url())

  const after = await open()
  ctx.assert('chapters still render after the reload', after > 0, `${after} chapters`)
  ctx.assert('the same content came back', after === before, `before=${before} after=${after}`)

  const auth = await readAuth(page)
  ctx.assert('token survived the reload', Boolean(auth?.token))
}, { screenshot: true })

/* ------------------------------------------------------------------- runner */

async function runCase(browser, spec, shared) {
  const { id, title, fn, options } = spec
  const started = Date.now()
  const record = { id, title, status: 'failed', duration_ms: 0, assertions: 0, failure_reason: null, notes: [], screenshot: null }
  log(`\n[CASE] ${id} :: ${title}`)

  const context = await browser.newContext({
    viewport: DESKTOP,
    locale: 'zh-CN',
    ignoreHTTPSErrors: true,
    // The student session is produced by S2 and reused afterwards; without it the
    // router guard bounces every later case to /login.
    ...(shared.studentState ? { storageState: shared.studentState } : {}),
  })
  const page = await context.newPage()
  page.setDefaultTimeout(30000)
  page.setDefaultNavigationTimeout(45000)

  const caseErrors = { console: [], page: [] }
  page.on('pageerror', (error) => {
    const entry = { case: id, message: String(error?.message ?? error).slice(0, 400) }
    caseErrors.page.push(entry)
    results.page_errors.push(entry)
  })
  page.on('console', (message) => {
    if (message.type() !== 'error') return
    const text = message.text().slice(0, 400)
    if (/favicon|Download the Vue Devtools/i.test(text)) return
    const entry = { case: id, message: text }
    caseErrors.console.push(entry)
    results.console_errors.push(entry)
  })
  page.on('response', (response) => {
    const url = response.url()
    if (!/:(8001|8002|8003)\//.test(url)) return
    if (!/\/resources/.test(url)) return
    if (results.network.length < 400) {
      results.network.push({ case: id, status: response.status(), method: response.request().method(), url })
    }
  })

  const ctx = new CaseContext(id)
  ctx.page = page
  ctx.context = context
  ctx.shared = shared
  ctx.ENV = shared.env

  try {
    await fn(ctx)
    if (caseErrors.page.length) throw new Error(`uncaught pageerror: ${caseErrors.page[0].message}`)
    record.status = 'passed'
    if (options.screenshot) record.screenshot = await shot(page, id)
  } catch (error) {
    record.status = 'failed'
    record.failure_reason = String(error?.message ?? error).slice(0, 900)
    log(`    [FAIL] ${record.failure_reason}`)
    record.screenshot = await shot(page, `${id}-FAILURE`)
  } finally {
    record.assertions = ctx.assertions
    record.notes = ctx.notes
    record.duration_ms = Date.now() - started
    results.ui.push(record)
    log(`    [${record.status.toUpperCase()}] ${id} (${record.duration_ms} ms, ${record.assertions} assertions)`)
    await context.close()
  }
  return record
}

async function main() {
  ensureDirs()
  fs.mkdirSync(SHOT_DIR, { recursive: true })
  const startedAt = Date.now()

  const env = {
    suffix: `${Date.now()}${Math.floor(Math.random() * 900 + 100)}`,
    studentPass: `E2ePass_${Date.now()}`,
  }

  log('='.repeat(78))
  log('structured-resource E2E run')
  log(`started_at : ${new Date().toISOString()}`)
  log(`base_url   : ${BASE_URL}`)
  log(`apis       : user=${USER_API} agent=${AGENT_API} resource=${RESOURCE_API}`)
  log(`throwaway  : student e2es_${env.suffix} (password redacted)`)
  log('='.repeat(78))

  const probe = await fetch(BASE_URL, { redirect: 'manual' }).catch((e) => ({ error: e }))
  if (probe.error || probe.status !== 200) {
    throw new Error(`dev server not reachable at ${BASE_URL}: ${probe.error ?? probe.status}`)
  }
  log(`dev server probe: HTTP ${probe.status}`)

  for (const [name, url] of Object.entries({ user: USER_API, agent: AGENT_API, resource: RESOURCE_API })) {
    const health = await fetch(`${url}/health`).catch((e) => ({ error: e }))
    log(`backend ${name} ${url}/health -> ${health.error ? `ERROR ${health.error}` : health.status}`)
    if (health.error || health.status !== 200) {
      throw new Error(`${name} API is not healthy at ${url}`)
    }
  }

  const { module: pw } = loadPlaywright()
  const req = createRequire(import.meta.url)
  const pwVersion = req(path.join(REPO_ROOT, 'tests', 'e2e', 'node_modules', 'playwright', 'package.json')).version
  log(`playwright : v${pwVersion}`)

  const browser = await pw.chromium.launch({ headless: true })
  results.browser = { name: 'chromium', version: browser.version() }
  log(`browser    : chromium ${browser.version()} (headless)`)

  const shared = { env }
  for (const spec of CASES) {
    await runCase(browser, spec, shared)
  }
  await browser.close()

  results.duration_ms = Date.now() - startedAt
  const uiSummary = results.ui.reduce((acc, c) => {
    acc[c.status] = (acc[c.status] ?? 0) + 1
    return acc
  }, {})

  writeOutputs()
  log('\n' + '='.repeat(78))
  log(`UI      : ${JSON.stringify(uiSummary)}`)
  log(`LLM gen : real_llm=${results.generation.real_llm} resources=${results.generation.resources.length}`)
  log(`page errors    : ${results.page_errors.length}`)
  log(`console errors : ${results.console_errors.length}`)
  log(`screenshots    : ${results.screenshots.length}`)
  log('='.repeat(78))

  const failed = (uiSummary.failed ?? 0) > 0 || !results.generation.real_llm
  if (failed) process.exitCode = 1
}

function writeOutputs() {
  fs.mkdirSync(OUT_DIR, { recursive: true })
  fs.writeFileSync(path.join(OUT_DIR, 'results.json'), `${JSON.stringify(results, null, 2)}\n`, 'utf8')
  fs.writeFileSync(path.join(OUT_DIR, 'run.log'), `${LOG.join('\n')}\n`, 'utf8')
}

main().catch((error) => {
  log(`\n[FATAL] ${error?.stack ?? error}`)
  try {
    writeOutputs()
  } catch {
    /* ignore */
  }
  process.exitCode = 1
})
