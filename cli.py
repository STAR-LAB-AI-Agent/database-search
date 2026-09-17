"""命令行入口：把各个模块接成可执行的子命令。

默认输出人类易读的文本，加 `--json` 则输出原始 JSON（便于脚本/程序解析）。
"""

import argparse
import datetime
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


def _human_size(n):
    """把字节数转成易读的 B/KB/MB/GB。"""
    size = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024


def _human_time(ts):
    """把时间戳转成易读的本地时间。"""
    if not ts:
        return "-"
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def _render(obj):
    """把命令结果渲染成易读文本。"""
    if "error" in obj:
        return f"❌ 出错：{obj['error']}"

    action = obj.get("action")

    if action == "ingest":
        return (f"✅ 导入完成：新增 {obj['added']}，更新 {obj['updated']}，"
                f"删除 {obj['deleted']}，跳过 {obj['skipped']}")

    if action == "sync":
        return (f"🔄 同步完成：新增 {obj['added']}，更新 {obj['updated']}，"
                f"删除 {obj['deleted']}，跳过 {obj['skipped']}")

    if action == "find":
        if obj["count"] == 0:
            return "🔍 没有找到匹配的文件。"
        lines = [f"🔍 找到 {obj['count']} 个文件："]
        for r in obj["results"]:
            lines.append(f"  · {r['name']}  （{_human_size(r['size'])}，{_human_time(r['mtime'])}）")
            lines.append(f"    {r['path']}")
        return "\n".join(lines)

    if action == "search":
        if obj["count"] == 0:
            return "🔍 没有找到相关内容。"
        lines = [f"🔍 找到 {obj['count']} 个相关片段："]
        for i, r in enumerate(obj["results"], 1):
            page = f"，第 {r['page']} 页" if r.get("page") else ""
            lines.append(f"\n[{i}] {r['source']}{page}  （相关度 {r['score']}）")
            lines.append("    " + r["text"].strip().replace("\n", " "))
        return "\n".join(lines)

    if action == "ask":
        lines = [obj["answer"].strip(), ""]
        if obj.get("sources"):
            lines.append("📚 参考来源：")
            for s in obj["sources"]:
                lines.append(f"  · {s}")
        if obj.get("context_chunks"):
            lines.append(f"（本次检索使用了 {obj['context_chunks']} 个片段，共 {obj.get('rounds', 1)} 轮）")
        return "\n".join(lines).rstrip()

    if action == "list":
        if not obj["files"]:
            return "资料库为空（还没有导入任何文件）。"
        lines = ["📁 资料库中的文件："]
        for f in obj["files"]:
            lines.append(f"  · {f['name']}  （{f['chunks']} 块，{_human_size(f['size'])}）")
            lines.append(f"    {f['path']}")
        return "\n".join(lines)

    if action == "remove":
        if obj.get("removed"):
            lines = [f"🗑️  已删除 {obj.get('count', 0)} 个文件："]
            for p in obj.get("paths", []):
                lines.append(f"    {p}")
            for f in obj.get("failed", []):
                lines.append(f"    ⚠️ 删除失败：{f}")
            return "\n".join(lines)
        return f"⚠️  未删除：{obj.get('reason', '')}"

    if action == "stats":
        return (f"📊 资料库统计：{obj['files']} 个文件，"
                f"{obj['chunks']} 个片段，总大小 {_human_size(obj['size_bytes'])}")

    if action == "catalog":
        return f"🗂️  {obj.get('status', '已更新元数据库')}"

    if action == "cquery":
        if obj["count"] == 0:
            return "🗂️  没有找到匹配的文件。"
        lines = [f"🗂️  找到 {obj['count']} 个文件："]
        for r in obj["results"]:
            ext = r["ext"] or "无后缀"
            lines.append(f"  · {r['name']}  （{ext}，{_human_size(r['size'])}）")
            lines.append(f"    {r['path']}")
        return "\n".join(lines)

    if action == "cstats":
        lines = [f"📊 元数据库共 {obj['total']} 个文件"]
        for ext, count in obj.get("by_ext", {}).items():
            lines.append(f"    {ext or '无后缀'}: {count}")
        return "\n".join(lines)

    if action == "read":
        text = obj.get("text", "")
        if text:
            return f"📄 {obj['path']}\n\n{text}"
        return f"📄 {obj['path']}（文件为空或无法解析）"

    if action == "agent":
        return obj.get("answer", "")

    # 未知 action：回退成 JSON，至少不丢信息
    return json.dumps(obj, ensure_ascii=False, indent=2)


def _output(obj, as_json):
    if as_json:
        _emit(obj)
    else:
        print(_render(obj))


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


def cmd_sync(args):
    """显式同步：扫描搜索目录，把新增/修改/删除的文件反映到资料库。"""
    db = get_db_path()
    result = sync_index(get_search_dirs(), db)
    return {"action": "sync", **result}


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

    # 所有子命令共享的选项：--json 输出原始 JSON
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="输出原始 JSON（默认输出易读文本）")

    p = sub.add_parser("ingest", help="导入文件或目录", parents=[common])
    p.add_argument("path")
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("find", help="按文件名/所在文件夹检索", parents=[common])
    p.add_argument("pattern")
    p.add_argument("--dir", default=None)
    p.set_defaults(func=cmd_find)

    p = sub.add_parser("search", help="按内容语义检索", parents=[common])
    p.add_argument("query")
    p.add_argument("--top-k", type=int, default=None)
    p.add_argument("--dir", default=None)
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("ask", help="基于资料问答", parents=[common])
    p.add_argument("question")
    p.add_argument("--top-k", type=int, default=None)
    p.set_defaults(func=cmd_ask)

    p = sub.add_parser("list", help="列出库中文件", parents=[common])
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("remove", help="从磁盘和资料库删除文件（需 --yes）", parents=[common])
    p.add_argument("name")
    p.add_argument("--yes", action="store_true")
    p.set_defaults(func=cmd_remove)

    p = sub.add_parser("stats", help="库统计", parents=[common])
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("sync", help="扫描搜索目录，同步新增/修改/删除的文件", parents=[common])
    p.set_defaults(func=cmd_sync)

    p = sub.add_parser("catalog", help="建立元数据库（文件名+格式）", parents=[common])
    p.add_argument("--dir", default=None, help="扫描目录（默认用 search_dirs）")
    p.set_defaults(func=cmd_catalog)

    p = sub.add_parser("cquery", help="查询元数据库", parents=[common])
    p.add_argument("--name", default=None, help="关键词（匹配文件名/文件夹/路径）")
    p.add_argument("--ext", default=None, help="格式精确匹配，如 .pdf")
    p.add_argument("--folder", default=None, help="文件夹精确匹配")
    p.set_defaults(func=cmd_cquery)

    p = sub.add_parser("cstats", help="元数据库统计", parents=[common])
    p.set_defaults(func=cmd_cstats)

    p = sub.add_parser("read", help="读取指定文件的内容", parents=[common])
    p.add_argument("path")
    p.set_defaults(func=cmd_read)

    p = sub.add_parser("agent", help="智能体：自动调用工具完成任务", parents=[common])
    p.add_argument("question")
    p.set_defaults(func=cmd_agent)

    args = parser.parse_args()

    try:
        result = args.func(args)
    except ValueError as e:
        _output({"error": str(e)}, args.json)
        return 1
    except Exception as e:
        _output({"error": f"出错了: {e}"}, args.json)
        return 1

    _output(result, args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
