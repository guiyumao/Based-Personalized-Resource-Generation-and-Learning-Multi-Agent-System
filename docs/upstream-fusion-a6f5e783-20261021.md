# 远端 a6f5e783 增量融合与格式核验

日期：2026-10-21，Asia/Shanghai。

## 结果

已把 origin/main 新增提交 `a6f5e78361a97125b01917e6d3bca97bb7ec9ec5` 的功能融合到当前现有工作区，并保留本地通知系统及同期其他修改。远端提交标题为“修改：1.固定数量题目改为可选数量题目（最多25题）2.为知识图谱模块添加参考信息超链接”。

本次是审查后的工作区增量融合：没有清理、stash、reset 或自动提交/推送。HEAD 仍为605feaab，origin/main为a6f5e783，Git显示behind 1；新功能已在工作区及当前运行环境加载，不代表已生成Git合并提交。

## 远端实际内容

通过 git fetch 获取并逐文件审查。共22个变更路径，其中21个应用：

- 练习题量选择器，1～25题，默认10；按账号保存选择，刷新恢复，后端请求模型/助手能力声明同步放宽。
- 默认题型配比随请求数量缩放，Prompt明确要求按本次题量输出；审核重试补充缺失占位符。
- 图谱GraphNode增加url/provider/kind，已有公开参考链接经过图谱构建、合并、响应模型到前端资源链接显示。
- PlanAdaptationPanel处理no_change缺少before/after时旧弹窗崩溃。
- 教师学生详情转发原始Authorization头；作答时间按模型的UTC无时区字段写入。
- .gitignore、部署说明、四份环境配置模板、lockfile调整及三份随仓库提交的知识语料。

唯一没有应用的是 `.cache/knowledge-write.lock`：这是本机活跃运行锁，保留本地状态。没有覆盖已有.env、连接参数、凭证或个人音视频；新语料没有自动注册为已发布版本，没有重建共享Chroma索引。

集成前保存本地差异和远端补丁至 artifacts/upstream-fusion-a6f5e783/；应用后核对19个原有已修改文件的哈希均未被远端补丁覆盖。后续只在必要的assistant_tasks等文件做衔接修复，保留通知终态写入等原有改动。

## 本次补齐的衔接

1. QA原先把题量截断到3～10，现改为1～25。
2. 助手1/2题中文请求可识别；完整识别125等数字，由接口拒绝越界，避免误取末尾25。
3. 助手大题量按每批最多10题执行，25题为10+10+5；每批有不同稳定执行键，保留取消/部分失败与原通知机制。
4. 审核重试传递真实生成计划和已有题目签名，不使用空值绕过去重。
5. 图谱链接匹配优先精确标题；随后才允许有长度限制的模糊匹配。过滤无主机、非HTTP(S)、带账号密码或控制字符的地址；前端再次校验，外链使用noopener noreferrer。
6. 读取旧练习记录时保留明确保存的新题量选择，旧25题可以继续做，下一次选7题刷新后仍为7题。
7. 修正手机上原练习双栏内容被裁切的问题，改为窄屏单栏，不改变桌面布局与原练习功能。

本次没有增加强制搜索/抓取闭环；远端新增提交也不包含此项。先前指出的“搜索失败仍可尝试模型建设”行为没有借本次融合擅自改变。

## 验证

- 最终Python定向集：**175 passed / 6179 warnings**，见 `unit-final/command.log`。覆盖新增边界、精确持久化、按比例题型、助手分批/中文题量/去重重试、教师凭证转发，以及原练习、图谱权限/缓存、助手、评估报告、QA、计划适应、通知回归。
- 最终TypeScript/Vite构建退出0，5.03秒，见 `build-delivery.log`。保留原第三方构建提示。
- 隔离真实API/JWT/SQLite浏览器：5组通过，pageErrors=[]。实际发送1/7/25请求、真实入库和回读；范围校正、旧会话恢复、新题量偏好、账号隔离；390px内部内容无横向溢出；真实图谱库参考资料经过API到前端成为链接。仅习题模型输出为明确受控夹具，没有伪称真实模型质量验收。见 `browser-v2/result.json`，截图已查看。
- 实际5175/8002平台：3组通过，pageErrors=[]。验证实际OpenAPI/助手能力1～25、0/26请求在生成前返回422；题量偏好刷新/移动端；原通知卡片仍默认收起；真实公共图谱链接到达页面。没有发送有效的付费生成请求。专用账号及其学习活动记录已清理，见 `current-browser/{result,cleanup}.json`。
- 新增测试和运行脚本Ruff通过；关联旧report_service.py有已有F402变量遮蔽提示，本轮没有声称全仓lint通过，也未为此改写无关循环。
- 初版新增持久化测试误把Exercise归属当作独立列；实际保存在content JSON内，修正断言后最终175项通过，初次失败日志保留。

