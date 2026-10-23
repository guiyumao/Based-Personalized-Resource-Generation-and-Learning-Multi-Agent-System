/**
 * Mock-only browser check for the learning-path background generation fix.
 *
 * Verifies, with every backend call intercepted (zero real model calls, zero
 * database writes):
 *   A. starting a generation, navigating to another SPA route, and letting the
 *      server task finish still writes the courseware/exercise artifacts;
 *   B. a full page reload mid-generation resumes the persisted task and renders
 *      the finished plan instead of losing it.
 *
 * Usage: node run-path-background-resume.mjs [artifactDir]
 */
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { loadPlaywright } from './lib/env.mjs'

const outDir = path.resolve(process.argv[2] || path.join('artifacts', 'path-background-20261022'))
fs.mkdirSync(outDir, { recursive: true })

const BASE = 'http://127.0.0.1:5175'
const AUTH = { token: 'e2e-background-token', user: { userId: 6, username: 'student', role: 'student' } }
const TASK_ID = 9001

const coordinationResult = {
  status: 'success',
  selected_agents: ['path_planning_agent', 'resource_generation_agent', 'exercise_generation_agent'],
  route_reason: 'e2e',
  outputs: {
    path_planning_agent: {
      status: 'completed',
      learning_path: {
        user_id: 6,
        subject: '计算机网络',
        knowledge_point: '存储系统原理',
        overview: '理解存储层次与访问路径',
        estimated_days: 3,
        knowledge_scope: 'public',
        knowledge_versions: [{ id: 1, version: 1 }],
        stages: [
          {
            stage_id: 'stage-1',
            title: '基础概念',
            description: '存储层次',
            tasks: [
              {
                task_id: 'task-1',
                title: '阅读存储层次课件',
                task_type: 'courseware',
                knowledge_point: '存储系统原理',
                objective: '理解存储层次',
                estimated_minutes: 30,
                difficulty: 'easy',
                completed: false,
                status: 'pending',
              },
            ],
          },
        ],
      },
    },
    resource_generation_agent: {
      status: 'completed',
      resource: {
        user_id: 6,
        knowledge_point: '存储系统原理',
        resource_type: 'courseware',
        resource_style: 'interactive',
        content: '# 存储系统原理\n\n存储层次从寄存器到磁盘依次变慢。',
        variants: [
          {
            variant_id: 'default',
            title: '默认版本',
            summary: '系统梳理存储层次',
            resource_style: 'interactive',
            content: '# 存储系统原理\n\n存储层次从寄存器到磁盘依次变慢。',
            is_recommended: true,
          },
        ],
      },
    },
    exercise_generation_agent: {
      status: 'completed',
      exercise_set: { exercise_id: 1, questions: [] },
    },
  },
}

function json(status, payload) {
  return { status, contentType: 'application/json', body: JSON.stringify(payload) }
}

async function installMocks(context, state) {
  await context.route(
    (url) => url.href.startsWith('http://127.0.0.1:800'),
    async (route) => {
      const request = route.request()
      const { pathname } = new URL(request.url())
      if (pathname === '/users/me') return route.fulfill(json(200, { id: 6, username: 'student', role: 'student' }))
      if (pathname === '/paths/preflight') {
        return route.fulfill(json(200, { ready: true, message: '知识库已就绪', reason: 'READY' }))
      }
      if (pathname === `/paths/history/${AUTH.user.userId}`) return route.fulfill(json(200, { items: [] }))
      if (pathname === `/paths/${AUTH.user.userId}`) return route.fulfill(json(404, { detail: '暂无学习路径' }))
      if (pathname === '/agents/coordinate/async' && request.method() === 'POST') {
        state.enqueued += 1
        return route.fulfill(json(200, { task_id: TASK_ID, status: 'QUEUED' }))
      }
      if (pathname === `/agents/coordinate/tasks/${TASK_ID}`) {
        state.polls += 1
        return route.fulfill(
          state.polls >= 3
            ? json(200, { id: TASK_ID, status: 'SUCCEEDED', result: coordinationResult })
            : json(200, { id: TASK_ID, status: 'RUNNING' }),
        )
      }
      if (pathname === '/knowledge-base/subjects') return route.fulfill(json(200, { subjects: [] }))
      if (pathname === '/evaluation/overview/me') {
        return route.fulfill(json(200, {
          data: {
            active_plans: [],
            due_cards: 0,
            suggestions: [],
            recent_resources: [],
            weak_points: [],
            analytics: {
              daily: [],
              summary: { study_seconds: null, current_streak_days: 0 },
              week_comparison: { this_week_study_seconds: null, previous_week_study_seconds: null },
            },
          },
        }))
      }
      return route.fulfill(json(200, { data: [] }))
    },
  )
}

