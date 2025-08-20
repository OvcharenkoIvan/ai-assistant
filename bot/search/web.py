# bot/search/web_async.py
from __future__ import annotations
import logging
from typing import List, Dict
import os
import aiohttp
from bot.core.config import SERPAPI_KEY, SEARCH_LOCALE, SEARCH_COUNTRY
from bot.gpt.translate import translate_text # Импортируем функцию перевода
  # твоя функция перевода через GPT

logger = logging.getLogger(__name__)

class WebSearchError(Exception):
    pass

async def web_search(query: str, max_results: int = 5, lang: str | None = None, country: str | None = None, translate: bool = True) -> List[Dict]:
    """
    Асинхронный поиск через SerpAPI и возврат списка результатов:
    [{title, link, snippet}, ...]
    """
    if not SERPAPI_KEY:
        logger.warning("SERPAPI_KEY не настроен — web_search пропущен")
        return []

    lang = lang or SEARCH_LOCALE
    country = country or SEARCH_COUNTRY

    params = {
        "engine": "google",
        "q": query,
        "api_key": SERPAPI_KEY,
        "hl": lang,
        "gl": country,
        "num": max_results,
        "safe": "active",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://serpapi.com/search.json", params=params, timeout=15) as r:
                r.raise_for_status()
                data = await r.json()
    except Exception as e:
        logger.exception("Ошибка запроса SerpAPI")
        raise WebSearchError(str(e)) from e

    results = []
    for item in (data.get("organic_results") or [])[:max_results]:
        snippet = (item.get("snippet") or "").strip()
        if translate and snippet:
            try:
                snippet = await translate_text(snippet, target_language="Russian")
            except Exception as e:
                logger.warning("Не удалось перевести сниппет: %s", e)
        results.append({
            "title": (item.get("title") or "").strip(),
            "link": (item.get("link") or "").strip(),
            "snippet": snippet,
        })

    return results

def render_results_for_prompt(results: List[Dict]) -> str:
    """
    Превращает результаты в компактный текст для передачи модели.
    """
    if not results:
        return ""
    lines = []
    for i, r in enumerate(results, 1):
        title = r["title"]
        link = r["link"]
        snippet = r["snippet"] or ""
        if len(snippet) > 400:
            snippet = snippet[:400] + "…"
        lines.append(f"{i}. {title}\n{link}\n{snippet}")
    return "\n\n".join(lines)
