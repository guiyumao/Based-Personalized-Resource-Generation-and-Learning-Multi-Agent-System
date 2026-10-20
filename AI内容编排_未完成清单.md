# AI 内容编排 · 真实调用 · 未完成清单

> 2026-10-20。记录本轮已打通项与仍未完成项，供后续连续开发与验收对照。状态分级沿用：未实现 / 部分实现 / 已编码未验收 / 隔离测试通过 / 实际运行已验证 / 因外部依赖阻断。

## 一、本轮已完成（实际运行已验证）

| 项 | 状态 | 证据 |
|---|---|---|
| 提示词列表 `GET /admin/prompts` | ✅ 实际运行已验证 | 200 / 11 模板 |
| 图片 Provider 状态 `GET /admin/image-provider` | ✅ 实际运行已验证 | blocked/invalid/disabled/configured 四态 + enabled/health |
| 章节读取 `GET /admin/resources/{id}/sections` | ✅ 实际运行已验证 | resource 220 → 9 节 |
| AI 改写 `POST /admin/resources/{id}/rewrite` | ✅ 真实调用已验证 | deepseek-chat 生成 2810 字符，台账 LIVE/SUCCEEDED |
| 改写应用 `PUT /admin/resources/{id}/content` | ✅ 实际运行已验证 | resource_revisions 写入旧版本快照 |
| 图片配图 `POST .../illustrations` | ✅ blocked（诚实安全态） | 无 Provider 凭据时明确 blocked，不伪造 |
| 提示词版本生命周期 | ✅ 实际运行已验证 | save→1 版本→restore→2 版本闭环 |
| 提示词统一加载（mtime 失效） | ✅ 隔离测试通过 | 三处 `_load_prompt_template` 统一到 `prompt_registry.load_prompt_template` |
| 12 张缺失表补齐 | ✅ 已执行 | 0026–0031 表，`Base.metadata.create_all`，改前备份 |
| AI 改写付费闸门 | ✅ 已编码 | `RUN_LIVE_LLM=1` 且 `DEEPSEEK_LIVE_PAID_ACK=1` 双闸门 |

## 二、未完成项

### P0 级（影响真实可用性）

| # | 未完成项 | 当前状态 | 阻塞/需要 |
|---|---|---|---|
| 1 | ~~章节配图真实图片生成~~ | ✅ 真实闭环已验证 | 通义万相 wanx2.1-t2i-turbo 实测生成→审核→插入→发布全链路通过（见下「第三节已解决」） |
| 2 | **runtime.sqlite 台账表与共享库/线上库基线对齐** | 部分实现 | runtime.sqlite 已定向补表；共享 SQLite 与线上库仍需基线审计后再对齐，禁止空库迁移 |
| 3 | ~~孤儿提示词模板~~ | ✅ 已清理 | 5 个无消费方模板（coordinator/knowledge_graph/learner_profile/path_planning/qa）已从 `ALLOWED_PROMPTS` 白名单移除，管理端只显示 6 个真实被生成链消费的模板；**接线到 coordinator 是独立后续任务（见 P1 追加项）** |

### P1 级（补全闭环）

| # | 未完成项 | 当前状态 |
|---|---|---|
| 4 | AI 改写「草稿→待审核→已批准→历史」显式状态机（当前为「生成→应用」两步） | 部分实现 |
| 5 | 改写前后差异 diff 可视化 | 未实现（当前仅并列预览） |
| 6 | 改写幂等保护 + 双管理员并发冲突检测（已用 `expected_version` 部分覆盖） | 部分实现 |
| 7 | 提示词「新建/启用停用/按业务类型分类/默认模板保护/变量白名单类型校验」 | 未实现（当前仅 list/read/update/version/restore + 占位符保留校验） |
| 8 | 图片生成结果的资源/章节/知识点/任务/模型/审核状态/存储/版本关联落库 | 未实现（依赖 #1） |
| 9 | Provider 健康检查 / 失败信息 / 预算限制字段 | 部分实现（`health=unknown`，未接真实探测与预算） |
| 13 | **coordinator/QA 提示词接线统一**（把硬编码 inline prompt 迁移为加载 `prompts/*.md`，消除「两个系统」） | 未实现（已从白名单移除 5 个孤儿 stub，接线本身是 61KB coordinator 的独立重构，需单独规划） |

### P2 级（统一与验收）

| # | 未完成项 | 当前状态 |
|---|---|---|
| 10 | 统一交互与异常反馈（区分「空数据 vs 接口错误 vs blocked vs failed」） | 部分实现 |
| 11 | 完整浏览器回归（Chromium 实际操作 + 截图 + DB 读回 + 任务状态） | 未实现 |
| 12 | 学生端全链路验收（课件/习题/计划/画像与知识库/资源真实联动） | 未实现 |

## 三、需要用户提供或决策

1. ~~图片 Provider 凭据~~ **已解决**：通义万相 `IMAGE_PROVIDER_API_KEY`（已写入 `.env`，gitignored）+ `IMAGE_PROVIDER_BASE_URL=https://dashscope.aliyuncs.com/api/v1` + `IMAGE_PROVIDER_MODEL=wanx2.1-t2i-turbo`。真实闭环实测：`POST /admin/resources/220/illustrations` → status=generated（671KB PNG 落盘）→ `/storage/...` 静态服务 686921 字节 PNG → approve → insert（resource 220 内容+版本快照）。
2. **共享 SQLite / 线上库基线审计授权**（接 P0#2）：是否允许我对共享库做只读审计并产出对齐清单（不自动迁移）。
3. **真实调用预算口径**（接 P1#8/#9）：后续验证允许的最大 Chat/图片生成次数与输出预算。

## 四、运行环境注意

- agent_service 8002 当前以 `RUN_LIVE_LLM=1` + `DEEPSEEK_LIVE_PAID_ACK=1` 运行（已授权真实调用）。若之后用 `start.ps1` 重启而未注入这两个变量，AI 改写会回到 blocked 安全态（这是预期行为，不是故障）。
- 运行时库为 `artifacts/local-start-20261019/runtime.sqlite`（已补 12 表）；原库 `learning_system.db` 未动；改表前备份在 `runtime-before-tables-20261020-200640.sqlite`。
- 本轮未提交、未重启 8001/8003–8007/5175、未迁移共享库、未删除资源、未清空模板。真实付费调用 1 次（改写 220，1597/1535 tokens）。
