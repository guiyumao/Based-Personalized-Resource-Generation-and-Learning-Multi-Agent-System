# 独立知识库

本目录集中保存项目当前使用的 RAG 知识库，避免原始语料、向量索引和业务源码混放。

```text
knowledge_base/
├── corpus/   # 119 份可审计 Markdown 原始文档，按 23 个学科分类
└── index/    # Chroma 持久化索引及 index_manifest.json
```

## 数据说明

- `corpus/` 纳入版本管理，每份文档包含来源、学校、课程、许可、语言、时间和内容哈希等元数据。
- `index/` 是可重新生成的本地运行数据，已被 Git 忽略；当前集合名称为 `education_resources`。
- 采集器遵守来源站点的 `robots.txt`，禁止或无法稳定提取的页面不会绕过限制。

## 必备计算机基础科目

| 科目 | 目录 | 文档数 | 向量分块数 |
| --- | --- | ---: | ---: |
| 计算机网络 | `corpus/computer_networks/` | 2 | 12 |
| 数据结构 | `corpus/data_structures/` | 8 | 98 |
| 计算机组成原理 | `corpus/computer_architecture/` | 2 | 13 |
| 操作系统 | `corpus/operating_systems/` | 3 | 20 |

## 常用操作

```powershell
# 补全或更新允许列表中的公开课程资料
python scripts/crawl_resources.py --university-only --skip-existing

# 规范化文档元数据
python scripts/normalize_corpus_metadata.py

# 增量重建 Chroma 索引
python scripts/index_resources.py --batch-size 128
```

更完整的权限、接口和检索策略说明见 [`../docs/knowledge-base-operations.md`](../docs/knowledge-base-operations.md)。
