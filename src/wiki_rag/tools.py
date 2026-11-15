"""Wikipedia RAG two-stage tool wiring: search_wikipedia + read_articles."""

import os
from typing import Any

from .engine import WikiSearchEngine
from .reader import WikiArticleReader

INDEX_DIR = os.environ.get("WIKI_RAG_INDEX_DIR") or "/home/minch/wiki_rag/tantivy_index"
PARQUET_DIR = os.environ.get("WIKI_RAG_PARQUET_DIR") or "/mnt/d/wiki_parquet_clean"

SEARCH_TOOL = {
    "name": "search_wikipedia",
    "description": (
        "Search offline English Wikipedia using BM25. Provide 1 to 3 distinct English keyword "
        "queries (including synonyms or technical terms) to search in parallel and get deduplicated "
        "top results with summaries and keyword-matched snippets."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "queries": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "1 to 3 English search queries, e.g. ['speculative decoding', "
                    "'draft model LLM inference']"
                ),
            },
            "top_k": {
                "type": "integer",
                "default": 15,
                "description": "Number of deduplicated results to return (10 to 20).",
            },
        },
        "required": ["queries"],
    },
}

READ_TOOL = {
    "name": "read_articles",
    "description": (
        "Fetch the full text of specific Wikipedia articles by their doc_ids after reviewing "
        "search snippets. Select only the 1 to 3 most relevant doc_ids needed to answer the "
        "user's question."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "doc_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "description": (
                    "List of 1 to 3 doc_id integers selected from search_wikipedia results."
                ),
            }
        },
        "required": ["doc_ids"],
    },
}


class _SingletonRegistry:
    """Module-level singletons so an agent loop pays the index-open cost once."""

    SEARCHER: WikiSearchEngine | None = None
    READER: WikiArticleReader | None = None

    @classmethod
    def get_searcher(cls) -> WikiSearchEngine:
        if cls.SEARCHER is None:
            cls.SEARCHER = WikiSearchEngine(INDEX_DIR)
        return cls.SEARCHER

    @classmethod
    def get_reader(cls) -> WikiArticleReader:
        if cls.READER is None:
            cls.READER = WikiArticleReader(PARQUET_DIR)
        return cls.READER


def get_searcher() -> WikiSearchEngine:
    return _SingletonRegistry.get_searcher()


def get_reader() -> WikiArticleReader:
    return _SingletonRegistry.get_reader()


def run_tool(name: str, arguments: dict) -> Any:
    if name == "search_wikipedia":
        engine = get_searcher()
        queries = arguments["queries"]
        top_k = int(arguments.get("top_k") or 15)
        results = engine.search(queries, top_k=top_k)
        if len(queries) == 1:
            return results
        out = []
        for r in results:
            out.append(
                {
                    "doc_id": r["doc_id"],
                    "title": r["title"],
                    "summary": r["summary"],
                    "matched_snippets": r["matched_snippets"],
                    "hit_queries": r.get("hit_queries", [queries[0]]),
                }
            )
        return out

    if name == "read_articles":
        reader = get_reader()
        doc_ids = arguments["doc_ids"]
        records = reader.read_articles(doc_ids, max_chars_per_article=16_000, include_redirects=False)
        return records

    raise ValueError(f"unknown tool: {name}")


SYSTEM_PROMPT_ADDITION = """## Wikipedia 檢索工作流程（兩階段）

- 先搜後讀：需要查證的問題，先呼叫 `search_wikipedia`（建議一次給 2 組不同切入點的英文關鍵字），審閱回傳的標題與加粗命中片段。
- 精準讀取：從搜尋結果中挑選 1 至 3 個最相關的 `doc_id` 呼叫 `read_articles` 取得全文；若第一輪片段顯示關鍵字偏移，允許再呼叫一次 `search_wikipedia` 換詞重搜，不要直接憑記憶編造細節。
"""
