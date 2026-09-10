import json
import os
from pathlib import Path

from dotenv import load_dotenv

# 项目根目录 = 这个文件(config.py)再往上两级。
# config.py 位于 F:\Agent\project\tools\ 里，往上两级就是 F:\Agent\project
BASE_DIR = Path(__file__).resolve().parent.parent

# 默认值：config.json 里某个字段没写时，就用这里的值兜底。
DEFAULT_CONFIG = {
    "storage": {
        "search_dirs": ["F:/"],
        "exclude_dirs": [".venv", ".git", ".idea", "__pycache__", "node_modules", "db", "reference", "$RECYCLE.BIN", "System Volume Information"],
        "extensions": [".pdf", ".docx", ".txt", ".md"],
        "max_file_size_mb": 50,
        "db_path": "db",
    },
    "indexing": {
        "chunk_size": 500,
        "chunk_overlap": 50,
        "embedding_model": "BAAI/bge-m3",
    },
    "retrieval": {"top_k": 5, "reranker_model": "BAAI/bge-reranker-v2-m3"},
    "llm": {
        "model": "deepseek-chat",
        "base_url": "https://api.deepseek.com",
    },
}

# 缓存：第一次读完就存这里，之后直接用，不再重复读文件。
_config_cache = None


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config() -> dict:
    global _config_cache

    # 已经读过就直接返回缓存，不再读文件。
    if _config_cache is not None:
        return _config_cache

    # 先把 .env 里的密码读进环境变量
    load_dotenv(BASE_DIR / ".env")

    # 读 config.json 文件。
    config_path = BASE_DIR / "config.json"
    raw = {}
    if config_path.exists():
        try:
            raw = json.loads(config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # 文件坏了或读不了，就用空字典，交给默认值兜底。
            raw = {}

    # 和默认值合并：文件里写了就用文件的，没写就用默认的。
    merged = _deep_merge(DEFAULT_CONFIG, raw)

    _config_cache = merged
    return merged

#获取搜索路径
def get_search_dirs(extra=None) -> list:
    cfg = load_config()
    dirs=list(cfg["storage"]["search_dirs"])
    if extra:
        if isinstance(extra, (str, Path)):
            dirs.append(extra)
        else:
            dirs.extend(extra)
    result=[]
    for d in dirs:
        p=Path(d)
        if not p.is_absolute():
            p=BASE_DIR / p
        result.append(p.resolve())

    return result
#获取dp绝对路径
def get_db_path() -> Path:
    cfg = load_config()
    db_dir=Path(cfg["storage"]["db_path"])
    if not db_dir.is_absolute():
        db_dir=BASE_DIR / db_dir
    return db_dir.resolve()

# 获取 embedding 模型名
def get_embedding_model() -> str:
    cfg = load_config()
    return cfg["indexing"]["embedding_model"]


def get_top_k() -> int:
    return load_config()["retrieval"]["top_k"]


def get_reranker_model() -> str:
    """返回重排序用的模型名。"""
    return load_config()["retrieval"].get("reranker_model", "BAAI/bge-reranker-v2-m3")


def get_llm_config() -> dict:
    cfg = load_config()
    return {
        "model": cfg["llm"]["model"],
        "base_url": cfg["llm"]["base_url"],
        "api_key": os.getenv("DEEPSEEK_API_KEY", ""),
    }