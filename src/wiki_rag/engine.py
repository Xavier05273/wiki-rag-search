"""BM25 search engine over the offline Wikipedia tantivy index."""

import html
import re
from typing import Any

import tantivy

DEFAULT_FIELD_BOOSTS = {"title": 5.0, "aliases": 3.0, "summary": 2.0, "body": 1.0}
DEFAULT_SEARCH_FIELDS = ["title", "aliases", "summary", "body"]
RRF_K = 60


class WikiSearchEngine:
    def __init__(
        self,
        index_dir: str,
        field_boosts: dict[str, float] | None = None,
        search_fields: list[str] | None = None,
    ) -> None:
        self.index = tantivy.Index.open(index_dir)
        self.schema = self.index.schema
        self.searcher = self.index.searcher()
        self.field_boosts = field_boosts if field_boosts is not None else DEFAULT_FIELD_BOOSTS
        self.search_fields = search_fields if search_fields is not None else DEFAULT_SEARCH_FIELDS

    @staticmethod
    def _format_snippet(raw_html: str) -> str:
        text = html.unescape(raw_html)
        text = re.sub(r"<b>(.*?)</b>", r"**\1**", text)
        return re.sub(r"\s+", " ", text).strip()

    def _single_search(self, query_str: str, fetch_k: int) -> list[dict]:
        query = self.index.parse_query(
            query_str, self.search_fields, field_boosts=self.field_boosts
        )
        hits = self.searcher.search(query, limit=fetch_k).hits
        snippet_gen = tantivy.SnippetGenerator.create(self.searcher, query, self.schema, "summary")
        results = []
        for rank, (score, doc_addr) in enumerate(hits, start=1):
            doc = self.searcher.doc(doc_addr)
            raw_snip = snippet_gen.snippet_from_doc(doc).to_html()
            snip_text = self._format_snippet(raw_snip)
            if not snip_text:
                snip_text = doc.get_first("summary") or ""
            results.append(
                {
                    "doc_id": doc.get_first("doc_id"),
                    "title": doc.get_first("title"),
                    "summary": doc.get_first("summary"),
                    "snippet": snip_text,
                    "query": query_str,
                    "rank": rank,
                    "bm25_score": score,
                }
            )
        return results

    def search(self, queries, top_k: int = 15, rrf_k: int = RRF_K) -> list[dict]:
        if isinstance(queries, str):
            queries = [queries]
        queries = [q.strip() for q in queries if q.strip()]
        if len(queries) == 1:
            hits = self._single_search(queries[0], fetch_k=top_k)
            return [
                {
                    "doc_id": h["doc_id"],
                    "title": h["title"],
                    "summary": h["summary"],
                    "matched_snippets": [h["snippet"]] if h["snippet"] else [],
                }
                for h in hits
            ]
        per_query_k = max(top_k, 20)
        all_runs = [self._single_search(q, per_query_k) for q in queries]
        merged = {}
        for run in all_runs:
            for item in run:
                did = item["doc_id"]
                rrf_score = 1.0 / (rrf_k + item["rank"])
                if did not in merged:
                    merged[did] = {
                        "doc_id": did,
                        "title": item["title"],
                        "summary": item["summary"],
                        "rrf_score": 0.0,
                        "matched_snippets": [],
                        "hit_queries": [],
                    }
                merged[did]["rrf_score"] += rrf_score
                merged[did]["hit_queries"].append(item["query"])
                if item["snippet"] and item["snippet"] not in merged[did]["matched_snippets"]:
                    merged[did]["matched_snippets"].append(item["snippet"])
        ranked = sorted(merged.values(), key=lambda x: x["rrf_score"], reverse=True)[:top_k]
        for r in ranked:
            r.pop("rrf_score", None)
        return ranked
