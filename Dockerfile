# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    WIKI_RAG_INDEX_DIR=/data/tantivy_index \
    WIKI_RAG_PARQUET_DIR=/data/wiki_parquet_clean

WORKDIR /app

# tantivy / pyarrow / huggingface_hub wheels bundle their own native deps;
# only CA certificates are needed for the Hugging Face Datasets download.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "tantivy>=0.21.0" "pyarrow>=14.0.0" "huggingface_hub>=0.25.0"

COPY pyproject.toml requirements.txt ./
COPY src ./src
COPY scripts/build_index.py ./scripts/build_index.py

# Default: build the tantivy BM25 index from the mounted cleaned parquet shards.
# Override with: docker compose run --rm wiki-rag python -c "from wiki_rag.tools import run_tool; ..."
CMD ["python", "scripts/build_index.py"]
