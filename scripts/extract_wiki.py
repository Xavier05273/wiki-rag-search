"""Stage 1: extract valid Wikipedia articles (text/html, non-redirect, non-disambiguation) from a ZIM archive into Parquet shards."""

import os
import pickle
import re
import time
from collections import defaultdict
from multiprocessing import Pool, cpu_count

import pyarrow as pa
import pyarrow.parquet as pq
from libzim.reader import Archive
from selectolax.lexbor import LexborHTMLParser as HTMLParser

ZIM_PATH = os.environ.get("WIKI_RAG_ZIM", "/mnt/d/wikipedia_en_all_nopic_2026-06.zim")
OUT_DIR = os.environ.get("WIKI_RAG_EXTRACT_OUT_DIR", "/mnt/d/wiki_parquet_shards")
CACHE_PATH = os.environ.get("WIKI_RAG_CACHE", "/mnt/d/wiki_stage1_cache.pkl")
SHARD_SIZE = 100_000

EXCLUDE_PREFIXES = (
    "Category:", "Portal:", "File:", "Wikipedia:", "Template:", "Help:",
    "Draft:", "Module:", "MediaWiki:", "TimedText:", "Book:",
)

TAIL_HEADINGS = {
    "references", "external links", "see also", "further reading",
    "notes", "bibliography", "citations", "sources",
}


def build_redirect_map(zim_path: str):
    if os.path.exists(CACHE_PATH):
        print(f"偵測到快取檔 {CACHE_PATH}，直接載入階段一結果...")
        with open(CACHE_PATH, "rb") as f:
            return pickle.load(f)

    zim = Archive(zim_path)
    total = zim.entry_count
    redirects_map = defaultdict(list)
    valid_entries = []

    for idx in range(total):
        if idx > 0 and idx % 2_000_000 == 0:
            print(f"  已掃描 {idx:,} / {total:,} 筆...")
        entry = zim.get_entry_by_id(idx)
        title = entry.title
        if title.startswith(EXCLUDE_PREFIXES):
            continue
        if entry.is_redirect:
            target = entry.get_redirect_entry()
            if not target.title.startswith(EXCLUDE_PREFIXES):
                redirects_map[target.path].append(title)
        else:
            if entry.get_item().mimetype == "text/html":
                valid_entries.append((idx, entry.path))

    result = (valid_entries, dict(redirects_map))
    with open(CACHE_PATH, "wb") as f:
        pickle.dump(result, f, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"已將階段一索引快取儲存至 {CACHE_PATH}")
    return result


def clean_html_to_text(html: str) -> str:
    tree = HTMLParser(html)
    for node in tree.css("sup.reference, sup.noprint, span.mw-editsection, .noprint"):
        node.decompose()
    for node in tree.css(".reflist, .mw-references-wrap, ol.references, .navbox, .infobox"):
        node.decompose()
    for heading in tree.css("h2, h3"):
        if heading.text(strip=True).lower() in TAIL_HEADINGS:
            parent = heading.parent
            if parent and "mw-heading" in (parent.attributes.get("class") or ""):
                curr = parent
            else:
                curr = heading
            while curr is not None:
                nxt = curr.next
                curr.decompose()
                curr = nxt
            break
    body = tree.body
    if not body:
        return ""
    text = body.text(separator="\n", strip=True)
    return re.sub(r"\n{3,}", "\n\n", text)


_worker_zim = None


def _init_worker(zim_path):
    global _worker_zim
    _worker_zim = Archive(zim_path)


def _process_entry(args):
    idx, aliases = args
    entry = _worker_zim.get_entry_by_id(idx)
    if "(disambiguation)" in entry.title.lower():
        return None
    html = bytes(entry.get_item().content).decode("utf-8", errors="ignore")
    clean_text = clean_html_to_text(html)
    if len(clean_text) < 150:
        return None
    return {"path": entry.path, "title": entry.title, "aliases": aliases, "text": clean_text}


def main() -> None:
    t0 = time.time()
    os.makedirs(OUT_DIR, exist_ok=True)
    print("Stage 1: scan redirects and valid entries")
    valid_entries, redirects_map = build_redirect_map(ZIM_PATH)
    print(f"done scanning ({time.time()-t0:.1f}s) | valid entries: {len(valid_entries):,} | with aliases: {len(redirects_map):,}")

    tasks = [(idx, redirects_map.get(path, [])) for idx, path in valid_entries]
    del valid_entries, redirects_map

    schema = pa.schema([
        ("path", pa.string()),
        ("title", pa.string()),
        ("aliases", pa.list_(pa.string())),
        ("text", pa.string()),
    ])

    buffer = []
    shard_idx = 0
    saved_total = 0
    workers = max(1, cpu_count() - 2)
    print(f"Stage 2: launching {workers} workers to parse bodies...")
    with Pool(processes=workers, initializer=_init_worker, initargs=(ZIM_PATH,)) as pool:
        for record in pool.imap_unordered(_process_entry, tasks, chunksize=2000):
            if record is None:
                continue
            buffer.append(record)
            if len(buffer) >= SHARD_SIZE:
                out_file = os.path.join(OUT_DIR, f"wiki_en_{shard_idx:04d}.parquet")
                pq.write_table(pa.Table.from_pylist(buffer, schema=schema), out_file, compression="zstd", compression_level=6)
                saved_total += len(buffer)
                shard_idx += 1
                buffer.clear()

    if buffer:
        out_file = os.path.join(OUT_DIR, f"wiki_en_{shard_idx:04d}.parquet")
        pq.write_table(pa.Table.from_pylist(buffer, schema=schema), out_file, compression="zstd", compression_level=6)
        saved_total += len(buffer)

    print(f"All done! {saved_total:,} valid entries")


if __name__ == "__main__":
    main()
