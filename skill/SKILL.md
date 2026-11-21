---
name: wiki-rag-search
description: Two-stage offline Wikipedia retrieval toolkit. BM25 candidate search over 7.1M articles followed by doc_id addressed full-text reading.
version: 0.1.1
author: Xavier05273
license: MIT
platforms: [linux, windows, darwin]
metadata:
  hermes:
    tags: [bm25, rag, wikipedia, search, retrieval]
    related_skills: []
---

# Wiki RAG Search Skill

Two-stage retrieval over the offline English Wikipedia corpus (~7.13 million articles):
1. **Stage 1 (`search_wikipedia`)**: BM25 keyword search across title, aliases, lead summary, and body with Reciprocal Rank Fusion (RRF). Returns top hits with `doc_id`, title, summary, and bolded matched snippets (`matched_snippets`). Soft redirects (such as Wiktionary look up stubs) are automatically deprioritized.
2. **Stage 2 (`read_articles`)**: Direct `doc_id` addressed reader fetching the clean full text from local Parquet shards in milliseconds.

---

## When to Use

- When an agent must **verify facts or look up accurate knowledge** against offline English Wikipedia without hallucinations.
- When an agent needs to cite authoritative encyclopedic definitions, historical timelines, scientific principles, or technical specifications.
- When a task requires broad multi-query candidate retrieval followed by deep reading of selected articles.

---

## Environment & Prerequisites

- Python packages: `tantivy`, `pyarrow`, `huggingface_hub`
- Optional environment variables (auto-detected if omitted):
  - `WIKI_RAG_INDEX_DIR`: Path to `tantivy_index` (auto-unpacks `tantivy_index_v1.tar` if found).
  - `WIKI_RAG_PARQUET_DIR`: Path to the 286 Parquet shards directory.

---

## How to Call (Invocation Methods)

### Method 1: Python API (Standard)

The primary and recommended invocation method inside an agent script or Python runner:

```python
from wiki_rag.tools import run_tool

# ---------------------------------------------------------
# Step 1: Search Wikipedia (1 to 3 distinct English keyword queries)
# ---------------------------------------------------------
search_results = run_tool("search_wikipedia", {
    "queries": ["speculative decoding", "draft model LLM inference"],
    "top_k": 5
})

for hit in search_results:
    print(f"[{hit['doc_id']}] {hit['title']}")
    print(f"  Summary: {hit['summary']}")
    print(f"  Snippets: {hit['matched_snippets']}")

# ---------------------------------------------------------
# Step 2: Read Full Text for Selected doc_id(s) (1 to 3 articles)
# ---------------------------------------------------------
selected_doc_ids = [search_results[0]["doc_id"]]

articles = run_tool("read_articles", {
    "doc_ids": selected_doc_ids
})

for article in articles:
    print(f"Title: {article['title']}")
    print(f"Length: {len(article['text'])} chars (Truncated: {article['truncated']})")
    print(f"Full Text:\n{article['text'][:500]}...")
```

---

### Method 2: Shell / Bash One-liner

If the agent operates via a terminal or shell tool (`run_command` / `exec`):

#### 1. Search:
```bash
python -c "from wiki_rag.tools import run_tool; import json; print(json.dumps(run_tool('search_wikipedia', {'queries': ['speculative decoding'], 'top_k': 3}), indent=2))"
```

#### 2. Read full article:
```bash
python -c "from wiki_rag.tools import run_tool; import json; print(json.dumps(run_tool('read_articles', {'doc_ids': [6001760]}), indent=2))"
```

---

### Method 3: Agent Function Calling / Tool Registration

Export ready-to-use tool definitions directly into your LLM tool calling schema:

```python
from wiki_rag.tools import SEARCH_TOOL, READ_TOOL, run_tool

# Register SEARCH_TOOL and READ_TOOL with OpenAI / Anthropic / Gemini SDK:
tools = [SEARCH_TOOL, READ_TOOL]

# Dispatch function call by tool name:
# tool_name, tool_args = call.name, call.arguments
# tool_output = run_tool(tool_name, tool_args)
```

---

## Tool Reference

### `search_wikipedia`
Search offline Wikipedia using BM25 with multi-query Reciprocal Rank Fusion (RRF).

* **Arguments**:
  * `queries` (*list[str]*, required): 1 to 3 English search phrases (synonyms, technical terms, or variations).
  * `top_k` (*int*, optional): Number of deduplicated results to return (default: `15`, recommended: `5~15`).
* **Returns**: List of dicts:
  * `doc_id` (*int*): Unique integer ID used to fetch full text.
  * `title` (*str*): Wikipedia article title.
  * `summary` (*str*): Lead section summary (up to 350 characters).
  * `matched_snippets` (*list[str]*): Snippet with markdown bolding (`**term**`) indicating term matches generated from lead summary.
  * `hit_queries` (*list[str]*, only in multi-query): Queries that matched this document.

### `read_articles`
Directly read the full text of specified Wikipedia articles by their `doc_id`.

* **Arguments**:
  * `doc_ids` (*list[int]*, required): 1 to 3 `doc_id` integers selected from `search_wikipedia`.
* **Returns**: List of dicts:
  * `doc_id` (*int*): The requested article ID.
  * `title` (*str*): Article title.
  * `text` (*str*): Full cleaned article content (capped at 16,000 characters per article).
  * `truncated` (*bool*): `True` if article was truncated due to length.

---

## Best Practices & Guardrails

1. **Two-Stage Workflow ("Search First, Read Top Hits")**:
   - Never guess or fabricate Wikipedia details.
   - Always run `search_wikipedia` first with 2 complementary English terms (e.g. `['transformer architecture', 'self attention mechanism']`).
   - Review titles and matched snippets. Only pick the 1 to 3 most relevant `doc_id`s to pass to `read_articles`.
2. **Corpus Language**:
   - The offline corpus is **English Wikipedia**. Always formulate queries in English.
3. **Data Source Distinction**:
   - The Tantivy BM25 index stores only search metadata and lead summaries (~5.5 GB).
   - Full article content is read on-demand from the Parquet shards (~9.2 GB).

---

## Runtime & Environment Configuration

- **Dependencies**: Ensure required packages (`tantivy`, `pyarrow`, `huggingface_hub`) are installed in your Python environment.
- **Package Path**: Include `src` in `PYTHONPATH` (e.g., `export PYTHONPATH=src` or run `pip install -e .`).
- **Data Directories**: By default, searches `./data/tantivy_index` and `./data` (or automatically unpacks `tantivy_index_v1.tar` if present). Override when needed using environment variables:
  - `WIKI_RAG_INDEX_DIR`: Path to the `tantivy_index` directory.
  - `WIKI_RAG_PARQUET_DIR`: Path to the Parquet shards directory.
