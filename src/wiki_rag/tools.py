"""Wikipedia RAG two-stage tool wiring: search_wikipedia + read_articles."""

import os
import tarfile
from pathlib import Path
from typing import Any

from .engine import WikiSearchEngine
from .reader import WikiArticleReader


def resolve_index_dir() -> str:
    """Resolve tantivy index directory, or auto-unpack from tarball if available."""
    env_dir = os.environ.get("WIKI_RAG_INDEX_DIR")

    # 1. If explicit env var is given
    if env_dir:
        p = Path(env_dir)
        if p.is_dir() and (p / "meta.json").exists():
            return str(p)
        # Check if tarball exists nearby to unpack
        tar_candidates = [
            p.parent / "tantivy_index_v1.tar",
            p / "tantivy_index_v1.tar",
            Path(p.name + "_v1.tar"),
        ]
        for tar_path in tar_candidates:
            if tar_path.is_file():
                print(f"[wiki_rag] Found pre-built index tarball: {tar_path}. Unpacking to {p.parent}...")
                with tarfile.open(tar_path, "r") as tf:
                    tf.extractall(path=p.parent)
                if p.is_dir() and (p / "meta.json").exists():
                    print(f"[wiki_rag] Index unpacked successfully to {p}")
                    return str(p)

    # 2. Check default relative and system directories
    default_candidates = [
        Path("./data/tantivy_index"),
        Path("./tantivy_index"),
        Path("/data/tantivy_index"),
    ]
    for p in default_candidates:
        if p.is_dir() and (p / "meta.json").exists():
            return str(p)

    # Check for tarball in default locations
    default_tar_candidates = [
        Path("./data/tantivy_index_v1.tar"),
        Path("./tantivy_index_v1.tar"),
        Path("/data/tantivy_index_v1.tar"),
    ]
    for tar_path in default_tar_candidates:
        if tar_path.is_file():
            target_parent = tar_path.parent
            print(f"[wiki_rag] Found pre-built index tarball: {tar_path}. Unpacking to {target_parent}...")
            with tarfile.open(tar_path, "r") as tf:
                tf.extractall(path=target_parent)
            unpacked_dir = target_parent / "tantivy_index"
            if unpacked_dir.is_dir():
                print(f"[wiki_rag] Index unpacked successfully to {unpacked_dir}")
                return str(unpacked_dir)

    # 3. Local author fallback
    author_path = Path("/home/minch/wiki_rag/tantivy_index")
    if author_path.is_dir() and (author_path / "meta.json").exists():
        return str(author_path)

    return env_dir or str(Path("./data/tantivy_index"))


def resolve_parquet_dir() -> str:
    """Resolve directory containing parquet shards."""
    env_dir = os.environ.get("WIKI_RAG_PARQUET_DIR")
    candidates = []
    if env_dir:
        candidates.append(Path(env_dir))
    candidates.extend([
        Path("./data/wiki_parquet_clean"),
        Path("./data"),
        Path("/data/wiki_parquet_clean"),
        Path("/data"),
        Path("/mnt/d/wiki_parquet_clean"),
    ])
    for p in candidates:
        if p.is_dir() and (list(p.glob("*.parquet")) or list(p.glob("*/*.parquet"))):
            return str(p)
    return str(candidates[0] if candidates else Path("./data"))


INDEX_DIR = resolve_index_dir()
PARQUET_DIR = resolve_parquet_dir()

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
