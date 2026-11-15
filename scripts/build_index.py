"""Build the tantivy BM25 index from cleaned Wikipedia Parquet shards."""

import glob
import os
import shutil
import time
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import tantivy

PARQUET_DIR = os.environ.get("WIKI_RAG_PARQUET_DIR") or "/mnt/d/wiki_parquet_clean"
INDEX_DIR = os.environ.get("WIKI_RAG_INDEX_DIR") or "/home/minch/wiki_rag/tantivy_index"
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
        raise FileNotFoundError(f"找不到任何分片檔案在 {PARQUET_DIR}")

    if os.path.exists(INDEX_DIR):
        print(f"清空舊索引目錄 {INDEX_DIR}...", flush=True)
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
    print(f"開始建置索引，共 {total_shards} 個分片...", flush=True)

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
            print(f"[Checkpoint] Shard {shard_idx+1}/{total_shards} committed (total {total:,} docs) in {time.time()-t_c0:.1f}s | 記憶體已釋放", flush=True)

        print(f"shard {shard_idx} done, total {total:,}, elapsed {time.time()-t0:.1f}s", flush=True)

    print("正在執行最終提交與段合併 (Final Commit & Merge)...", flush=True)
    writer.commit()
    writer.wait_merging_threads()
    elapsed = round(time.time() - t0, 1)

    total_idx_size = sum(os.path.getsize(os.path.join(INDEX_DIR, f)) for f in os.listdir(INDEX_DIR))
    print(f"BUILD_DONE: {total:,} docs in {elapsed}s | 索引總大小: {total_idx_size / (1024**3):.2f} GB", flush=True)

    tar_path = os.path.join(os.path.dirname(INDEX_DIR), "tantivy_index_v1.tar")
    print(f"正在打包索引至 {tar_path}...", flush=True)
    import subprocess
    subprocess.run(["tar", "-cf", tar_path, "-C", os.path.dirname(INDEX_DIR), os.path.basename(INDEX_DIR)], check=True)
    tar_size = os.path.getsize(tar_path) / (1024**3)
    print(f"打包完成！{tar_path} 總大小: {tar_size:.2f} GB", flush=True)
    return total


if __name__ == "__main__":
    build()
