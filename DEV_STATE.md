## 产品首页重设计与内外主题联动（2026-10-23）

- LandingView 使用独立“知识探索地图”插画 knowledge-landscape.webp（约169KB），不复用登录页书本图；重排首屏、功能/角色/协同区，保留导航与登录入口。ThemePicker 为首页与登录页共享外观入口；LoginView 清除固定调色，继承原全站主题变量。
- useTheme 增加一次性 storage 监听；首页/登录/已登录工作台共用原 app-theme，跨标签同步六种外观及恢复默认，不影响账号隔离与权限。
- 验证：build退出0；主题单元4 passed（系统Node22的undici缺zstd，改用内置Node24.19运行通过）；Chromium六主题正反同步/刷新、独立图片加载、首页导航、320/390/768/1440宽度全部通过，pageErrors空。工作台使用模拟API，无DB写入/后端服务重启/付费业务模型调用。证据 artifacts/homepage-theme-20261023/；未逐个验收全部业务子页。

## GitHub 上传快照验证（2026-10-23）

- 用户明确要求项目上传 GitHub；沿用 origin/main，上传当前已整理的源码、迁移、测试与文档。保留本机代理笔记、生成语料、数据库、密钥和运行产物；准备快照后出现的 LoginView.vue 并行改动保留本地。
- 本轮前端 TypeScript/Vite build 通过；后端定向 pytest 97 passed。默认 Node 的 undici 环境启动失败，切换已安装 Node 24.19.0 后前端 66 passed / 1 failed；失败位于 workspaceGeneration.spec.ts:26，恢复任务后 error 预期 offline、实际空串，未在上传任务中修改业务实现。
- 日志：artifacts/github-upload-build.log、github-upload-backend-test.log、github-upload-frontend-test-node.log。未执行真实模型调用或数据库迁移，不声明全站验证通过。

# 当前开发状态

## 学习工作区离开后持续生成（2026-10-23）

- 根因：Assistant Worker 已退出（原 #16/#17 PENDING）；工作区轮询随组件卸载停止，提交响应晚于离开时任务号丢失；新路径归档全部 active 计划使截图 #369 失效。
- 新增 `stores/workspaceGeneration.ts`：用户/上下文隔离、离页轮询、本地回执、瞬时错误重试、TIMED_OUT 终态；返回/刷新由按上下文过滤的 `/assistant/tasks` 找回，无需重发生成，完成仅在打开对应工作区时跳转。路径保存只替换同学科同主题非教师计划，保留排队/运行中的计划。启动脚本在 worker 模式补启缺失 Assistant Worker。
- 运行库在线备份 + 副本演练后仅恢复 #369 active，无迁移；重载8002/8007、path-worker，恢复assistant-worker PID27920。原#16真实生成SUCCEEDED → resource#241（10316字）→ #369新上下文；原#17也SUCCEEDED，未另提交测试生成。恢复队列执行了原任务的真实模型调用。
- 验证：后端相关34 passed；前端全套46 passed，后补提交超时找回后定向4 passed；tsc/Vite通过，定向Ruff/PS语法通过（assistant.py原I001未重排）；模拟后端浏览器离页/刷新两例无重复POST且pageErrors空；真实demo_s01从原上下文自动进入#241课件，pageErrors空、生成POST=0。证据 `artifacts/workspace-background-20261023/`（before.sqlite、repair.json、browser/result.json、live-readback.json、live-browser.json、live-workspace.png、final-tasks.json）。不宣称正文教学质量或视频通过，运行日志提示本地视频制作失败。


## 全站雷达图共用绘制规则（2026-10-23）

- 新增共享 `components/RadarChart.vue`，学习画像的偏好量表（-1～1）与学习概览的能力指标（0～100）均复用。全站源码雷达入口已排查；三项以上已知值连线填充、两项连线、缺失值保留空并提示，零值有效，不补造维度。概览保留原数值条便于阅读；不足三维不构造雷达。支持不同维度数量、主题配色与响应式尺寸。
- TypeScript检查及共享组件/画像页14项测试通过，覆盖3/4/5/7维、缺失与非有限值、量表映射及数据更新。只改前端，无模型调用、数据库变更或服务重启；未做当前浏览器截图级验收。

## 学习画像改为模型推断（2026-10-23）

- 用户截图指出画像雷达空置且只能手填。新增 `services/user_service/app/services/learning_style_inference.py`：模型读取已收集的自述维度/自述风格、真实作答知识点、资源浏览、画像对话、笔记/闪卡计数与既有分析摘要，输出四轴（-1..1）+ 每轴置信度/依据 + 总述；严格 JSON 校验（越界、非数字、全空都拒绝），证据不足保持 null，明确禁止用正确率单独推断风格。
- 手动值仍存 `habits.learning_style_axes` 且优先；推断单独存 `habits.learning_style_inference`（含 Prompt 版本、证据指纹、模型名、时间），不污染其他智能体读取的 `profile_dimensions`。GET 合并并按轴标 `user_reported/model_inferred/missing`；`POST /users/{id}/learning-portrait/infer` 一次有界模型调用，24h + 证据指纹缓存，新增记录后标记 stale；四项全手填时跳过模型。
- 前端画像页新增“AI 生成画像/更新画像”（`force=false`，无新证据直接复用缓存），雷达与维度条按来源着色，模型项展示依据与置信度；进入编辑时推断项默认不勾选，避免“编辑即据为己有”。空态文案改为模型生成入口。
- 验证：`tests/unit/test_learning_insights_portrait.py` 13 passed（新增 6 项：合并/手动优先/缓存/非法输出/无证据不调用/无凭据 blocked/越权），`test_profile_analysis.py` 5 passed；3 个新前端组件用例、全套 39 passed、build 通过；Ruff 通过。8001 已重载（PID 81844），openapi 有 infer 路由；demo_s01 真实 JWT GET 返回 inference=never、跨用户 403。
- 边界：未做真实付费模型调用（未获本轮预算授权），真实模型对 Prompt 的遵从度与推断质量未验证；辅助六维文本仍由画像对话/深度分析生成，不写入 `profile_dimensions`；未跑浏览器点击级 E2E。

## 历史课件可打开 + 真实检索资料入库（2026-10-23）

- 历史课件：`GET /paths/history/{user_id}` 每条记录新增 `courseware_resource_id/title/created_at`（按用户+知识点，取该路径生成后30分钟内最新的一条，没有则回退到时间最接近的一条；排除归档/他人），前端历史卡片显示“查看课件 #id”，弹窗直接读 `/resources/{id}` 原文；不依赖 sessionStorage，不触发生成。实测 167/168/169 分别命中 234/235/236，12:56/15:13 存储系统均命中 237，15:15 UDP 命中 233；老师范围旧路径无知识点ID时不强配。
- 真实资料：新增 `services/agent_service/app/services/knowledge_sources.py`——检索到的外部正文写成 `knowledge_base/corpus/<subject>/source_<hash>.md`（带 URL/站点/授权/知识点/知识点ID 头），`scripts/index_resources.py` 识别 `知识点` 头并按点索引；`plan_preflight` 在已发布版本 chunk 之外补入 `source_type=web_reference` 的真实资料（每来源最多3块、总计≤12，`visible_chunks` 仍只对 candidate 做版本校验）；`acquire_context(enrich_sources=True)` 在无外部资料时检索一次并入库，7天 marker 防止重复搜索/失败重试。路径页请求已开 `allow_web_knowledge/enrich_knowledge`。
- 已真实检索并入 UDP（计算机网络）3 个中文来源、存储系统（计算机组成原理）3 个来源；`acquire_context` 实测 UDP 10 chunks（9 外部）、存储系统 12 chunks（4 外部），第二轮不再搜索。未发起新的课件生成（未授权付费），公开正文/版本未被改写。
- 验证：新增 `tests/unit/test_knowledge_sources.py` 5 项、历史挂课件 2 项（含 30 分钟窗口），后端相关 49 passed；前端 36 passed、build 通过；Ruff 通过。8002 已按 runtime.sqlite 重启（最终 PID 32732），path_worker PID 55576 载入 3s/2s 扫描（原25s队列空转）；`GET /paths/history/6` 真实 JWT 返回 25 条，167/168/169→234/235/236、367/212→237、368→233；`acquire_context` 实测 UDP 10 chunks（9 外部）、存储系统 12（4 外部），课件上下文 10 chunks/6954 字符。证据 `artifacts/history-courseware-20261022/`、`artifacts/knowledge-sources-20261023/`。
- 边界：外部资料仅作检索参考（授权标 `external-reference`，不冒充已审核版本）；公网检索依赖 DeepSeek search key/额度；未做旧版本自动替换（UDP 的682字节占位版本仍 active，但已由真实资料补足）；未跑付费生成/浏览器点击。

## 学习路径后台生成跨页面续接（2026-10-22）

- 现象/根因：协调任务已由path_worker在服务端继续执行（coordination_tasks#1 SUCCEEDED、learning_paths#212、resources#237均已落库），但轮询与结果落盘只存在于LearningPathView组件内；离开页面即触发`pageDisposed`抛错，组件内的`persistCoordinatedCourseware/persistCoordinatedExercises`永不执行，任务号也随之丢失，故表现为“离开就不生成”。
- 新增 `web-app/src/stores/pathGeneration.ts`：框架无关单例，持有排队/轮询/失败状态；任务号写入localStorage（`student-path-generation-pending:<userId>`，6小时内有效），重新进入页面、刷新甚至关闭浏览器后`resumePathGeneration`原地续接、不重复提交；成功时由store统一写入课件/练习快照与工作区上下文，失败/超时保留可续接状态，瞬时网络错误不终止轮询。公共知识PUBLIC_KNOWLEDGE_PROCESSING的3秒预检重试也迁入该模块，离开页面不再中断。
- LearningPathView改为store驱动：`loading`由store状态派生，返回页面自动续接并直接回显路径；在后台生成期间不被历史路径覆盖表单；新增“可离开本页”提示。CoursewareView在无快照且后台任务在跑时等待该任务并采纳其课件（12分钟上限），避免另起一次付费课件生成。
- 验证：前端`npm run test` 35项全通过（新增后台完成/持久任务续接/失败清理/瞬时错误/遗留任务过期5项，路径页原5项不变）；`npm run build`（tsc+vite）通过；5175 dev server已实际返回新模块。新增 `tests/e2e/run-path-background-resume.mjs`（后端全部拦截，零真实模型调用、零数据库写入）：A.生成中切到“学习概览”，任务完成后课件/练习快照已写入且无待续接记录，返回后路径直接回显；B.生成中整页刷新，提示条重新出现并续接（`enqueued`仍为1，未重复提交），完成后渲染路径并清理待续接记录；两例`pageErrors`均为空，证据 `artifacts/path-background-20261022/`。未跑真实付费生成；运行中的agent/worker未重启（纯前端改动）。

