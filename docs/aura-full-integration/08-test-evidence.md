# 本轮可核验测试证据

## 当前运营/多模态/真实模型证据

最新见[12验收报告](12-operations-media-acceptance.md)，根artifacts/aura-ops-20261020。global-unit-v2：592 passed /2133 warnings；browser-final：九组通过、pageErrors空，生成/QA受控桩、本地PPTX/SVG/WAV实际下载或播放、导图保存/历史/权限、管理员台账与独立Worker心跳；migration-final：空库至0031及0031→0028→0027→0031保留原数据；build-final.log退出0、2.89秒。live-authorized-v2/v3同一授权累计4 Chat HTTP200，输出3432，输出预留6000已满，工具/外部图片/外部TTS为0；包含1次截断失败，后续真实三题无fallback、QA及服务端评分通过。金额未核验，不能据此宣称全站/完整付费Worker通过。以下是前一检查点历史证据。

## P1最终新增证据（2026-10-20）

证据根artifacts/aura-p1-20261020。各批次存在重叠，不相加宣称唯一用例总数。

| 证据 | 结果/准确范围 |
|---|---|
| regression-final/command.log | 当前最终167 passed /1432 warnings，包含随后计划版本复核及图谱零预算/取消用例；退出0 |
| regression-v4/command.log | 164 passed /1394 warnings；上下文/图谱/预算/任务/活动/调整/笔记/助手/文档/成绩单/编排定向组合 |
| planning-final/command.log | 62 passed /901 warnings；随后计划生成前后/确认版本复核、生成中撤回等相关回归 |
| graph-final-v2/command.log | 40 passed /156 warnings；新增零预算/取消前Provider阻断与历史标签隔离 |
| browser-v6/browser-report.json、db-evidence.json | 七组工作区/管理员业务检查通过，pageErrors为空；1笔记+3绑定题+1作答+1成功任务；生成/QA为受控桩；最终截图已实际查看 |
| documents-real-v1/runtime-result.json、browser-result.json | 真实Chroma HTTP/SQLite/独立Worker/Chromium发布、修订、回滚、撤回、硬退出恢复；生成Provider仍LOCAL_STUB_ONLY |
| documents-real-v1/plan-knowledge-live-result.json | 正式PDF发布→实际Chroma当前片段→计划准入READY，有真实版本ID，模型调用0 |
| migration-v1/migration-result.json | 空库到0029及0029→0028→0027→0029，旧用户/笔记保留，无共享库修改 |
| build-final.log | vue-tsc+Vite退出0，3.94秒，保留原构建提示 |
| ruff-final.log | 新增16个Python文件全规则检查通过；定向git diff --check通过，仅CRLF提示 |

新增测试/执行脚本与精确路径见11。浏览器截图含1600/1024/390工作区与管理员执行详情；窄屏实际关闭导航抽屉并测试两侧折叠。首次失败和修正过程见11及保留日志。真实付费Provider、真实Neo4j、PG、全站/全部多模态仍未执行；未把预算预留计作真实Token。

证据根：`artifacts/aura-full-integration-20261020/`。Python均通过 `scripts/run_no_cost_tests.py`，禁dotenv、真实凭证与远端网络；浏览器限制localhost。所有测试数据库与端口独立，fixture不是用户真实学习记录。

## 最终通过结果

| 检查 | 结果 | 证据 |
|---|---|---|
| 相关Python回归 | **91 passed / 909 warnings**，退出0 | unit-v4/command.json、command.log |
| 单用户活动真实并发 | 4个独立SQLAlchemy会话竞争同一心跳，只提交一个15秒区间；失败insert不能提交游标 | test_study_activity.py，包含于91项 |
| 计划提案 | 本人/他人、30天及未来时间排除、至少3次、确认前任务不变、确认幂等、过期和旧写入拒绝 | test_path_adaptation.py，包含于91项 |
| TypeScript + Vite | 最终`npm run build`退出0，Vite 2.41秒；vis-network注解和重复import警告保留 | frontend-build-final.log，包含最终按钮和进度修正 |
| 迁移 | 空库至0026、0026↔0025、再至当前0027，全通过，旧用户保留 | migration-v3/migration-result.json |
| 真实HTTP/SQLite/Chromium | **10项业务检查通过**，pageErrors=[]；包含1440/768/390宽度 | browser-v4/browser-result.json |
| 浏览器真实活动入库 | 3条明确fixture + 1条真实浏览器心跳区间；合计134.995496秒，其中实际活动14.995496秒 | browser-v4/db-evidence.json |
| Ruff定向 | 通过 | 本轮执行8个相关新增/修改文件，未称全仓库lint |

