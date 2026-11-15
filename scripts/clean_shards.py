"""Clean raw extracted Wikipedia Parquet shards (marker / footer / whitespace repair)."""

import glob
import os
import re
import time
from multiprocessing import Pool

import pyarrow as pa
import pyarrow.parquet as pq

IN_DIR = os.environ.get("WIKI_RAG_EXTRACT_OUT_DIR", "/mnt/d/wiki_parquet_shards")
OUT_DIR = os.environ.get("WIKI_RAG_PARQUET_DIR", "/mnt/d/wiki_parquet_clean")

START_MARKER = "/* start https://en.wikipedia.org/ */"
END_MARKER = "/* end   https://en.wikipedia.org/ */"
FOOTER_MARKER = "This article is issued from Wikipedia"

APOSTROPHE_RE = re.compile(r"\s+('s|'t|'re|'ve|'m|'ll|'d)\b", re.IGNORECASE)
PUNCT_SPACING_RE = re.compile(r"[ \t]+([,.:;?!’\)])")
BRACKET_OPEN_RE = re.compile(r"([(\[{])\s+")
MULTI_SPACE_RE = re.compile(r"[ \t]+")
PARA_SPLIT_RE = re.compile(r"\n{2,}")
NEWLINE_RE = re.compile(r"\n+")


def clean_doc(text: str) -> str:
    if not text:
        return ""
    if START_MARKER in text:
        parts = []
        idx = 0
        while True:
            s_pos = text.find(START_MARKER, idx)
            if s_pos == -1:
                parts.append(text[idx:])
                break
            parts.append(text[idx:s_pos])
            e_pos = text.find(END_MARKER, s_pos + len(START_MARKER))
            if e_pos == -1:
                break
            idx = e_pos + len(END_MARKER)
        text = "".join(parts)
    f_pos = text.rfind(FOOTER_MARKER)
    if f_pos != -1:
        text = text[:f_pos]
    paragraphs = PARA_SPLIT_RE.split(text)
    cleaned_paras = []
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        p = NEWLINE_RE.sub(" ", p)
        p = PUNCT_SPACING_RE.sub(r"\1", p)
        p = BRACKET_OPEN_RE.sub(r"\1", p)
        p = APOSTROPHE_RE.sub(r"\1", p)
        p = MULTI_SPACE_RE.sub(" ", p).strip()
        if p:
            cleaned_paras.append(p)
    return "\n\n".join(cleaned_paras)


def process_shard(file_path: str):
    filename = os.path.basename(file_path)
    out_path = os.path.join(OUT_DIR, filename)
    if os.path.exists(out_path) and os.path.getsize(out_path) > 1024 * 1024:
        return filename, 0, 0.0
    t0 = time.time()
    table = pq.read_table(file_path)
    num_rows = table.num_rows
    cleaned_texts = [clean_doc(t.as_py()) for t in table["text"]]
    new_table = table.set_column(3, "text", pa.array(cleaned_texts, type=pa.string()))
    del table, cleaned_texts
    tmp_path = out_path + ".tmp"
    pq.write_table(new_table, tmp_path, compression="zstd", compression_level=6)
    del new_table
    os.replace(tmp_path, out_path)
    return filename, num_rows, time.time() - t0


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    all_files = sorted(glob.glob(os.path.join(IN_DIR, "wiki_en_*.parquet")))
    print(f"Found {len(all_files)} Parquet shards, preparing to clean...")
    workers = 4
    print(f"Launching {workers} parallel workers (memory-safe mode)...")
    with Pool(processes=workers, maxtasksperchild=5) as pool:
        done = 0
        total_files = len(all_files)
        for fname, rows, elapsed in pool.imap_unordered(process_shard, all_files):
            done += 1
            if done % 10 == 0 or done == total_files:
                print(f"[{done}/{total_files}] cleaned {fname} | cumulative entries: {rows:,}")
    print(f"\nAll cleaning complete! Output {done} files to {OUT_DIR}.")


if __name__ == "__main__":
    main()
