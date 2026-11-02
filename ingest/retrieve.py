"""retrieve(): find the chunks closest to a question in pgvector."""
from fastembed import TextEmbedding

from db import connect

MODEL = "BAAI/bge-small-en-v1.5"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
DEFAULT_CONFIG = "s512-o64"

_model = None


def get_model():
    global _model
    if _model is None:
        _model = TextEmbedding(MODEL)
    return _model


def embed_query(question):
    return next(get_model().embed([QUERY_PREFIX + question]))


def retrieve(question, k=5, part=None, config=DEFAULT_CONFIG):
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


if __name__ == "__main__":
    for r in retrieve("maximum supply voltage", part="lm358"):
        print(f"{r['id']:<22} {r['part']:<10} p{r['page']:<4} {r['kind']:<5} score {r['score']}")