"""重排序模块：用 cross-encoder 对候选片段精排，提升检索准确度。"""

import sys

_model = None


def get_reranker():
    """懒加载单例：重排序模型只加载一次。"""
    global _model
    if _model is None:
        from tools.config import get_reranker_model

        model_name = get_reranker_model()  # 先读配置（内部会 load_dotenv，加载 HF_ENDPOINT）

        from sentence_transformers import CrossEncoder

        print("正在加载重排序模型（首次会自动下载约 2GB，请稍候）...", file=sys.stderr)
        _model = CrossEncoder(model_name, local_files_only=True)
        print("重排序模型加载完成", file=sys.stderr)
    return _model


def rerank(query, texts, top_k=5):
    """对候选文本列表精排，返回按相关性从高到低的 [(下标, 分数), ...]。"""
    if not texts:
        return []
    model = get_reranker()
    results = model.rank(query, texts, top_k=min(top_k, len(texts)))
    return [(r["corpus_id"], float(r["score"])) for r in results]
