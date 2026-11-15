#!/usr/bin/env bash
set -e

# If pre-built index tarball exists and index directory is not unpacked yet, unpack it
INDEX_DIR="${WIKI_RAG_INDEX_DIR:-/data/tantivy_index}"
DATA_DIR="$(dirname "$INDEX_DIR")"
TAR_FILE="$DATA_DIR/tantivy_index_v1.tar"

if [ -f "$TAR_FILE" ] && [ ! -d "$INDEX_DIR" ]; then
    echo "==> [Docker Entrypoint] Found pre-built index: $TAR_FILE"
    echo "==> Unpacking to $DATA_DIR..."
    tar -xf "$TAR_FILE" -C "$DATA_DIR"
    echo "==> Unpacked successfully to $INDEX_DIR"
fi

# If no arguments provided, default to smoke test search if index exists, or build index
if [ $# -eq 0 ]; then
    if [ -d "$INDEX_DIR" ] && [ -f "$INDEX_DIR/meta.json" ]; then
        echo "==> Index is ready. Running smoke search..."
        exec python -c "from wiki_rag.tools import run_tool; import json; print(json.dumps(run_tool('search_wikipedia', {'queries': ['speculative decoding'], 'top_k': 3}), indent=2))"
    else
        echo "==> Index not found. Building tantivy index from parquet..."
        exec python scripts/build_index.py
    fi
fi

exec "$@"