## GitHub ac840f42 融合与本机激活（2026-10-22）

- main 从66a78ec7无冲突快进至origin/main的ac840f42，合入学习路径历史、异步生成、课堂显示及公共知识截断处理；保留原本地笔记和运行数据。新增语料文件仅作为源码合入，未绕过数据库审核自动发布。
- 补齐0042 coordination_tasks迁移；修复path_worker非原子领取与RabbitMQ连接失败时不扫描数据库的问题，连接超时有界。补充异步/历史权限、重复执行、故障回退和截断重写测试，更新上游重构后的测试接口。
- Python相关72项+截断补测1项通过；前端原29项及含新增历史交互的路径页5项通过（共30个不同用例）；TypeScript/Vite构建、定向Ruff通过。Windows内存不足的早期中断记录不作为通过证据。
- 在线备份及副本幂等演练后，仅新增运行库coordination_tasks表，无全量迁移/stamp。重载相关agent/teacher/assistant-worker并启动path_worker；8001–8007健康、5175可访问，两个agent入口历史读库一致、匿名401/跨用户403及任务列表共10项只读检查通过。业务表计数和模型调用数不变，worker_instances注册记录15→16属预期。
- 证据artifacts/path-fusion-20261022-204706/（before/rehearsal.sqlite、result.json、live-readonly.json）；artifacts/github-fusion-pytest-final.log、github-fusion-python.xml、github-fusion-build-final.log。说明docs/GitHub融合-ac840f42-20261022.md。补充修复未提交/推送；未跑真实付费生成或浏览器端到端。旧桌面ZIP仍是融合前快照。

## 多角色演示教学环境与跨角色联动验收（2026-10-22）

- 新增 `scripts/demo_teaching_dataset.py`：seed/check/refresh/reset 四动作，全部经 TeacherManager/CheckinManager/ClassScheduleManager 真实业务层写入，幂等（二次执行 created={}、15 表行数不变），只操作 `demo_%` 账号及其派生数据，写前自动备份 `artifacts/demo-teaching/backups/`，拒绝写入 `learning_system.db`。
- 数据规模（运行库 runtime.sqlite）：4 教师 / 24 学生（3 行政班×8，优秀·普通·困难·待处理四画像）/ 6 课程 / 8 教学班 + 3 行政班 / 9 排课 / 13 作业（64 提交、23 已批改）/ 6 打卡任务 / 6 场考勤（含 3 迟到）/ 256 条真实作答 / 462 通知。
- 建模约束（未新增平行实体）：系统无行政班实体，用 `classrooms`（course_id=NULL、is_public=0）承载；无入班审批流，"待审批申请"标注不适用；`create_class` 强制新建 Course，同课程第二教学班用 ORM 复用 course_id；数据库原理/Java/Python/软件工程无公共知识点，故不生成作答与学情，避免虚构。
- 修复真实缺陷 P1：`_publish_scope_to_students` 会归档学生全部 active 学习路径，多教学班学生丢失前一门课计划；改为只归档同 class_id 旧版本。新增 `tests/unit/test_teacher_scope_paths.py` 2 passed，重建后 demo_s05 两个教学班路径同时 active。
- 新增 `scripts/verify_demo_teaching.py`：真实账号密码登录的 HTTP 跨角色断言 46 项（身份/班级创建与入班/课表同步与冲突/作业闭环/签到闭环/通知未读/学情/并发/边界/一致性）全 PASS，证据 `artifacts/demo-teaching/verify-postfix/result.json`，跑完自动清理 `[VERIFY]` 临时数据。
- 文档 `docs/demo-validation/01~06`（审计、账号、数据清单、测试报告、人工验收、使用指南）。为加载修复重启 8005（当前 PID 48664，会话内后台进程，退出后按 06 文档命令重启）；无迁移、无前端改动、付费模型调用 0。未验证浏览器点击级 E2E / PG / 公网 / 真实模型链路。

## 教师资源→补强作业→即时答案→错题与模型反馈（2026-10-22）

- 教师“学习范围/学生洞察/作业管理”新增课程资源与个性化补强：课程资源发全班/个人，按学生真实学情+课程资料生成模型草稿，教师审阅后定向下发，复用既有作业。三张新表及0041迁移，原有Assignment表无新增列。
- 学生提交后立即展示参考答案与解析；选择题即时判定，简答题后台模型评分，失败保持未知。新Exercise/AnswerRecord写入原错题本及学情；首次答案不可覆盖，重试幂等。教师收到完成/分析通知，在“学生错题与模型分析”及原作业详情查看逐题答案、判错与建议。平台总学习时长明确非课程时长，缺失保留null。
- 40项后端回归、build/Ruff通过；最终当前服务真实DeepSeek+Chromium17项通过，证据 `artifacts/teacher-support-20261022/live-v4/`（其他live目录是失败调试记录）。受控临时账号验证，不宣称真实学生学习效果；最终2次真实模型调用成功，前期调试/诊断另6次，审计保留。
- 运行库先在线备份/副本两次演练，只增三表，仅重载8005至PID72348；最终18表计数恢复，users124/classes15/assignments15，保留运行中既有数据。报告 `docs/教师资源补强与错题反馈闭环-20261022.md`。
- 边界：教师资料为已有资源/Markdown正文，未新增教师文件上传；未测PG/公网/多实例。分析任务保留数据库状态及5分钟执行保护，服务中断后教师重试，未接独立队列Worker。

## 课堂广场邀请码搜索加入已接入（2026-10-22）

- 原搜索框支持完整邀请码精确命中（大小写/首尾空格），正确码可查非公开课堂并点击“使用邀请码加入”；保留名称/学科/教师搜索，响应无邀请码，部分/旧码/停用不命中。加入复用现有邀请码接口，保留容量/幂等/通知和课堂、课表同步；请求过期响应及未提交查询错用已防护。
- 17项后端测试、build/Ruff、当前HTTP闭环和真实浏览器16项断言通过；临时数据清理，16表计数恢复，模型156→156。证据 `artifacts/plaza-invite-20261022/live/`，说明 `docs/课堂广场邀请码搜索加入-20261022.md`。
- 无schema变更，运行库先备份，仅重载8005至PID39140；未改真实成员关系。未测公网/其他DB。

## 课程表自动导入与学生编辑已接入（2026-10-22）

- 当前student已加入2课堂却无教师排课，旧页只读排课故0节。现按成员关系自动导入所有有效课堂，缺时间显示“待安排”可自行补充；教师已排课程按周同步。学生可新增/编辑/删除个人课程、私人调整/隐藏本次课堂课程并恢复；仅影响本人。新增 `personal_schedules` 与0040迁移，退出课堂后关联安排停止展示，独立课程保留。
- 已修复上一轮跨周调课漏课与调整冲突漏拦截。34项后端回归、前端build/Ruff通过；当前HTTP闭环及14项真实浏览器通过，含个人CRUD/刷新/恢复/跨周/390px。最终证据 `artifacts/timetable-edit-20261022/live-final/`，报告 `docs/课程表自动导入与学生编辑-20261022.md`。
- 运行库先在线备份、在副本演练、最小新增表；仅重载8005至PID11480，不批量迁移/stamp。真实student只读确认2课堂自动导入，无虚构课时；测试临时数据清理，16表计数恢复，模型调用156→156。未测PG/公网/多实例，个人学习路径未自动叠加。

## 交付功能联动复核（2026-10-22，修复前历史记录）

- 对截图对应的打卡/课堂广场/课表交付重新测试：现有6文件28项通过，当前8001/8005真实HTTP闭环及5175 Chromium 16项通过；临时数据清理，15张表计数恢复，模型调用156→156。证据 `artifacts/linkage-20261022/`。
- 新增 `tests/unit/test_schedule_linkage_boundaries.py` 两项均失败：跨周调课通知已发但目标周课表漏课；两门课调整到同一时段仍200。业务逻辑本轮未修改，不能宣称完整验收通过。下一步修复 `classroom_schedule.py` 的跨周实例补入及实际调整后的冲突校验，复跑失败用例和相关回归。
- 报告 `docs/交付功能联动性测试报告-20261022.md`；新增真实服务验收脚本 `scripts/verify_delivery_linkage.py`（备份/断言/清理计数），浏览器脚本支持独立证据目录，避免覆盖旧结果。

## 平台学习打卡 + 课堂广场 + 课程表（2026-10-22，按最新口径修订）

最终口径：**平台学习打卡完全独立于课堂/考勤**，每自然日最多一次、无需加入课堂；课堂是可选协作入口，学生自主加入/退出；加入后教师课程安排自动同步到个人课程表。

