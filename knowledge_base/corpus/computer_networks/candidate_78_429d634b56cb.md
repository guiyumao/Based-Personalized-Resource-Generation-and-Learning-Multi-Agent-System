# HTTPS · 应用层：C/S 与 P2P、DNS、HTTP、FTP、邮件与 DHCP

> 文档ID: candidate-78-429d634b56cb
> 来源: https://www.chinakaoyan.com/info/article/id/412451.shtml
> 来源类型: ai_generated_auto_published
> 审核状态: 模型审核通过后自动发布，未经人工审核
> 授权: AI_GENERATED
> 学科: computer_networks | 难度: 未标注
> 内容哈希: 429d634b56cb5288fa0c48a93c523564c010ba60f3cfbdd9c8170328923cdea7
> 更新时间: 2026-10-22T16:34:48.496239Z

## 知识点

HTTPS

## 正文

## 知识点定位

知识点：HTTPS（所属：计算机网络 / 应用层：C/S 与 P2P、DNS、HTTP、FTP、邮件与 DHCP）

## 本知识点要点（考研向）

- HTTP over TLS/SSL，端口 443，提供加密、完整性校验与身份认证。
- 握手阶段用非对称加密协商会话密钥，传输数据用对称加密。
- 依靠 CA 颁发的数字证书验证服务器身份，防中间人攻击。
- 相比 HTTP 增加握手开销，可用会话复用降低时延。

## 所属章节完整讲解

### 应用层：C/S 与 P2P、DNS、HTTP、FTP、邮件与 DHCP

## 考纲定位

应用层考纲：网络应用模型（C/S、P2P）、DNS（层次域名空间、服务器类型、解析过程）、FTP、电子邮件（SMTP/POP3/IMAP、MIME、万维网 WWW 与 HTTP 协议）。每年 1~2 道选择题。

## 网络应用模型

- C/S 模型：服务器常开、地址固定，客户请求服务；扩展靠服务器集群，服务器是性能瓶颈。
- P2P 模型：结点对等，无固定服务器（或仅索引服务器），自扩展性强（用户越多下载越快），典型 BitTorrent；内存与带宽利用率高但管理难、版权问题。

## DNS

- 层次域名空间：根 → 顶级域（com/org/cn…）→ 二级域 → 主机名，FQDN 自左向右级别升高。
- 服务器四类：根（13 组）、顶级域、权限（授权）、本地（递归查询入口）；DNS 使用 UDP 53（区域传送用 TCP）。
- 解析过程：主机 → 本地域名服务器（递归查询）→ 根/顶级/权限服务器（通常迭代查询，返回下一站地址）；有缓存。资源记录类型：A（域名→IP）、CNAME 别名、MX 邮件交换、NS 权威名服务器、PTR 反向。

## HTTP 与 WWW

- URL = 协议://主机:端口/路径。HTTP 基于 TCP 80 端口，无状态（Cookie 补状态）。
- 报文：请求行（方法 GET/POST/HEAD/PUT/DELETE）+ 首部 + 实体；响应：状态行（1xx 信息 2xx 成功 3xx 重定向 4xx 客户端错 5xx 服务器错）。
- 非持久连接每对象一次 TCP（HTTP/1.0）；持久连接（HTTP/1.1 默认）流水线方式可连续发请求。请求一个网页的时延计算：TCP 握手 1 RTT + 请求/响应 1 RTT（非持久每对象再来一轮）。
- HTTP/1.1、HTTP/2 多路复用、HTTP/3 over QUIC(UDP) 作了解。
- HTTPS = HTTP over TLS/SSL，443 端口：非对称加密交换会话密钥 + 对称加密传输数据 + 证书认证身份，提供加密、完整性与身份验证。

## FTP

控制连接（TCP 21，全程保持）与数据连接（TCP 20，按需建立，主动模式服务器发起；被动模式客户端发起）分离；控制信息带外传送（out-of-band）。

## 电子邮件

- 组成：用户代理 UA、邮件服务器、协议。发送方 UA →(SMTP)→ 发方服务器 →(SMTP)→ 收方服务器 →(POP3 110 / IMAP)→ 收方 UA。
- SMTP 推协议、只能传 7 位 ASCII，MIME 扩展支持多媒体与多字符集；Web 邮件走 HTTP。

## DHCP

应用层、UDP、广播工作（服务器 67 / 客户端 68）；四步交互 Discover/Offer/Request/ACK；分配 IP、子网掩码、默认网关、DNS 服务器地址；租期机制；跨网段用 DHCP 中继代理。

## 高频考查方式与易错点

1. DNS 递归与迭代查询的组合场景图题：客户端到本地服务器递归，本地到根迭代。
2. FTP 两个连接与端口号；SMTP 是推、POP3 是拉。
3. HTTP 非持久/持久连接请求总时延计算（区分对象数）。
4. 各协议端口：DNS 53(UDP/TCP)、HTTP 80、HTTPS 443、SMTP 25、POP3 110、FTP 20/21。