## 当前平台激活

确认没有PENDING/QUEUED/RUNNING/CANCEL_REQUESTED任务，核对所有目标进程的cwd与DATABASE_URL，SQLite备份至 `activation/before.sqlite` 后，按原环境及参数重载8002、8004、8005、8007及原助手/知识Worker，启动均关闭lifespan自动建表与模型预热。

没有数据库迁移或Alembic stamp。激活前后用户96、资源120、计划164、笔记2、通知0、model_calls155均未变，integrity_check=ok。后续当前浏览器核验台账为156→156，说明同期其他使用需与本轮测试区分；本轮没有发送付费模型/搜索/抓取请求。端口、数据库路径、当前业务数据均保留。进程证据见 `activation/result.json`，启动清单仅更新对应PID。

## 关于错题本、收藏本的全局格式核验

这是本轮用户追加的现状问题；当前工作区已有同期格式改动，本次保留并验证，不能算作远端a6f5e783新增能力。

当前错题本和收藏本的题干、选项、用户答案、参考答案、解析使用 `LearningContent.vue`，内部统一走 `learningMarkdownCore.mjs`；排版由全局 `.learning-markdown` 样式提供。支持Markdown标题/列表/表格、代码高亮、$...$/$$...$$/\\(...\\)/\\[...\\]公式、空态及渲染后预览折叠。错题预览不会先截断公式源码。

本轮实际运行这三份测试：

- src/utils/__tests__/learningMarkdown.spec.ts：8项；
- src/components/__tests__/LearningContent.spec.ts：6项；
- src/views/student/__tests__/notebooksFormat.spec.ts：3项。

**共17项通过**，见 `format-tests-node24.log`。默认Node22.14运行jsdom/undici时缺少解压API，未收集到测试；使用本机已有Node24.21重新执行通过，没有安装依赖或修改系统默认Node。之前失败日志保留。

因此，“两本已接入全局统一显示规范”可以确认；这不等于已经重写全部历史数据，也不保证异常JSON包装、字面转义或损坏公式会自动修复。按钮/计数/状态、RAG截断来源摘要等仍是普通文本；没有在真实登录账号下对两本做全量内容端到端验收。同期完整格式方案见 docs/global-learning-format-20261021.md，本轮只复核上述实际代码和17项测试，不把其中其他会话的验证冒认为本轮成果。

## 主要衔接文件

- common/schemas/agent.py
- prompts/exercise_gen.md
- services/agent_service/app/api/routes/assistant.py
- services/agent_service/app/connectors/neo4j_connector.py
- services/agent_service/app/services/exercise_generation.py
- services/agent_service/app/services/assistant_tasks.py
- services/agent_service/app/services/qa_service.py
- services/evaluation_service/app/services/report_service.py
- services/teacher_service/app/api/routes/classes.py
- web-app/src/api/types.ts
- web-app/src/components/PlanAdaptationPanel.vue
- web-app/src/views/student/ExerciseView.vue
- web-app/src/views/student/KnowledgeGraphView.vue
- tests/unit/test_upstream_a6f5e783.py
- scripts/activate_upstream_fusion.py
- scripts/run_upstream_fusion_browser.py
- scripts/verify_upstream_current.py
- tests/e2e/upstream_fusion_server.py
- tests/e2e/run-upstream-fusion.mjs
- tests/e2e/run-upstream-current.mjs

其余导入文件为远端部署模板、说明、忽略规则、lockfile及三份语料。全部原有与同期未提交改动保留；没有自动提交、推送或部署到公网。
