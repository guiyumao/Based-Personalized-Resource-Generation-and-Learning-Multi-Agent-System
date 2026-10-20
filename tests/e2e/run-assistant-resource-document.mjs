/** Isolated learner -> real Worker generation -> resource preview -> DOCX download. */
import fs from 'node:fs'
import path from 'node:path'
import { randomUUID } from 'node:crypto'
import { BASE_URL, DESKTOP, REPO_ROOT, ensureDirs, loadPlaywright, shot } from './lib/env.mjs'

function assert(condition, message) {
  if (!condition) throw new Error(message)
  process.stdout.write(`[ok] ${message}\n`)
}

const userUrl = process.env.E2E_USER_URL || 'http://127.0.0.1:8001'
const agentUrl = process.env.E2E_AGENT_URL || 'http://127.0.0.1:8002'
const combined = process.env.E2E_COMBINED === '1'
const withPlan = process.env.E2E_WITH_PLAN === '1'
const { module: pw } = loadPlaywright()
const browser = await pw.chromium.launch({ headless: true })
const context = await browser.newContext({ viewport: DESKTOP, acceptDownloads: true })
const page = await context.newPage()
const errors = []
page.on('pageerror', (error) => errors.push(String(error)))

try {
  ensureDirs()
  const registered = await context.request.post(`${userUrl}/users/register`, { data: {
    username: `xiaozhi_e2e_${Date.now()}`, password: randomUUID(), role: 'student',
  } })
  assert(registered.status() === 201, 'isolated learner registered through the real authentication API')
  const auth = await registered.json()
  const headers = { Authorization: `Bearer ${auth.access_token}` }
  await page.addInitScript((payload) => localStorage.setItem('learning-system-auth', JSON.stringify(payload)), {
    token: auth.access_token, user: { userId: auth.user_id, username: auth.username, role: auth.role },
  })
  await page.goto(`${BASE_URL}/student/resources`, { waitUntil: 'domcontentloaded' })
  await page.getByRole('button', { name: '打开可拖动的 AI 学习助手' }).click()
  const assistant = page.locator('.assistant-pet-panel')
  await assistant.getByRole('button', { name: '生成学习课件', exact: true }).click()
  const uploadResponse = page.waitForResponse((response) => response.url().endsWith('/assistant/attachments') && response.request().method() === 'POST')
  await assistant.locator('input[type="file"]').setInputFiles({
    name: 'TCP-reference.txt', mimeType: 'text/plain',
    buffer: Buffer.from('课堂案例编号 XZ-TCP-042：发送端依次发送序号41、42、43的数据段，42在传输中丢失。接收端缓存43，等待重传42后按序交付。这个简化案例用于理解序号、确认和重传。', 'utf8'),
  })
  assert((await uploadResponse).status() === 201, 'private reference document uploaded')
  if (combined) await assistant.locator('.pet-selected-action button').click()
  await assistant.locator('textarea').fill(combined
    ? `生成 TCP 协议课件和三道练习题${withPlan ? '，并制定三天复习计划' : ''}，依据附件中的三段数据案例，把案例编号 XZ-TCP-042 放在例题标题中。`
    : '依据附件中的三段数据案例生成 TCP 可靠传输复习课件，把案例编号 XZ-TCP-042 放在例题标题中，讲解序号、确认和重传机制。')
  const taskResponse = page.waitForResponse((response) => response.url().endsWith('/assistant/chat') && response.request().method() === 'POST')
  await assistant.getByRole('button', { name: '发送', exact: true }).click()
  const accepted = await taskResponse
  assert(accepted.status() === 200, 'real courseware task was accepted')
  const taskId = (await accepted.json()).task.id
  const resourceCard = assistant.locator('.pet-result-cards button').filter({ hasText: '查看资源' }).first()
  try {
    await resourceCard.waitFor({ state: 'visible', timeout: 240000 })
  } catch {
    const response = await context.request.get(`${agentUrl}/assistant/tasks/${taskId}`, { headers })
    const task = await response.json()
    throw new Error(`Courseware did not finish: ${task.status} ${task.result?.content || ''}`)
  }
  const completed = await context.request.get(`${agentUrl}/assistant/tasks/${taskId}`, { headers })
  const completedTask = await completed.json()
  assert(completedTask.result.evidence.learning_context_used === false, 'default privacy preference keeps historical learner data out of generation')
  assert(completedTask.agent_executions.some((execution) => execution.agent_code === 'learner_profiling_agent' && execution.status === 'SKIPPED'), 'execution trace records skipped profile loading')
  assert(completedTask.result.sources.some((source) => source.title === 'TCP-reference.txt'), 'task returns the actual uploaded file as a source')
  if (combined) {
    assert(completedTask.task_type === 'combined' && completedTask.result.exercise_set?.exercises.length === 3, 'combined task saved three real exercises')
    if (withPlan) assert(completedTask.result.path_draft?.stages.length > 0, 'requested plan is generated as a draft')
    else assert(!completedTask.result.path_draft && !completedTask.result.cards.some((card) => card.type.startsWith('plan')), 'combined task creates only the requested resource and exercises')
  }
  await resourceCard.click()
  const preview = page.getByTestId('generated-resource-content')
  await preview.waitFor({ state: 'visible', timeout: 20000 })
  await preview.getByRole('heading').first().waitFor({ state: 'visible', timeout: 20000 })
  assert((await preview.innerText()).length > 300, 'stored model-generated courseware is readable in the resource module')
  assert((await preview.innerText()).includes('XZ-TCP-042'), 'real model used the uploaded classroom example')
  assert(!(await assistant.isVisible()), 'assistant collapses when opening the generated resource')
  const downloadButton = page.getByRole('button', { name: '下载 Word 文档', exact: true })
  await downloadButton.scrollIntoViewIfNeeded()
  const downloadEvent = page.waitForEvent('download')
  await downloadButton.click()
  const download = await downloadEvent
  assert(download.suggestedFilename().endsWith('.docx'), 'browser received an actual Word document download')
  const output = path.join(REPO_ROOT, 'artifacts', 'global-testing', 'assistant-generated-courseware.docx')
  await download.saveAs(output)
  const bytes = fs.readFileSync(output)
  assert(bytes.length > 1000 && bytes.subarray(0, 2).toString() === 'PK', 'download contains real DOCX package bytes')
  process.stdout.write(`screenshot=${await shot(page, 'assistant-resource-document')}\n`)
  if (combined) {
    await page.getByRole('button', { name: '关闭资源详情', exact: true }).click()
    await page.getByRole('button', { name: '打开可拖动的 AI 学习助手' }).click()
    await assistant.locator('.pet-result-cards button').filter({ hasText: '开始练习' }).click()
    await page.waitForURL('**/student/exercise', { timeout: 15000 })
    await page.getByText(/第 1 题.*共 3 题/).waitFor({ timeout: 15000 })
    if (await page.getByRole('radio').count()) await page.getByRole('radio').first().click()
    else await page.getByPlaceholder('输入你的答案...').fill('根据序号识别丢失的数据段，重传42，接收端按序交付。')
    const feedbackResponse = page.waitForResponse((response) => response.url().endsWith('/evaluation/practice/submit') && response.request().method() === 'POST', { timeout: 60000 })
    await page.getByRole('button', { name: '提交答案', exact: true }).click()
    const feedback = await feedbackResponse
    assert(feedback.status() === 200, 'generated exercise submitted to the real evaluation service')
    const graded = (await feedback.json()).data
    assert(typeof graded.is_correct === 'boolean' && typeof graded.mastery_after_update === 'number', 'evaluation returns a real result and updated mastery')
    const attemptPayload = feedback.request().postDataJSON()
    assert(typeof attemptPayload.client_request_id === 'string', 'browser sends a stable practice attempt key')
    const replay = await context.request.post(feedback.url(), { headers, data: attemptPayload })
    assert(replay.status() === 200 && JSON.stringify((await replay.json()).data) === JSON.stringify(graded), 'network retry returns the persisted grading result')
    const changed = await context.request.post(feedback.url(), { headers, data: { ...attemptPayload, user_answer: `${attemptPayload.user_answer}-changed` } })
    assert(changed.status() === 409, 'an attempt key cannot silently submit a different answer')
    const analysisResponse = await context.request.post(`${agentUrl}/assistant/chat`, { headers, data: {
      action: 'profile', message: '分析我的学情', conversation_id: completedTask.conversation_id, client_request_id: randomUUID(),
    } })
    const analysisId = (await analysisResponse.json()).task.id
    let profile
    for (let attempt = 0; attempt < 30; attempt += 1) {
      const response = await context.request.get(`${agentUrl}/assistant/tasks/${analysisId}`, { headers })
      profile = await response.json()
      if (profile.status === 'SUCCEEDED' || profile.status === 'FAILED') break
      await new Promise((resolve) => setTimeout(resolve, 1000))
    }
    assert(profile?.status === 'SUCCEEDED' && profile.result.evidence.answer_records === 1 && profile.result.evidence.profile_mastery_items >= 1, 'assistant analysis reads the submitted exercise and updated profile')
    process.stdout.write(`exercise_screenshot=${await shot(page, 'assistant-generated-exercise-submitted')}\n`)
    if (withPlan) {
      await page.getByRole('button', { name: '打开可拖动的 AI 学习助手' }).click()
      await assistant.locator('.pet-result-cards button').filter({ hasText: '确认保存学习路径' }).click()
      const confirmation = page.waitForResponse((response) => response.url().endsWith(`/assistant/tasks/${taskId}/confirm-path`) && response.request().method() === 'POST')
      await page.getByRole('button', { name: '确认保存', exact: true }).click()
      assert((await confirmation).status() === 200, 'combined task plan saved after user confirmation')
      const savedPath = await context.request.get(`${agentUrl}/paths/${auth.user_id}`, { headers })
      assert(savedPath.status() === 200 && (await savedPath.json()).stages.length > 0, 'combined task plan is visible in the existing learning-path service')
    }
  }
  assert(errors.length === 0, `no browser errors occurred (${errors.join('; ')})`)
  process.stdout.write(`task_id=${taskId}\nfinal_url=${page.url()}\ndocument=${output}\n`)
} finally {
  await context.close()
  await browser.close()
}
