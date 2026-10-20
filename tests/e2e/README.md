# web-app E2E suite (Playwright, live dev server + live backends)

Real-browser end-to-end coverage for the Vue 3 SPA in `web-app/` running against
`http://127.0.0.1:5175` with the six live backend services on 8001–8006.

## 1. Prerequisites

| Requirement | Value used in this environment |
| --- | --- |
| Node.js | v24.17.0 (`npm 10.9.2`) |
| Frontend dev server | `http://127.0.0.1:5175` (Vite, `web-app/vite.config.ts` → `FRONTEND_PORT \|\| 5175`) |
| Backends | `127.0.0.1:8001` … `127.0.0.1:8006` (must already be running) |
| Playwright | **not installed here** — consumed from the existing `workspace/node_modules/playwright` (v1.61.1) |
| Browsers | Chromium only (`%USERPROFILE%\AppData\Local\ms-playwright\chromium-1228`) |
| axe-core | installed locally at `tests/e2e/node_modules/axe-core` (v4.x) |

### Start the dev server (if it is not already up)

```powershell
cd web-app
npm install            # already satisfied: "up to date"
npx vite --host 127.0.0.1 --port 5175 --strictPort
```

Verify it really serves the app (not just a port that answers):

```powershell
Invoke-WebRequest http://127.0.0.1:5175 -UseBasicParsing      # → 200 + <div id="app">
Invoke-WebRequest http://127.0.0.1:5175/src/main.ts -UseBasicParsing   # → 200 + Vue entry
```

## 2. How Playwright is resolved (no reinstall)

`tests/e2e/node_modules/playwright` and `tests/e2e/node_modules/playwright-core`
are **directory junctions** into the existing checkout:

```powershell
$src = "<repo>\workspace\node_modules"
$dst = "<repo>\tests\e2e\node_modules"
New-Item -ItemType Junction -Path "$dst\playwright"      -Target "$src\playwright"
New-Item -ItemType Junction -Path "$dst\playwright-core" -Target "$src\playwright-core"
```

`lib/env.mjs → loadPlaywright()` tries the junction first and falls back to
`createRequire(<repo>/workspace/package.json)('playwright')`, so the suite keeps
working even if the junctions are removed. Nothing from the npm registry is
needed for Playwright.

## 3. Run

```powershell
cd tests\e2e
node run-all.mjs
```

Optional overrides:

```powershell
$env:E2E_BASE_URL = "http://127.0.0.1:5175"
node run-all.mjs
```

The suite is a plain Node.js script (no test-runner install, no TypeScript).
`npx playwright test` was **not** used: there is no `@playwright/test` in
`tests/e2e` and the existing `workspace` checkout only exposes the
`playwright` library package, so the library API is the supported path here.

## 4. What it does

* Reads `DEFAULT_ADMIN_USERNAME` / `DEFAULT_ADMIN_PASSWORD` from the **repo root
  `.env`** at runtime. The password is never printed, logged or written to an
  artifact.
* Registers throwaway accounts through the real UI:
  `e2e_<timestamp><rand>` (student) and `e2et_<timestamp><rand>` (teacher).
* Uses viewport `1440x900` for all desktop cases and `390x844` for the mobile case.
* Captures `page.on('pageerror')` and console `error` messages for every case; an
  uncaught page error fails the case.
* Writes screenshots on every case (and a `*-FAILURE` screenshot plus a trace on
  failure).

### Case list