- 新增 `platform_daily_checkins`（唯一 user+date，无 class/course 引用）、`class_sessions`、`class_schedule_exceptions`；课堂表新增 join_mode/description/objective/syllabus/semester/is_public/capacity；Alembic 0037/0038/0039。旧的多条自主打卡表 `study_checkin_logs` 已删除（仅含本轮测试遗留的 5 条孤儿记录，无真实用户数据）。
- 后端复用 teacher_service（8005）：`/learning/checkin/daily*`、`/learning/classrooms/{plaza,mine,{id},join,leave}`、`/learning/classes/{id}/schedule*`、`/learning/schedule/me`；排课冲突/容量/权限全部后端确定性校验，关键写入事务化，调整与通知同事务。
- 前端新增：学生「课堂广场」「我的课堂」（原班级空间改造，含退出）、「我的课程表」（周视图/今日/调课标记）、「平台学习打卡」（一键/连续/日历/历史）；教师「课程安排」（排课/停课/调课/补课）；管理员只读审计。
- 验证：checkin 9 项（含并发）、plaza 3 项（容量/退出/私密）、schedule 2 项（冲突/调停补/退课）pytest 通过；班级/通知回归 12 项通过；真实 HTTP 运行库全链路（无课堂打卡→广场选课→课程表同步→停课移除→课堂任务/审核→签到→通知→持久化）通过；真实 Chromium 16 项通过，pageErrors/5xx 空；build 退出 0；Ruff 通过。临时账号与业务行清理，users 仍 96。
- 运行库已先备份再增量应用 schema（`artifacts/checkin-20261022/runtime-before-*.sqlite`），仅重载 8005（最终 PID 49376）；本轮无模型付费调用。
- 缺口（详见 docs/checkin-classroom-plaza-20261022.md）：课程表未叠加个人学习计划；无教室资源冲突；课堂封面/详情独立页未做；管理员只读；签到二维码图片未渲染；课堂任务附件 UI 未接；到期自动提醒未调度；平台打卡未写入画像/推荐；未验证 PG/公网/多实例。

## 学生作业附件与教师预览已接入（2026-10-22）

学生支持照片、Word、PDF、Excel、PPT、文本及ZIP，单文件20MB/最多10个/总计100MB，允许仅附件提交。教师提交详情与学生本人共用预览下载组件：图片/PDF在线、DOCX与文本安全文字预览，其余下载原文件。私有原件、草稿、提交/历史关联及角色权限完整；已评分禁止覆盖，保留原始字节。

15项后端回归、29项前端测试/build通过；隔离真实浏览器11组通过（仅附件PNG/DOCX/PDF→教师预览/原字节下载→94分批改→学生回看、重启/越权/重试），临时数据清理，付费0。当前8005已加载路由且运行库已存在附件表，本轮未重复迁移/重启；备份/副本0036演练与结构/完整性及师生实际只读200检查通过，业务计数不变。证据artifacts/homework-files-browser/、homework-files-unit-final/、homework-files-runtime/；说明docs/作业附件上传与教师预览-20261022.md。真实账号未写测试作业，未验公网/外部DB，未提交推送。


## 同浏览器师生标签页身份混用修复（2026-10-22）

学生端Requires student、教师端Requires teacher/admin的同源根因已实证：Pinia显示旧账号，Axios/助手流每次却取共享localStorage最新token。修复前同context双标签真实登录复现班级GET/POST403（artifacts/auth-tab-baseline/）。现按sessionStorage标签页隔离登录，HTTP/SSE取当前Pinia；校正users/me返回身份、旧请求401/旧身份响应防串号、退出不清他账号；教师刷新成员同步人数、避免切班旧响应覆盖，失败不显示空洞察，同名班级显示编号。

29项前端测试/build通过；同context四账号真实密码登录的成员/洞察/入班/课件/提交/94分批改/通知/重启/权限10组通过（artifacts/auth-tab-final/，清理账号班级0，模型调用0）。当前5175的teacher111/student共享浏览器只读验证班级4人数1/成员1、班级3人数2/成员2及学生洞察成功，errors/failures空（artifacts/auth-tabs-current/）。只改前端，无DB/业务成员修改、无后端重启；保留当前浅色主题，仅修默认常量未用的TS错误。报告docs/师生同浏览器身份混用修复-20261022.md。旧页面若缓存已混用需两标签分别重新登录一次。

## 师生业务闭环修复已启用（2026-10-22）

沿用原FastAPI/SQLite和通知系统：班级邀请码/轮换/启停/成员管理、学生自主查找入班与真实班级列表、作业本人提交/成绩/评语/历史、教师按作业选择学生批改（去除内部ID输入），失败/空态分离并提供重试。已评分禁止学生覆盖，重复请求幂等，SQLite写事务加锁。教师范围校验入班、事务与路径一致，后入班继承全班范围，移出后撤销范围和活动路径；班级练习复用common.learning_evidence有效证据，展示真实作业统计，不读跨课程全局报告。

0035已备份/副本演练后增量应用当前runtime.sqlite并重载8005，未stamp/全量upgrade。users96/classes3/enrollments8/assignments2/submissions0/resources120/paths172/notifications14/model_calls156前后不变；teacher111班级/作业接口200。历史列表失败当前未复现，不能归因于跨库或缺路由。

完整unit811通过；69项师生/通知/上游兼容通过；最终证据规则补测+全部integration为65通过2个原有opt-in跳过；前端21测试/build通过。真实隔离浏览器双账号密码登录、创建班级→邀请码入班→课件范围→发作业→提交→94分批改→学生查看→双端通知→API进程重启/重登录持久化、越权、网络失败重试9组通过，无业务Mock或付费调用，临时账号/班级清理0。证据artifacts/teacher-loop-browser-evidence/；运行库备份及激活artifacts/teacher-loop-runtime/；报告docs/教师端与学生端业务闭环修复验收报告-20261022.md。

边界：完整写入链在同一隔离真实服务/DB验收，当前5175/teacher111只读复核8模块通过；未改真实班级成绩。练习历史无原生class_id，以成员+学科+教师范围权威知识点关联，不声称恢复历史练习发起班级。SQLite已验，外部DB与付费生成未验；未自动提交推送。保留同期其他修改。

## 教师模块空白修复与实际服务验证（2026-10-22）

教师 TeacherView 原为多个顶层节点，直接作为 AppLayout 的 out-in Transition 子组件存在页面切换消失风险。保留工作区已有 TeacherView 单根包装修正，本轮 AppLayout 再改为对固定 div 容器执行页面动画，兼容包含弹窗/抽屉的多根路由页。没有改变教学数据、权限或主题偏好。

build 退出0；scripts/verify_teacher_navigation.py 使用 teacher111 只读检查实际5175和后端，无API mock/无模型调用：八个入口连续点击两轮，教学分析直接进入、刷新、390px手机和深浅主题均通过，pageerror/过渡警告/相关HTTP失败均空。证据 artifacts/teacher-navigation-20261022-000321/result.json 及截图；构建 artifacts/teacher-navigation-build.log。账号当前无班级，验证了正确空态，未声称班级教学数据全链路已测。脚本只在子进程环境内传临时JWT，不写凭证文件。

## 远端a6f5e783已增量融合并激活（2026-10-21）

导入origin/main新提交21个路径，保留运行锁和原19个修改文件；HEAD605feaab保留，本次是工作区内容融合，未自动提交/推送，Git仍behind1。课后练习1～25题/按账号偏好与旧会话恢复、图谱url/provider/kind及真实参考链接、计划no_change防崩、教师JWT转发/UTC时间和部署模板已接入。补QA旧10题上限、助手中文1/2及完整数字/每批≤10题稳定键、审核重试保留去重和计划、图谱安全URL/精确匹配、练习手机单栏。未改变原公共知识Search/Fetch缺口，不自动发布远端三份语料。

175项Python定向通过，最终build退出0/5.03秒；隔离5组真实API/持久化浏览器通过（模型受控），实际5175/8002三组UI/schema/图谱检查通过，pageErrors均空。无活动任务核对/SQLite备份后重载8002/4/5/7和Worker，无迁移；激活model_calls155不变，随后专用浏览器156→156，专用用户/活动已清理，本轮付费0。当前错题本/收藏本已有LearningContent统一正文渲染，追加Node24下17项格式测试通过；默认Node22的undici环境失败日志保留，未改系统默认环境。格式显示统一不等于历史JSON/转义已全库清洗。保留同期格式/视频/通知修改，未声明全站/真实25题模型质量已验收。详见docs/upstream-fusion-a6f5e783-20261021.md、artifacts/upstream-fusion-a6f5e783/。


## 全局学习内容格式规范化已落地（2026-10-21）

用户截图指出错题本/收藏本仍输出普通文本（`$\frac{x^2-1}{x-1}$` 原样显示）。根因不是缺渲染器，而是各页面各自决定：部分走 `renderLearningMarkdown`，部分仍是 `{{ }}`，`.learning-markdown` 样式也散落在多个组件，`ProfileAnalysisView` 甚至有一份不含 KaTeX 的本地实现。现收敛为唯一入口 `components/LearningContent.vue`（props：content/inline/tag/empty/clampLines）+ `styles.css` 的全局 `.learning-markdown` 规则；渲染器允许 `$...$` 内单换行（长公式被模型折行不再退化为源码）。错题卡片预览由 `slice(0,80)` 改为渲染后 2 行折叠，不再切断公式。

已迁移：错题本、收藏本、练习测评、笔记与闪卡、学情报告、资源、知识库、班级讨论、工作台、画像分析（删除本地实现）、成绩分析、教师端，以及课件阅读器/学习概览/计划反馈三件套。tsc 0、vitest 21 项通过（新增渲染器 8 项、组件 6 项、错题本+收藏本 3 项）、build 0；5175 真实 Chromium 渲染检查见 artifacts/global-format-20261021/format-check.png。未用验收账号在真实页面做端到端点击；`AssistantPet` 来源摘要是 `slice(0,180)` 的截断摘要，故意保留纯文本。详见 docs/global-learning-format-20261021.md。

## 全局视频公式排版已激活（2026-10-21）

用户明确要求全局视频规则。自动课件视频、单独制作及学习工作区导出共用render_video：网页/视频复用Markdown+KaTeX，Chromium本地排版按真实行/公式/表格行分页，取代纯文本30字硬切；无效公式阻断。来源为所选资源正文、本机合成无声WebM，页面标明。math-v2缓存隔离旧文件。12项回归、Ruff、前端build通过；真实334公式/34页预览检查。备份runtime.sqlite并确认无活动任务后重载8002/8007/Worker，已有8段视频重制、解码和鉴权HTTP200通过，模型台账155→155；无迁移/正文修改/自动提交。依赖现有Node/前端包/Playwright Chromium；未全站或三个前端入口交互复验。详见docs/video-math-global-20261021.md和artifacts/video-math-20261021/。

## 学生/教师统一消息通知已在当前平台激活（2026-10-21）

