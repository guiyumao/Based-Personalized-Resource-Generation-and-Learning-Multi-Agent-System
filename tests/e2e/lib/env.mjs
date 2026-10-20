/**
 * Shared helpers for the web-app Playwright E2E suite.
 *
 * Playwright is NOT installed in this repo. It is consumed from the existing
 * checkout at <repo>/workspace/node_modules/playwright (v1.61.1), either through
 * the junction tests/e2e/node_modules/playwright or through an explicit
 * createRequire() bound to <repo>/workspace/package.json. See README.md.
 */
import fs from 'node:fs'
import path from 'node:path'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

export const E2E_DIR = path.resolve(__dirname, '..')
export const REPO_ROOT = path.resolve(E2E_DIR, '..', '..')
export const ARTIFACT_DIR = path.join(REPO_ROOT, 'artifacts', 'global-testing')
export const SHOT_DIR = path.join(ARTIFACT_DIR, 'e2e', 'screenshots')
export const TRACE_DIR = path.join(ARTIFACT_DIR, 'e2e', 'traces')

export const BASE_URL = process.env.E2E_BASE_URL || 'http://127.0.0.1:5175'
export const DESKTOP = { width: 1440, height: 900 }
export const MOBILE = { width: 390, height: 844 }

export function ensureDirs() {
  for (const dir of [ARTIFACT_DIR, SHOT_DIR, TRACE_DIR]) {
    fs.mkdirSync(dir, { recursive: true })
  }
}

/** Minimal .env parser (no dependency on dotenv). */
export function parseDotEnv(file) {
  const out = {}
  if (!fs.existsSync(file)) return out
  for (const raw of fs.readFileSync(file, 'utf8').split(/\r?\n/)) {
    const line = raw.trim()
    if (!line || line.startsWith('#')) continue
    const eq = line.indexOf('=')
    if (eq === -1) continue
    let key = line.slice(0, eq).trim()
    if (key.startsWith('export ')) key = key.slice(7).trim()
    let value = line.slice(eq + 1).trim()
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1)
    }
    out[key] = value
  }
  return out
}

/** Resolve the `playwright` CJS module without installing anything. */
export function loadPlaywright() {
  // 1) junction at tests/e2e/node_modules/playwright (preferred)
  try {
    const local = createRequire(path.join(E2E_DIR, 'noop.js'))
    return { module: local('playwright'), how: 'tests/e2e/node_modules/playwright (junction -> workspace/node_modules/playwright)' }
  } catch {
    /* fall through */
  }
  // 2) explicit absolute resolution against the existing workspace install
  const workspaceReq = createRequire(path.join(REPO_ROOT, 'workspace', 'package.json'))
  return {
    module: workspaceReq('playwright'),
    how: 'createRequire(<repo>/workspace/package.json)("playwright")',
  }
}

/** Read the vendored/local axe-core bundle. */
export function loadAxeSource() {
  const candidates = [
    path.join(E2E_DIR, 'node_modules', 'axe-core', 'axe.min.js'),
    path.join(REPO_ROOT, 'node_modules', 'axe-core', 'axe.min.js'),
  ]
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      return { source: fs.readFileSync(candidate, 'utf8'), from: candidate }
    }
  }
  return { source: null, from: null }
}

export function uniqueSuffix() {
  return `${Date.now()}${Math.floor(Math.random() * 900 + 100)}`
}

export function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

/** Best-effort screenshot that never throws into the case result. */
export async function shot(page, name) {
  const file = path.join(SHOT_DIR, `${name}.png`)
  try {
    await page.screenshot({ path: file, fullPage: false })
    return path.relative(REPO_ROOT, file).replace(/\\/g, '/')
  } catch {
    return null
  }
}

export function relFromRepo(abs) {
  if (!abs) return null
  return path.relative(REPO_ROOT, abs).replace(/\\/g, '/')
}

export function truncate(text, max = 400) {
  if (text == null) return ''
  const value = String(text).replace(/\s+/g, ' ').trim()
  return value.length > max ? `${value.slice(0, max)}…` : value
}
