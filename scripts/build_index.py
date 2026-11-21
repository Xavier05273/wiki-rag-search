"""Build the tantivy BM25 index from cleaned Wikipedia Parquet shards."""

import glob
import os
import shutil
import time
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import tantivy

def _resolve_default_parquet_dir() -> str:
    env = os.environ.get("WIKI_RAG_PARQUET_DIR")
    if env:
        return env
    for candidate in ["./data", "./data/wiki_parquet_clean", "/mnt/d/wiki_parquet_clean"]:
        if os.path.isdir(candidate):
            return candidate
    return "./data"


def _resolve_default_index_dir() -> str:
    env = os.environ.get("WIKI_RAG_INDEX_DIR")
    if env:
        return env
    for candidate in [
        "./data/tantivy_index",
        "./tantivy_index",
        os.path.expanduser("~/wiki_rag/tantivy_index"),
    ]:
        if os.path.isdir(candidate):
            return candidate
    return "./data/tantivy_index"


PARQUET_DIR = _resolve_default_parquet_dir()
INDEX_DIR = _resolve_default_index_dir()
SHARD_SIZE = 25_000
LEAD_SUMMARY_MAX_CHARS = 350

COMMON_HEADINGS = {
    "plot", "plot summary", "synopsis", "summary", "overview", "background",
    "history", "early life", "career", "biography", "reception", "cast",
    "production", "development", "mechanism", "description", "architecture",
    "geography", "demographics", "climate", "economy", "education", "transportation",
    "notable people", "track listing", "discography", "filmography", "awards",
    "see also", "references", "external links", "further reading", "notes",
}


def is_section_heading(line: str) -> bool:
    clean = line.strip().lower()
    if clean in COMMON_HEADINGS:
        return True
    if clean.startswith(("#", "==", "===", "====")):
        return True
    return False


def extract_lead_summary(text: str, max_chars: int = LEAD_SUMMARY_MAX_CHARS, title: str = "") -> str:
    if not text:
        return ""
    title_clean = (title or "").strip().lower()
    current = []
    current_len = 0

    lines = [l.strip() for l in text.split("\n") if l.strip()]
    for line in lines:
        if title_clean and line.lower() == title_clean:
            continue
        if current and is_section_heading(line):
            break
        current.append(line)
        current_len += len(line)
        if current_len >= max_chars:
            break

    summary = " ".join(current)
    if len(summary) > max_chars:
        cut = summary[:max_chars].rfind(" ")
        if cut > int(max_chars * 0.7):
            summary = summary[:cut] + "..."
        else:
            summary = summary[:max_chars] + "..."
    return summary


def build() -> int:
    shard_files = sorted(glob.glob(os.path.join(PARQUET_DIR, "wiki_en_*.parquet")))
    if not shard_files:
        raise FileNotFoundError(f"No shard files found in {PARQUET_DIR}")

    if os.path.exists(INDEX_DIR):
        print(f"Removing old index directory {INDEX_DIR}...", flush=True)
        shutil.rmtree(INDEX_DIR, ignore_errors=True)
    os.makedirs(INDEX_DIR, exist_ok=True)

    schema_builder = tantivy.SchemaBuilder()
    schema_builder.add_unsigned_field("doc_id", stored=True, indexed=True)
    schema_builder.add_text_field("title", stored=True, tokenizer_name="en_stem")
    schema_builder.add_text_field("aliases", stored=False, index_option="freq", tokenizer_name="en_stem")
    schema_builder.add_text_field("summary", stored=True, tokenizer_name="en_stem")
    schema_builder.add_text_field("body", stored=False, index_option="freq", tokenizer_name="en_stem")
    schema = schema_builder.build()

    index = tantivy.Index(schema, path=INDEX_DIR)
    writer = index.writer(heap_size=2_000_000_000)

    total = 0
    t0 = time.time()
    total_shards = len(shard_files)
    print(f"Starting index build across {total_shards} shards...", flush=True)

    for shard_idx, fp in enumerate(shard_files):
        table = pq.read_table(fp)
        n = table.num_rows
        titles = table["title"].to_pylist()
        aliases_col = table["aliases"].to_pylist()
        texts = table["text"].to_pylist()
        del table

        for row_idx in range(n):
            doc_id = shard_idx * SHARD_SIZE + row_idx
            text = texts[row_idx] or ""
            summary = extract_lead_summary(text, title=titles[row_idx] or "")
            alias_val = aliases_col[row_idx]
            alias_str = " ".join(alias_val) if isinstance(alias_val, list) else (alias_val or "")

            doc = tantivy.Document()
            doc.add_unsigned("doc_id", doc_id)
            doc.add_text("title", titles[row_idx] or "")
            doc.add_text("aliases", alias_str)
            doc.add_text("summary", summary)
            doc.add_text("body", text)
            writer.add_document(doc)
            total += 1
            if total % 100_000 == 0:
                pct = (shard_idx + 1) / total_shards * 100
                print(f"added {total:,} docs ({pct:.1f}%), elapsed {time.time()-t0:.1f}s", flush=True)

        del titles, aliases_col, texts

        if (shard_idx + 1) % 20 == 0:
            t_c0 = time.time()
            writer.commit()
            import gc
            import pyarrow

            gc.collect()
            pyarrow.default_memory_pool().release_unused()
            print(f"[Checkpoint] Shard {shard_idx+1}/{total_shards} committed (total {total:,} docs) in {time.time()-t_c0:.1f}s | memory released", flush=True)

        print(f"shard {shard_idx} done, total {total:,}, elapsed {time.time()-t0:.1f}s", flush=True)

    print("Executing final commit and segment merge...", flush=True)
    writer.commit()
    writer.wait_merging_threads()
    elapsed = round(time.time() - t0, 1)

    total_idx_size = sum(os.path.getsize(os.path.join(INDEX_DIR, f)) for f in os.listdir(INDEX_DIR))
    print(f"BUILD_DONE: {total:,} docs in {elapsed}s | Total index size: {total_idx_size / (1024**3):.2f} GB", flush=True)

    tar_path = os.path.join(os.path.dirname(INDEX_DIR), "tantivy_index_v1.tar")
    print(f"Archiving index to {tar_path}...", flush=True)
    import subprocess
    subprocess.run(["tar", "-cf", tar_path, "-C", os.path.dirname(INDEX_DIR), os.path.basename(INDEX_DIR)], check=True)
    tar_size = os.path.getsize(tar_path) / (1024**3)
    print(f"Archive complete: {tar_path} total size: {tar_size:.2f} GB", flush=True)
    return total


if __name__ == "__main__":
    build()
