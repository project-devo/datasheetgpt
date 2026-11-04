"""retrieve(): find the chunks closest to a question in pgvector."""
from fastembed import TextEmbedding

from db import connect

from rerank import rerank

MODEL = "BAAI/bge-small-en-v1.5"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
DEFAULT_CONFIG = "s512-o64"
# Postgres full-text query from the question. "all" needs every word in the chunk
# (websearch_to_tsquery default AND); "any" turns the ANDs into ORs, and ts_rank
# then puts chunks that match more of the words first.
TSQUERY = {
    "all": "websearch_to_tsquery('english', %s)",
    "any": "to_tsquery('simple', replace(websearch_to_tsquery('english', %s)::text, ' & ', ' | '))",
}


POOL = 20
RRF_K = 60

_model = None


def get_model():
    global _model
    if _model is None:
        _model = TextEmbedding(MODEL)
    return _model


def embed_query(question):
    return next(get_model().embed([QUERY_PREFIX + question]))


def vector_search(question, k=5, part=None, config=DEFAULT_CONFIG):
    vector = embed_query(question)
    sql = (
        "SELECT id, part, page, kind, section, content, embedding <=> %s AS distance "
        "FROM chunks WHERE config = %s"
    )
    params = [vector, config]
    if part:
        sql += " AND part = %s"
        params.append(part.lower())
    sql += " ORDER BY distance LIMIT %s"
    params.append(k)

    with connect() as conn:
        conn.execute("SET hnsw.iterative_scan = strict_order")
        rows = conn.execute(sql, params).fetchall()

    return [
        {
            "id": r[0], "part": r[1], "page": r[2], "kind": r[3],
            "section": r[4], "content": r[5], "score": round(1 - r[6], 4),
        }
        for r in rows
    ]


def keyword_search(question, k=20, part=None, config=DEFAULT_CONFIG, match="any"):
    sql = (
        "SELECT id, part, page, kind, section, content, ts_rank(tsv, query) AS rank "
        f"FROM chunks, {TSQUERY[match]} AS query "
        "WHERE config = %s AND tsv @@ query"
    )
    params = [question, config]
    if part:
        sql += " AND part = %s"
        params.append(part.lower())
    sql += " ORDER BY rank DESC LIMIT %s"
    params.append(k)

    with connect() as conn:
        rows = conn.execute(sql, params).fetchall()

    return [
        {
            "id": r[0], "part": r[1], "page": r[2], "kind": r[3],
            "section": r[4], "content": r[5], "score": round(r[6], 4),
        }
        for r in rows
    ]

def hybrid_search(question, k=5, part=None, config=DEFAULT_CONFIG):
    lists = [
        vector_search(question, POOL, part, config),
        keyword_search(question, POOL, part, config),
    ]
    fused = {}
    for results in lists:
        for rank, r in enumerate(results, 1):
            row = fused.setdefault(r["id"], {**r, "score": 0.0})
            row["score"] += 1 / (RRF_K + rank)
    ranked = sorted(fused.values(), key=lambda r: r["score"], reverse=True)[:k]
    for r in ranked:
        r["score"] = round(r["score"], 4)
    return ranked


def retrieve(question, k=5, part=None, config=DEFAULT_CONFIG, mode="vector"):
    if mode == "rerank":
        # hybrid finds a wide pool of 20, the cross-encoder picks the best k
        return rerank(question, hybrid_search(question, POOL, part, config), k)
    if mode == "hybrid":
        return hybrid_search(question, k, part, config)
    return vector_search(question, k, part, config)


    
if __name__ == "__main__":
    for r in retrieve("maximum supply voltage", part="lm358"):
        print(f"{r['id']:<22} {r['part']:<10} p{r['page']:<4} {r['kind']:<5} score {r['score']}")