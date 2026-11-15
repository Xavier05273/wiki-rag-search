# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    WIKI_RAG_INDEX_DIR=/data/tantivy_index \
    WIKI_RAG_PARQUET_DIR=/data

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates tar \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "tantivy>=0.21.0" "pyarrow>=14.0.0" "huggingface_hub>=0.25.0" "pytest>=7.0.0"

COPY pyproject.toml requirements.txt ./
COPY src ./src
COPY scripts ./scripts
COPY tests ./tests
COPY docker-entrypoint.sh ./docker-entrypoint.sh

RUN chmod +x ./docker-entrypoint.sh

ENTRYPOINT ["/app/docker-entrypoint.sh"]
