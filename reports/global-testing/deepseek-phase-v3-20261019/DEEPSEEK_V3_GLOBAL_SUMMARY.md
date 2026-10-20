# DeepSeek集成安全与全链路测试V3验收报告

生成：2026-10-19T15:24:27.508318+00:00（UTC）。本轮先按无费用约束实施隔离，随后用户明确要求真实调用并授权Chat≤30、Search/Fetch≤6、总输出≤60000。

## 已完成

- 测试默认安全：普通pytest导入前隔离；dotenv、第三方dotenv、凭证继承、HTTP/Socket、Python子进程均有防护。误开两个live标志仍不能出网。
- 最终安全/预算16 passed，Provider34 passed，Worker67 passed，内容/知识/成绩52 passed；合计169次，通过节点去重169。模拟与真实结果分列，旧INC-01通过数不累加。
- 真实浏览器本地模拟链路通过；后续真实DeepSeek课件3619字符、3道题非fallback、Worker持久化/重放、DOCX、浏览器QA刷新读回及课件列表通过。
- 真实请求：5 Chat+1 Search，输入3740 Token、输出3506 Token。全部HTTP200。请求模型deepseek-chat，响应模型deepseek-flash；经本地记录网关访问api.deepseek.com，不是应用直连证明。金额UNKNOWN。
- 真正的Fetch请求0次：现有安全检查阻断，仍BLOCKED。没有放宽SSRF。

## 验收边界

核心Chat/课件/练习/Search授权实测已通过所列场景；不能宣布DS-01至DS-30全绿，也不能宣布全站上线验收通过。结构化三类资源仍保留历史PASS_UNAUTHORIZED，没有借本轮授权追认旧事故。知识真实发布/检索、全站全部权限与浏览器、专家内容质量均未完整验收。

## 仍需处理

INC-01发生于dotenv回退+测试授权门不足，账单仍UNKNOWN；新授权事件独立保存。Python防护不覆盖任意恶意native代码或OS层网络；未来付费只能使用专用受控入口。生产统一成本控制、图谱匿名付费及个人草稿泄露、SQLite历史降级、fallback语义均未获本轮生产修改授权，补丁/方案保留，公网部署仍No-Go。

## 交付与下一步

本目录12份报告、DS矩阵、来源指纹、人审样本和历史证据清单；原始日志在artifacts/deepseek-phase-v3-20261019，真实ledger及产物在artifacts/deepseek-authorized-20261019-v1。真实密钥仅getpass读入内存，子API只有本地网关随机令牌。无需再提供相同密钥；若要修复生产风险，最少还需明确批准具体补丁范围；若要继续Fetch，需提供不弱化SSRF的正常公网DNS/受控执行环境。账单核对需脱敏控制台导出。
