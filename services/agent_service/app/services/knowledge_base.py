"""Curated knowledge snippets used to ground courseware and exercise generation."""

from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class KnowledgeArticle:
    """One curated knowledge article for a learning topic."""

    title: str
    subject: str
    level: str
    summary: str
    concepts: list[str]
    syntax: list[str]
    examples: list[str]
    mistakes: list[str]
    applications: list[str]
    checks: list[str]


class KnowledgeBaseService:
    """Provide curated topic knowledge before falling back to generic generation.

    All hardcoded articles have been removed. This service now returns None for
    get_article() and empty lists for list_articles()/search(), forcing the system
    to rely on LLM-generated content and the pgvector knowledge base.
    """

    def __init__(self) -> None:
        self._articles: list[tuple[tuple[str, ...], KnowledgeArticle]] = []

    def get_article(self, knowledge_point: str) -> KnowledgeArticle | None:
        """Return a curated article for a knowledge point if one exists."""
        return None

    def list_articles(self, subject: str | None = None) -> list[KnowledgeArticle]:
        """Return curated articles, optionally filtered by subject."""
        return []

    def article_to_dict(self, article: KnowledgeArticle) -> dict[str, object]:
        """Convert a KnowledgeArticle to a dictionary."""
        return {
            "title": article.title,
            "subject": article.subject,
            "level": article.level,
            "summary": article.summary,
            "concepts": article.concepts,
            "syntax": article.syntax,
            "examples": article.examples,
            "mistakes": article.mistakes,
            "applications": article.applications,
            "checks": article.checks,
            "external_resources": [],
        }

    def search(self, question: str, subject: str | None = None, top_k: int = 3) -> list[KnowledgeArticle]:
        """Search for articles relevant to a question."""
        return []

    def search_by_keywords(self, question: str, top_k: int = 3) -> list[KnowledgeArticle]:
        """Deprecated: alias for search()."""
        return []

    def list_subjects(self) -> list[str]:
        """Return available knowledge subjects."""
        return []

    def _slugify(self, text: str) -> str:
        return re.sub(r"[\s：、，,]+", "-", text.strip().lower()).strip("-")

    def _extract_keywords(self, question: str) -> list[str]:
        tokens = [
            token.strip().lower()
            for token in re.split(r"[\s，。！？,!.?；;：:、（）()]+", question)
            if token.strip()
        ]
        return [token for token in tokens if len(token) >= 2]