公共AppTopbar复用NotificationCard：右上角默认收起、分页下拉/外部及Escape关闭、详情/幂等已读/全读/完整消息中心，移除班级页旧大通知面板。原Notification扩sender/event/read_at，0034与dispatch回执去重；8005统一收件箱与管理员/本人课程班级发布，最多5000人，读取重新检查当前成员关系。接入作业发布/提交聚合/批改、课程提问回复、真实助手及知识任务终态/中断、知识请求处理、计划反馈确认；15秒轮询+退避/online/Storage同步。不存在的截止调整、课程资料分发/审批没有虚构。

实际runtime.sqlite先备份/副本演练再定向0034，没有stamp/全库升级；8002/5/7和Worker重载，5175已可用。82项定向回归通过；最终9项通知含6线程去重及11项事件回归通过（有重叠），知识中断专项见knowledge-delivery；最终build通过。实际5175专用账号浏览器六组闭环/pageErrors空，含课程提问回复、多标签页、断网与390px；验收账号及业务清理完毕。用户96/资源118/计划162/笔记2保留，model_calls133不变，本轮付费0。磁盘曾不足导致一次测试失败，后串行复验通过；自动审批拒绝临时目录清理，目录保留。未全站/PG/大规模长时验证，未自动提交，保留其他会话改动。完整文件/接口/限制/证据见docs/unified-notifications-20261021.md及artifacts/notifications-20261021/。


## 公共知识自动建设与模型审核（2026-10-21）

用户明确要求缺失知识自动建设公共知识，由模型审核，不等待管理员，也不回退个人临时草稿。新增 public_knowledge.py 和两份 Prompt；学习计划及有学科上下文的课件/习题补充共用入口：公共版本预检→模型建设→独立模型全文审核→现有发布/文件/索引验证→重新检索。审核仅接受严格 PASS，正文哈希绑定；拒绝最多修订一次，不可用/发布失败阻断。新公共内容不输入私人画像/附件；旧私人资料保留。自动发布使用真实正文摘要标识，不伪造外部授权链接。既有公共版本可跨用户复用。管理员原治理入口保留，但不是新链路审核前提。

无费用隔离定向回归97 passed/341 warnings（artifacts/public-knowledge-model-review-20261021/unit-final-v3/command.log），前端TypeScript/Vite构建退出0；改动导入/未使用检查通过，未声明全仓lint/全站验收。未使用真实Provider、未修改共享数据库、未重载现有API/Worker；代码需由后续运行环境加载。普通只读知识搜索、教师私人范围及历史个人草稿兼容不等于自动公开。先推送修复，再编写详尽Prompt/工具/实现链路文档；保留既有文档与.workbuddy未提交改动。


## 管理员数据看板完整重构（2026-10-21）

`/admin` 接入 OperationsDashboard（dashboard/独立组件）：四项KPI、请求模型/真实工具趋势及环图切换、Worker状态/全部注册、预算与Token、任务状态及最近6条。UTC自然日7/30/90/自定义、日/周聚合、图例、点选筛选、任务/调用抽屉、PNG/同筛选CSV、独立失败/取消请求/重试齐备；原统计/快捷入口/完整运营面板按需折叠保留。工具依provider=deepseek-tools，不能按模型名猜测；预算未配不算百分比、缓存不重复、Token已知小计、成功分母仅成功+失败。助手看板入口预留在顶栏，展开层和其他页悬浮按钮Teleport到body，保留拖动/会话功能。

后端新增 /admin/dashboard、/admin/operations/tasks、/admin/usage/export，增量扩展usage日期/搜索/类别、预算及Worker，复用admin鉴权。18项隔离回归通过，Ruff通过；现有5175→8002真实管理员浏览器通过（5种尺寸、原生图例/点/任务柱、日期、周聚合、工具明细、PNG/CSV、503部分降级/重试、助手及原任务页），pageErrors为空。最终证据 `artifacts/admin-dashboard-20261021/activation/delivery-live-browser-v3/`，本轮台账104→104、Provider请求0。已备份实际runtime.sqlite且无排队/运行任务，仅重载8002 PID10616（lifespan off），Worker20348及其他服务保留；无迁移/自动提交。

详见 `docs/admin-dashboard-20261021.md`（完整文件、接口、口径和验证清单）。历史预算配置/账单金额/未接入历史/Worker历史在线率仍未知，未伪造；未进行全站回归、大规模压测或长时间内存分析。P2个性化布局/自定义报表未实施，其他项目融合事项仍按原状态。保留同期全部改动。

## 公共生成链路与多入口验收（2026-10-21）

用户澄清修复全局生成机制。公共资源/练习服务统一学科上下文和补充资料获取；Coordinator共享检索避免重复；最近30天本人候选复用，保留审核发布边界和入库编号；索引失败仍可读真实本地语料。课件按用户/目标/学情/资料/模板及性能篇幅指纹跨请求复用，明确重生成仍新建；篇幅预算实际生效，notes/exam不再强套旧课件栏目。所有课件生成共享本地无声WebM与Reader播放器，历史课件可单独制作；工作区资源挂到精确任务下，自动打开结果、保留同任务练习、公式渲染和分章预览。

140项组合回归、24项定向（重叠）及前端build通过；运行库副本三入口真实视频播放/移动布局通过，任务完成提示采用受控回调。实际5175/原API/Worker本地视频及资源读取验证见artifacts/generation-global-20261021/current-browser-v3，模型台账71→71。8002/8007/Worker按无活动任务检查、SQLite备份后重载，PID49204/57892/20348，未迁移。新模型内容质量、首次生成耗时、真实Search/Fetch补充效果尚未验收；不能宣称全局质量已通过。详见docs/generation-global-repair-20261021.md。保留全部既有及同期未提交改动。


## 调用台账可视化（2026-10-21）

按用户参考图将 UsageWorkerPanel 改为四项指标卡、每日调用/Token 柱状图、功能/请求模型环形图和预算进度；UsageChart 为本地轻量图表，无新增依赖。保留预算设置、环境/时间/状态筛选、分页、所有分组明细及 Worker 表；未知 Token 标记已知小计。复用原接口，未修改共享库/后端/模型调用。近 N 天沿用接口滚动时段，按 UTC 显示覆盖的 N+1 个自然日。

前端 build 通过（4.08秒），最终 TypeScript 检查通过；5175 页面使用拦截 API 测试数据完成四图表、未知用量、分页、环境切换复位、390px无页面溢出、空态和503清空旧指标浏览器验收，pageErrors空。截图与结果 artifacts/usage-dashboard-20261021/；本轮未进行真实登录接口端到端复验，原5175 Vite可热加载。保留其他会话未提交改动。


## 课件统一取消流程图（2026-10-21）

用户要求不只处理单份课件，后端生成规则同时修改：resource_gen.md和exercise_gen.md禁止Mermaid flowchart/graph，以文字步骤、状态/过程表替代；courseware_quality章节规划改为“步骤与状态对照”，质量门禁拒绝流程图。阅读器对历史正文仅隐藏流程图及其专属标题，保留数据库原文和其他讲解。8项Prompt/分章回归、前端构建通过；实际5175资源222→225浏览器验证无流程图、旧学情隐藏、目录定位保留，付费调用0。8002/8007及Worker重载，无迁移。证据artifacts/teaching-no-flowchart-20261021/。新规则未新增真实模型生成验收（此前授权已用尽）。


## 独立课件页实际入口追修（2026-10-21）

用户截图证实旧正文/目录失效：CoursewareView旧锚点不再存在，sessionStorage一直展示资源222。现目录直接控制Reader实际章节；刷新回读服务端、停用旧学情段落，并按本人/正式知识点ID/学科提示打开已存在九章新版225（12699字符），不会改写历史。重生成使用当前主题且不复用完成任务pending键。

resource_gen/exercise_gen内部模板完整重写，实际调用链重读模板；取消无证据强制风格个性化，加入逐步推演/边界/验算/题型解析合同，课件指纹存Prompt hash。核心章输出上限3600、其他2400，服从显式更低限额。44项回归、最后8项Prompt/分章测试（重叠）、构建通过；运行库副本及实际5175资源222→225桌面/移动点击目录滚动验收通过，pageErrors空。相关8002/3/7及Worker重载，无迁移。本轮0模型调用，当前共享台账29前后不变、作答67。

详见docs/teaching-followup-20261021.md与artifacts/teaching-followup-20261021/current-browser/。225早于本轮Prompt追修生成；新模板仅验证实际消息与业务回归，未新增真实模型质量验收（上轮授权次数已耗尽）。保留其他会话改动，未自动提交。


## 笔记历史/分类与闪卡证据已在当前平台激活（2026-10-21）

新增0033（三张独立表，无旧列改写）、common/study_evidence.py和StudyToolsView：真实来源学科/资源/知识点筛选、摘录/版本、追加历史及旧标签页CAS保护；笔记→闪卡来源绑定、到期复习回执去重、卡片/事件/画像自评/有效任务证据同事务。自评独立于习题掌握度，不自动完成任务；来源已变更只继续私人复习，不写新计划。用户服务增加请求追踪以支持实名调用预算。

实际运行库study_notes缺0028的三个可空来源列，已先备份/副本演练再补齐及建3表，仅重载8001（最终PID45480）；保留同期学情修复，未全库upgrade/stamp或自动提交。当前5175 `/student/study-tools` 两组浏览器业务通过/pageErrors空，使用独立私有验收账号，不给真实用户灌入自评分数；本轮model_calls前后仍18、付费0。global-unit-final：681 passed/2526 warnings；随后追踪追加7项定向通过；0032↔0033与上下文至当前head演练均保留旧数据，前端build退出0。证据 artifacts/aura-study-20261021；完整范围/文件/失败/恢复见 docs/aura-full-integration/14-note-card-current-runtime.md。P1-07完整AI图文编排、视频URL及全18项/A–E仍待继续，勿宣称全功能融合完成。以下保留其他会话及历史状态。

## 学情归属修复与分章课件交付（2026-10-21）

同备份复现：用户6冒泡排序旧实现5次/60→当前0条有效证据/null，TCP作答保留。point-evidence-v4统一归属/权重/去重/低样本状态；93画像重算、120历史报告失效、67原始作答保留，37个悬空归属题目待可靠归类。runtime.sqlite已备份定向修复，未执行共享库Alembic升级/stamp。

