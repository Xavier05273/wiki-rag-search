---
name: wiki-rag-search
description: BM25 Wikipedia search then full article read by doc_id.
version: 0.1.0
author: Minchen (minchen), Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [bm25, rag]
    related_skills: []
---

# Wiki RAG Search Skill

Two-stage retrieval over the offline English Wikipedia corpus: a tantivy BM25
index for candidate generation, then a doc id addressed reader for full text.

## When to Use

- The user asks to search or verify facts against the local Wikipedia corpus.
- An agent loop needs candidate retrieval followed by document fetch.

## Prerequisites

- tantivy and pyarrow installed in the agent environment.
- BM25 index built from the cleaned wiki Parquet shards.

## How to Run

- Build the index with the wiki RAG build script.
- Run the search handler with one to three English keyword queries.
- Fetch full text with the read handler.

## Quick Reference

- Build script: index builder for the cleaned wiki Parquet shards.
- Reader script: doc id to full article text mapping.
- Tools module: search and read tool handlers.

## Procedure

1. Build the BM25 index from the cleaned wiki Parquet shards. Completion: index build finishes and reports the expected doc count.
2. Run a BM25 search with one to three English keyword queries. Completion: hits come back with doc ids.
3. Pick the top doc ids from the search results. Completion: chosen ids exist in the index.
4. Fetch full text with the read handler. Completion: fetched text is not truncated.
5. Answer from the fetched content. Completion: answer cites fetched facts.

## Pitfalls

- The Parquet schema field is named aliases, not redirects.
- The index stores summaries and bodies; full text lives in the body.
- The last shard is partial, so doc id ranges are not uniform.

## Verification

- Run a smoke search and confirm hits include doc ids.
- Fetch full text for the top hit and confirm it is not truncated.
