# 知识库采集、索引与检索运维

## 当前数据口径

- 本地语料：119 份 Markdown 文档，23 个学科目录。
- Chroma 集合：`education_resources`，1,296 个按 Markdown 标题切分的语义分块。
- 大学公开课程来源：MIT、UC Berkeley、Stanford、Harvard、University of Helsinki 等；本轮 20 个大学目标中 17 个已落库。
- 每份文档记录来源 URL、站点、大学、课程、作者或机构、许可说明、采集范围、语言、采集时间、更新时间和内容哈希。

采集器使用明确的教育用途 User-Agent，读取并执行 `robots.txt`。禁止抓取或无法稳定提取的来源会记录为失败，不绕过访问控制。`source-terms` 表示内容仍受来源站点条款约束，不等于开放许可；使用前应查看原始链接。

## 命令行操作

仅检查大学来源，不发起请求：

```powershell
python scripts/crawl_resources.py --university-only --dry-run
```

采集尚未存在的大学课程页，然后增量索引：

```powershell
python scripts/crawl_resources.py --university-only --skip-existing
python scripts/normalize_corpus_metadata.py
python scripts/index_resources.py --batch-size 128
```

对单一学科操作：

```powershell
python scripts/crawl_resources.py --subject algorithms --skip-existing
python scripts/index_resources.py --subject algorithms --batch-size 128
```

固定 50 条查询的检索回归测试：

```powershell
python scripts/benchmark_rag.py --top-k 5 --output benchmarks/results/rag-top5.json
```

## HTTP API

Agent Service 默认监听 `http://127.0.0.1:8002`。

- `GET /knowledge-base/search`：公开搜索；支持 `subject`、`course`、`chapter`、`difficulty`、`university`、`source`、`source_site`、`language`、`license` 与 `retrieval_mode=hybrid|lexical|vector`。
- `GET /knowledge-base/status`：教师或管理员查看语料与实时 Chroma 状态。
- `GET /knowledge-base/sources`：教师或管理员查看允许采集的来源和本地状态。
- `POST /knowledge-base/reindex`：仅管理员执行增量或强制重建。
- `POST /knowledge-base/sources/crawl`：仅管理员从允许列表选择来源采集，可在完成后自动增量索引。

采集和重建共用单操作锁，避免并发写坏索引；一次 API 采集最多 30 个预配置来源。URL 不能由客户端任意指定，因此该接口不会成为通用 SSRF 代理。

## 检索策略

默认 `hybrid` 先尝试本地词法索引，置信度不足时才调用向量检索。查询、过滤条件、用户隔离范围、语料版本、嵌入版本和检索配置版本共同组成缓存键；私有缓存必须包含用户 ID。当前词法阈值为 `0.35`，它来自固定数据集的实测取舍，而不是主观设定。

课程资源生成和练习生成继续通过同一个 `ChromaRetriever` 读取这些分块，因此新语料和元数据过滤会直接进入课件、练习与知识库搜索链路。
