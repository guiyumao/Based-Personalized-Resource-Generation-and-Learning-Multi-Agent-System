# INC-01复盘

历史事故不关闭、不删除：PowerShell空赋值移除了环境变量，项目dotenv回退加载开发密钥；普通live标志被误当成执行授权。历史至少4次真实生成、6个测试成功仍标PASS_UNAUTHORIZED，不计本轮正式通过。

本轮没有读取开发.env或原密钥。git check-ignore确认.env被忽略，git ls-files及按.env路径的git log未发现该路径被跟踪/提交；这不能证明其他路径或旧日志从未泄露。子服务仅接收随机本地网关令牌，真实密钥由getpass无回显输入，只保留在受控网关进程内存，未写环境、配置、命令行或报告。用户在对话中提供了密钥，建议撤销换新，不擅自轮换。

普通pytest与子进程隔离已加强；这不是对任意恶意Python/native代码的OS级沙箱。原始证据SHA256见inherited-evidence.json。后续用户明确授权的真实调用单独记录，不能倒推为INC-01已获授权。