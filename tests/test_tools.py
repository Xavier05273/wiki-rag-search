"""Smoke tests for the two-stage Wikipedia RAG query tools (tiny in-memory index)."""

import os

from wiki_rag.engine import WikiSearchEngine


def _build_tiny_index(index_dir: str):
    import tantivy

    os.makedirs(index_dir, exist_ok=True)
    schema_builder = tantivy.SchemaBuilder()
    schema_builder.add_unsigned_field("doc_id", stored=True, indexed=True)
    schema_builder.add_text_field("title", stored=True, tokenizer_name="en_stem")
    schema_builder.add_text_field("aliases", stored=False, index_option="freq", tokenizer_name="en_stem")
    schema_builder.add_text_field("summary", stored=True, tokenizer_name="en_stem")
    schema_builder.add_text_field("body", stored=False, index_option="freq", tokenizer_name="en_stem")
    schema = schema_builder.build()
    index = tantivy.Index(schema, path=index_dir)
    writer = index.writer(heap_size=50_000_000)
    doc = tantivy.Document()
    doc.add_unsigned("doc_id", 42)
    doc.add_text("title", "Speculative decoding")
    doc.add_text("aliases", "draft model LLM inference")
    doc.add_text("summary", "Speculative execution is an optimization technique.")
    doc.add_text("body", "In large language models, speculative decoding uses a smaller draft model to predict tokens.")
    writer.add_document(doc)
    writer.commit()
    writer.wait_merging_threads()
    return index


def test_tiny_index_search(tmp_path):
    index_dir = str(tmp_path / "index")
    _build_tiny_index(index_dir)
    engine = WikiSearchEngine(index_dir)
    results = engine.search(["speculative decoding"], top_k=5)
    assert len(results) > 0
    assert results[0]["doc_id"] == 42
    assert "Speculative" in results[0]["title"]


def test_tiny_index_multi_query_rrf(tmp_path):
    index_dir = str(tmp_path / "index")
    _build_tiny_index(index_dir)
    engine = WikiSearchEngine(index_dir)
    results = engine.search(["speculative decoding", "draft model LLM inference"], top_k=5)
    assert isinstance(results, list)
    assert len(results) > 0
    assert all("doc_id" in r for r in results)