| id | what it proves |
| --- | --- |
| `C1-login-success-admin` | admin login → `/admin`, token persisted, username shown |
| `C2-login-failure` | wrong password → visible error, **no** `learning-system-auth` in localStorage |
| `C3-student-register` | brand-new student registers through `/register` |
| `C4-student-dashboard` | dashboard renders and greets that student |
| `C5-student-qa` | ask a question; LLM slowness is recorded, never blocks the suite |
| `C6-student-resources` | resource list/search page renders |
| `C7-student-learning-path` | learning path page renders (timeline *or* empty state) |
| `C8-admin-flow` | admin console loads real data |
| `C9-teacher-flow` | teacher registers and `/teacher/overview` renders |
| `C10-api-error-list` | forced HTTP 500 on `/knowledge-base` → in-page error banner, no white screen |
| `C11-api-error-detail` | forced HTTP 500 on `/users/:id/profile/dashboard` → inline alert + retry |
| `C12-empty-data` | brand-new user sees defined empty states (mistakes / report / exercise) |
| `C13-session-recovery` | survives `page.reload()`; token + user intact; protected route reachable |
| `C15-mobile-login-390x844` | login layout at 390×844: no horizontal overflow |
| axe login / dashboard / resources | axe-core WCAG 2 A/AA + best-practice audit |

`page.route()` is used with CORS headers (including `OPTIONS` preflight handling)
so the injected failures surface as real HTTP 500 responses, not as CORS noise.

### Diagnostic helper

```powershell
node axe-detail.mjs
```

Re-runs the axe audit and prints each violation's **DOM target**, outer HTML and
the failure summary (e.g. the measured contrast ratio), which is what you need to
map a violation back to a source file.

## 5. Outputs

| Path | Content |
| --- | --- |
| `artifacts/global-testing/e2e-results.json` | machine-readable results |
| `artifacts/global-testing/_r4-e2e-log.txt` | raw console log of the run |
| `artifacts/global-testing/e2e/screenshots/*.png` | per-case screenshots (incl. failure shots) |
| `artifacts/global-testing/e2e/traces/*.zip` | Playwright traces, failures only |

## 6. Notes / limitations

* **Firefox and WebKit are not available**: `%USERPROFILE%\AppData\Local\ms-playwright`
  contains only `chromium-1217`, `chromium-1228`, `chromium_headless_shell-*`,
  `ffmpeg` and `winldd`. Downloading them is out of scope (external network is
  off-limits in this environment).
* Case `C5` deliberately never fails on a slow/absent LLM answer — the observed
  condition is recorded under `observed_conditions` in the JSON result.

## 7. Structured-resource suite (mind_map / code_case / video_script)

```powershell
node tests/e2e/run-structured-resources.mjs
```

A second, independent suite covers the three structured resource types end to end.
It is separate from `run-all.mjs` because it **generates real resources through the
live LLM API**, so generation alone takes tens of seconds.

### What it does

1. Registers a throwaway student through the UI (`e2es_<timestamp><rand>`).
2. Calls the **live** agent API `POST /resources/generate` three times with that
   student's token, recording the real `http_status`, latency, resource id, audit
   status and validation verdict. This is reported as the `generation` section and
   is the only place a "the model generated it" claim is made.
3. Drives Chromium against `/student/resources` and asserts, per type: the card's
   type label, the panel's type name, the structured body (nodes / code block /
   chapters), the validation verdict, and a read-back of the payload from
   `GET /resources/{id}`.
4. Covers injected states — an empty payload, HTTP 409/422/503 on the detail API,
   HTTP 503 on the list API, and an unknown resource type — each labelled
   `injected: true` in `results.json` so it can never be confused with live data.
5. Reloads the page and proves the structured content is still readable.

### Outputs

| Path | Content |
| --- | --- |
| `artifacts/upstream-integration/e2e-structured/results.json` | `generation`, `ui`, `injected_states`, `network`, console/page errors |
| `artifacts/upstream-integration/e2e-structured/run.log` | raw console log |
| `artifacts/upstream-integration/e2e-structured/screenshots/*.png` | one per case (+ `*-FAILURE`) |

### Assertion hooks used

The resource library card exposes `data-resource-id`, and the structured panel
exposes `data-testid="structured-resource-panel"` / `"validation-block"` /
`"structured-empty"` / `"structured-detail-error"` / `"unknown-resource-type"`,
so the suite targets stable anchors instead of visible text.

### Limitation

The suite exits non-zero when `generation.real_llm` is false, so a run that only
proved "the page renders" can never be mistaken for a successful model run.

