# 本地与真实链路分开验收

本地模拟阶段：六服务、独立Worker、隔离SQLite、Vite和真实Chromium；QA登录/提问/刷新读回、课件任务/幂等重放/展示/DOCX、3题非fallback任务、CSV上传解析/分析均通过，browser-report无pageErrors。证据local-e2e-v3，外部模型明确LOCAL_MOCK。

用户随后要求真实调用并确认预算：真实课件/3题Worker任务、幂等重放、DOCX导出、浏览器登录/真实QA/刷新读回/资源列表均通过，证据deepseek-authorized-20261019-v1。应用经本地记录网关访问真实官方API，不能称应用官方直连。

知识候选审核/发布/版本逻辑在隔离单元测试通过，但本轮没有全新真实Chroma发布→检索的浏览器闭环。取消/超时/崩溃由故障与Worker测试覆盖，没有在本轮收费请求上重复注入。