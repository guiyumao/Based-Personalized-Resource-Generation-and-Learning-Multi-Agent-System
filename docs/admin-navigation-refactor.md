# 管理员导航重构交付报告

日期：2026-10-20。基于现有 Vue 3 / Pinia / Vue Router / Element Plus 与 FastAPI 六服务增量实现。

## 根因与实际范围

原 `src/config/navigation.ts` 仅配置一个管理员菜单，`router.ts` 也仅声明 `/admin`。`AdminView.vue` 将用户、角色分配、学科、知识建设、语料索引、采集任务、候选审核、版本管理、维护计划、资源、配置和日志放在同一个长页面，进入页面便集中读取多个模块。侧边栏原先只将平铺菜单按文字分组，没有可展开的业务层级。

因此不是动态路由初始化遗漏，也不是现有管理员菜单被权限过滤。项目已有共用 AppLayout/AppSidebar/AppTopbar，可以扩展，无需重建后台。

当前权限为 student / teacher / admin 固定角色；没有独立的自定义角色、权限关系编辑 API。角色分配继续放在用户管理。没有为模型配置、平台 Worker 状态、统一费用账单或全平台预算编辑制造空页面。任务已有的用量与预算预留仍从真实接口读取，预留金额不代表实际账单。

## 菜单、页面、路由、API 与验收映射

以下页面均位于 `web-app/src/views/admin/`。每一行的菜单跳转、标题、路由高亮、主查询 HTTP 200 均在浏览器验证；每个页面均覆盖 1440 / 1280 / 768 / 390px，无文档横向溢出。管理页面路由全部限定 admin，进入前通过 `/users/me` 核实数据库中的当前角色。

| 一级分类 | 二级菜单 | 实际页面 | 路由 | 主要 API | 结果 |
|---|---|---|---|---|---|
| 管理概览 | 数据看板 | overview.vue，经原 AdminView.vue 兼容入口 | /admin | GET /system/dashboard | PASS |
| 用户与权限 | 用户管理 | users.vue | /admin/users | GET /system/users；POST /users；PATCH /system/users/{id}/status；POST /system/roles/assign | PASS |
| 学科与知识库 | 学科管理 | subjects.vue | /admin/subjects | GET/POST /system/subjects | PASS |
| 学科与知识库 | 学科规划与知识点 | construction.vue | /admin/knowledge/construction | /knowledge-base/construction/subjects、/subjects/{id}/points、/subject-plans、/points/build | PASS |
| 学科与知识库 | 知识库管理 | knowledge.vue | /admin/knowledge | /knowledge-base/status、/sources、/reindex | PASS |
| 学科与知识库 | 审核与发布 | review.vue | /admin/knowledge/review | /knowledge-base/candidates；/knowledge-base/versions | PASS |
| 学科与知识库 | 自动维护配置 | maintenance.vue | /admin/knowledge/maintenance | /knowledge-base/maintenance-plans；/{id}/reports | PASS |
| 教学与资源 | 学习资源管理 | resources.vue | /admin/resources | GET /resources/managed；GET /resources/{id}；PATCH /resources/{id}/status | PASS |
| AI 与任务管理 | 知识建设与采集任务 | tasks.vue | /admin/tasks | /knowledge-base/tasks；/{id}/cancel、/retry、/usage | PASS |
| 系统运维 | 操作日志 | logs.vue | /admin/logs | GET /system/logs | PASS |
| 系统运维 | 系统配置 | settings.vue | /admin/settings | GET /system/configs；PUT /system/configs/{key} | PASS |

API 按现有服务基地址调用，隔离浏览器的 `/user`、`/system` 等前缀只是临时挂载前缀，不是生产 API 变更。

## 功能迁移与交互

