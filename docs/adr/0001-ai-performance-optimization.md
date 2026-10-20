# ADR-0001: Incremental AI performance optimization

- Status: accepted
- Date: 2026-09-16

## Context

Courseware, exercise, tutoring, learning-path, report, and resource generation
share LLM and retrieval dependencies. Their latency has not been separated into
retrieval, generation, audit, retry, and persistence stages, while some request
paths repeat profile loading, retrieval, model calls, or queue publication.

## Decision

Keep the existing six-service boundary, Vue 3 client, FastAPI services,
LangGraph coordinator, databases, RabbitMQ, and Chroma. Optimize in this order:

1. Add request-level timing and token traces without logging secrets.
2. Make Chroma mode, collection, corpus, chunking, and embedding versions explicit.
3. Reuse clients and retrieval results within one request, and add versioned caches.
4. Use metadata filtering before vector search and keep retrieval depth configurable.
5. Run query rewrite, rerank, and LLM audit only when deterministic rules require them.
6. Preserve authentication, tenant and class isolation, persistence, and audit states.

Advanced search infrastructure will only be considered after repeatable benchmark
evidence shows that the preceding changes are insufficient.

## Consequences

The initial implementation adds no mandatory external infrastructure. Process-local
caches improve single-worker reuse; multi-worker distributed caching remains an
optional later step. Existing API shapes stay backward compatible while optional
generation and retrieval settings are added.
