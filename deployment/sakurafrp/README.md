# SakuraFrp 单隧道部署（Windows）

## 真实架构

此目录针对当前 **Vue 3 + Vite + 六个 FastAPI 服务**，不是附件中假设的 Spring Boot/MySQL 项目。前端在 `web-app/`，服务在 `services/`；本机 `.env` 当前使用 SQLite，另配置了 Redis、RabbitMQ、Neo4j 和本地 Chroma。它们仍按原项目方式运行，不经公网代理。`java-services/` 和 `pom.xml` 不属于当前前端调用的六个 FastAPI 入口，本次不改动。

| 路径 | 本机服务 | 端口 |
| --- | --- | ---: |
| `/api/user/` | 用户、登录和画像 | 8001 |
| `/api/agent/` | 问答、协作、知识库、生成 | 8002 |
| `/api/resource/` | 资源与受保护下载 | 8003 |
| `/api/evaluation/` | 评估与成绩单解析 | 8004 |
| `/api/teacher/` | 教师与班级 | 8005 |
| `/api/system/` | 管理员配置 | 8006 |
| `/` | Vue 构建结果 | Nginx 127.0.0.1:80 |

代理保留各 FastAPI 原始路径。例如浏览器请求 `/api/user/users/login`，后端收到 `/users/login`。`/api/agent/` 先调用用户服务验证 Bearer 令牌；智能体的用户数据接口也校验 `user_id`。Nginx 隐藏各服务的 `/docs`、`/redoc`、`/openapi.json`。前端的 `build:sakurafrp` 模式使用相对 API 基址，开发用 `.env.local` 不受影响。当前问答接口是普通 HTTP 请求响应，源码未发现 SSE 或 WebSocket；代理仍预留 Upgrade 与禁用 agent 响应缓冲。资源下载通过 Axios 携带登录令牌。

## 本机准备与启动

1. 确认本机 Python 3.11+、Node/npm 已可用，项目 `.env` 中后端所需密钥和依赖配置有效。按项目现有方式准备可选基础设施；脚本不会安装或停止数据库、Redis、RabbitMQ、Neo4j 或 Chroma。
2. 从 [Nginx 官方 Windows 页面](https://nginx.org/en/docs/windows.html) 下载 Windows 版，解压到自己管理的目录。复制 `config.example.ps1` 为被 Git 忽略的 `config.ps1`，设置 `$NginxExe`。本次本机已经在 `deployment/sakurafrp/runtime/nginx-1.31.7/` 放置官方版并生成了 `config.ps1`。
3. 在项目根目录运行：

   ```powershell
   & .\deployment\sakurafrp\build.ps1
   & .\deployment\sakurafrp\start.ps1
   & .\deployment\sakurafrp\health-check.ps1
   ```

4. 浏览器打开 `http://127.0.0.1/`。`build.ps1` 执行 TypeScript/Vite 构建、复制静态文件并运行 `nginx.exe -t`。`start.ps1` 复用已经健康的 8001–8006 服务，只启动缺失服务和本部署 Nginx；`stop.ps1` 只停止它记录且核对过的进程。更新配置可再次运行 `start.ps1` 触发 `nginx.exe -s reload`。故障用 `diagnose.ps1`，重启用 `restart.ps1`。

Nginx/Windows 无法可靠读取此项目的中文路径，所以脚本把生成的站点、配置和日志放到 `%LOCALAPPDATA%\learning-sakurafrp\<项目路径哈希>\`，源码仍在原目录。若 Windows 用户目录也含非 ASCII 字符，在 `config.ps1` 设置 ASCII 路径的 `$RuntimeRoot`。不要把 `config.ps1`、访问密钥或证书私钥提交 Git。

## SakuraFrp 面板与客户端

你提供的配置说明当前隧道意图是 **TCP，转发 `localhost:80`，远程端口 `63446`**。`frp-end.com:8088` 是客户端控制连接配置，不能据此推断公网访问域名。`# id = ...` 是注释，需以面板当前隧道为准。

1. 在 SakuraFrp 面板核对现有隧道的真实节点、隧道 ID、远程端口、访问认证和节点建站限制；不要重复创建第二条隧道。若新建，名称可填“学习系统”，类型 TCP，本地 IP `127.0.0.1`，本地端口 `80`，远程端口以面板分配为准。
2. 按 [Web 应用穿透指南](https://doc.natfrp.com/app/http.html) 核对节点、实名认证及备案条件。国内节点的建站要求可能不同；没有备案时选符合官方规则的节点。
3. 当前贴出的配置**没有启用 HTTPS**。公网登录前，按 [自动 HTTPS 指南](https://doc.natfrp.com/frpc/auto-https.html) 和 [子域绑定与受信任证书指南](https://doc.natfrp.com/bestpractice/domain-bind.html) 在面板开启 TCP 自动 HTTPS，并绑定带可信证书的域名；重启隧道，检查客户端日志确实加载了证书。自动生成的自签证书不能作为真实账号登录的验收结果。访问认证如已启用，也需在手机访问时完成认证。
4. 用 SakuraFrp 官方客户端手动启动现有隧道，确认日志显示“连接节点成功”和面板当前**公网连接地址:远程端口**。在关闭 Wi‑Fi 的手机移动网络上，用 `https://实际域名:实际远程端口/` 打开，检查浏览器证书有效、登录与角色页面、问答、成绩单上传、资源下载。不要把 `frp-end.com:8088` 当站点地址。
5. 演示结束先在 SakuraFrp 客户端关闭隧道，再运行 `stop.ps1`。如服务原本由其他脚本启动，它们会继续运行。

你在聊天中粘贴了 SakuraFrp 访问密钥。它没有写入本仓库；**启用公网前请到面板轮换该密钥**，并更新客户端私有配置。明文 HTTP 仅可用于无敏感数据的临时连通性检查，不可让真实用户输入密码。

## 验收与排障

本机先运行 `health-check.ps1`，再按 [验收清单](deployment-checklist.md) 用手机移动网络逐项测试。这个脚本检查首页、History 刷新、六个本机和代理健康接口；健康接口只证明进程和路由可用，不证明模型、缓存或第三方服务可用。公网域名、证书、流量和隧道恢复必须人工验证。[实际测试记录](test-report.md)列出已执行与待执行项目。

常见问题：

- `502/503`：查看运行目录 `logs/` 与对应 FastAPI 服务日志，确认 8001–8006 仅在回环地址监听。
- API `404`：检查 `/api/{服务名}/` 前缀和 `proxy_pass` 尾部斜杠；静态页面刷新应返回 `index.html`。
- 上传 `413`：Nginx `client_max_body_size` 当前 25 MB，仍受后端实际文件限制约束。
- AI 超时：代理读写超时 180 秒，后端模型自己的初始化和推理期限仍独立生效。
- 公网打不开：核对客户端日志、远程端口、节点限制、访问认证与 HTTPS 状态；本地健康通过不等于公网通过。

官方 Nginx/Windows 说明其性能不适合高负载；此配置面向课程演示，不以本机测试推断并发能力。[Nginx 官方说明](https://nginx.org/en/docs/windows.html)
