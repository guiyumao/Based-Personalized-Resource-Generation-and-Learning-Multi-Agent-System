# Search/Fetch

DEEPSEEK_SEARCH_BASE独立于Chat基址；默认源码路径为/v1/tools/search和/v1/tools/fetch。每次出站尝试前预留，408/429/5xx/超时按现有两次尝试处理；公网URL及解析地址限制保留。本地MockTransport校验官方默认URL、网关覆盖、重试/超时及SSRF。

本轮真实Search HTTP200并取得IETF RFC5681等来源，实际1次。Fetch在项目URL/公网校验处ValueError: Invalid source URL，无真实Fetch出站，记录BLOCKED而非PASS。受控子进程禁止外部DNS以及原环境fake-IP均不能通过放宽SSRF解决。

本轮只读官方文档访问失败/超时，逐字段当前官方契约仍CONTRACT_UNVERIFIED；Search实际响应成功仅证明当前已用字段可工作，不证明全契约或Fetch可用。