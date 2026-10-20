from __future__ import annotations

from bs4 import BeautifulSoup

from scripts.crawl_resources import _html_to_markdown
from scripts.index_resources import _extract_source_metadata, chunk_document


def test_html_to_markdown_keeps_blocks_without_nested_duplicates() -> None:
    soup = BeautifulSoup(
        "<article><h2>标题</h2><p>第一段 <strong>重点</strong></p>"
        "<ul><li>要点一</li><li>要点二</li></ul></article>",
        "html.parser",
    )
    markdown = _html_to_markdown(soup.article)
    assert markdown.count("第一段 重点") == 1
    assert markdown.count("要点一") == 1
    assert "## 标题" in markdown


def test_chunk_document_preserves_heading_context_and_size_limit() -> None:
    content = "# Python\n\n## 异步函数\n\n" + "await 用于等待协程结果。" * 80
    chunks = chunk_document(content, chunk_size=240, overlap=36)
    assert len(chunks) > 2
    assert all(len(chunk) <= 240 for chunk in chunks)
    assert any("异步函数" in chunk and "await" in chunk for chunk in chunks)


def test_source_metadata_is_preserved_for_vector_filters() -> None:
    content = """# 课程资料

> 文档ID: abc123
> 来源: https://example.edu/course
> 来源站点: example.edu
> 大学: Example University
> 课程: CS 101
> 授权: CC BY 4.0
> 学科: computer_systems | 难度: 进阶
"""

    metadata = _extract_source_metadata(content)

    assert metadata["document_id"] == "abc123"
    assert metadata["university"] == "Example University"
    assert metadata["course"] == "CS 101"
    assert metadata["difficulty"] == "进阶"
