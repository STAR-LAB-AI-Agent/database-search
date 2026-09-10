from tools.embeddings import embed

def search(query, collection, top_k=5):
    """问句 → 向量 → 在库里查 top-k 最相关片段，返回带来源/页码/分数。"""
    if collection.count() == 0:
        return []

    vector = embed([query], is_query=True)[0]

    result = collection.query(
        query_embeddings=[vector],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )

    hits = []
    for text, meta, dist in zip(
            result["documents"][0],
            result["metadatas"][0],
            result["distances"][0],
    ):
        hits.append({
            "text": text,
            "source": meta.get("source"),
            "page": meta.get("page"),
            "score": round(1 - dist / 3, 4),
        })
    return hits


def search_with_rerank(query, collection, top_k=5, candidate_k=20):
    """先粗检索 candidate_k 个，再用 reranker 精排，返回 top_k 个。"""
    hits = search(query, collection, top_k=candidate_k)
    if len(hits) <= top_k:
        return hits

    from tools.reranker import rerank

    texts = [h["text"] for h in hits]
    ranked = rerank(query, texts, top_k=top_k)

    result = []
    for idx, score in ranked:
        hit = dict(hits[idx])
        hit["score"] = round(float(score), 4)
        result.append(hit)
    return result