截图位于browser-v4：`overview-1440.png`、`overview-768.png`、`overview-390.png`、`plan-change-preview.png`、`overview-empty.png`、`overview-failure.png`。此前v3五类截图已实际打开检查，修正按钮对比度并在v4重新生成；最终v4桌面、计划变化、空账户截图已实际打开复核，按钮文字可见，路径侧栏进度与首页均为50%，空账户没有他人资源。

## 可复现命令（先换成新的输出目录）

```powershell
python scripts/run_no_cost_tests.py --run-root artifacts/aura-next/unit -- -m pytest tests/unit/test_path_adaptation.py tests/unit/test_study_activity.py tests/unit/test_aura_analytics_admin.py tests/unit/test_learning_workspace.py tests/unit/test_learning_path_prerequisites.py tests/unit/test_profile_dashboard.py tests/unit/test_assistant_tasks.py tests/unit/test_transcript_learning_path.py -q
python scripts/run_no_cost_tests.py --run-root artifacts/aura-next/migration -- tests/e2e/study_activity_migration.py
python scripts/run_no_cost_tests.py --run-root artifacts/aura-next/browser --allow-port 15189 --allow-port 18306 --timeout 260 -- tests/e2e/study_overview_runtime.py
# web-app目录
npm run build
```

运行器command.log使用独占创建，不能覆盖已有目录；migration脚本要求空库。浏览器运行器仅挂载真实路由于独立18306并起15189前端，运行后退出。它验证真实持久化和UI，不验证六服务分别部署/反向代理/真实Worker或外部模型。

## 失败留痕

- unit-v1 10项、unit-v2 41项通过；unit-v3出现5个旧策略测试FakeDb不支持execute的失败。测试隔离持久化边界后，unit-v4共91项通过；未在生产加入兼容FakeDb的降级。
- browser-v1因异步response.json尚未收集就断言而失败，改查真实聚合读回；v2通过，新增计划确认后v3通过，修UI及空账号fixture后v4通过。
- migration-v1使用不可导入的模块路径；v2遇到同期0027使固定head断言失败；v3显式演练0026再升级实际head通过。

## 明确未测试

真实DeepSeek Chat/Search/Fetch、TTS、FFmpeg/视频导出、PPTX、真实Chroma发布回滚、Neo4j、PostgreSQL、全站E2E、独立Vue组件测试、管理员本轮浏览器、长时并发/性能均NOT_RUN。测试桩、fixture、既有历史记录不替代外部真实验收。

## 后续文档专项实测（2026-10-20，更新首轮NOT_RUN范围）
首轮的“管理员浏览器/真实Chroma发布回滚未执行”已由文档专项补验，其他原未测项继续保留。documents-browser-v9/browser-result.json与runtime-result.json均passed=true：真实SQLite、Chroma HTTP、独立Worker、Chromium；含原件字节/角色权限/审核/索引/学生检索/版本记录/归档/修订回滚/并发同键/队列取消/Worker硬退出恢复/撤回缓存隔离。生成Provider为LOCAL_STUB_ONLY。pageErrors与apiErrors为空，路由切换ERR_ABORTED保留。migration-resume-v2为head0029及0009→0008、0027→0026往返/账号保留通过。最新完整build退出0；定向Ruff通过；最终Python统计见resume-final-unit-v2/command.log。执行命令与前序失败见10，未使用付费凭证或改写共享库。

最终Python定向组合：resume-final-unit-v2/command.log为106 passed /396 warnings，退出0；新文件全规则Ruff通过，关联既有服务F级检查resume-associated-ruff-final.log通过。未把现有整仓全部lint宣称通过。