- `/admin`、路由名 `admin` 和原统计卡片保留；未读取成功时显示破折号，避免将加载失败呈现成真实零值。新增的快捷入口同样来源于统一菜单配置。
- 各业务模板实际提取为独立页面；原请求、验证、搜索分页、表单、角色操作、状态操作、审核、差异/版本恢复、确认对话框及错误提示复用 `useAdminWorkspace.ts`，没有给每个页面复制整份控制台。
- 每页仅在挂载时读取该模块的数据。现有操作完成后的相关刷新逻辑继续保留。学科系统目录与课程规划/知识点建设分别保留原有 API 语义。
- `adminNavigation.ts` 作为管理员功能 ID、路由、角色、图标、分类及标题的统一来源，菜单、路由、搜索、面包屑和概览快捷入口共同使用。
- 一级按钮可收起/展开；子页面激活与分组展开独立；路由切换、刷新及前进后退恢复所属分组。桌面保留项目原有 256/80px 宽度和折叠偏好，折叠图标使用原生 title 提示。
- 长菜单在侧边栏内独立滚动。900px 以下使用抽屉和遮罩，选择菜单、Esc、点击遮罩均关闭；切换宽度清理打开状态。原生 button 支持 Enter/Space，设置 aria-expanded / aria-controls / aria-current 和可见焦点。关闭的移动导航 inert，打开抽屉时主体 inert，焦点在抽屉内循环，关闭后返回菜单按钮。
- 抽屉打开时隐藏小智悬浮按钮，避免压在导航与退出入口上。学生、教师继续使用原有菜单和页面，未复制生成页面为管理员页面。

## 权限检查及最小修复

1. 原路由守卫仅在 `user` 存在时验证角色，有 token 但缺失 user 信息时可能放行。现在缺失用户或角色不匹配均拒绝；每次进入管理员模块都向 `/users/me` 核实当前身份，失败清理会话并进入登录页。未知 `/admin/*` 地址回到受保护的 `/admin`。
2. 原资源目录只列出公共/本人资源，无法覆盖管理员业务。新增 `GET /resources/managed`，独立执行 `require_role('admin')`，复用已有 `ResourceManager.list_resources()`；学生/教师接口和目录语义保持原样。
3. 原资源详情对其他所有者的资源一律 404，管理员也无法预览新管理目录中的私有资源。现在允许经过后端认证的管理员访问；匿名/其他普通用户继续受对象所有权约束。回归验证了管理员可读、匿名不可读。
4. 配置列表已过滤敏感键，但旧 PUT 响应可回显所写敏感键值。现在敏感配置键在进入持久层前被 422 拒绝，响应不回显值。普通配置更新保持原流程。
5. 学科目录读取仍按原设计公开，新增需 admin；知识状态/来源读取仍允许 teacher/admin，重建需 admin；资源状态修改仍按既有 staff 与对象规则处理。没有为了菜单展示提升学生、教师权限。

## 修改文件

前端导航与权限：

- `web-app/src/config/adminNavigation.ts`
- `web-app/src/config/navigation.ts`
- `web-app/src/router.ts`
- `web-app/src/components/AppSidebar.vue`
- `web-app/src/components/AppTopbar.vue`
- `web-app/src/layouts/AppLayout.vue`

业务复用、原入口与页面样式：

- `web-app/src/composables/useAdminWorkspace.ts`
- `web-app/src/views/AdminView.vue`
- `web-app/src/views/admin/overview.vue`
- `web-app/src/views/admin/users.vue`
- `web-app/src/views/admin/subjects.vue`
- `web-app/src/views/admin/construction.vue`
- `web-app/src/views/admin/knowledge.vue`
- `web-app/src/views/admin/review.vue`
- `web-app/src/views/admin/maintenance.vue`
- `web-app/src/views/admin/resources.vue`
- `web-app/src/views/admin/tasks.vue`
- `web-app/src/views/admin/logs.vue`
- `web-app/src/views/admin/settings.vue`
- `web-app/src/views/admin/admin.css`

后端、验证、交付：

- `services/resource_service/app/api/routes/resources.py`
- `services/system_service/app/api/routes/admin.py`
- `tests/unit/test_admin_navigation_api.py`
- `tests/unit/test_system_configs_authz.py`：排除历史 artifacts 产物，修复非运行代码导致的静态误报；原权限断言保留。
- `tests/e2e/admin_navigation_runtime.py`
- `tests/e2e/run-admin-navigation.mjs`
- `scripts/reload_admin_services.ps1`
- 本报告及 `DEV_STATE.md`。

仓库启动时已有大量未提交变更，本清单仅表示本次涉及的文件，不表示这些文件的全部 Git 差异均由本轮产生。没有自动提交、重置或清理既有内容。

## 执行结果与证据

证据根目录：`artifacts/admin-navigation-20261020/`。

