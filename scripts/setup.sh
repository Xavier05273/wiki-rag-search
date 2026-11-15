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

DATA_DIR="${WIKI_DATA_DIR:-./data}"
mkdir -p "$DATA_DIR"

export WIKI_RAG_PARQUET_DIR="${WIKI_RAG_PARQUET_DIR:-$DATA_DIR}"
export WIKI_RAG_INDEX_DIR="${WIKI_RAG_INDEX_DIR:-$DATA_DIR/tantivy_index}"

echo "==> [1/3] checking python deps ..."
python3 -c "import tantivy, pyarrow; print('deps ok')"

echo "==> [2/3] downloading dataset & pre-built index from Hugging Face Datasets ..."
python3 -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='Ada0220/wikipedia-en-nopic-2026-06-clean', repo_type='dataset', revision='main', local_dir='$DATA_DIR')"

TAR_FILE="$DATA_DIR/tantivy_index_v1.tar"
if [ -f "$TAR_FILE" ] && [ ! -d "$WIKI_RAG_INDEX_DIR" ]; then
    echo "==> [3/3] found pre-built index tarball $TAR_FILE, unpacking directly (zero-wait setup) ..."
    tar -xf "$TAR_FILE" -C "$DATA_DIR"
    echo "==> pre-built index unpacked to $WIKI_RAG_INDEX_DIR"
elif [ -d "$WIKI_RAG_INDEX_DIR" ] && [ -f "$WIKI_RAG_INDEX_DIR/meta.json" ]; then
    echo "==> [3/3] index directory $WIKI_RAG_INDEX_DIR already exists, skipping."
else
    echo "==> [3/3] pre-built index not found; building tantivy index from parquet shards ..."
    python3 scripts/build_index.py
fi

echo "==> [4/3] running smoke tests ..."
PYTHONPATH=src python3 -m pytest tests/ -q

echo "==> setup finished. run: python -c \"from wiki_rag.tools import run_tool; print(run_tool('search_wikipedia', {'queries': ['speculative decoding'], 'top_k': 5}))\""
