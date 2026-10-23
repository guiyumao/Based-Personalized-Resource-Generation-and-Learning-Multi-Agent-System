# 项目长期约定

## 知识库补建策略（2026-10-21 决策）

- 学生触发的知识构建不再等待管理员：公共知识库缺学科/知识点/已发布内容时，生成的草稿**直接自动入库**（建 SystemSubject/KnowledgePoint + 发布 KnowledgeVersion + 索引），并标记 `license_name=AI_GENERATED`、正文注明「AI 自动构建，管理员可修订/下架」。
- 入库失败（索引不可用等）必须回滚新建的目录行，退回个人草稿模式，不污染公共目录。
- 约定：相关单测中 `plan_knowledge.KNOWLEDGE_ROOT` 若被夹具指向 tmp_path，需指回运行时根才能验证端到端「发布→检索命中」；测试需自行清理 `auto_*` 学科码产生的行。
- 事务约定：SQL/语料文件/Chroma 无法原子提交，自动入库必须走「写锁 → 复用检查 → 发布 → 版本级校验 → 失败补偿（DB→文件→索引→reconcile）→ 补偿失败写 AuditLog ERROR 并排队 RECONCILE_PUBLICATIONS」。返回 `{"ok":False,"reason":...}` 而不是伪成功。
- 状态约定：`AUTO_APPROVED` = AI 自动生成并自动发布（未经人工审核），必须与人工 `APPROVED` 区分；语料头写「来源类型: ai_generated_auto_published」。管理员下架（WITHDRAWN）/驳回（REJECTED）的知识不得被自动补建。
- 测试约定：完整 unit 存在 20 个失败（vulnerability_policy 11 / resource_type_integration 6 / teaching_migration_repair 2 / knowledge_lock 1），经对照基线取证来自用户其他未提交改动，不是自动入库引入。

## 知识库「批量补料」约定（2026-10-23，408 案例沉淀）

- 覆盖率不是自动算出来的：`knowledge_documents.coverage` 要求「KnowledgeDocumentPoint 显式关联 + 已 PUBLISHED 候选 + 活动 KnowledgeVersion + manifest 的 document_version == 文件 sha256」四者齐备，只把 md 丢进 corpus 目录恒为 0。
- 粒度必须是**知识点级别**：`plan_preflight` 用 `KnowledgeVersion.knowledge_point == 点名` 精确查找，一篇覆盖多个知识点的章节文档只能让其中一个点 READY。批量补料要「章节级文档（保证可读性）+ 每知识点一个候选（保证可用）」两层。
- 走正式管道的幂等做法：`KnowledgeBuildTask.client_request_id` 唯一 → 候选 + 模型审核 PASS 证据 JSON → `publish_candidate()`（自动写文件、索引、校验检索、建版本）→ 再补 KnowledgeDocument/`knowledge_document_points` 关联。参见 `scripts/kaoyan408_ingest.py` 与 `scripts/kaoyan408_pointwise.py`。
- 脚本用项目依赖所在解释器 `C:\Users\wdx\anaconda3\python.exe`，而不是托管的 3.13（后者没装 sqlalchemy/chromadb）。
- 重启本机微服务时，PowerShell `Start-Process` 会因会话里 HTTPS_PROXY/https_proxy 大小写重复抛 ArgumentException；改用 Git Bash 内联 env 后台启动 uvicorn。

## 接口响应约定（2026-10-22 踩坑）

- 所有后端 API 统一返回 `ApiResponse`：`{"code":..,"message":..,"data":...}`。**取业务数据一律用 `d["data"]`**，不是 `items` / `classes` / `results`。用错键会得到空列表，容易误判成"服务连错库 / 数据丢失"，排查时先直连 ORM 或业务层方法对拍，别急着改配置或杀进程。

## 本地服务启动约定（2026-10-22）

- 教师服务 8005 必须带 `DATABASE_URL=sqlite+pysqlite:///<绝对路径>/artifacts/local-start-20261019/runtime.sqlite` 启动；不带则读 `.env` 的 `./learning_system.db`（那是打包默认库，seed 脚本刻意拒绝写入，里面没有演示数据）。
- 端口被不明进程占据时，先看命令行有无 DATABASE_URL 再决定处置。

## 学情证据链约定（2026-10-22，P0 级）

教师端「学生洞察 / 教学分析」的掌握度**不是存储字段**，而是 `answer_records` 经 `common.learning_evidence.load_evidence` 实时反算。造作答数据必须同时满足：

1. 题目知识点在该班 `TeachingScope.knowledge_points` 内（`_class_answers` 第一层过滤），且知识点名能被 `resolve_point(name, subject=classroom.subject)` 唯一解析；
2. `exercise.content.generated_for_user_id` 为空或等于该学生 id —— 否则整条作答被丢弃（这是最容易漏的一条，模板生成题通常带真实用户 id）；
3. `exercise.content.classification_status != "pending"`；
4. `answer.evaluation_json` 不得含 `evidence_excluded` / `test_data` / `evidence_source in {demo,test,synthetic}`（写 `{"source":"demo_seed","scoring_status":"completed"}` 是安全的）。

另外：`summarize` 每题只取最新一次，累计权重 <3 无 mastery、<8 不算 sufficient，所以每生每知识点至少 8~10 道不同题。

演示数据正确做法见 `scripts/demo_learning_evidence.py`：复制公共演示题（去掉归属，`assistant_operation_key=demo-evidence-<源题id>`）+ 补教学范围 + 按画像精确分配正确题数（90/70/40/60），而不是随机判定。

## 测试断言约定

学情类断言必须校验**数据非空且存在差异**（mastery 非空、distinct>=2、错题>0、total_answers>0），只检查 key 是否存在会让全空数据"通过"，属于假通过。

## 演示数据「不准硬编码」约定（2026-10-22，用户明确要求）

- 演示/测试环境里**结果类指标必须跑出来，不能写出来**。掌握度、正确率、错题数、画像分值属于系统输出，
  seed 脚本一律不得直接写库；脚本只负责准备环境（账号、班级、课程、演示题库、教学范围）。
- 正确链路：学生登录 → `POST /evaluation/batch_submit` 逐题作答（剧本只决定"想选哪个选项"，
  答错就真提交干扰项 / 判断取反 / 填空错误答案）→ `ReportService._compare_objective_answer`
  比对标准答案得 `is_correct` → `ProfileUpdater` 递推 mastery → `load_evidence`
  → 教师端 `insights` / `teaching-analytics`。
- 演示题库只克隆 `choice / judge / blank / fill` 客观题（主观题走 LLM 评分，会破坏 0 模型调用约束）。
- 角色用例必须覆盖**所有端并验证联动**：管理员 8006（治理 + 审计）、教师 8005（范围/排课/资料/作业/打卡/签到/通知/批改）、
  学生 8001+8004（课表/范围/资料/提交/打卡/签到/通知/真实作答/错题本/画像）；每条动作都要断言对端接口能看到变化。
- 演示管理员用 seed 创建独立的 `demo_admin`，**不复用/改动真实 `admin` 账号**。
- 判定不要写死数值：用「非空 + 有梯度 + 优秀画像正确题数多于困难画像」三条，重跑数值会浮动。
