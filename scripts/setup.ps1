# One-click local setup for wiki-rag-search on Windows.
# No need to download a ~50 GB ZIM and transcode; the cleaned parquet is hosted.
# The extract stage (ZIM -> parquet) requires a Linux environment (libzim).
$ErrorActionPreference = "Stop"
Set-Location "$PSScriptRoot\.."

if (-not $env:WIKI_RAG_PARQUET_DIR) { $env:WIKI_RAG_PARQUET_DIR = "C:\data\wiki_parquet_clean" }
if (-not $env:WIKI_RAG_INDEX_DIR) { $env:WIKI_RAG_INDEX_DIR = "C:\data\tantivy_index" }

Write-Host "== [1/3] checking python deps ..."
python -c "import tantivy, pyarrow; print('deps ok')"

Write-Host "== [2/3] downloading cleaned parquet from Hugging Face Datasets ..."
python -c "import os; from huggingface_hub import snapshot_download; snapshot_download(repo_id='Ada0220/wikipedia-en-nopic-2026-06-clean', repo_type='dataset', revision='main', local_dir=os.path.dirname(os.environ['WIKI_RAG_PARQUET_DIR']))"

Write-Host "== [3/3] building tantivy index from $($env:WIKI_RAG_PARQUET_DIR) -> $($env:WIKI_RAG_INDEX_DIR) ..."
python scripts\build_index.py

Write-Host "== [4/3] running smoke tests ..."
$env:PYTHONPATH = "src"
python -m pytest tests\ -q

Write-Host "== setup finished."
