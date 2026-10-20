# 2026-10-17 本机部署测试记录

| 项目 | 结果 | 证据/边界 |
| --- | --- | --- |
| SakuraFrp 专用 Vue 构建 | 通过 | `npm run build:sakurafrp`、TypeScript 与 Vite 退出码 0；Rolldown 第三方纯注释和大 chunk 警告仍在 |
| Nginx 正式配置 | 通过 | 官方 nginx/Windows 1.31.7 `nginx.exe -t` 输出 syntax is ok / test is successful |
| 本地统一入口 | 通过 | `start.ps1`、`health-check.ps1`：首页、History 路由及 6 个代理健康接口通过 |
| 未登录保护 | 通过 | 用户、教师、系统、资源下载、评估、智能体接口返回 401；API docs 返回 404 |
| 路由拼接 | 通过 | `/api/user/users/login` 用空 JSON 请求返回后端 422，说明请求到达原登录路由 |
| 用户归属与认证回归 | 通过 | 独立临时 SQLite 上，智能体权限、安全认证、学习路径和 API smoke：42 passed、23 warnings |
| 安全停止 | 通过 | `stop.ps1` 关闭脚本启动的 Nginx，保留预先运行的 8001 服务；随后重新启动成功 |
| 学生/教师/管理员真实登录与角色全链路 | 待用户人工验证 | 未使用真实账号进行公网浏览器操作 |
| 模型回答、知识库、成绩单解析、导出和受保护下载 | 待用户人工验证 | 健康接口不代表这些业务调用成功 |
| SSE / WebSocket | 不适用 | 当前前后端未发现这些传输路径，现有问答为普通 HTTP 请求响应 |
| 公网隧道、可信 HTTPS、手机移动网络与断线恢复 | 待用户人工验证 | 未控制 SakuraFrp 面板或客户端；当前贴出的配置未启用 HTTPS |

已发现的限制：Windows Nginx 运行目录需 ASCII 路径；普通 HTTP 隧道不适合真实登录；当前健康探针不检查 Redis/RabbitMQ/Neo4j 或模型供应商；Nginx 180 秒超时不延长后端模型期限。首次演示前请逐项完成验收清单。
