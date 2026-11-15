"""Strip Kiwix footer ('This article is issued from Wikipedia') from cleaned Parquet shards."""

import glob
import os

import pyarrow as pa
import pyarrow.parquet as pq

IN_DIR = os.environ.get("WIKI_RAG_PARQUET_DIR", "/mnt/d/wiki_parquet_clean")
FOOTER_MARKER = "This article is issued from Wikipedia"


def strip_footer(text):
    if not text:
        return text
    f_pos = text.rfind(FOOTER_MARKER)
    if f_pos != -1:
        text = text[:f_pos]
    return text


def main() -> None:
    files = sorted(glob.glob(os.path.join(IN_DIR, "wiki_en_*.parquet")))
    n = 0
    for f in files:
        table = pq.read_table(f)
        col = table.column("text")
        cleaned = [strip_footer(v) for v in col.to_pylist()]
        new_table = table.set_column(
            table.column_names.index("text"), "text", pa.array(cleaned, type=pa.string())
        )
        tmp_path = f + ".tmp"
        pq.write_table(new_table, tmp_path, compression="zstd", compression_level=6)
        os.replace(tmp_path, f)
        n += 1
    print("STRIP_DONE", n)


if __name__ == "__main__":
    main()
