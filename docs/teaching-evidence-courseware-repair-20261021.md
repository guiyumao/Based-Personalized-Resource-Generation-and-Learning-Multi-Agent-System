# 学情分析修复与课件升级交付报告

2026-10-21。复用当前 FastAPI、SQLAlchemy、Vue 3、Coordinator、Resource、Exercise、AssistantTask 和独立 Worker，未提交代码，保留并行开发改动。

## A. 根因报告

真实调用链：用户作答 → evaluation report_service → AnswerRecord / Exercise / KnowledgePoint → profile_updater / UserProfile → user learning_content_profile / profile_analysis → agent personalization → Coordinator → ResourceGenerationService → Resource → Vue 阅读器。

直接根因是原 personalization.py 的 `_load_records` 使用 `exercise_payload.get("knowledge_point") or knowledge_point`，把题目JSON缺失的知识点替换成当前浏览知识点，再作字符串包含匹配，没有以既有 Exercise.knowledge_point_id 为权威归属。因此打开冒泡排序时，TCP作答被错误引用。旧画像分数与全局推断摘要进一步传播污染；无证据默认分、速度奖励和重复提交计数也需要纠正。

实际运行库为 artifacts/local-start-20261019/runtime.sqlite。用户6有TCP记录，冒泡排序目录点459没有有效作答。同一原始备份分别运行Git旧实现和新实现，重现用户报告的问题；不是仅修改界面文案。

## B. 实际修改清单

- common/learning_evidence.py：point-evidence-v4统一证据。精确解析知识点ID、学科、章节、确认别名；歧义不猜测。按用户与正式题目归属关联作答、评分、时间和来源。缺失归属、候选模型标签、测试/演示标记及无效记录不能直接进入知识点统计。
- common/models/learning.py、alembic/versions/20261020_0032_exercise_evidence.py：增加ExerciseKnowledgePoint，支持confirmed及归一weight；多知识点题不重复算成多个完整样本。
- personalization.py、learning_content_profile.py、profile_analysis.py、profile_updater.py、report_service.py、path_adaptation.py：共用证据、旧缓存版本失效、修复下游路径建议。保留原始作答，不使用客户端或页面知识点覆盖题目归属；当前知识点不再复用无依据的全局风格与错因推断。
- 算法按每题最新有效作答去重，综合难度、近期权重；至少3个有效归属样本才给数值估计。区分无证据/不足/初步/相对充分，输出样本、趋势、覆盖和不确定性近似。记录作答时间但取消速度奖励。该算法不是经过心理测量标定的能力模型。
- common/schemas/user.py、evaluation schemas/report.py、user routes/users.py、DashboardView.vue、TS类型等支持null掌握度。
- scripts/repair_learning_evidence.py：默认审计，apply前检查完整性/活跃任务并备份。实际重算93画像，标记120历史报告失效，67条原始作答均保留。37个已作答题目归属缺失或悬空，排除并保留待可靠归类。
- prompts/resource_gen.md、courseware_quality.py、resource_generation.py：teaching-v2九模块，按算法/网络/结构/数学动态要求；标准目标从旧约1300–1600提升为4200字以上目标。现有检索/来源 → 大纲 → 分章生成 → 门禁 → 定向重试 → 完整持久化，来源缺失明示模型未核验。
- Resource.structured_json保存请求指纹、来源、章节、拒收正文与in_flight；复用持久任务及Worker。完成态重放不重复生成；传输结果不确定时禁止自动重发，需明确确认。供应商不支持幂等时，人工确认重试仍可能二次计费。
- resources.py新增 POST /resources/{id}/chapters/{chapter_key}/regenerate：归属/精确版本校验、202持久任务、幂等冲突409。assistant.py / assistant_worker.py执行修订，生成新资源并保留旧版及其他8章。Coordinator仅重用已完成资源。
- 配套练习保存到既有Exercise、关联当前正式知识点和私有资源、稳定键去重；真实提交进入既有评分与学情更新。阅读完成不算掌握。
- CoursewareReader.vue用于工作区/资源详情/独立课件页：目录折叠、KaTeX、highlight.js、Mermaid、步骤表格、答案独立展开、阅读续接、来源、章节修订和配套题。图示失败保留文字/源码；normalizeMermaidSource.ts修复数组下标节点语法。窄容器与移动端适配。
- LearningWorkspaceView.vue防止旧请求覆盖新知识点；CoursewareView.vue创建真实持久任务并刷新恢复，隔离用户/主题状态。对应API/schema传回真实版本及teaching_json。

本轮还增加单元、迁移、真实模型和浏览器执行脚本。其他会话的管理员监控、笔记、学习画像页面修改不计为本轮成果，也未回退。

## C. 同数据修复前后

证据：artifacts/teaching-evidence-20261020/before-after.json；tests/e2e/audit_teaching_before_after.py实际执行。

| 用户6冒泡排序 | 旧实现 | 当前实现 |
| --- | --- | --- |
| 作答次数 | 5 | 0 |
| 掌握度 | 60 | null，暂无有效证据 |
| 错题ID | 723800000、1867146920 | 空 |

原始TCP记录仍保留。5次提交不等于5道不同题目。

## D. 课件质量对比

