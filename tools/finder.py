"""文件名检索模块：按文件名查找文件，支持子串匹配 + 模糊匹配（容忍错别字）。"""

import os
from pathlib import Path
from difflib import get_close_matches

from tools.config import load_config


def find(pattern, dirs, cutoff=0.6):
    """按文件名模糊匹配：子串包含 或 模糊相似（容忍错别字）都算命中。"""
    pattern_lower = pattern.lower()
    exclude_dirs = set(load_config()["storage"]["exclude_dirs"])

    results = []
    for d in dirs:
        d = Path(d)
        if not d.exists():
            continue
        for root, dirnames, filenames in os.walk(d):
            dirnames[:] = [n for n in dirnames if n not in exclude_dirs]
            for name in filenames:
                stem = Path(name).stem   # 去掉后缀，比如 config.json → config
                # 第一关：子串包含（快、准）
                hit = pattern_lower in stem.lower()
                # 第二关：模糊相似（容忍错别字）
                if not hit:
                    hit = bool(get_close_matches(pattern, [stem], n=1, cutoff=cutoff))
                if hit:
                    path = Path(root) / name
                    stat = path.stat()
                    results.append({
                        "path": str(path.resolve()),
                        "name": name,
                        "size": stat.st_size,
                        "mtime": stat.st_mtime,
                    })
    return results
