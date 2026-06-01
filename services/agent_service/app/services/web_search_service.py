"""Lightweight public-web grounding for open-domain QA."""

from __future__ import annotations

import html
import re
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from common.config import Settings


class WebSearchService:
    """Fetch compact, citation-like snippets from public endpoints without API keys."""

    CURRENT_INFO_TOKENS = (
        "今天",
        "明天",
        "后天",
        "现在",
        "实时",
        "最新",
        "刚刚",
        "天气",
        "温度",
        "降雨",
        "新闻",
        "股价",
        "汇率",
        "价格",
        "比赛",
        "比分",
        "票房",
        "日期",
        "时间",
    )
    WEATHER_TOKENS = ("天气", "温度", "下雨", "晴", "阴", "风力", "湿度", "降雨", "空气质量")

    def __init__(self, settings: Settings) -> None:
        timeout = max(3, min(settings.llm_request_timeout_seconds, 10))
        self.client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
                )
            },
        )

    def should_search(self, question: str) -> bool:
        normalized = question.strip().lower()
        return any(token in normalized or token in question for token in self.CURRENT_INFO_TOKENS)

    def search(self, question: str, max_results: int = 5) -> list[str]:
        snippets: list[str] = []

        if any(token in question for token in self.WEATHER_TOKENS):
            weather = self._fetch_weather(question)
            if weather:
                snippets.append(weather)

        snippets.extend(self._duckduckgo_instant_answer(question, limit=max_results))
        if len(snippets) < max_results:
            snippets.extend(self._duckduckgo_html_results(question, limit=max_results - len(snippets)))

        deduped: list[str] = []
        seen: set[str] = set()
        for item in snippets:
            cleaned = re.sub(r"\s+", " ", item).strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            deduped.append(cleaned)
        return deduped[:max_results]

    def _fetch_weather(self, question: str) -> str | None:
        location = self._extract_weather_location(question)
        if not location:
            return None

        try:
            response = self.client.get(f"https://wttr.in/{location}", params={"format": "j1", "lang": "zh"})
            response.raise_for_status()
            payload = response.json()
            current = (payload.get("current_condition") or [{}])[0]
            weather_today = (payload.get("weather") or [{}])[0]
            hourly = (weather_today.get("hourly") or [{}])[0]
            desc_items = current.get("lang_zh") or current.get("weatherDesc") or []
            description = desc_items[0].get("value", "") if desc_items else ""
            temp = current.get("temp_C", "")
            feels_like = current.get("FeelsLikeC", "")
            humidity = current.get("humidity", "")
            wind = current.get("windspeedKmph", "")
            rain = hourly.get("chanceofrain", "")
            return (
                f"天气参考（{location}）: 当前{description or '天气信息已返回'}，"
                f"气温 {temp}°C，体感 {feels_like}°C，湿度 {humidity}%，"
                f"风速 {wind} km/h，降雨概率 {rain}%。"
            )
        except Exception:
            return None

    def _extract_weather_location(self, question: str) -> str | None:
        cleaned = question.strip()
        cleaned = re.sub(r"[？?。！!,，]", " ", cleaned)
        match = re.search(r"(今天|明天|后天|现在)?(?P<location>[\u4e00-\u9fa5A-Za-z\s]{2,20}?)(的)?天气", cleaned)
        if match:
            return match.group("location").strip()
        match = re.search(r"(?P<location>[\u4e00-\u9fa5A-Za-z\s]{2,20})\s+(天气|温度)", cleaned)
        if match:
            return match.group("location").strip()
        return None

    def _duckduckgo_instant_answer(self, question: str, limit: int) -> list[str]:
        try:
            response = self.client.get(
                "https://api.duckduckgo.com/",
                params={"q": question, "format": "json", "no_html": "1", "skip_disambig": "1"},
            )
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return []

        results: list[str] = []
        answer = payload.get("Answer")
        abstract = payload.get("AbstractText")
        heading = payload.get("Heading")
        if answer:
            results.append(f"{heading or '即时答案'}: {answer}")
        elif abstract:
            results.append(f"{heading or '参考摘要'}: {abstract}")

        for item in payload.get("RelatedTopics", []):
            if isinstance(item, dict) and item.get("Text"):
                results.append(item["Text"])
            elif isinstance(item, dict) and isinstance(item.get("Topics"), list):
                for sub_item in item["Topics"]:
                    text = sub_item.get("Text") if isinstance(sub_item, dict) else None
                    if text:
                        results.append(text)
            if len(results) >= limit:
                break
        return results[:limit]

    def _duckduckgo_html_results(self, question: str, limit: int) -> list[str]:
        try:
            response = self.client.post(
                "https://html.duckduckgo.com/html/",
                data={"q": question},
            )
            response.raise_for_status()
            body = response.text
        except Exception:
            return []

        pattern = re.compile(
            r'<a[^>]*class="result__a"[^>]*href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>.*?'
            r'(?:<a[^>]*class="result__snippet"[^>]*>(?P<snippet_a>.*?)</a>|'
            r'<div[^>]*class="result__snippet"[^>]*>(?P<snippet_div>.*?)</div>)',
            flags=re.S,
        )
        results: list[str] = []
        for match in pattern.finditer(body):
            title = self._clean_html(match.group("title"))
            snippet = self._clean_html(match.group("snippet_a") or match.group("snippet_div") or "")
            url = self._decode_duckduckgo_url(match.group("href"))
            if not title and not snippet:
                continue
            if url:
                results.append(f"{title}: {snippet} 来源: {url}")
            else:
                results.append(f"{title}: {snippet}")
            if len(results) >= limit:
                break
        return results

    def _decode_duckduckgo_url(self, raw_url: str) -> str:
        parsed = urlparse(raw_url)
        if parsed.netloc.endswith("duckduckgo.com"):
            query = parse_qs(parsed.query)
            uddg = query.get("uddg")
            if uddg:
                return unquote(uddg[0])
        return raw_url

    def _clean_html(self, raw: str) -> str:
        text = html.unescape(raw)
        text = re.sub(r"<.*?>", "", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()
