# 模型调用链

call-sites.json枚举当前模型工厂、Search/Fetch及预算调用位置。QA、聊天、课件、练习、结构化资源、路径、画像、报告、协调器及Worker均有独立入口，不能只检查一个API。知识规划/综合与Search/Fetch有knowledge_budget预留；普通聊天/资源/评价和图谱不自动享受该保护。同步/后台及重试边界见既有source-audit和Worker实现，本轮未修改生产调用链。

图谱依赖实际为POST /graph/dependencies；匿名模型调用及个人资源元数据泄露仍是前轮确认的OPEN业务问题，补丁在global-audit-resume-20261019/patches，未因真实调用授权而自动应用。