"""Permission-filtered retrieval: filter -> k-NN -> Nova rerank -> dynamic cut.

Lesson 7's pipeline. The access filter is applied INSIDE the k-NN query
(pre-filtering), so a restricted chunk never leaves OpenSearch for a caller who
may not see it — a refusal written after the chunk reached the model would
already be a leak (spec section 12).
"""
from .. import config, db, llm
from .store import client

CANDIDATES = 20        # retrieve wide...
# ...cut narrow. Chosen by measurement (evals/retrieval_eval.py, ADR 0003): on the golden
# retrieval cases ">=0.5, max 8, <=2 chunks per document" found 12/17 expected documents
# vs 9/17 for Lesson 7's ">=0.6, max 5".
MIN_SCORE = 0.5
MAX_RESULTS = 8
PER_DOC = 2

_RANK_TOOL = {"toolSpec": {
    "name": "rank",
    "description": "Score every candidate passage for relevance to the query.",
    "inputSchema": {"json": {
        "type": "object", "required": ["scores"],
        "properties": {"scores": {"type": "array", "items": {
            "type": "object", "required": ["index", "score"],
            "properties": {"index": {"type": "integer"},
                           "score": {"type": "number", "description": "0.0 to 1.0"}},
        }}},
    }},
}}


def access_clauses(caller_id: str) -> list[dict]:
    """THE permission boundary. Fail closed: only a caller the database proves is a
    manager gets the manager corpus; everyone else (unknown ids included) sees
    audience=all only."""
    return [] if db.is_manager(caller_id) else [{"term": {"audience": "all"}}]


def build_filter(caller_id: str, collections: list[str] | None = None) -> dict | None:
    must = access_clauses(caller_id)
    if collections:
        must.append({"terms": {"collection": collections}})
    return {"bool": {"must": must}} if must else None


def knn(query: str, caller_id: str, collections: list[str] | None = None,
        k: int = CANDIDATES) -> list[dict]:
    body_knn = {"vector": llm.embed(query), "k": k}
    filt = build_filter(caller_id, collections)
    if filt:
        body_knn["filter"] = filt
    body = {"size": k, "query": {"knn": {"vector": body_knn}},
            "_source": {"excludes": ["vector"]}}
    return [hit["_source"] for hit in
            client().search(index=config.INDEX_NAME, body=body)["hits"]["hits"]]


def rerank(query: str, candidates: list[dict]) -> list[tuple[dict, float]]:
    """One Nova call scores every candidate (Lesson 7 reranker.py)."""
    if not candidates:
        return []
    listing = "\n\n".join(
        f"[{i}] ({c['source']} — {c['section']})\n{c['text']}" for i, c in enumerate(candidates))
    result = llm.converse(
        f"Query: {query}\n\nScore each candidate passage from 0.0 to 1.0 for how well it "
        f"helps answer the query. Use the exact [index] shown.\n\n{listing}",
        tool=_RANK_TOOL)
    scores = {}
    for entry in result.get("scores", []):
        i = entry.get("index")
        if isinstance(i, int) and 0 <= i < len(candidates):
            scores[i] = max(0.0, min(1.0, float(entry.get("score", 0.0))))
    order = sorted(range(len(candidates)), key=lambda i: scores.get(i, 0.0), reverse=True)
    return [(candidates[i], scores.get(i, 0.0)) for i in order]


def cut(ranked: list[tuple[dict, float]], min_score: float = MIN_SCORE,
        max_results: int = MAX_RESULTS, per_doc: int | None = PER_DOC) -> list[dict]:
    """Keep the best hits: score >= min_score, at most max_results, and at most per_doc
    chunks from any one document (so one long document cannot crowd out the others)."""
    hits, per_source = [], {}
    for c, score in ranked:                       # ranked is best-first
        if score < min_score or len(hits) >= max_results:
            break
        if per_doc and per_source.get(c["source"], 0) >= per_doc:
            continue
        per_source[c["source"]] = per_source.get(c["source"], 0) + 1
        hits.append({"source": c["source"], "section": c["section"], "title": c["title"],
                     "doc_date": c.get("doc_date"), "relevance": round(score, 2), "text": c["text"]})
    return hits


def search(query: str, caller_id: str, collections: list[str] | None = None) -> list[dict]:
    """The function behind the MCP `search_documents` tool. Returns cite-ready hits:
    source, section, doc_date, text, relevance."""
    return cut(rerank(query, knn(query, caller_id, collections)))
