"""元数据库模块：用 SQLite 记录每个文件夹里有哪些文件、什么格式。

和 Chroma 分工不同：Chroma 存"内容向量"做语义检索，这里只存"文件名/格式/位置"做文件定位。
"""

import os
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

from tools.config import load_config


_SCHEMA = """CREATE TABLE IF NOT EXISTS files (
    path   TEXT PRIMARY KEY,
    folder TEXT,
    name   TEXT,
    stem   TEXT,
    ext    TEXT,
    size   INTEGER,
    mtime  REAL
)"""


def _ensure_schema(conn):
    """保证 files 表存在，避免 cquery/cstats 在未建库时报 'no such table'。"""
    conn.execute(_SCHEMA)


def _is_under(path_str, dirs):
    """判断一个文件路径是否在 dirs 中某个目录下。"""
    p = Path(path_str)
    for d in dirs:
        try:
            p.resolve().relative_to(Path(d).resolve())
            return True
        except ValueError:
            continue
    return False


def build(dirs, catalog_path):
    """扫描目录，把文件元数据写入 SQLite（不含文件内容）。"""
    exclude_dirs = set(load_config()["storage"]["exclude_dirs"])

    print("正在扫描目录建立元数据库...", file=sys.stderr)
    current_paths = set()
    with closing(sqlite3.connect(str(catalog_path))) as conn:
        _ensure_schema(conn)
        for d in dirs:
            d = Path(d)
            if not d.exists():
                continue
            for root, dirnames, filenames in os.walk(d):
                dirnames[:] = [n for n in dirnames if n not in exclude_dirs]
                for name in filenames:
                    p = Path(root) / name
                    st = p.stat()   # 只调一次 stat，复用大小和修改时间
                    current_paths.add(str(p))
                    conn.execute(
                        "INSERT OR REPLACE INTO files VALUES (?,?,?,?,?,?,?)",
                        (str(p), str(p.parent), p.name, p.stem,
                         p.suffix, st.st_size, st.st_mtime),
                    )

        # 删除扫描范围内已不存在的文件（陈旧条目）
        for (path,) in conn.execute("SELECT path FROM files").fetchall():
            if path not in current_paths and _is_under(path, dirs):
                conn.execute("DELETE FROM files WHERE path = ?", (path,))
        conn.commit()

    print(f"元数据库更新完成，共 {len(current_paths)} 个文件", file=sys.stderr)


def query(catalog_path, name=None, ext=None, folder=None, limit=50):
    """按条件查询：name 关键词同时匹配文件名/主干/文件夹/完整路径，ext/folder 精确匹配。"""
    sql = "SELECT path, folder, name, stem, ext, size, mtime FROM files WHERE 1=1"
    params = []
    if name:
        # 关键：用户往往按主题/课程名找文件（如"区块链"），但这个词可能只出现在
        # 文件夹名里（文件名是"第1讲-导论.pdf"），所以关键词要同时命中 folder/path。
        like = f"%{name}%"
        sql += " AND (name LIKE ? OR stem LIKE ? OR folder LIKE ? OR path LIKE ?)"
        params.extend([like, like, like, like])
    if ext:
        sql += " AND ext = ?"
        params.append(ext)
    if folder:
        sql += " AND folder LIKE ?"
        params.append(f"%{folder}%")
    sql += " LIMIT ?"
    params.append(limit)

    with closing(sqlite3.connect(str(catalog_path))) as conn:
        _ensure_schema(conn)
        rows = conn.execute(sql, params).fetchall()

    keys = ["path", "folder", "name", "stem", "ext", "size", "mtime"]
    return [dict(zip(keys, r)) for r in rows]


def stats(catalog_path):
    """统计：文件总数 + 各格式数量。"""
    with closing(sqlite3.connect(str(catalog_path))) as conn:
        _ensure_schema(conn)
        total = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        by_ext = conn.execute(
            "SELECT ext, COUNT(*) FROM files GROUP BY ext ORDER BY COUNT(*) DESC"
        ).fetchall()
    return {"total": total, "by_ext": {e: c for e, c in by_ext}}
