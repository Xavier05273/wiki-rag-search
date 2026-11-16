"""BM25 search engine over the offline Wikipedia tantivy index."""

import html
import re
from typing import Any

import tantivy

DEFAULT_FIELD_BOOSTS = {"title": 5.0, "aliases": 3.0, "body": 1.0}
DEFAULT_SEARCH_FIELDS = ["title", "aliases", "body"]
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

    @staticmethod
    def _is_soft_redirect(summary: str) -> bool:
        """Check if summary is a soft redirect or disambiguation stub (e.g. Wiktionary look up)."""
        if not summary:
            return False
        return bool(re.match(r"^\s*Look up\b.*\bin Wiktionary", summary, re.IGNORECASE))

    def _single_search(self, query_str: str, fetch_k: int) -> list[dict]:
        query = self.index.parse_query(
            query_str, self.search_fields, field_boosts=self.field_boosts
        )
        hits = self.searcher.search(query, limit=fetch_k).hits
        # Generate snippet from 'summary' (which is stored in index) instead of unstored 'body'
        try:
            summary_query = self.index.parse_query(query_str, ["summary"])
            snippet_gen = tantivy.SnippetGenerator.create(self.searcher, summary_query, self.schema, "summary")
        except Exception:
            snippet_gen = None

        results = []
        for rank, (score, doc_addr) in enumerate(hits, start=1):
            doc = self.searcher.doc(doc_addr)
            summary = doc.get_first("summary") or ""
            formatted_snip = ""
            if snippet_gen is not None:
                try:
                    raw_snip = snippet_gen.snippet_from_doc(doc).to_html()
                    if raw_snip:
                        formatted_snip = self._format_snippet(raw_snip)
                except Exception:
                    pass
            # Fallback snippet: keyword highlighting on summary directly if generator returned empty
            if not formatted_snip and summary:
                words = [re.escape(w) for w in re.findall(r"\w+", query_str) if len(w) > 1]
                if words:
                    pattern = re.compile(rf"\b({'|'.join(words)})\b", re.IGNORECASE)
                    if pattern.search(summary):
                        # take the first matching sentence or prefix
                        highlighted = pattern.sub(r"**\1**", summary[:300])
                        formatted_snip = highlighted.strip()

            results.append(
                {
                    "doc_id": doc.get_first("doc_id"),
                    "title": doc.get_first("title"),
                    "summary": summary,
                    "snippet": formatted_snip,
                    "is_soft_redirect": self._is_soft_redirect(summary),
                    "query": query_str,
                    "rank": rank,
                    "bm25_score": score,
                }
            )
        return results

    def search(
        self,
        queries,
        top_k: int = 15,
        rrf_k: int = RRF_K,
        filter_soft_redirects: bool = True,
    ) -> list[dict]:
        if isinstance(queries, str):
            queries = [queries]
        queries = [q.strip() for q in queries if q.strip()]
        if not queries:
            return []

        # Over-fetch slightly to allow soft redirect filtering / deprioritization
        fetch_k = top_k * 2 if filter_soft_redirects else top_k

        if len(queries) == 1:
            hits = self._single_search(queries[0], fetch_k=fetch_k)
            if filter_soft_redirects:
                # Put regular articles first, soft redirects last
                normal_hits = [h for h in hits if not h["is_soft_redirect"]]
                redirect_hits = [h for h in hits if h["is_soft_redirect"]]
                hits = (normal_hits + redirect_hits)[:top_k]
            else:
                hits = hits[:top_k]

            return [
                {
                    "doc_id": h["doc_id"],
                    "title": h["title"],
                    "summary": h["summary"],
                    "matched_snippets": [h["snippet"]] if h["snippet"] else [],
                }
                for h in hits
            ]

        per_query_k = max(fetch_k, 20)
        all_runs = [self._single_search(q, per_query_k) for q in queries]
        merged = {}
        for run in all_runs:
            for item in run:
                did = item["doc_id"]
                rrf_score = 1.0 / (rrf_k + item["rank"])
                if item["is_soft_redirect"]:
                    # Penalize soft redirects so substantial articles rank higher
                    rrf_score *= 0.1

                if did not in merged:
                    merged[did] = {
                        "doc_id": did,
                        "title": item["title"],
                        "summary": item["summary"],
                        "rrf_score": 0.0,
                        "matched_snippets": [],
                        "hit_queries": [],
                        "is_soft_redirect": item["is_soft_redirect"],
                    }
                merged[did]["rrf_score"] += rrf_score
                merged[did]["hit_queries"].append(item["query"])
                if item["snippet"] and item["snippet"] not in merged[did]["matched_snippets"]:
                    merged[did]["matched_snippets"].append(item["snippet"])

        ranked = sorted(merged.values(), key=lambda x: x["rrf_score"], reverse=True)
        if filter_soft_redirects:
            normal = [r for r in ranked if not r["is_soft_redirect"]]
            redirects = [r for r in ranked if r["is_soft_redirect"]]
            ranked = (normal + redirects)[:top_k]
        else:
            ranked = ranked[:top_k]

        for r in ranked:
            r.pop("rrf_score", None)
            r.pop("is_soft_redirect", None)
        return ranked
