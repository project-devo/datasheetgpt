"""rerank(): reorder retrieved chunks with a cross-encoder (Goal 15)."""
from fastembed.rerank.cross_encoder import TextCrossEncoder

RERANK_MODEL = "BAAI/bge-reranker-base"
# mode name -> cross-encoder model
RERANK_MODELS = {
    "rerank": RERANK_MODEL,                           # 1.06 GB, best quality
    "rerank-small": "Xenova/ms-marco-MiniLM-L-6-v2",  # 0.08 GB, fits Render free
}

_rerankers = {}


def get_reranker(name=RERANK_MODEL):
    if name not in _rerankers:
        _rerankers[name] = TextCrossEncoder(name)
    return _rerankers[name]


def rerank(question, chunks, k=5, model=RERANK_MODEL):
    """Score each (question, chunk) pair together and keep the k best."""
    if not chunks:
        return []
    docs = [c["content"] for c in chunks]
    scores = list(get_reranker(model).rerank(question, docs))
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