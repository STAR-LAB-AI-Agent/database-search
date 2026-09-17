"""库管理模块：列出文件、删除文件、统计。"""

from pathlib import Path

from tools.indexer import _load_state, _save_state


def list_files(db_path):
    """列出资料库里所有文件：名字、块数、大小、时间。"""
    state = _load_state(db_path)
    files = []
    for path, info in state.items():
        files.append({
            "name": Path(path).name,
            "path": path,
            "chunks": len(info.get("chunk_ids", [])),
            "size": info.get("size", 0),
            "mtime": info.get("mtime"),
        })
    files.sort(key=lambda f: f["name"].lower())
    return files


def remove_file(db_path, collection, name, confirm=False):
    """按文件名删除文件：同时从磁盘和资料库（向量库 + 账本）删除。"""
    if not confirm:
        return {"removed": False, "reason": "删除是高危操作，请加 --yes 确认"}

    state = _load_state(db_path)
    matched = {p: info for p, info in state.items() if Path(p).name == name}
    if not matched:
        return {"removed": False, "reason": f"没有找到文件: {name}"}

    removed_paths = []
    failed = []
    for p, info in matched.items():
        ids = info.get("chunk_ids", [])
        if ids:
            collection.delete(ids=ids)
        del state[p]
        # 同时删除磁盘上的真实文件，否则下次自动同步又会被索引回来
        try:
            Path(p).unlink(missing_ok=True)
            removed_paths.append(p)
        except OSError as e:
            failed.append(f"{p}（{e}）")

    _save_state(db_path, state)
    result = {"removed": True, "count": len(matched), "paths": removed_paths}
    if failed:
        result["failed"] = failed
    return result


def stats(db_path):
    """统计：文件数、块数、总大小。"""
    state = _load_state(db_path)
    files = len(state)
    chunks = sum(len(info.get("chunk_ids", [])) for info in state.values())
    size = sum(info.get("size", 0) for info in state.values())
    return {"files": files, "chunks": chunks, "size_bytes": size}
