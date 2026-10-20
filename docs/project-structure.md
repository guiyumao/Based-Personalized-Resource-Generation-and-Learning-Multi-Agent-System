# 项目目录说明

本仓库是 Python/FastAPI 多服务、Vue 3 前端以及 Java 迁移骨架并存的全栈项目。目录整理遵循“运行代码稳定、生成物集中、历史材料可追溯”的原则。

| 目录 | 用途 | 是否参与运行 |
| --- | --- | --- |
| `common/` | Python 公共配置、数据库模型、安全与性能组件 | 是 |
| `services/` | 8001–8007 FastAPI 服务 | 是 |
| `web-app/` | Vue 3 前端 | 是 |
| `java-services/` | Java/Spring Boot 迁移骨架 | 预研 |
| `alembic/` | 数据库迁移 | 是 |
| `scripts/` | 本地启动、采集、索引和基准脚本 | 是 |
| `knowledge_base/corpus/` | 可审计的知识库 Markdown 原文 | 是 |
| `knowledge_base/index/` | 本地 Chroma 向量索引，运行时生成并被 Git 忽略 | 是 |
| `benchmarks/` | 固定查询集和 RAG 性能结果 | 验证 |
| `tests/` | 自动化测试 | 验证 |
| `docs/` | 当前文档、ADR 和历史方案 | 否 |
| `prompts/` | 智能体提示词模板 | 是 |
| `infrastructure/` | 网关等基础设施配置 | 部署 |
| `ui-demo/` | 早期静态界面参考，不是当前前端入口 | 否 |
| `workspace/` | 已纳入版本管理的答辩/PPT 源文件 | 否 |
| `artifacts/` | 本地媒体、导出物和历史快照 | 否 |
| `logs/` | 性能与各服务运行日志，Git 忽略 | 运行时 |

## 根目录保留内容

根目录只保留入口文档、环境模板、构建与启动配置，例如 `README.md`、`.env.example`、`pyproject.toml`、`docker-compose.yml`、`alembic.ini` 和启动脚本。数据库文件、日志、缓存、向量索引以及大体积交付物均为本地运行数据，不应提交。

## 常用入口

- 启动全部本地服务：`scripts/start_local_services.ps1`
- 知识库采集：`scripts/crawl_resources.py`
- Chroma 增量索引：`scripts/index_resources.py`
- RAG 基准：`scripts/benchmark_rag.py`
- 当前知识库运维说明：`docs/knowledge-base-operations.md`