旧链路目标短、单次输出，缺少逐章质量门槛与恢复。新链路包含导入、概念、原理、图解、案例、对比、易错、练习、总结九模块，另有教学概览。下面是实际模型产物经真实SQL/API及浏览器重新打开读取的正文字符数，不是Token数。

| 类型 | 正文字符 | 教学模块 | 保存练习 | 浏览器图示 |
| --- | ---: | ---: | ---: | ---: |
| 冒泡排序 | 10670 | 9 | 3 | 1 |
| TCP协议 | 10011 | 9 | 3 | 2 |
| 链表 | 10968 | 9 | 3 | 3 |
| 一元二次方程求根公式 | 10697 | 9 | 3 | 1 |

算法有执行步骤/复杂度，网络有交互/字段，链表有代码/指针案例，数学有配方/条件。旧版对照来自源码审计，未额外付费重新生成旧版，不能视为严格质量对照实验。

结构门禁检查深度、章节、步骤图表、公式代码边界和练习答案结构，不证明学术正确性。人工发现链表赋值顺序解释、数学根式符号错误后，各用1次调用定向修订；其余8章不变，原版保留并标记待复核。四份内容尚未完成专家逐句审核，例如链表空表插入的边界表述仍需进一步复核，不能宣称全部知识准确。

## E. 真实测试报告

证据根目录：artifacts/teaching-evidence-20261020/。

| 验证 | 结果/证据 |
| --- | --- |
| 核心回归 | final-unit-v3/command.log：137 passed、1334 warnings、85秒 |
| 最后下游回归 | downstream-final/command.log：30 passed、151 warnings；与137重叠，不累计为167个独立测试 |
| 迁移/修复 | 隔离空库升级、0032降级/再升级、真实库副本修复及账号/作答保留通过 |
| 同备份旧代码复现 | before-after.json：5/60→0/null，通过 |
| 前端 | build-final2.log：TypeScript/Vite退出0，3.41秒 |
| 局部Ruff | 新证据/质量/修复脚本及三个新增测试文件：All checks passed；不是全仓库lint |
| 浏览器 | browser-release/browser-result.json：四类真实正文、1440桌面/390移动无溢出、0 pageErrors、公式/代码/图示、答案展开、续读与重新打开通过 |
| 真实SQL/API | 配套题持久化、跨用户拒绝、两次真实上下文请求乱序不覆盖、章节任务幂等通过 |
| 任务恢复 | 独立课件页刷新恢复同一任务通过；浏览器阶段只排队修订，不调用模型 |
| 真实模型 | live-v1/v3/v4最终四样本通过结构验收；含两次单章语义修订 |
| 当前运行 | runtime-final.json：8001–8007 health均ok、新章节路由可见、Worker68224心跳新鲜 |

数据用例覆盖仅TCP、混合冒泡/TCP、无记录、多知识点权重、跨用户、同题重复和旧缓存失效。受控单测文本没有冒充真实模型产物；浏览器采用真实生成正文与实际服务/隔离SQLite。

早期失败保留在原证据目录：章节格式拒收、一次参数适配错误造成该轮0模型调用、伪代码高亮断言、Mermaid下标解析及浏览器定位器失败；修复后重新验收，没有删除失败记录。

授权上限40次Chat/60000输出Token，累计已执行40次、实际输出27124 Token、总预留60000、Search/Fetch=0。请求deepseek-chat、响应deepseek-flash，HTTP200；实际货币账单未核对。调用次数预算已耗尽，不再调用。隔离测试未增加共享model_calls（仍18）；真实调用证据在网关台账，不在共享18条记录里。

## F. 上线、回滚与剩余风险

- 实际运行库已备份并定向建关联表/重算；没有在无可信基线共享库执行Alembic upgrade或stamp。备份：shared-repair/before.sqlite（首次修复前）、shared-repair-final/before.sqlite（追加报告标记前）。恢复前停全部写入方，保留当前库，再恢复合适备份及兼容代码；不要在线覆盖SQLite或忽略WAL。
- 无活动生成任务后按现有配置重载8001/2/3/4/7及Worker，保留8005/6/5175。最后只读检查仍67条作答、18条共享模型记录、七服务健康。Worker历史表可能保留RUNNING，在线判断须依据最新心跳。
- 37个题目缺失/悬空归属需要可靠人工或目录规则确认；不删除历史、不按题面猜测。排除后学情覆盖变少是显式限制。
- 四样本在隔离库生成，空来源标记model_generated_unverified。本轮没有验收真实公共Chroma命中、Search/Fetch、审核发布或公网部署；未审核内容没有自动公开。
- 结构/持久化/界面及所列业务回归通过，完整学科内容审核仍未完成。自动门禁不能保证任意新课件公式/程序/概念正确。供应商不支持幂等时的重试计费风险仍在。
- 未执行全站全仓库回归，弃用警告仍需后续治理。并行开发可能继续变化，接续须核对实时Git和DEV_STATE。本报告不是同时开发的其他功能验收。

结论：真实跨知识点污染已复现并修复，代码和当前本地服务已加载；分章课件、持久任务、配套题及阅读器通过所列验收。历史归类和完整学科准确性审核仍待后续完成。
