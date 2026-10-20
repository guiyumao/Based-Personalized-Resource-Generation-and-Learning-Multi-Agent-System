# 19项问题与修复

原始19条不删除、不都视为代码缺陷：文档、测试、事故、环境和生产风险分列。

| D-01 | High | 验收计划写入了不存在的 `LLM_TOTAL_TIMEOUT_SECONDS`、`LLM_MAX_TOTAL_RETRIES`，并把重试默认值写成 3 | `common/config.py:166-173`；`llm_factory.py:31`；旧计划 v1.0 第 51 行 | 执行方会按错误配置估算预算/超时，结论不可复现 | 改为真实 `MAX_TOTAL_RETRIES=2` 与业务期限；新增文档契约测试 | FIXED_DOC |
| D-02 | High | “1 秒预算真实超时”实际上被工厂钳到 3 秒 | `llm_factory.py:31`；旧 live 测试 `test_live_timeout_is_a_real_error` | 用错误预期验收超时；可能把 3 秒行为误判为 1 秒 | DS-27 改为本地桩验证 3 秒生效值；删除真实端点 1 秒测试 | FIXED_TEST |
| D-03 | High | 通过提示词强迫真实模型输出散文来构造“非 JSON”失败用例 | 旧 `test_live_non_json_answer_is_rejected`；`test_live_llm_resources.py:244-263`（修改前） | 模型可能仍输出 JSON，用例不稳定；且产生不必要费用 | 新增本地 HTTP 桩测试；删除强制散文用例 | FIXED_TEST |
| D-04 | High | 取消用例要求必须捕获 `CANCEL_REQUESTED`，并暗示“远端停止后续调用/计费” | `assistant.py:353-375`；`coordinator.py:344-355`；`assistant-task-reliability.md:63` | 短暂中间态导致误判；把协作式取消误写成远端中止，可能作出无法证实的计费结论 | 改为接受终态/竞态；只承诺本地停止后续调度与写入；远端计费保持“无法确认” | FIXED_DOC |
| D-05 | High | 预算总表容易被当作已授权预算；知识预算只覆盖知识链路 | `knowledge_budget.py:20-63`；仅 `knowledge_construction.py` 与 `deepseek_search.py` 调用 | 问答/资源/评价可能绕过预算；执行方可能超支 | 明确“建议≠授权”；增加预算覆盖表；新增本地计数代理 | FIXED_DOC + MITIGATED |
| D-06 | High | 练习生成在模型失败时静默使用确定性题，并仍返回 `audit_status=passed` | `exercise_generation.py:76-84,376-386` | live 测试可能 0 次模型成功却判定“真实生成通过” | DS-06 增加 `deterministic_fallback` 检测要求；未改业务兜底 | OPEN（测试门已加） |
| D-07 | High | 原 live 套件接受 Qwen/OpenAI 凭证，可能验证了别的 Provider | 旧 `_credentials_configured()`；`test_live_llm_resources.py:49-58`（修改前） | 把 Qwen 结果写成 DeepSeek 结论 | 只接受 DeepSeek 配置；新增 base_url 主机断言与网关标记 | FIXED_TEST |
| D-08 | Medium | `audit_status=unavailable` 在测试中被与 `passed` 一起当作成功，没有单列 | `audit_service.py:203-204`；live 测试第 190 行 | 审核未执行被误读为审核通过 | 文档明确语义；live 测试对 `unavailable` 发警告；DS-05 要求单列原因 | FIXED_DOC |
| D-09 | Medium | Search/Fetch 根地址硬编码，`DEEPSEEK_API_BASE` 不影响它；经网关无法计数/标记 | `deepseek_search.py:16`（修改前） | 网关运行可能被误写成官方直连；无法用本地代理计数 | 新增 `DEEPSEEK_SEARCH_BASE` 覆盖（默认官方）；文档要求标记“经网关” | FIXED_CODE |
| D-10 | Blocker | 本机 DNS 把所有主机解析到 `198.18.0.0/15` fake-IP；Fetch 的公网校验必然失败 | `environment.json` DNS；`deepseek_search.py:25-49` | DS-21/DS-22 无法在本机执行；也无法证明官方直连 | 记录为环境 BLOCKED；拒绝放宽 SSRF 规则 | BLOCKED |
| D-11 | Medium | 文档把 Search/Fetch 预算描述成“调用次数”，实现是在每次出站尝试前预留（重试也计数） | `deepseek_search.py:56-75` | 预算对账口径不一致 | 文档改为“按尝试次数”，并说明保守预留 | FIXED_DOC |
| D-12 | Medium | 官方 Search/Fetch 文档在本机不可读，请求/响应契约未逐字核对 | `web_fetch` 报 `api-docs.deepseek.com` 非公网 IP | 可能遗漏官方字段/限制 | 只按源码契约记录；标注未逐字核对 | OPEN |
| D-13 | High | `.env` 中存在 DeepSeek 密钥，但密钥存在不是费用授权；且 PowerShell 的 `$env:VAR=""` 会删除变量，导致“置空”失效并回落到 `.env` | `environment.json` `dotenv_key_presence.DEEPSEEK_API_KEY=true`；INC-01 | 误用密钥产生真实费用 | 测试进程改用非空哨兵/本地地址；新增 `DEEPSEEK_LIVE_PAID_ACK` 第二道闸门 | MITIGATED（INC-01 已发生） |
| D-14 | Medium | 全局设置 `ASSISTANT_TASK_EXECUTION_MODE=worker` 会让同步任务单元测试停在 PENDING | 首次任务链运行 41 passed/9 failed；第二次默认 background 50 passed | 被误判为代码缺陷 | 文档要求该套件用默认 background；worker 专项测试自行设模式 | FIXED_DOC |
| D-15 | Low | live 测试清理只删除 `Resource`，练习/任务/附件等产物没有通用清理 | `test_live_llm_resources.py:120-131` | 隔离库可能残留测试数据 | 文档要求按用例登记并清理；未实现通用清理 | OPEN |
| D-16 | Low | usage 缺失时 `traced_invoke` 使用字符估算，预算/账单无法精确对账 | `common/performance.py:164-174` | Token/金额可能偏差 | 报告要求 usage 缺失记“未知”，不得记 0 | OPEN |
| D-17 | Low | 知识预算只做预留，没有用真实 usage 回填/释放 | `knowledge_budget.py:20-63` | 预留与实耗可能偏离 | 仅记录为已知限制；本轮不改预算模型 | OPEN |
| D-18 | Low | Provider 身份没有挂到客户端实例，日志 `provider=deepseek` 不是链路证据 | `llm_factory.py:147-257` | 可能把代理/其他 Provider 当成 DeepSeek | DS-01 要求记录 base_url、DNS、响应模型、ID、usage | FIXED_DOC |
| D-19 | High | **INC-01：未授权真实调用。** 一次 `RUN_LIVE_LLM=1` 的闸门检查实际执行了 6 个 live 测试，产生至少 4 次真实 DeepSeek 生成 | `evidence/live-gate.log`（6 passed / 49.43s）；`live.sqlite` 4 个知识点；`request-ledger.jsonl` | 未经授权的费用；若隐瞒会违反“不隐藏首次失败”和预算约束 | 已加 `DEEPSEEK_LIVE_PAID_ACK` 第二道闸门；记录 4 条 ledger（未知字段为 null）；要求核对账单 | OPEN（账单待核对） |

## 本轮状态更新

- D-05：测试网关覆盖本轮；生产统一预算仍OPEN
- D-06：真实本轮非fallback通过；生产fallback语义仍OPEN
- D-10：Fetch仍BLOCKED，未绕过SSRF
- D-12：官方文档当前逐字段核对仍UNVERIFIED
- D-13：测试默认dotenv/网络/子进程独立防护已实施并回归
- D-16：新授权Chat获得usage；生产估算逻辑未改
- D-18：新授权网关记录请求/响应模型、ID、usage；客户端全局标记未改
- D-19：INC-01账单仍UNKNOWN；后续新授权调用独立记录

已实施只涉及测试隔离、运行工具、配置关闭dotenv开关与文档。图谱权限/成本、迁移、生产fallback及知识业务规则未修改；依据用户附件第10.2节保留待决补丁。撤回本轮具体增量即可回滚测试工具，不回滚其他未提交改动；新证据与INC-01应保留。