teaching-v2九章生成/检查/断点、章节修订新版本、真实Exercise和统一阅读器已落地。137项回归及最后30项通过（有重叠不累加）；最终构建及四类真实正文浏览器验收通过，含乱序切换、跨用户拒绝、任务刷新恢复。重载8001/2/3/4/7及Worker，最终七服务健康、路由可见、Worker68224心跳新鲜，共享model_calls仍18。保留其他会话修改。

本轮真实模型预算已耗尽：40次Chat、实际输出27124 Token、Search/Fetch=0，不再付费调用。四类正文超1万字符；结构通过不等于学科审核，空来源标记模型未核验。两处错误定向修订，其他内容仍需复核。详见 docs/teaching-evidence-courseware-repair-20261021.md，证据 artifacts/teaching-evidence-20261020/。下一步仅在新任务下处理历史归类或专家审核。


## 当前平台直接可用修复（2026-10-21）

用户要求以实际页面可用为准。本轮核查发现8002已加载新路由，但 `/admin/operations` 仍500；Worker82280为旧进程，无注册心跳；Token面板被任务概览的v-if隐藏；旧计划新建同名知识点导致本人旧课件409。实际运行库是 `artifacts/local-start-20261019/runtime.sqlite`，不是根目录learning_system.db，不能用后者缺表清单诊断当前服务。

已备份实际运行库、重载8002和Worker（最终API PID83068、Worker79584；保留原端口/数据库/凭证环境，不重启其他服务），运营200、18条LIVE台账可读、Worker ONLINE。Token/心跳面板独立显示，菜单改为“AI用量与任务监控”。新增管理员 `/admin/model-budget` GET/PUT，以SystemConfig持久保存平台/每用户日调用限额；API/Worker下次调用自动读取，环境更严上限不可放松，当前原有未设限策略保留。新增资源中心本人导图编辑/历史API，不再要求先有学习计划。修正旧资源私有知识点复用，不弱化资源归属。

当前5175真实浏览器已通过：预算页面保存、LIVE台账/ONLINE心跳、真实旧课件→独立Worker→PPTX下载/SVG帧变化/WAV播放、执行尝试、资源中心导图示例编辑/保存/历史/读回；pageErrors空，模型调用前后均18，本轮付费0。导图仅新增标明“导图编辑验收示例”的私有本地模板，不改用户原导图。证据 `artifacts/aura-availability-20261021/current-browser-final/result.json`；定向回归32项，随后新增资源中心导图权限/旧版本用例5项通过（有重叠不累加）；最终build退出0、3.72秒，修复同期Mermaid未使用变量导致构建失败。Ruff定向通过。当前入口/备份及限制见 `docs/aura-full-integration/13-current-runtime-availability.md`。历史“共享服务未激活”的结论已过时，以下为历史。

## 最新 学习工作区通用可打开 + 管理端运营数据修复 + 知识自动融合决策层（2026-10-20 夜）

- **学生工作区 409 修复（截图 2）**：`common/learning_context.create_context` 不再因「计划学科不在公共目录」直接 409；任何本人计划（旧计划 `knowledge_scope=None`、个人草稿、LLM 子知识点）都回退到 owner-scoped `personal KnowledgePoint`（`subject_id=None`，`PERSONAL_DRAFT`），工作区可直接打开，公共目录零污染。测试：`test_legacy_plan_with_unknown_subject_can_open_workspace_context`。
- **管理端「任务运营数据暂不可用」修复（截图 1）**：根因 `operations.task_summary` 访问 `task.started_at`，而 `KnowledgeBuildTask` 无该字段 → 500。改为 `getattr(task, "started_at", None)`；测试 `test_operations_handles_knowledge_task_without_started_at`（`/admin/operations` 200）。另修该文件 pre-existing I001 行内 import 顺序。
- **知识自动融合决策层（第一增量）**：新增 `services/agent_service/app/services/knowledge_fusion.py`——`classify_candidate`（学科→章节→知识点分层匹配，优先已有 code/别名，不靠关键词相似）、`assess_quality`（长度/来源可追溯/损坏等**非模型**规则）、`decide_fusion`（A 新建 / B 补充 / C 修订 / D 重复 / E 冲突）、`auto_publish_allowed`（默认人工审核；仅 `strict_auto` 且质量+归类通过且 create/supplement 才自动发布；revise/duplicate/冲突强制人工）、`fusion_summary`（管理员统计）。新增测试 `tests/unit/test_knowledge_fusion.py` 5 passed；Ruff 通过。
- **提交**：`d3eb8fe`（工作区+运营修复）、`1c302b2`（融合决策层）。**注意**：工作树当前有另一并发会话的大量未提交改动（`learning_evidence`/`report_service`/迁移 0032/courseware 等），本轮只提交上述自有文件；`create_context`/`operations`/`knowledge_fusion` 需在并发改动稳定后重启 8002 才生效。
- **剩余（融合全链）**：把 `knowledge_fusion` 接入候选处理/发布流程（`knowledge_tasks`/`knowledge_candidates`/`publish_candidate`）、管理员融合统计页面、自动发布策略配置、索引一致性重试、学生端检索联动、10 条验收场景。

## 最新 学生端自主学科建设 P0-1 / P0-2：建设式门禁 + 个人学科草稿（2026-10-20）


按新任务（学生端自主学科建设/知识补全/计划全链路）落地 P0-1、P0-2：`SUBJECT_MISSING` 不再终止学生请求，缺失时自动构建**个人学科草稿**并据此生成计划。

- **P0-1 门禁**：新增 `plan_knowledge.assess_plan_knowledge`（返回 `mode`：public / personal_draft，缺失时不抛 409 但记录缺口）；`coordinator._execute_agents`、`generate_path`、`/paths/preflight`、`/paths/generate` 全部改为建设式；前端 `LearningPathView.checkKnowledge()` 对 personal_draft 继续生成（info 提示）。
- **P0-2 个人草稿**：新增 `knowledge_bootstrap.build_personal_draft`——按 `actor_user_id + subject` 在 `KnowledgeBuildTask(operation_type="PERSONAL_SUBJECT_DRAFT")` 中持久化 `SubjectOutline` + 检索 chunks；**不写公共 SystemSubject/KnowledgePoint**、不建平行库；同一学生复用（不重复生成）、跨学生隔离。LLM 出大纲走 `plan_subject`（schema 校验）且受 `RUN_LIVE_LLM=1 && DEEPSEEK_LIVE_PAID_ACK=1` 双闸门，未授权时用确定性草稿（标 `source=deterministic_fallback`）。
- **自动续接（P0-5 部分）**：`generate_path` 在 personal_draft 时先建/复用草稿，把草稿 chunks 作为 `retrieval_context` 喂给计划模型，同一请求内续接出稿；计划标 `knowledge_scope="personal_draft"`、`knowledge_draft`、`knowledge_draft_task_id`，**不冒充公共正式知识**。
- 证据：`test_plan_knowledge_p1.py` 10 passed（未知学科→personal_draft、不建公共学科、缺口=1）；新增 `test_knowledge_bootstrap.py` **3 passed**（个人且可复用、跨学生隔离、generate_path 用个人草稿 chunks 接地且无 subject_id/versions）；相关回归合计 **48 passed**；改动文件 Ruff 通过；前端 build 退出 0。
- **P0-4 个人草稿向量可检索**：`knowledge_bootstrap._index_personal_chunks` 把草稿 chunks upsert 到 Chroma（best-effort，metadata 带 `owner_user_id`/`scope=personal_draft`）；`rag._normalize_filters` 允许 `owner_user_id/scope`；新增 `ChromaRetriever.retrieve_personal(user_id, …)` 仅按 owner+scope 检索；`knowledge_publication.visible_chunks` **fail-closed 丢弃 `scope=personal_draft`**，公共检索永不泄露个人草稿。
- 证据：`test_knowledge_bootstrap.py` 5 passed（+visible_chunks 丢弃个人草稿、retrieve_personal 只按 owner+scope）；knowledge/rag/publication 相关 89 passed；改动文件 Ruff 通过。
- **P0-3 搜索抓取与候选（已真实跑通）**：`_search_and_fetch_personal`——受双闸门（`RUN_LIVE_LLM=1 && DEEPSEEK_LIVE_PAID_ACK=1`）控制，用 `search_sources(query, need_content=True)` 取回真实来源正文（**发现 `/v1/tools/fetch` 在 DeepSeek 公开 API 上 404 不存在，改用 search 内联 `content` 替代**），落 `KnowledgeCandidate(status=DRAFT, subject=personal_<hash>)`；`deepseek_search` 新增 `DEEPSEEK_SEARCH_ALLOW_FAKE_IP=1` 显式放宽 SSRF（本机 fake-IP DNS）。真实证据：搜到清华《数据结构》第3章，正文 6528 字，候选 #1 DRAFT，草稿 37 chunks（含 1 条真实正文）。
- 证据：`test_knowledge_bootstrap.py` **9 passed**（+SSRF 开关、未授权不调用、授权时用内联正文建候选）；相关回归 **106 passed**；改动文件 Ruff 通过；前端 build 退出 0。
- **真实 HTTP 全链路验收（2026-10-20）**：运行库已建立 5 个真实学科（数据结构/计算机网络/计算机组成原理/操作系统/离散数学，194 知识点）；`GET /knowledge-base/catalog/subjects` 返回真实目录（DB 驱动，前端不再硬编码）；工作区 `POST /learning/contexts` 对计划 154 解析到**真实知识点 id=437（链表）**（`build_subject_outline` + `_snap_tasks_to_real_points` 生效）；`POST /paths/task-feedback/preview` → `added=1、impact 2→3`，`POST /paths/feedback/{id}/confirm` → `applied`，重放 → `already_applied`（幂等）。**P0-1~P0-4 + 真实知识点吸附 + 工作区 create_context 修复均已完成。**
- 剩余：P0-7 前端异步进度面板（当前同步生成）、P0-8 A–G 浏览器 E2E（需一次真实计划生成调用）。运行中 8002 已重启（PID 44292）加载最新代码；真实 Search/计划生成需 `RUN_LIVE_LLM=1`+`DEEPSEEK_LIVE_PAID_ACK=1`(+`DEEPSEEK_SEARCH_ALLOW_FAKE_IP=1`)。