async function newPage(browser, state) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
  await installMocks(context, state)
  await context.addInitScript((auth) => {
    localStorage.setItem('learning-system-auth', JSON.stringify(auth))
    sessionStorage.setItem('learning-system-tab-auth', JSON.stringify(auth))
  }, AUTH)
  const page = await context.newPage()
  const pageErrors = []
  page.on('pageerror', (error) => pageErrors.push(error.message))
  return { context, page, pageErrors }
}

const { chromium } = loadPlaywright().module
const browser = await chromium.launch({ headless: true })
const report = { mockedBackends: true, realModelCalls: 0, databaseWrites: 0, cases: {} }

try {
  // Case A: finish while another route is open.
  {
    const state = { enqueued: 0, polls: 0 }
    const { context, page, pageErrors } = await newPage(browser, state)
    try {
      await page.goto(`${BASE}/student/learning-path`)
      await page.locator('input[aria-label="输入学科"]').fill('计算机网络')
      await page.locator('input[placeholder="知识点 / 主题"]').fill('存储系统原理')
      await page.getByRole('button', { name: '生成学习路径' }).click()
      await page.locator('.path-background-hint').waitFor({ timeout: 15000 })
      assert.equal(state.enqueued, 1)

      await page.locator('.app-sidebar .nav-item').filter({ hasText: '学习概览' }).first().click()
      await page.waitForURL('**/student/dashboard', { timeout: 15000 })
      await page.waitForTimeout(6000)

      const stored = await page.evaluate(() => ({
        courseware: sessionStorage.getItem('student-workspace-courseware'),
        exercise: sessionStorage.getItem('student-workspace-exercise-set'),
        pendingKeys: Object.keys(localStorage).filter((key) => key.startsWith('student-path-generation-pending')),
      }))
      assert.ok(stored.courseware?.includes('存储层次从寄存器到磁盘依次变慢'), 'courseware artifact missing')
      assert.ok(stored.exercise?.includes('exerciseSet'), 'exercise artifact missing')
      assert.deepEqual(stored.pendingKeys, [])

      await page.goBack()
      await page.locator('.timeline .stage-item').first().waitFor({ timeout: 15000 })
      await page.screenshot({ path: path.join(outDir, 'A-returned-path.png') })
      assert.deepEqual(pageErrors, [])
      report.cases.A = { passed: true, polls: state.polls, pageErrors }
    } finally {
      await context.close()
    }
  }

  // Case B: reload mid-generation, then resume and render the finished plan.
  {
    const state = { enqueued: 0, polls: 0 }
    const { context, page, pageErrors } = await newPage(browser, state)
    try {
      await page.goto(`${BASE}/student/learning-path`)
      await page.locator('input[aria-label="输入学科"]').fill('计算机网络')
      await page.locator('input[placeholder="知识点 / 主题"]').fill('存储系统原理')
      await page.getByRole('button', { name: '生成学习路径' }).click()
      await page.locator('.path-background-hint').waitFor({ timeout: 15000 })
      const pendingBeforeReload = await page.evaluate(() =>
        Object.keys(localStorage).filter((key) => key.startsWith('student-path-generation-pending')),
      )
      assert.equal(pendingBeforeReload.length, 1)

      await page.reload()
      await page.locator('.path-background-hint').waitFor({ timeout: 15000 })
      await page.locator('.timeline .stage-item').first().waitFor({ timeout: 20000 })
      await page.waitForFunction(
        () => !Object.keys(localStorage).some((key) => key.startsWith('student-path-generation-pending')),
        undefined,
        { timeout: 20000 },
      )
      assert.equal(state.enqueued, 1, 'reload must not enqueue a second task')
      await page.screenshot({ path: path.join(outDir, 'B-resumed-path.png') })
      assert.deepEqual(pageErrors, [])
      report.cases.B = { passed: true, enqueued: state.enqueued, polls: state.polls, pageErrors }
    } finally {
      await context.close()
    }
  }
} finally {
  await browser.close()
}

fs.writeFileSync(path.join(outDir, 'result.json'), JSON.stringify(report, null, 2))
console.log(JSON.stringify(report))
