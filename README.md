# wiki-rag-search

Two-stage retrieval toolkit for **offline English Wikipedia** - a tantivy BM25
index for candidate generation, plus a doc-id addressed full-article reader, wired
up as agent tools.

[![License: CC BY-SA 4.0](https://img.shields.io/badge/License-CC_BY-SA_4.0-light.svg)](https://creativecommons.org/licenses/by-sa/4.0/)

## Source & license

- Source corpus: English Wikipedia via Kiwix.
  - ZIM: `wikipedia_en_all_nopic_2026-06.zim` - <https://browse.library.kiwix.org/#lang=eng>
- License: CC BY-SA 4.0 (Creative Commons Attribution-ShareAlike 4.0 International).
- The cleaned Parquet shards (~9 GB) are intended to be hosted on Hugging Face Datasets.

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

## Quick start (Docker - primary deployment)

```bash
docker compose build
docker compose run --rm wiki-rag   # build tantivy BM25 index from mounted cleaned parquet -> /data/tantivy_index

# run the query tool against the built index
docker compose run --rm wiki-rag python -c "from wiki_rag.tools import run_tool; print(run_tool('search_wikipedia', {'queries': ['speculative decoding'], 'top_k': 5}))"
```

- Docker is the **primary** deployment method (Linux containers; Docker Desktop on
  Windows runs via the WSL2 backend, so it works on both Windows and Linux hosts).
- Mount/bind `./data/wiki_parquet_clean` (cleaned ~9 GB parquet) and
  `./data/tantivy_index` (built index, ~5.5 GB) via volumes in `docker-compose.yml`.

## Quick start (local, no Docker)

### Option A: One-click setup (Recommended)

Automatically downloads dependencies, grabs the Hugging Face dataset + pre-built index, auto-unpacks it, and runs verification tests in under 1 minute:

```bash
# Linux / macOS / WSL:
bash scripts/setup.sh

# Windows (PowerShell):
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

### Option B: Manual step-by-step

```bash
pip install -r requirements.txt
pip install huggingface_hub

# 1) Download the cleaned Parquet shards + pre-built Tantivy index (~14.5 GB total)
python -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='Ada0220/wikipedia-en-nopic-2026-06-clean', repo_type='dataset', revision='main', local_dir='./data')"

export WIKI_RAG_PARQUET_DIR=./data
export WIKI_RAG_INDEX_DIR=./data/tantivy_index

# 2) Unpack the pre-built Tantivy BM25 index (~5.5 GB, ready to search immediately)
tar -xf ./data/tantivy_index_v1.tar -C ./data

# (Optional) Or rebuild the index from scratch if modifying schema (~12 mins)
# python scripts/build_index.py

# 3) Run the query tool
python -c "from wiki_rag.tools import run_tool; print(run_tool('search_wikipedia', {'queries': ['speculative decoding'], 'top_k': 5}))"
```

No need to download a ~50 GB ZIM and transcode: the cleaned ~9 GB Parquet is the
input to the index builder; the extract/clean/strip scripts remain in `scripts/`
for reference.

## Windows note

- **Query side** (index build / search / read): expected to work natively on Windows
  (tantivy + pyarrow; tantivy may require a source build with Rust if no Windows wheel is published).
- **Extract side** (ZIM -> Parquet): **requires a Linux environment** (libzim /
  selectolax / multiprocessing handling). Do this stage in WSL or a Linux VM.

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

CC BY-SA 4.0: see [LICENSE](./LICENSE).