## 最新 AI 内容编排真实可用性修复（2026-10-20；提示词/Provider/改写接口已 LIVE_VERIFIED）

本轮定位并修复管理员端截图中的"提示词列表获取失败 / Provider 状态失败 / AI 改写失败 / 章节配图只有读取入口"：

- **根因**：agent_service 8002 仍跑 P1-07 之前的旧代码，前端 5175 已热加载新导航但后端 `/admin/prompts`、`/admin/image-provider`、`/admin/resources/{id}/rewrite|sections|illustrations` 全部 404。已按 `artifacts/local-start-20261019/start.ps1` 同款 runtime.sqlite + env 重启 8002（`--lifespan off`），openapi 现含全部 admin 路由；真实 HTTP 验证 prompts=200/11 模板、image-provider=blocked、sections=9 节、rewrite=blocked(未授权)、illustrations=blocked(未配置)。
- **提示词统一加载**：`resource_generation/exercise_generation/feedback_synthesis` 三处 `_load_prompt_template` 的 lru_cache 改为 `prompt_registry.load_prompt_template`（按文件 mtime 失效），管理员编辑后新生成无需重启即生效。
- **提示词版本生命周期**：`prompt_registry` 新增 `.history/` 文件式快照 + `list_prompt_versions/read_prompt_version/restore_prompt`；新增路由 `/admin/prompts/{name}/versions[/{version}][/restore]` + 前端 prompts.vue 版本列表/恢复 UI；`.history/` 已加入 .gitignore。
- **图片 Provider 状态细分**：`image_provider_status` 增加 `enabled/health` 与 `blocked/invalid/disabled/configured` 四态；`PUT /admin/image-provider` 支持 `enabled`；前端类型/展示同步。
- **AI 改写付费闸门**：`rewrite_resource` 增加 `RUN_LIVE_LLM=1` 且 `DEEPSEEK_LIVE_PAID_ACK=1` 双闸门，未授权返回 blocked"需要授权"，杜绝后台误触发付费调用（此前会因 runtime.sqlite 缺 `model_calls` 表在 begin_call 处崩溃）。

验证：相关单测 53 passed（test_prompt_admin/test_resource_editor/test_learning_prompt_templates/test_plan_feedback/test_resource_generation/test_structured_resource_generation）；改动 Python 文件 Ruff 通过；前端 `npm run build` 退出 0。真实付费调用 0。未提交、未迁移共享库、未重启 8001/8003–8007/5175。

下一步/阻塞：runtime.sqlite 缺 P1-06 台账表（`model_calls` 等 0030/0031 五表），授权后改写与真实生成需先补齐（共享 SQLite 无可信 Alembic 基线，须先基线审计再定向补表，禁止空库迁移）；孤儿模板 coordinator/knowledge_graph/learner_profile/path_planning/qa 无生成消费方，需接线或移出白名单；图片生成后端接入仍属 P1-08。详见 ADMIN_FUNCTION_FUSION_MATRIX.md 本轮注记。

### 续：补齐台账表 + 打通真实改写调用（用户授权后）

- **补齐 12 张缺失表**：runtime.sqlite 经 ORM 对照缺 0026–0031 的 `model_calls/worker_instances/task_attempts/resource_revisions/resource_artifacts/study_sessions/study_activities/learning_contexts/context_exercises/learning_knowledge_gaps/knowledge_documents/knowledge_document_points` 共 12 表。已用 `Base.metadata.create_all`（幂等，只建缺失表）补齐，改前用 sqlite3 backup API 备份至 `artifacts/local-start-20261019/runtime-before-tables-20261020-200640.sqlite`。
- **打通真实 AI 改写**：8002 以 `RUN_LIVE_LLM=1`+`DEEPSEEK_LIVE_PAID_ACK=1` 重启后，`POST /admin/resources/220/rewrite` 真实调用 deepseek-chat 返回 `status=generated`（改写 2810 字符），台账 `model_calls` 记录 LIVE/SUCCEEDED/KNOWN，input 1597 / output 1535 tokens。`PUT /admin/resources/{id}/content` 应用改写成功，`resource_revisions` 写入旧版本快照（resource 220 已用快照回滚还原，无残留）。用户已授权本轮真实调用预算。
- **剩余真实调用缺口**：章节配图/图片生成后端未接入（无图片 Provider 凭据），需用户提供 `IMAGE_PROVIDER_API_KEY/BASE_URL/MODEL` 才能接真实图片生成；否则保持 blocked 安全态。授权环境变量需在重启 8002 时一并注入，否则改写回到 blocked。

### 续2：清理 5 个孤儿提示词模板

