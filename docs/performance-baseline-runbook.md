# 性能基线运行手册

代码已经提供统一 JSONL Trace、50 条固定 RAG Query 和 30 条课件任务样本。基线和优化结果必须使用同一模型、同一输入、同一并发和同一 Chroma 模式；不能用关闭审核或减少业务数据来制造速度提升。

## 启动条件

1. 安装项目依赖（包括 `chromadb`），启动 `docker compose up chroma` 或使用本地 `CHROMA_MODE=persistent`。
2. 确认导入脚本与 agent 服务打印的 `mode`、`collection`、`collection_version`、`embedding_model_version` 和 `corpus_version` 完全一致。
3. 运行 `python scripts/index_resources.py --dry-run` 检查文件、分块和版本；确认后再执行正式索引。索引脚本在 Chroma 不可用时不会写 manifest。

语料增量和批量索引：

```powershell
python scripts/crawl_resources.py --skip-existing
python scripts/index_resources.py --batch-size 128
```

爬虫会保存来源、站点、爬取时间、学科、难度和标签。索引脚本使用标题感知分块、句子边界和批量 upsert；`RAG_CHUNKER_VERSION` 参与指纹，分块算法更改时不会错误复用旧向量。

## 检索实验

```powershell
python scripts/benchmark_rag.py --top-k 3 5 8 10 --output benchmarks/results/rag.json
```

该实验比较 Vector only 与 Metadata + Vector，并输出 Recall@K、MRR、P95 retrieval_ms、平均上下文长度。Hybrid 或 Rerank 只有在这组数据证明收益后才应开启。

当 `RAG_LEXICAL_FAST_PATH=true` 时，高置信词法命中会在查询嵌入前返回，其余问题仍回退到 Chroma 向量检索。基准结果中的 `strategy_counts` 必须与 Recall/MRR 一起阅读，避免只看延迟。

## 生成实验

使用 `benchmarks/courseware_tasks.json` 逐项调用课件生成接口，分别保存优化前和优化后的 `logs/ai-performance.jsonl`。调用时保持并发、模型、请求体和用户数据不变。完成后运行：

```powershell
python scripts/performance_report.py logs/baseline-ai-performance.jsonl --output benchmarks/results/baseline.md
python scripts/performance_report.py logs/optimized-ai-performance.jsonl --baseline logs/baseline-ai-performance.jsonl --output benchmarks/results/optimized.md
```

报告会给出每个任务的 P50/P95 总耗时、检索/生成/审核阶段、输入 Token、上下文缓存命中率和前后改善比例。当前工作区未安装 `chromadb`，因此不能把未执行的 P50/P95 写成结果；安装依赖并启动服务后再生成正式报告。
