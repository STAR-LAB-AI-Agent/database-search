"""命令行入口：把各个模块接成可执行的子命令。"""

import argparse
import json
import sys

from tools.config import get_db_path, get_search_dirs, get_top_k
from tools.indexer import _get_collection, sync_index, ingest
from tools.finder import find
from tools.retriever import search
from tools.qa import ask
from tools.manage import list_files, remove_file, stats


def _emit(obj):
    """输出 JSON（带缩进换行，方便人阅读）。"""
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def cmd_ingest(args):
    return {"action": "ingest", **ingest(args.path)}


def cmd_find(args):
    dirs = [args.dir] if args.dir else get_search_dirs()
    results = find(args.pattern, dirs)
    return {"action": "find", "count": len(results), "results": results}


def cmd_search(args):
    db = get_db_path()
    sync_index([args.dir] if args.dir else get_search_dirs(), db)
    collection = _get_collection(db)
    top_k = args.top_k if args.top_k is not None else get_top_k()
    results = search(args.query, collection, top_k=top_k)
    return {"action": "search", "count": len(results), "results": results}


def cmd_ask(args):
    db = get_db_path()
    sync_index(get_search_dirs(), db)
    collection = _get_collection(db)
    top_k = args.top_k if args.top_k is not None else get_top_k()
    result = ask(args.question, collection, top_k=top_k)
    return {"action": "ask", **result}


def cmd_list(args):
    return {"action": "list", "files": list_files(get_db_path())}


def cmd_remove(args):
    db = get_db_path()
    collection = _get_collection(db)
    result = remove_file(db, collection, args.name, confirm=args.yes)
    return {"action": "remove", "name": args.name, **result}


def cmd_stats(args):
    return {"action": "stats", **stats(get_db_path())}


def cmd_catalog(args):
    """建立元数据库：记录每个文件夹里有哪些文件、什么格式。"""
    from tools.catalog import build

    dirs = [args.dir] if args.dir else get_search_dirs()
    build(dirs, str(get_db_path() / "catalog.db"))
    return {"action": "catalog", "status": "已更新元数据库"}


def cmd_cquery(args):
    """查询元数据库：按名字/格式/文件夹定位文件。"""
    from tools.catalog import query

    results = query(
        str(get_db_path() / "catalog.db"),
        name=args.name, ext=args.ext, folder=args.folder,
    )
    return {"action": "cquery", "count": len(results), "results": results}


def cmd_cstats(args):
    """元数据库统计：文件总数 + 各格式数量。"""
    from tools.catalog import stats as catalog_stats

    return {"action": "cstats", **catalog_stats(str(get_db_path() / "catalog.db"))}


def cmd_read(args):
    """按路径读取文件内容（支持 pdf/docx/txt/md/html）。"""
    from tools.loader import load_file

    pages = load_file(args.path)
    text = "\n\n".join(p["text"] for p in pages if p["text"])
    return {"action": "read", "path": args.path, "text": text}


def cmd_agent(args):
    """智能体：用 DeepSeek 自动调用工具完成任务。"""
    from tools.agent import run_agent

    answer = run_agent(args.question)
    return {"action": "agent", "answer": answer}


def main():
    # Windows 控制台中文乱码修复
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(prog="cli.py", description="AI 本地资料检索 CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("ingest", help="导入文件或目录")
    p.add_argument("path")
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("find", help="按文件名检索")
    p.add_argument("pattern")
    p.add_argument("--dir", default=None)
    p.set_defaults(func=cmd_find)

    p = sub.add_parser("search", help="按内容语义检索")
    p.add_argument("query")
    p.add_argument("--top-k", type=int, default=None)
    p.add_argument("--dir", default=None)
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("ask", help="基于资料问答")
    p.add_argument("question")
    p.add_argument("--top-k", type=int, default=None)
    p.set_defaults(func=cmd_ask)

    p = sub.add_parser("list", help="列出库中文件")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("remove", help="删除文件（需 --yes）")
    p.add_argument("name")
    p.add_argument("--yes", action="store_true")
    p.set_defaults(func=cmd_remove)

    p = sub.add_parser("stats", help="库统计")
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("catalog", help="建立元数据库（文件名+格式）")
    p.add_argument("--dir", default=None, help="扫描目录（默认用 search_dirs）")
    p.set_defaults(func=cmd_catalog)

    p = sub.add_parser("cquery", help="查询元数据库")
    p.add_argument("--name", default=None, help="文件名模糊匹配")
    p.add_argument("--ext", default=None, help="格式精确匹配，如 .pdf")
    p.add_argument("--folder", default=None, help="文件夹精确匹配")
    p.set_defaults(func=cmd_cquery)

    p = sub.add_parser("cstats", help="元数据库统计")
    p.set_defaults(func=cmd_cstats)

    p = sub.add_parser("read", help="读取指定文件的内容")
    p.add_argument("path")
    p.set_defaults(func=cmd_read)

    p = sub.add_parser("agent", help="智能体：自动调用工具完成任务")
    p.add_argument("question")
    p.set_defaults(func=cmd_agent)

    args = parser.parse_args()

    try:
        result = args.func(args)
    except ValueError as e:
        _emit({"error": str(e)})
        return 1
    except Exception as e:
        _emit({"error": f"出错了: {e}"})
        return 1

    _emit(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
