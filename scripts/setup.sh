#!/usr/bin/env bash
# One-click local setup for wiki-rag-search:
#   1) verify Python deps (tantivy / pyarrow / huggingface_hub)
#   2) download the cleaned ~9 GB parquet from Hugging Face Datasets
#   3) build the tantivy BM25 index from cleaned parquet shards
#   4) run the smoke tests
#
# No need to download a ~50 GB ZIM and transcode; the cleaned parquet is hosted.
# The extract stage (ZIM -> parquet) requires a Linux environment (libzim).
set -euo pipefail

cd "$(dirname "$0")/.."

export WIKI_RAG_PARQUET_DIR="${WIKI_RAG_PARQUET_DIR:-/mnt/d/wiki_parquet_clean}"
export WIKI_RAG_INDEX_DIR="${WIKI_RAG_INDEX_DIR:-/home/minch/wiki_rag/tantivy_index}"

echo "==> [1/3] checking python deps ..."
python3 -c "import tantivy, pyarrow; print('deps ok')"

echo "==> [2/3] downloading cleaned parquet from Hugging Face Datasets ..."
python3 -c "import os; from huggingface_hub import snapshot_download; snapshot_download(repo_id='Ada0220/wikipedia-en-nopic-2026-06-clean', repo_type='dataset', revision='main', local_dir=os.path.dirname(os.environ['WIKI_RAG_PARQUET_DIR']))"

echo "==> [3/3] building tantivy index from ${WIKI_RAG_PARQUET_DIR} -> ${WIKI_RAG_INDEX_DIR} ..."
python3 scripts/build_index.py

echo "==> [4/3] running smoke tests ..."
PYTHONPATH=src python3 -m pytest tests/ -q

echo "==> setup finished. run: python -c \"from wiki_rag.tools import run_tool; print(run_tool('search_wikipedia', {'queries': ['speculative decoding'], 'top_k': 5}))\""