`coordinator/knowledge_graph/learner_profile/path_planning/qa` 五个模板无任何加载方（coordinator/qa_service 仍硬编码 inline prompt；PPT slide10 的「加载 prompts/*.md」是设计稿而非实现），已从 `prompt_registry.ALLOWED_PROMPTS` 移除，管理端「提示词模板维护」现只显示 6 个真实被生成链消费的模板（resource_gen/exercise_gen/evaluation_feedback/mind_map_gen/code_case_gen/video_script_gen）。文件保留在 `prompts/` 未删除；接线统一（把 inline prompt 迁到模板加载）是 61KB coordinator 的独立重构，记为后续任务而非隐藏。单测 25 passed、Ruff 通过；8002 已重启加载新白名单，`GET /admin/prompts` 现返回 6 条。

## 最新 学习计划反馈闭环 + 两个 API 错误修复（2026-10-20；总体仍PARTIAL）

本轮完成“计划生成→预览→自然语言反馈→AI调整→差异预览→确认”的计划制定反馈闭环，并定位两个 API 错误根因。

- 两个 API 错误根因：运行中 8002 agent/8004 evaluation 是旧进程（10-19 23:43 启动，早于路由提交），且共享 `learning_system.db` 无 Alembic 基线、缺 0026/0028/0029 表。源码路由均在，隔离“最新代码+`upgrade head`(0031)”验证 `learning/contexts/*`、`overview/me` 由 404→401 且 openapi 可见。**未迁移共享库/未重启共享进程**（无基线，禁止直接 upgrade）；上线需一次性基线审计+备份+定向补表（沿用 runtime.sqlite 副本补列模式）。
- 新增 `plan_feedback.py`（PlanFeedbackService + compute_plan_diff）、`task_feedback.py`（TaskFeedbackService，8 类任务级执行反馈，确定性改稿无需 LLM）；路由 `POST /paths/feedback/preview`、`POST /paths/feedback/{id}/confirm`、`POST /paths/task-feedback/preview`；复用 path_revision CAS + applied_feedback 幂等，确认保留已完成任务、删除已完成任务记入 removed_completed_history，无凭据 503、真无变化 no_change。
- 前端 `PlanFeedbackPanel.vue`（计划级）+ `TaskFeedbackButton.vue`（每任务反馈弹层）接入 `LearningPathView.vue`。
- 证据：test_plan_feedback.py 7 + test_task_feedback.py 7 + test_path_adaptation 5 = **19 passed**、Ruff 通过、前端 build 退出0。真实付费 DeepSeek 0。报告 `docs/aura-full-integration/13-plan-feedback-loop.md`。
- 共享环境现状（20:22 复核，**两个 API 错误均已解除**）：8002 由同期 P1-07 会话重启、8004 evaluation 由本会话重启（均 runtime.sqlite+`--lifespan off`），`learning/contexts/*` 与 `/evaluation/overview/me` openapi 可见、均 404→401；端到端真实断言注册 api-verify 用户 → `/evaluation/overview/me` Bearer 返回 HTTP 200 真实数据（active_plans=[]/due_cards=0/study_seconds=0）。剩余：真实 LLM 修订验收、任务级反馈浏览器 E2E、进度/画像全链 A–E。工作树另含 P1-07 未提交改动（非本任务）。

## 最新P1-07 管理员Prompt优化/改写/图文编排（2026-10-20；总体仍PARTIAL）

本轮实现 P1-07 管理员专用 AI 内容编排子链：
- 管理员 Prompt 优化：新增 `prompt_registry.py`（白名单 list/read/update + 占位符保留校验，路径永不出白名单）与 `/admin/prompts` 路由；前端 `prompts.vue` 提示词编辑页 + `adminNavigation` 新增“提示词与图文配置”入口。
- 改写：`POST /admin/resources/{id}/rewrite` 调用已配置文本模型（无凭据返回 `blocked`，不伪造改写；真实调用走 P1-06 台账）；`PUT /admin/resources/{id}/content` 应用改写并保留 ResourceRevision 快照 + 审计日志；资源管理页新增改写/应用 UI。
- 图文编排/图片 Provider：`GET/PUT /admin/image-provider` 读取/保存非敏感 provider 名称+模型；`GET /admin/resources/{id}/sections` 列章节；`POST /admin/resources/{id}/illustrations` 在无图片凭据时返回明确 `blocked`（凭据由部署环境 `IMAGE_PROVIDER_API_KEY` 管理，管理界面不回显）。`common/config.py` 新增 `image_provider_api_key/base_url/model`，`.env.example` 记录。

验证：`tests/unit/test_prompt_admin.py` + `test_resource_editor.py` 共 15 passed；新增/改动 Python 文件 Ruff 通过；前端 `npm run build` 退出 0（tsc+vite 6.68s，仅保留既有第三方 INVALID_ANNOTATION/分块提示）。未做真实 LLM 改写（无付费授权，blocked 路径用桩 LLMFactory 验证）；未接入真实图片生成后端；未重启 8001–8007/5175、未迁移共享库、未自动提交、真实付费调用 0。

恢复入口：改写真实模型链待新一轮付费授权后验收；图片生成后端接入属 P1-08 外部图片适配；P1-07 剩余（草稿审核编排完整闭环）与 P1-08/P1-09/P1-10 继续。以下为更早检查点。

## 最新运营/多模态接续（2026-10-20；总体仍PARTIAL）

本次在原多服务完成ModelCall真实逐调用持久台账/调用与输出预留预算、WorkerInstance独立空闲心跳、TaskAttempt执行尝试；管理员可读LIVE/TEST分离用量、分布、明细、心跳和历史尝试。新增0030→0031五表；LearningContext绑定的PPTX下载重读、SVG动画实际播放、本机Windows Speech WAV存储播放、导图CAS编辑与前后版本历史已接入原AssistantTask/Worker。修复画像聊天/新知识点习题在模型调用期间持有SQLite写锁导致台账互锁。完整文件表与剩余范围先读 docs/aura-full-integration/12-operations-media-acceptance.md。

证据 artifacts/aura-ops-20261020：global-unit-v2为592 passed /2133 warnings；build-final.log退出0、2.89秒；browser-final九组通过/pageErrors空，真实PPTX/SVG/WAV/导图/权限/管理员，生成问答受控桩；独立Worker空闲心跳推进+强制退出后超时；migration-final空库至0031、0031→0028→0027→0031保留原用户笔记，migration-v1另验证0029↔0031；12个新增Python业务/迁移/只读审计文件Ruff通过。

本轮用户明确授权Chat≤6、输出≤6000；实际4 Chat HTTP200、输入5177/输出3432，输出预留6000已用满，停止付费调用。第2次习题截断记失败，重试第3次真实三题无fallback；课件/上下文QA/服务端评分与画像隔离入库通过；供应商金额UNKNOWN，Search/Fetch/外部图片/外部TTS均0。真实模型证据 live-authorized-v2/v3 属同一累计授权，不重置计数。QA测试依赖覆盖导致该条台账用户归属为空，正常JWT归属另测，未扩大为完整付费Worker复合链。

共享库已只读审计：无Alembic版本记录，缺13表及9张旧表字段，详情 shared-schema-readonly.json；不能直接stamp或假设0029基线。遵守任务原限制，未升级共享SQLite、重启8001–8007/5175或自动提交。P1-07管理员Prompt优化/改写/图文编排、P1-08真实视频URL验证/外部图片适配、P1-09笔记历史/闪卡知识点画像、P1-10全部18项及A–E全局验收仍需继续；不要再把台账/空闲心跳/PPTX/SVG/WAV/导图误记为未实现。以下为较早检查点历史。

## 最新AURA P1接续（2026-10-20；总体PARTIAL）

本轮在原多服务中完成图谱核心权限/公私内容/读取零模型修复；新增LearningContext、ContextExercise、LearningKnowledgeGap及0028/0029；三栏文本/习题工作区打通真实资源引用问答、版本笔记、持久助手任务、作答/画像/任务证据同事务回写。计划生成校验正式学科/知识点/有效发布文件和当前Chroma片段，生成后及确认草案时复核；知识缺口进入管理员原建设队列。复用0027文档专项，实际再次跑通独立Worker/Chroma HTTP/浏览器发布修订回滚撤回及硬退出恢复，新增计划准入READY实证。管理员增加真实持久任务统计/执行阶段/预算预留面板；实际Token台账与空闲Worker在线状态仍UNKNOWN。

交接先读 docs/aura-full-integration/11-p1-learning-context-checkpoint.md、09及根目录GRAPH_SECURITY_FIX_REPORT.md。证据 artifacts/aura-p1-20261020：regression-final为167 passed /1432 warnings；planning-final 62 passed、graph-final-v2 40 passed为有重叠定向证据；migration-v1空库head0029及0029→0028→0027→0029保留旧用户/笔记；documents-real-v1真实文档发布和Chroma/Worker子链通过。browser-v6七组检查通过且pageErrors为空，真实DB读回1笔记/3绑定题/1作答/1成功任务；build-final.log退出0，3.94秒。截图已实际查看；生成与QA受控桩清楚标识，付费调用0。新增16个Python文件Ruff通过，未声明整仓lint通过。

下一步P1-06：common/performance.py的record_model_response及llm_factory.py→逐调用持久账本，区分真实/未知/估算/测试；补Worker独立心跳/完整尝试事件和统一脱敏日志。随后P1-07原Coordinator/AssistantTask+Resource草稿审核编排；P1-08多模态产物/播放器/版本历史；P1-09笔记编辑历史/分类、闪卡知识点画像；P1-10全局原子验收。历史图谱逐边来源/真实Neo4j、PG、公网均未完成。没有升级共享SQLite、修改共享Alembic版本、重启8001–8007/5175或自动提交；其他任务的0027文档和同期改动完整保留。

更新：2026-10-20（Asia/Shanghai）。main，最近核对 HEAD 05ee287。工作树含大量既有及其他任务改动，禁止重置、清理或整体覆盖。

## 当前目标与进度

AURA-MAS全功能融合首批P0检查点（2026-10-20）：重新克隆并核验上游5923cf6；新增首页真实overview、服务端CAS活动区间/北京时间日周汇总，修正LearningPath JSON与LearningTask及阶段/任务完成率口径不一致。新增学情驱动提案预览→本人确认→追加后续补强任务，JSON revision拒绝过期写，确认ID重放不重复。新增0026的StudySession/StudyActivity两表；同期独立0027知识文档变更保留、未计本轮成果。相关后端91 passed，最终build退出0；隔离Chromium10项业务、真实约15秒活动入库、0026↔0025再至当时head0027通过。证据 `artifacts/aura-full-integration-20261020/{unit-v4,browser-v4,migration-v3}`，报告 `docs/aura-full-integration/01-09`。**全功能尚未完成**；全仓库原子审计、三栏上下文、知识覆盖门禁、导图编辑/视频/动画/TTS/PPT、完整画像推荐、管理监控及A–E全链仍待开发验收。图谱匿名/私有资源/成本边界已定位但未修。下一步见04/07；勿重复全审。共享运行库/8001–8007未迁移重启，新接口在旧进程未激活，付费调用0；先核对当前Git和同期文档改动再推进。

管理员导航本轮完成：6 分组 / 11 实际页面，原 `/admin` 保留统计看板。统一 `adminNavigation.ts` 关联菜单、路由、搜索和标题；原 AdminView 业务移到 `useAdminWorkspace.ts` 与 `views/admin/`，按模块加载。包含分组展开、折叠、路由恢复、移动抽屉、键盘焦点。管理员路由通过 `/users/me` 复核；新增管理员资源目录并修复管理员私有资源预览，敏感配置 PUT 拒绝回显。详见 `docs/admin-navigation-refactor.md`；未添加没有真实后台的模型配置/Worker监控/角色权限编辑入口。

沿用真实 FastAPI 多服务 + Vue 3/Vite，继续小智学习闭环；不按提示词假设改建 Spring Boot。统一头像、SSE、会话、记忆、持久任务、Worker、资源正文/DOCX、练习和计划确认已接入原服务。

附件可用于问答、课件和练习；执行时校验归属，删除后的排队附件明确失败。复合任务仅生成所请求的成果。默认禁用历史画像，明确请求本人学情或设置启用才读取；禁用时跳过画像服务，评分返回 null。

评价提交补认证、题目归属及服务端答案权威；教师读报告限定本人班级。练习请求标识随进度持久化，原 AnswerRecord JSON 保存回执；同键重放不重复计分、更新画像或发事件，改答案返回 409，新标识允许重练。未新增幂等表。

## 最近验证

- 管理员导航（2026-10-20）：最终 `npm run build` 退出0（Vite 5.89秒）；隔离相关后端80 passed / 221 warnings；Chromium真实路由+SQLite 11菜单、44页面宽度检查、40角色接口断言、21流程通过，正常 pageErrors/apiErrors均空；503故障注入安全拒绝通过。含用户搜索分页启停、角色分配、学科/知识点保存、资源发布归档、候选送审批准、维护暂停、任务取消及用量。证据 `artifacts/admin-navigation-20261020/{unit-verified,browser-verified,activation}`，五类截图已实际查看。未重跑真实模型、真实Chroma发布回滚或全站回归；未执行真实业务数据写测试。

- DeepSeek V3 安全完善及用户后续真实授权（2026-10-19）：新增默认pytest隔离/专用无费用运行器，禁dotenv及第三方dotenv、真实凭证继承、非声明本机HTTP/Socket与缺guard子进程；新增Provider故障、预算网关、浏览器工具。最终相关回归169 passed，Ruff定向检查通过。六服务+Worker+Chromium本地模拟QA/课件/DOCX/成绩单闭环通过。随后用户明确授权Chat≤30、Search/Fetch≤6、输出≤60000：实际5 Chat+1 Search全HTTP200，输出3506 Token；真实课件3619字符、3题无fallback、Worker持久化/重放、DOCX、浏览器QA刷新读回及课件列表通过。请求deepseek-chat、响应deepseek-flash，经本地受控记录网关；金额未知。Fetch安全校验阻断、无出站；INC-01账单未关闭。证据 `reports/global-testing/deepseek-phase-v3-20261019/DEEPSEEK_V3_GLOBAL_SUMMARY.md` 及 `artifacts/deepseek-authorized-20261019-v1/`。生产图谱权限/成本、历史迁移及fallback语义仍按附件限制仅准备补丁，未修改共享库或既有服务。

- 无费用全局审计续跑（2026-10-19）：证据 `artifacts/global-audit-resume-20261019/GLOBAL_TEST_SUMMARY.md`。隔离 pytest 184 次通过（去重178节点，含风险复现探针），六服务9接口×8身份72项真实HTTP断言通过；Knowledge Worker真实进程终止/接管在12项组合内通过，原图谱23项测试本轮均通过。动态证实匿名依赖/可视化触发模型边界、匿名关联资源暴露个人草稿标题；0009降级错误删除0002列为全量回滚根因。四份待审补丁仅保存在产物目录，迁移副本head→base→head及6项定向补丁断言通过，未修改业务源码或共享库。进程网络审计钩子阻断非loopback连接，真实模型调用0。原执行卡死原因未确认，旧pip-audit结果已找到且白名单检查失败。公网部署No-Go；PG/真实Chroma/浏览器全站/全接口权限等仍有缺口。

- DeepSeek 无费用核对（2026-10-19）：修正 live 计划/Prompt 中不存在的全局超时/重试配置名、1 秒超时误判、强制模型输出非 JSON、取消“远端停止/必须捕获 CANCEL_REQUESTED”等错误口径；新增本地 HTTP 桩失败语义、计数代理、文档契约测试。无费用回归 33+50+77 passed。**发生 INC-01 未授权真实调用**：为验证闸门执行 live 套件时 PowerShell 空赋值删除了密钥变量，`.env` 真实密钥被加载，至少 4 次结构化生成成功；usage/金额未知，需核对账单/必要时轮换密钥。已加 `DEEPSEEK_LIVE_PAID_ACK` 第二道闸门。Search/Fetch 仍 BLOCKED（无授权；本机 DNS 为 198.18.x fake-IP，Fetch 过不了 SSRF 公网校验）。证据 `artifacts/deepseek-live-20261019-173354/`，源码核对 `docs/testing/deepseek-live-source-audit.md`。练习模型失败会走 `deterministic_fallback` 且仍报 audit passed，live 验收必须排除。
- V8.3 本轮：学科规划/确认、单点和批量建设、统一知识上下文、维护策略/预算、版本差异/恢复/影响及 Vue 管理入口已接入。隔离组合回归 141 passed；追加来源提示/51点分页回归 17 passed（有重叠）；前端 build 4.56秒通过。真实 DeepSeek 规划与综合草稿、Chroma HTTP 浏览器发布/回滚各检索命中1条、一次性维护和学生课件+3题持久任务通过。唯一 head 0025，空库升级和0025↔0024已验证；未迁移共享SQLite。证据见 docs/knowledge-v8-progress.md 与 artifacts/knowledge-v83-20261019-082220/report.json。
- 小智任务可靠性本轮：隔离库组合回归 113 passed；最终执行权补丁后任务单元+独立进程回归 45 passed（43+2），覆盖真实终止 Worker 恢复、过期续租拒绝、无轮询超时、题组 flush 冲突和模型返回时取消。前端 build 退出码 0；空库到0017、0017↔0016、先 bootstrap 后迁移均通过。共享 fixture 首次并行建表冲突后改用独立 DATABASE_URL；未修改共享 Alembic 版本，未重跑真实 DeepSeek 浏览器链路。详见 `docs/assistant-task-reliability.md`。
- 相关后端回归 116 passed / 479 warnings；前端 build 退出码 0。
- 隔离库真实 DeepSeek + 独立 Worker 浏览器任务 22：附件→课件/3题/计划草案→正文及 DOCX→评分重放/冲突→1条作答及画像读回→确认计划，退出码 0。DOCX 可解析为65段、2846字符。证据及命令见 docs/xiaozhi-assistant-upgrade.md。
- 首次重跑因测试评价服务漏配 CORS 失败；补5185来源、验证 OPTIONS 200 后完整重跑通过。本轮隔离端口8008/8009/8010/8011/5185及Worker已关闭；原8001/8002保留。

## 下一步与风险

本地增量更新（2026-10-20）：仅刷新8003 resource=52928、8006 system=94792；原运行SQLite保持，使用 `--lifespan off` 避免此次重启触发schema bootstrap。两服务health、六服务健康、管理资源路由OpenAPI/匿名401及5175 CORS通过；其余服务/Worker未停止，前端5175热加载新导航。最新PID证据 `artifacts/admin-navigation-20261020/activation/processes.json`，旧 `local-start-20261019/processes.json` 两项PID已过期。以后正常重启仍遵守既有数据库基线策略。

本地运行（2026-10-19 23:44）：前端5175、六服务8001–8006、QA兼容8007及合并Assistant/Knowledge Worker已启动，健康检查通过。旧进程已由本轮启动替换，当前接口含V8建设与request-cancel。运行数据库为`artifacts/local-start-20261019/runtime.sqlite`：从原库安全备份复制并在副本补齐26个ORM缺列，保留原账户/数据，未执行共享库Alembic迁移；本次运行产生的新数据写该副本。原库备份、PID、日志与启动脚本同目录。后台图谱自动模型补全在本轮进程关闭，显式学习任务正常使用现有模型配置。

V8.3 当前可在隔离环境运行知识建设闭环，原8002 PID81168未重启，隔离8012–8016/5186已关闭。下一步：共享库基线审计与上线、远端来源更新监测、跨DB/Chroma提交间崩溃恢复演练、多点模型压力与QA/路径浏览器验收。过时检测当前按保存时间；自动发布仅授权来源的纯格式变化，未实测无人值守分支；费用未配置费率，金额未知。完整边界以V8进度文档为准。

INC-01 后需核对 DeepSeek 账单并决定是否轮换测试密钥；后续真实调用必须同时满足 `RUN_LIVE_LLM=1` 与 `DEEPSEEK_LIVE_PAID_ACK=1`，且 PowerShell 不要用空赋值清空密钥（会删除变量并使 `.env` 生效）。

小智运行中取消改为 `/request-cancel` 协作式停止；原 `/cancel` 的 RUNNING 409 语义保留。课件与练习以原任务 ID 和阶段为稳定键并加唯一约束；心跳自行检查期限，执行代次和租约限制写入/最终结果，只读任务限次退避恢复，生成类超时不自动重放。同步请求不能强行中止；卡死线程收回执行权后需另一 Worker 或重启承接安全任务。详见 `docs/assistant-task-reliability.md`。仍需全站回归和真实模型/浏览器复验；图片OCR、PDF/PPTX、Word原生排版、Neo4j联调未完成。旧题所有者未回填；评价事件无持久Outbox。共享SQLite无可信Alembic基线，禁止直接执行空库迁移。保留临时测试库，勿尝试绕过先前自动安全审查的删除拒绝。

## AURA全局融合本轮中断交接（2026-10-20）
已建立根目录 ADMIN_FUNCTION_FUSION_MATRIX.md；核验 artifacts/aura-full-integration-20261020/reference 上游5923cf6。新增 KnowledgeDocument/KnowledgeDocumentPoint、迁移0027，knowledge_documents服务与admin路由（目录、全文、上传PDF/DOCX/MD/TXT、原件、Chunk、批量分类、学科preflight/coverage、转原候选审核、未送审上传归档）。前端 KnowledgeDocumentManager接入knowledge.vue，subjects.vue新增检查和显式关联。上传原件位于独立originals，未审核不进入corpus；沿用现有候选/版本发布。
本次隔离回归55 passed/197 warnings，证据 artifacts/aura-full-integration-20261020/documents-unit-v3/command.log；空库head0027及0027→0026→0027回滚、账户保留通过，documents-migration-v1/migration-result.json。新增Python文件Ruff通过；第一次前端build通过，但随后subjects.vue及审核路由修正后尚未重构建。首次测试失败是Windows原件CRLF与测试LF比较，已改为原件字节对比通过，失败日志保留。
用户中断；尚未浏览器验收/真实Chroma检索验证；未重启共享服务、未迁移共享库或产生付费调用。下一步先复查改动、最终build及隔离浏览器，再完善上传审核发布索引跨链路（重点校验version corpus_path去前缀/去重、覆盖率），然后AI补充资源/全量Token账本/预算/日志Worker统一监控。全局融合仍PARTIAL；15份最终报告尚未生成，不得宣称全量完成。原8002进程未加载新路由，新前端访问共享服务的文档功能需要隔离运行或后续审计上线。

## AURA文档发布专项续接验收（2026-10-20）
文档核心链已TESTED_ISOLATED：上传PDF/解析/分类/知识点关联/审核/独立Worker发布/真实Chroma学生检索；修订替换、并发同键、回滚、原件字节与角色权限、记录/上传归档通过。新增knowledge_publication读取门禁与对账，PUBLISH_CANDIDATE/RECONCILE_PUBLICATIONS复用原Worker；硬退出后孤立片段不可读、attempt2恢复仅1版本；撤回立即拦截缓存，后台清理。课件真实知识上下文及版本引用持久化通过，生成仅LOCAL_STUB_ONLY。关联RAG单篇详情、重用上下文和知识覆盖扫描也过滤未生效candidate。SQL flush/提交及执行权丢失补偿有回归。
最终相关106 passed/396 warnings（resume-final-unit-v2），完整Vue build退出0；documents-browser-v9两个result均true；migration-resume-v2空库至当前head0029，0009→0008保留0002列、0027→0026往返/账号保留通过。定向新文件Ruff及关联模块F级检查通过。全部证据artifacts/aura-full-integration-20261020；汇总docs/aura-full-integration/10-knowledge-publication-acceptance.md，04/07/08/09与根矩阵已追加更新。
保留同期0028/0029及图谱/学习上下文改动；图谱当前安全/性能测试纳入本次回归，真实Neo4j与历史来源清理未验收。共享8001–8007/5175未重启/迁移；隔离18207/18208/15188已关闭，无付费调用。总体PARTIAL：下一步继续AI补充资源编辑/优化/多模态、统一真实Token账本/后端预算/全Worker监控及学生余项；preflight实时Chroma匹配、大文件异步解析/OCR/原生DOCX预览/已发布资料批量归档/永久安全删除仍未完成。先读10和现有07，不重新全仓扫描；激活共享库前需基线/备份及同期迁移审计。


## 学习分析与学习画像可用性验收（2026-10-21）

已新增并激活 /student/analytics 与 /student/profile，侧栏及顶栏入口已接通。分析读取实际活动、作答、笔记、闪卡与对话，含7/30/90天热图/趋势/复习助手；画像支持四轴偏好、六项描述编辑保存、雷达和原行为指标证据。原报告/深度分析保留，未知不填虚假分数。复用UserProfile JSON，无迁移；笔记统计按id计数兼容当前运行库。

相关24 passed/90 warnings，最终前端build通过；独立Chromium保存刷新/取消/统计/越权/移动端通过。当前5175真实页面、8001/8004接口、菜单、编辑取消及刷新读回通过，pageErrors为空；共享数据仅只读验收。证据 artifacts/learner-insights-20261021/SUMMARY.md 及 activation/live-browser-result.json。当前库备份 activation/before-activation.sqlite，无付费调用。用户/评价服务已加载新路由，同期其他任务刷新进程后以实际端口及 verification-processes.json 为准；勿重用历史PID。全局融合仍PARTIAL，下一步沿既有P1范围继续，勿把两页验收扩称全站完成。
