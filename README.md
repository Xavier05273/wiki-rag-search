# wiki-rag-search

Two-stage retrieval toolkit for **offline English Wikipedia** — a tantivy BM25
index for candidate generation, plus a doc-id addressed full-article reader, wired
up as agent tools.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](#license)

## Why

When an LLM agent must *verify* a fact instead of hallucinating one, the cheap move is:

1. **Search** the corpus with BM25 (title / aliases / body, with field boosts and
   snippet generation).
2. **Read** the top hit(s) by `doc_id` and answer from the fetched full text.

That is the whole product. Everything else (cleaning, lead-sentence summaries,
redirect handling) exists to make step 2 trustworthy.

## Architecture

```
ZIM (libzim) ──extract──> Parquet shards (pyarrow) ──clean──> tantivy BM25 index
                                                                        │
agent loop ──search_wikipedia──> hits w/ doc_id/snippet ──read_articles──> full text
```

- **Query tool** (`wiki_rag.tools`): `search_wikipedia`, `read_articles`
- **Engine** (`wiki_rag.engine`): BM25 + reciprocal rank fusion (RRF)
- **Reader** (`wiki_rag.reader`): doc-id -> full article text over parquet shards

## Quick start

```bash
pip install -r requirements.txt

# 1) Point the env vars at your corpus
export WIKI_RAG_ZIM=/data/wikipedia_en_all_nopic_2026-06.zim
export WIKI_RAG_EXTRACT_OUT_DIR=/data/wiki_parquet_shards
export WIKI_RAG_PARQUET_DIR=/data/wiki_parquet_clean
export WIKI_RAG_INDEX_DIR=/data/tantivy_index

# 2) Build the index (reads cleaned parquet shards)
python scripts/build_index.py

# 3) Run the query tool
python -c "from wiki_rag.tools import run_tool; print(run_tool('search_wikipedia', {'queries': ['speculative decoding'], 'top_k': 5}))"
```

## Tool reference

### `search_wikipedia`

| param | type | required | notes |
|---|---|---|---|
| `queries` | string[] | yes | 1-3 English keyword queries (synonyms / technical terms ok) |
| `top_k` | int | no | deduplicated result count, default 15 (10-20) |

Returns hits with `doc_id`, `title`, `summary`, `matched_snippets`. Multi-query mode
returns `hit_queries` for RRF attribution.

### `read_articles`

| param | type | required | notes |
|---|---|---|---|
| `doc_ids` | int[] | yes | 1-3 doc_ids picked from `search_wikipedia` results |

Returns `{doc_id, title, text, truncated}`.

## Skill

`skill/SKILL.md` is the agent-facing prompt: when to use the tools, the
two-stage "search then read" workflow, and the anti-hallucination guardrails
(fetched content is authoritative; never invent details).

## Tests

```bash
pip install -r requirements.txt
pytest tests/
```

## License

MIT — see [LICENSE](./LICENSE).