| 验证层级 | 本次结果 | 证据 |
|---|---|---|
| 项目现有 TypeScript 检查 + Vite 构建 | npm run build，退出码 0，最终 Vite 5.89 秒 | build.log |
| 相关后端单元/接口回归 | 80 passed，221 warnings，58.83 秒 | unit-verified/command.json、command.log |
| Chromium 真实浏览器 | PASS；11 个菜单；44 组页面宽度检查；21 个流程断言 | browser-verified/browser-report.json |
| 接口权限矩阵 | 10 接口 × 匿名/学生/教师/管理员，40 项状态码断言通过 | browser-verified/browser-report.json 的 permissions |
| 正常浏览器错误 | pageErrors=[]，apiErrors=[] | 同上 |
| 受控错误注入 | 用户列表 503 有明确提示；身份核实 503 后清会话并拒绝进入 | injectedFaults、steps |
| 本机实际服务 | 8003/8006 新代码已加载；六服务健康；管理目录匿名 401；配置匿名 401；前端 CORS OPTIONS 200 | activation/processes.json、http-checks.json |

浏览器使用真实登录、真实 FastAPI 路由依赖和持久化查询；六个服务应用为隔离验收临时挂载到同一 loopback 端口，未替换业务响应。数据库为全新隔离 SQLite，截图中的账号、候选、统计为明确的验收夹具。仅最后错误处理流程在两个端点注入 HTTP 503，记录到三次响应。未启动 Worker，未调用真实收费模型。

浏览器实际操作还覆盖：用户搜索/分页、角色分配、停用读回；学科新增刷新读回；私有资源正文预览、发布及归档；系统配置保存和刷新读回；手工课程学科/知识点保存；候选编辑、保存、提交和批准；维护计划创建、暂停及刷新读回；巡检任务持久化、取消及用量读取；伪造缓存管理员角色的学生/教师被服务器当前身份拒绝；退出后后退不能重新读取管理员页面。

本次没有配置前端单元测试命令，`package.json` 中原本也没有 test 脚本；前端采用现有构建与新增浏览器验收。未宣称执行全项目后端回归或完整学生/教师业务回归。发布/索引恢复沿用原流程，相关服务测试通过，但本次未重跑真实 Chroma 发布/回滚和模型规划/建设链路。原构建存在大 chunk 与第三方 PURE 注解等警告，构建成功。

首次后端执行为 79 passed / 1 failed，失败来源是扫描到旧 `artifacts/global-audit-resume-20261019/harness/live_matrix.py`，修正扫描范围后完整相关集通过。早期浏览器脚本的隐藏菜单定位、Element Plus 原生隐藏 checkbox 和配置加载时序问题已修正，最终依据仅采用 `browser-verified` 成功记录。没有删除测试或放宽业务权限。

复现命令（新的 run-root 必须尚未存在）：

```powershell
cd web-app
npm run build
cd ..
python scripts/run_no_cost_tests.py --run-root artifacts/admin-nav-repeat-unit --timeout 240 -- -m pytest tests/unit/test_admin_navigation_api.py tests/unit/test_system_configs_authz.py tests/unit/test_resource_authz.py tests/unit/test_knowledge_base_admin_api.py tests/unit/test_knowledge_tasks.py tests/unit/test_knowledge_candidates.py tests/unit/test_knowledge_maintenance.py tests/unit/test_knowledge_construction.py tests/unit/test_knowledge_budget.py -q
python scripts/run_no_cost_tests.py --run-root artifacts/admin-nav-repeat-browser --allow-port 18206 --allow-port 15187 --timeout 420 -- tests/e2e/admin_navigation_runtime.py
```

临时浏览器服务在测试结束后关闭。当前本机前端仍为 5175；只刷新了 8003/8006，使用原 `artifacts/local-start-20261019/runtime.sqlite`，并以 `--lifespan off` 避免此次启动触发建表/兼容列回填。没有执行共享数据库迁移，也没有向真实业务数据库执行测试写操作。新 PID 为 resource=52928、system=94792；其余服务与 Worker 未停止。以后若正常重启，仍使用项目原有启动方式和数据库策略。

## 截图

以下均是本次通过的隔离浏览器验收实际截图，不是设计稿。

- 展开导航：`artifacts/admin-navigation-20261020/browser-verified/navigation-expanded.png`
- 一级分组展开：`artifacts/admin-navigation-20261020/browser-verified/group-expanded.png`
- 二级菜单激活：`artifacts/admin-navigation-20261020/browser-verified/submenu-active.png`
- 导航折叠：`artifacts/admin-navigation-20261020/browser-verified/navigation-collapsed.png`
- 手机抽屉：`artifacts/admin-navigation-20261020/browser-verified/mobile-drawer.png`
- 附加审核页面：`artifacts/admin-navigation-20261020/browser-verified/review-page.png`
