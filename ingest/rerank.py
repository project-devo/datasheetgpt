"""rerank(): reorder retrieved chunks with a cross-encoder (Goal 15)."""
from fastembed.rerank.cross_encoder import TextCrossEncoder

RERANK_MODEL = "BAAI/bge-reranker-base"

_reranker = None


def get_reranker():
    global _reranker
    if _reranker is None:
        _reranker = TextCrossEncoder(RERANK_MODEL)
    return _reranker


def rerank(question, chunks, k=5):
    """Score each (question, chunk) pair together and keep the k best."""
    if not chunks:
        return []
    docs = [c["content"] for c in chunks]
    scores = list(get_reranker().rerank(question, docs))
    for c, s in zip(chunks, scores):
        c["rerank_score"] = round(float(s), 4)
    return sorted(chunks, key=lambda c: c["rerank_score"], reverse=True)[:k]


if __name__ == "__main__":
    from retrieve import hybrid_search

    q = "What is the maximum supply voltage of the LM358?"
    pool = hybrid_search(q, k=20)
    print("hybrid top 5:  ", [f"{c['part']} p{c['page']}" for c in pool[:5]])
    top = rerank(q, pool, k=5)
    print("reranked top 5:", [f"{c['part']} p{c['page']} ({c['rerank_score']})" for c in top])