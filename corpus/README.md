# Corpus notes

This package ships the *plumbing* around the offline English Wikipedia corpus. The
corpus itself is intentionally not committed: it is multi-gigabyte and rebuilt from
source.

## Source & license

- Source corpus: English Wikipedia via Kiwix.
  - ZIM: `wikipedia_en_all_nopic_2026-06.zim` - <https://browse.library.kiwix.org/#lang=eng>
- License: CC BY-SA 4.0 (Creative Commons Attribution-ShareAlike 4.0 International).
- The cleaned Parquet shards (~9 GB) are hosted on Hugging Face Datasets:
  https://huggingface.co/datasets/Ada0220/wikipedia-en-nopic-2026-06-clean/tree/main

## Sources

| Stage | Input | Output | Notes |
|---|---|---|---|
| Extract | `wikipedia_en_all_nopic_*.zim` (ZIM, libzim) | `wiki_en_*.parquet` | excludes Category:/Portal:/File:/Wikipedia:/Template:/Help:/Draft:/Module:/MediaWiki:/TimedText:/Book: namespaces, redirects and disambiguation pages |
| Clean | raw shards | cleaned shards | strips `/* start ... */` markers, Kiwix footer, repairs paragraph / punctuation / apostrophe whitespace |
| Strip footer | cleaned shards | cleaned shards | removes `This article is issued from Wikipedia` |
| Build | cleaned shards | tantivy index | BM25 over `doc_id`, `title`, `aliases`, `summary`, `body` |

## Observed numbers (this machine)

- Extracted valid articles: **7,135,185** docs (final tantivy build reported `BUILD_DONE 7135185`)
- Index build time: ~46.8 min, 286 parquet shards at 25,000 docs/shard
- Index size on disk: ~29 GB (tantivy managed segments)

## Expected directory layout

```
WIKI_RAG_ZIM=/data/wikipedia_en_all_nopic_2026-06.zim
WIKI_RAG_EXTRACT_OUT_DIR=/data/wiki_parquet_shards
WIKI_RAG_PARQUET_DIR=/data/wiki_parquet_clean     # <- input to build_index.py
WIKI_RAG_INDEX_DIR=/data/tantivy_index           # <- output of build_index.py
```

The query-time env vars are:

- `WIKI_RAG_INDEX_DIR` - tantivy index directory (query tool reads here)
- `WIKI_RAG_PARQUET_DIR` - cleaned parquet shards directory (doc-id -> full text reader)

## Adding a new corpus

1. Point `WIKI_RAG_ZIM` / `WIKI_RAG_EXTRACT_OUT_DIR` at a new archive and re-run
   `scripts/extract_wiki.py`.
2. Run `scripts/clean_shards.py`, then `scripts/strip_footer.py`.
3. Run `scripts/build_index.py` and point the query tools at the new index.
