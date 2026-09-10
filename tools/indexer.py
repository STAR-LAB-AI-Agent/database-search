import hashlib
import json
import os
import sys
from pathlib import Path
from tools.config import load_config
from tools.embeddings import embed
from tools.loader import load_file
from tools.splitter import split_pages

def _scan_files(dirs):
    cfg = load_config()
    exclude_dirs = set(cfg["storage"]["exclude_dirs"])
    max_bytes = cfg["storage"]["max_file_size_mb"] * 1024 * 1024

    files = {}
    for d in dirs:
        d = Path(d)
        if not d.exists():
            continue
        for root, dirnames, filenames in os.walk(d):
            # 关键：原地删掉要排除的文件夹，os.walk 就不会再进去
            dirnames[:] = [n for n in dirnames if n not in exclude_dirs]
            for name in filenames:
                path = Path(root) / name
                stat = path.stat()
                if stat.st_size > max_bytes:
                    continue
                files[str(path.resolve())] = {
                    "mtime": stat.st_mtime,
                    "size": stat.st_size,
                }
    return files


def _load_state(db_path):
    """读上次的索引清单；没有或读不了就返回空字典。"""
    state_path = Path(db_path) / ".index_state.json"
    if not state_path.exists():
        return {}
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_state(db_path, state):
    db_path = Path(db_path)
    db_path.mkdir(parents=True, exist_ok=True)
    state_path = db_path / ".index_state.json"
    state_path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

def _get_collection(db_path):
    """打开（或创建）Chroma 集合，并检查 embedding 模型是否一致。"""
    import chromadb
    from tools.config import get_embedding_model

    model_name = get_embedding_model()
    client = chromadb.PersistentClient(path=str(db_path))
    collection = client.get_or_create_collection(
          name="local_docs",
          metadata={"embedding_model": model_name},
      )

    recorded = collection.metadata.get("embedding_model")
    if recorded and recorded != model_name:
        raise ValueError(
              f"资料库是用模型 '{recorded}' 建的，当前配置是 '{model_name}'。"
              "换了模型必须重建索引（删掉 db 文件夹重来）。"
        )
    return collection

def _index_file(path, collection):
    """处理单个文件：解析→切块→向量化→存库，返回产生的 chunk_id 列表。"""
    cfg = load_config()
    chunk_size = cfg["indexing"]["chunk_size"]
    chunk_overlap = cfg["indexing"]["chunk_overlap"]

    extensions = set(cfg["storage"]["extensions"])
    p = Path(path)
    if p.suffix.lower() in extensions:
        # 支持的类型：解析正文
        pages = load_file(path)
        chunks = split_pages(pages, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    else:
        # 不支持的类型：索引文件名 + 后缀 + 路径，让 AI 能区分不同文件
        chunks = [{"text": f"文件名：{p.name}，后缀：{p.suffix}，路径：{p}", "page": None, "chunk_index": 0}]

    if not chunks:
        return []

    # 3. 批量向量化
    texts = [c["text"] for c in chunks]
    vectors = embed(texts)

    # 4. 组装 ID 和元数据
    doc_id = hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:16]
    ids = []
    metadatas = []
    for i, c in enumerate(chunks):
        ids.append(f"{doc_id}_{i}")
        metadatas.append({
            "source": str(path),
            "page": c["page"] if c["page"] is not None else 0,
            "chunk_index": c["chunk_index"],
        })

      # 5. 存进 Chroma
    collection.upsert(
        ids=ids,
        documents=texts,
        embeddings=vectors,
        metadatas=metadatas,
      )
    return ids

def _is_under(path_str, dirs):
    """判断一个文件路径是否在 dirs 中的某个目录下。"""
    p = Path(path_str)
    for d in dirs:
        try:
            p.resolve().relative_to(Path(d).resolve())
            return True
        except ValueError:
            continue
    return False


def sync_index(dirs, db_path):
    """主入口：增量同步索引。对比磁盘文件和上次账本，只处理有变化的。"""
    db_path = Path(db_path)

    print("正在扫描目录...", file=sys.stderr)
    current = _scan_files(dirs)            # 磁盘上现在的文件
    state = _load_state(db_path)            # 上次的账本
    collection = _get_collection(db_path)   # 向量库集合

    added = updated = deleted = skipped = 0

    # 找新增、修改的文件
    for path, fp in current.items():
        old = state.get(path)
        if old is None:
            # 新增：直接入库
            try:
                print(f"正在索引: {Path(path).name}", file=sys.stderr)
                ids = _index_file(path, collection)
                state[path] = {"mtime": fp["mtime"], "size": fp["size"], "chunk_ids": ids}
                added += 1
            except Exception:
                skipped += 1
        elif old["mtime"] != fp["mtime"] or old["size"] != fp["size"]:
            # 修改了：先删旧块，再重建
            try:
                if old.get("chunk_ids"):
                    collection.delete(ids=old["chunk_ids"])
                print(f"正在索引: {Path(path).name}", file=sys.stderr)
                ids = _index_file(path, collection)
                state[path] = {"mtime": fp["mtime"], "size": fp["size"], "chunk_ids": ids}
                updated += 1
            except Exception:
                skipped += 1
          # 否则：没变化，跳过

    # 找已删除的文件（账本里有、磁盘上没了，且在本扫描范围内）
    for path in list(state.keys()):
        if path not in current and _is_under(path, dirs):
            old = state[path]
            if old.get("chunk_ids"):
                collection.delete(ids=old["chunk_ids"])
            del state[path]
            deleted += 1

    print(f"同步完成：新增 {added}，更新 {updated}，删除 {deleted}，跳过 {skipped}", file=sys.stderr)
    _save_state(db_path, state)
    return {"added": added, "updated": updated, "deleted": deleted, "skipped": skipped}


def ingest(path):
    """便捷封装：索引一个文件或目录（供命令行调用）。"""
    from tools.config import get_db_path

    p = Path(path)
    dirs = [p] if p.is_dir() else [p.parent]
    return sync_index(dirs, get_db_path())
