/** Real browser + HTTP acceptance. Run only via admin_navigation_runtime.py. */
import fs from 'node:fs'
import path from 'node:path'
import assert from 'node:assert/strict'
import { loadPlaywright } from './lib/env.mjs'
const { module: pw } = loadPlaywright()
const origin = process.env.E2E_BASE_URL
const api = process.env.ADMIN_NAV_API
const dir = process.env.ADMIN_NAV_ARTIFACTS
assert.ok(dir && api && process.env.NO_COST_TEST === '1')
const browser = await pw.chromium.launch({ headless: true })
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
await context.route('**/*', route => {
  const url = new URL(route.request().url())
  return ['127.0.0.1', 'localhost'].includes(url.hostname) ? route.continue() : route.abort()
})
const page = await context.newPage()
page.setDefaultTimeout(15000)
const report = { passed: false, mocked: false, isolated: true, menus: [], steps: [], pageErrors: [], apiErrors: [] }
let expectedFault = false
report.injectedFaults = []
page.on('pageerror', error => report.pageErrors.push(String(error)))
page.on('response', res => { if (res.url().startsWith(api) && res.status() >= 400) (expectedFault ? report.injectedFaults : report.apiErrors).push({ url: res.url().split(api)[1], status: res.status() }) })
const shot = name => page.screenshot({ path: path.join(dir, name + '.png') })
const check = async (name, action) => { await action(); report.steps.push(name) }
const apiLogin = async role => {
  const response = await context.request.post(`${api}/user/users/login`, { data: { username: 'navigation-' + role, password: process.env.ADMIN_NAV_PASSWORD } })
  assert.equal(response.status(), 200)
  return response.json()
}
try {
  await page.goto(origin + '/admin/users')
  await page.waitForURL('**/login')
  report.steps.push('anonymous_direct_route_denied')
  await page.getByRole('textbox', { name: '账号' }).count() // Inspect accessible tree before selectors.
  fs.writeFileSync(path.join(dir, 'login-aria.yml'), await page.locator('body').ariaSnapshot())
  await page.locator('input[autocomplete="username"]').fill('navigation-admin')
  await page.locator('input[autocomplete="current-password"]').fill(process.env.ADMIN_NAV_PASSWORD)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await page.waitForURL('**/admin')
  await page.locator('.admin-stat-grid strong').first().getByText('16', { exact: true }).waitFor()
  fs.writeFileSync(path.join(dir, 'admin-aria.yml'), await page.locator('body').ariaSnapshot())
  report.steps.push('real_login_and_persisted_dashboard_16_users')
  const groups = ['管理概览', '用户与权限', '学科与知识库', '教学与资源', 'AI 与任务管理', '系统运维']
  for (const group of groups) {
    const button = page.getByRole('button', { name: group, exact: true })
    if (await button.getAttribute('aria-expanded') !== 'true') await button.click()
    assert.equal(await button.getAttribute('aria-expanded'), 'true')
  }
  await shot('navigation-expanded')
  const menus = [
    ['数据看板', '/admin', '/system/system/dashboard'],
    ['用户管理', '/admin/users', '/system/system/users'],
    ['学科管理', '/admin/subjects', '/system/system/subjects'],
    ['学科规划与知识点', '/admin/knowledge/construction', '/agent/knowledge-base/construction/subjects'],
    ['知识库管理', '/admin/knowledge', '/agent/knowledge-base/status'],
    ['审核与发布', '/admin/knowledge/review', '/agent/knowledge-base/candidates'],
    ['自动维护配置', '/admin/knowledge/maintenance', '/agent/knowledge-base/maintenance-plans'],
    ['学习资源管理', '/admin/resources', '/resource/resources/managed'],
    ['知识建设与采集任务', '/admin/tasks', '/agent/knowledge-base/tasks'],
    ['操作日志', '/admin/logs', '/system/system/logs'],
    ['系统配置', '/admin/settings', '/system/system/configs'],
  ]
  for (const [label, route, endpoint] of menus) {
    console.log('Menu:', route)
    // First entry is already selected; explicitly refresh it for its request.
    const response = page.waitForResponse(res => res.url().includes(api + endpoint) && res.request().method() === 'GET')
    response.catch(() => {}) // Handle failure in the enclosing assertion/catch.
    if (new URL(page.url()).pathname === route) await page.reload({ waitUntil: 'domcontentloaded' })
    else {
      const item = page.locator('.sidebar-nav').getByRole('button', { name: label, exact: true, includeHidden: true })
      if (!await item.isVisible()) {
        const group = item.locator('xpath=ancestor::section').locator('.group-toggle')
        await group.click()
      }
      await item.click()
    }
    assert.equal((await response).status(), 200, endpoint)
    await page.getByRole('heading', { name: label, exact: true, level: 1 }).waitFor()
    assert.equal(new URL(page.url()).pathname, route)
    assert.equal(await page.locator('.sidebar-nav [aria-current="page"]').textContent().then(x => x.trim()), label)
    report.menus.push({ label, route, api: endpoint, navigation: 'PASS', load: 'PASS', apiStatus: 200 })
  }
  await check('history_refresh_and_auto_expand', async () => {
    await page.goBack(); await page.waitForURL('**/admin/logs')
    await page.goForward(); await page.waitForURL('**/admin/settings')
    await page.reload({ waitUntil: 'domcontentloaded' })
    await page.getByRole('heading', { name: '系统配置', level: 1 }).waitFor()
    assert.equal(await page.getByRole('button', { name: '系统运维', exact: true }).getAttribute('aria-expanded'), 'true')
  })
  await check('keyboard_group_toggle', async () => {
    const group = page.getByRole('button', { name: '学科与知识库', exact: true })
    await group.focus(); await page.keyboard.press('Space')
    assert.equal(await group.getAttribute('aria-expanded'), 'true')
    await page.keyboard.press('Enter'); assert.equal(await group.getAttribute('aria-expanded'), 'false')
  })
  await shot('submenu-active')
  await page.getByRole('button', { name: '学科与知识库', exact: true }).click()
  await shot('group-expanded')
  await page.getByRole('button', { name: '收起导航', exact: true }).click()
  await page.waitForFunction(() => document.querySelector('.app-sidebar').getBoundingClientRect().width === 80)
  assert.equal(await page.locator('.app-sidebar').evaluate(el => el.getBoundingClientRect().width), 80)
  await shot('navigation-collapsed')
  await page.getByRole('button', { name: '学科与知识库', exact: true }).click()
  await page.waitForFunction(() => document.querySelector('.app-sidebar').getBoundingClientRect().width === 256)
  await check('collapsed_group_opens_navigation', async () => assert.equal(await page.locator('.app-sidebar').evaluate(el => el.getBoundingClientRect().width), 256))
  for (const width of [1440, 1280, 768, 390]) {
    await page.setViewportSize({ width, height: 900 })
    await page.goto(origin + '/admin/knowledge/maintenance')
    await page.getByRole('heading', { name: '自动维护配置', level: 1 }).waitFor()
    if (width <= 900) {
      await page.getByRole('button', { name: '打开导航' }).click()
      await page.locator('.app-sidebar.mobile-open').waitFor()
      await page.waitForFunction(() => Math.abs(document.querySelector('.app-sidebar').getBoundingClientRect().x) < 1)
      const drawer = await page.locator('.app-sidebar').boundingBox()
      assert.ok(drawer.x >= -1 && drawer.x < 1)
      assert.ok(await page.locator('.navigation-backdrop').isVisible())
      if (width === 390) await shot('mobile-drawer')
      await page.keyboard.press('Escape')
      assert.equal(await page.locator('.navigation-backdrop').count(), 0)
      await page.getByRole('button', { name: '打开导航' }).click()
      await page.locator('.navigation-backdrop').click({ position: { x: width - 10, y: 200 } })
      assert.equal(await page.locator('.navigation-backdrop').count(), 0)
      await page.getByRole('button', { name: '打开导航' }).click()
      await page.locator('.sidebar-nav').getByRole('button', { name: '审核与发布', exact: true }).click()
      await page.waitForURL('**/admin/knowledge/review')
      assert.equal(await page.locator('.navigation-backdrop').count(), 0)
    }
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'horizontal overflow ' + width)
    for (const menu of report.menus) {
      await page.goto(origin + menu.route)
      await page.getByRole('heading', { name: menu.label, exact: true, level: 1 }).waitFor()
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), menu.route + ' overflow at ' + width)
      menu.responsive ??= []
      menu.responsive.push(width)
    }
    report.steps.push(`responsive_${width}_PASS`)
  }
  await page.setViewportSize({ width: 1440, height: 1000 })
  await check('user_search_pagination_role_and_status_persistence', async () => {
    await page.goto(origin + '/admin/users')
    await page.locator('.admin-user-row').first().waitFor()
    assert.equal(await page.locator('.admin-user-row').count(), 10)
    await page.locator('.el-pagination .btn-next').click()
    await page.locator('.admin-user-row').filter({ hasText: 'navigation-admin' }).waitFor()
    await page.getByPlaceholder('搜索用户名或邮箱').fill('navigation-learner-00')
    await page.getByRole('button', { name: '查询', exact: true }).click()
    const row = page.locator('.admin-user-row').filter({ hasText: 'navigation-learner-00' })
    await row.waitFor()
    await row.getByRole('button', { name: '选择分配角色' }).click()
    await page.getByRole('button', { name: '分配角色', exact: true }).click()
    await page.getByText('角色分配成功', { exact: true }).waitFor()
    await row.getByRole('button', { name: '停用', exact: true }).click()
    await row.getByRole('button', { name: '启用', exact: true }).waitFor()
  })
  await check('subject_catalog_reload', async () => {
    await page.goto(origin + '/admin/subjects')
    await page.getByRole('heading', { name: '学科目录与资料归位' }).waitFor()
    await page.reload(); await page.getByRole('heading', { name: '学科目录与资料归位' }).waitFor()
  })
  await check('private_resource_preview_publish_archive', async () => {
    await page.goto(origin + '/admin/resources')
    await page.locator('.admin-user-row').filter({ hasText: '隔离验收资源' }).waitFor()
    await page.getByRole('button', { name: '预览', exact: true }).click()
    await page.locator('.result-box pre').getByText(/本内容仅用于隔离导航测试/).waitFor()
    await page.getByRole('button', { name: '发布', exact: true }).click()
    await page.getByText('资源状态已更新', { exact: true }).waitFor()
    await page.getByRole('button', { name: '归档', exact: true }).click()
    await page.locator('.admin-user-row').getByText(/archived/).waitFor()
  })
  await check('settings_write_readback', async () => {
    await page.goto(origin + '/admin/settings')
    await page.getByText('light', { exact: true }).waitFor()
    await page.locator('.el-form-item').filter({ hasText: '配置值' }).locator('input').fill('navigation-verified')
    await page.getByRole('button', { name: '更新配置', exact: true }).click()
    await page.getByText('navigation-verified', { exact: true }).waitFor()
    await page.reload(); await page.getByText('navigation-verified', { exact: true }).waitFor()
  })
  await check('construction_page_controls', async () => {
    await page.goto(origin + '/admin/knowledge/construction')
    await page.getByPlaceholder('例如：机器学习').waitFor()
    await page.getByRole('button', { name: '让 AI 规划课程大纲', exact: true }).waitFor()
  })
  await check('candidate_edit_submit_review', async () => {
    await page.goto(origin + '/admin/knowledge/review')
    const candidate = page.locator('[data-candidate-id]').first()
    await candidate.locator('textarea').fill('# 隔离审核候选\n\n导航拆分后仍可保存、提交和审核。此内容仅用于隔离测试。')
    await candidate.getByRole('button', { name: '保存', exact: true }).click()
    await page.getByText('候选内容已保存', { exact: true }).waitFor()
    await candidate.getByRole('button', { name: '提交审核', exact: true }).click()
    await candidate.getByRole('button', { name: '批准', exact: true }).click()
    await candidate.getByRole('button', { name: '发布并验证检索', exact: true }).waitFor()
    await shot('review-page')
  })
  await check('maintenance_create_pause_and_reload', async () => {
    await page.goto(origin + '/admin/knowledge/maintenance')
    await page.getByPlaceholder('计划名称', { exact: true }).fill('隔离巡检计划')
    await page.locator('input[type="datetime-local"]').fill('2099-01-01T10:00')
    await page.getByRole('button', { name: '创建计划', exact: true }).click()
    const plan = page.locator('.list-card').filter({ hasText: '隔离巡检计划' })
    await plan.getByRole('button', { name: '暂停', exact: true }).click()
    await plan.getByRole('button', { name: '启用', exact: true }).waitFor()
    await page.reload(); await plan.getByRole('button', { name: '启用', exact: true }).waitFor()
  })
  await check('durable_health_task_cancel_and_usage', async () => {
    await page.goto(origin + '/admin/tasks')
    await page.getByRole('button', { name: '排队巡检', exact: true }).click()
    const task = page.locator('.list-card').filter({ hasText: 'KNOWLEDGE_HEALTH_CHECK' }).first()
    await task.getByRole('button', { name: '取消', exact: true }).click()
    await task.getByText(/CANCELLED/).waitFor()
    await task.getByRole('button', { name: '用量记录', exact: true }).click()
    await page.getByText('调用与预算预留', { exact: true }).waitFor()
  })
  const admin = await apiLogin('admin')
  const endpoints = ['/system/system/dashboard', '/system/system/users', '/system/system/logs', '/system/system/configs', '/resource/resources/managed', '/agent/knowledge-base/construction/subjects', '/agent/knowledge-base/tasks', '/agent/knowledge-base/candidates', '/agent/knowledge-base/maintenance-plans', '/agent/knowledge-base/versions']
  report.permissions = []
  for (const role of ['anonymous', 'student', 'teacher', 'admin']) {
    const login = role === 'anonymous' ? null : role === 'admin' ? admin : await apiLogin(role)
    for (const endpoint of endpoints) {
      const res = await context.request.get(api + endpoint, { headers: login ? { Authorization: `Bearer ${login.access_token}` } : {} })
      const expected = role === 'anonymous' ? 401 : role === 'admin' ? 200 : 403
      assert.equal(res.status(), expected, role + ' ' + endpoint)
      report.permissions.push({ role, endpoint, status: res.status() })
    }
  }
  for (const role of ['student', 'teacher']) {
    const login = await apiLogin(role)
    // A forged cached administrator role must still be rejected by /users/me.
    await page.evaluate(login => localStorage.setItem('learning-system-auth', JSON.stringify({ token: login.access_token, user: { userId: login.user_id, username: login.username, role: 'admin' } })), login)
    await page.goto(origin + '/admin/users')
    await page.waitForURL(role === 'student' ? '**/student/dashboard' : '**/teacher/overview')
    assert.equal(await page.locator('.sidebar-nav').getByRole('button', { name: '用户管理', exact: true }).count(), 0)
    report.steps.push(role + '_forged_cache_denied_and_normal_navigation_preserved')
  }
  await page.evaluate(login => localStorage.setItem('learning-system-auth', JSON.stringify({ token: login.access_token, user: { userId: login.user_id, username: login.username, role: 'admin' } })), admin)
  await page.goto(origin + '/admin')
  await page.getByRole('button', { name: '退出登录', exact: true }).first().click()
  await page.waitForURL('**/login')
  await page.goBack(); await page.waitForURL('**/login')
  report.steps.push('logout_history_cannot_reopen_admin_data')
  assert.deepEqual(report.pageErrors, [])
  assert.deepEqual(report.apiErrors, [])
  // Explicit HTTP fault injection verifies UI error handling and fail-closed RBAC.
  expectedFault = true
  await page.evaluate(login => localStorage.setItem('learning-system-auth', JSON.stringify({ token: login.access_token, user: { userId: login.user_id, username: login.username, role: 'admin' } })), admin)
  await page.route(`${api}/system/system/users?**`, route => route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"isolated-fault"}' }))
  await page.goto(origin + '/admin/users')
  await page.getByText('用户列表获取失败', { exact: true }).waitFor()
  await page.unroute(`${api}/system/system/users?**`)
  await page.route(`${api}/user/users/me`, route => route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"isolated-fault"}' }))
  await page.goto(origin + '/admin/settings')
  await page.waitForURL('**/login?reason=permission-unavailable')
  assert.equal(await page.evaluate(() => localStorage.getItem('learning-system-auth')), null)
  report.steps.push('injected_503_user_feedback_and_permission_fail_closed')
  report.passed = true
} catch (error) {
  report.error = String(error)
  await shot('failure')
  fs.writeFileSync(path.join(dir, 'failure-aria.yml'), await page.locator('body').ariaSnapshot())
  process.exitCode = 1
} finally {
  fs.writeFileSync(path.join(dir, 'browser-report.json'), JSON.stringify(report, null, 2))
  await browser.close()
}
console.log(JSON.stringify({ passed: report.passed, menus: report.menus.length, steps: report.steps, error: report.error }))
