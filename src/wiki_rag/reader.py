"""Doc-id addressed reader for the offline Wikipedia corpus (Parquet shards)."""

from collections import defaultdict
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

SHARD_SIZE = 25_000


class WikiArticleReader:
    def __init__(self, parquet_dir: str, shard_size: int = SHARD_SIZE) -> None:
        self.parquet_dir = Path(parquet_dir)
        self.shard_size = shard_size
        self.shard_files = sorted(self.parquet_dir.glob("*.parquet"))
        if not self.shard_files:
            # Fallback 1: check subfolder like wiki_parquet_clean
            sub_dir = self.parquet_dir / "wiki_parquet_clean"
            if sub_dir.is_dir():
                self.shard_files = sorted(sub_dir.glob("*.parquet"))
        if not self.shard_files:
            # Fallback 2: recursive search one level down
            self.shard_files = sorted(self.parquet_dir.glob("*/*.parquet"))
        if not self.shard_files:
            raise FileNotFoundError(f"No .parquet shard files found in {parquet_dir}")

    def read_articles(
        self,
        doc_ids: list,
        max_chars_per_article: int = 16_000,
        include_redirects: bool = False,
    ) -> list:
        if not doc_ids:
            return []

        unique_ids = list(dict.fromkeys(doc_ids))
        shard_groups = defaultdict(list)

        for did in unique_ids:
            if did < 0:
                continue
            shard_idx, row_idx = divmod(did, self.shard_size)
            if shard_idx < len(self.shard_files):
                shard_groups[shard_idx].append((did, row_idx))

        columns = ["title", "aliases", "text"] if include_redirects else ["title", "text"]
        fetched_map = {}

        for shard_idx, items in shard_groups.items():
            file_path = self.shard_files[shard_idx]
            pf = pq.ParquetFile(file_path)
            num_rows = pf.metadata.num_rows
            valid_items = [(did, r_idx) for did, r_idx in items if r_idx < num_rows]
            if not valid_items:
                continue
            table = pf.read(columns=columns)
            target_indices = pa.array([r_idx for _, r_idx in valid_items], type=pa.int64())
            sub_table = table.take(target_indices)
            titles = sub_table["title"].to_pylist()
            texts = sub_table["text"].to_pylist()
            redirects_col = sub_table["aliases"].to_pylist() if include_redirects else [None] * len(valid_items)

            for (did, _), title, text, redirects in zip(valid_items, titles, texts, redirects_col):
                clean_text = text or ""
                truncated = False
                if max_chars_per_article and len(clean_text) > max_chars_per_article:
                    clean_text = clean_text[:max_chars_per_article] + "\n...[Article truncated due to length]..."
                    truncated = True
                record = {
                    "doc_id": did,
                    "title": title or "",
                    "text": clean_text,
                    "truncated": truncated,
                }
                if include_redirects:
                    record["redirects"] = redirects or []
                fetched_map[did] = record

        return [fetched_map[did] for did in unique_ids if did in fetched_map]
