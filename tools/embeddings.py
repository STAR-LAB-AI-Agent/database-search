"""向量化模块：用 sentence-transformers 把文字变成向量。"""

import sys

_model = None


def get_model():
    """懒加载单例：向量模型只加载一次。"""
    global _model
    if _model is None:
        from tools.config import get_embedding_model

        model_name = get_embedding_model()  # 先读配置（内部 load_dotenv，加载 HF_ENDPOINT）

        from sentence_transformers import SentenceTransformer

        print("正在加载向量模型（首次会自动下载约 2GB，请稍候）...", file=sys.stderr)
        _model = SentenceTransformer(model_name, local_files_only=True)
        print("向量模型加载完成", file=sys.stderr)
    return _model


def embed(texts, is_query=False):
    """把一串文字变成向量（自动归一化）。is_query=True 表示是问句，会加查询指令。"""
    model = get_model()
    if is_query:
        texts = ["Represent this sentence for searching relevant passages: " + t for t in texts]
    vectors = model.encode(texts, normalize_embeddings=True)
    return vectors.tolist()
