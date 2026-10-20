# 无费用隔离

已实施：common.config支持关闭dotenv；普通tests/conftest在项目导入前自动bootstrap隔离；专用运行器采用宿主环境白名单、新SQLite/目录/JWT、空Provider基址和测试哨兵；第三方dotenv返回空值，直接读取.env被拒。

HTTPX同步/异步URL检查+socket DNS/connect/sendto审计，只允许显式端口或当前受控Python实际创建的loopback监听器；代理变量移除且NO_PROXY=*。Python子进程必须继承guard环境，Windows另加Popen验证。sitecustomize安装异常以78退出，不能吞异常后继续执行。两个live标志、缓存重载、fake-IP、未声明本机代理、Worker导入、重试与缺失guard子进程均已测试。

final-safety为16 passed，普通直接pytest另有13 passed。第一轮暴露Windows子进程校验和Chroma自读.env问题，失败保留，修复后复验通过。Node/浏览器通过精确本机origin路由限制、无真实Provider密钥及Vite独立envDir保护，不声称已建立OS防火墙。真实授权入口是独立父网关，子业务仍只能连接本机。