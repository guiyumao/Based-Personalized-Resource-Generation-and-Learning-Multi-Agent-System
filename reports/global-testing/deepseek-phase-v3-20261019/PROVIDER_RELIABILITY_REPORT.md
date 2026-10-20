# Provider可靠性

provider-v2：34 passed，涵盖本地真实HTTP客户端正常JSON、非JSON、空响应、非法JSON、缺choices、429/500/502/503、连接失败、断连、SSE中断及实际3秒钳制；包含计数网关、Search/Fetch和文档契约回归。Worker组合67 passed，包含真实进程终止与执行权围栏。

真实授权调用5个Chat均HTTP200；请求deepseek-chat，响应deepseek-flash。没有故意用真实服务制造429、断网或超时，因此故障场景仍仅PASS_MOCK。普通SDKmax_retries=0不等于业务层不会追加调用，全部按实际ledger统计。