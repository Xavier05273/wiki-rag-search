# One-click local setup for wiki-rag-search on Windows.
# No need to download a ~50 GB ZIM and transcode; the cleaned parquet is hosted.
# The extract stage (ZIM -> parquet) requires a Linux environment (libzim).
$ErrorActionPreference = "Stop"
Set-Location "$PSScriptRoot\.."

$DataDir = if ($env:WIKI_DATA_DIR) { $env:WIKI_DATA_DIR } else { ".\data" }
if (-not (Test-Path $DataDir)) { New-Item -ItemType Directory -Path $DataDir -Force | Out-Null }

if (-not $env:WIKI_RAG_PARQUET_DIR) { $env:WIKI_RAG_PARQUET_DIR = "$DataDir" }
if (-not $env:WIKI_RAG_INDEX_DIR) { $env:WIKI_RAG_INDEX_DIR = "$DataDir\tantivy_index" }

Write-Host "== [1/3] checking python deps ..."
python -c "import tantivy, pyarrow; print('deps ok')"

Write-Host "== [2/3] downloading dataset & pre-built index from Hugging Face Datasets ..."
python -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='Ada0220/wikipedia-en-nopic-2026-06-clean', repo_type='dataset', revision='main', local_dir='$DataDir')"

$TarFile = "$DataDir\tantivy_index_v1.tar"
if ((Test-Path $TarFile) -and (-not (Test-Path $env:WIKI_RAG_INDEX_DIR))) {
    Write-Host "== [3/3] found pre-built index $TarFile, unpacking directly (zero-wait setup) ..."
    tar -xf $TarFile -C $DataDir
    Write-Host "== pre-built index unpacked to $($env:WIKI_RAG_INDEX_DIR)"
} elseif ((Test-Path $env:WIKI_RAG_INDEX_DIR) -and (Test-Path "$($env:WIKI_RAG_INDEX_DIR)\meta.json")) {
    Write-Host "== [3/3] index directory $($env:WIKI_RAG_INDEX_DIR) already exists, skipping."
} else {
    Write-Host "== [3/3] pre-built index not found; building tantivy index from parquet shards ..."
    python scripts\build_index.py
}

Write-Host "== [4/3] running smoke tests ..."
$env:PYTHONPATH = "src"
python -m pytest tests\ -q

Write-Host "== setup finished."
