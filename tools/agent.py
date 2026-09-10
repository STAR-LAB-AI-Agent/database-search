"""agent 模块：用 DeepSeek 的 function calling 自动调用本地检索工具，实现"智能体"。"""

import json
import sys

from tools.config import get_db_path, get_top_k, get_llm_config


# 工具定义：告诉 DeepSeek 有哪些函数可以调用
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "cquery",
            "description": "按文件名/格式/文件夹在元数据库中定位文件，返回文件清单（含路径、名字、格式）",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "文件名关键词（模糊匹配）"},
                    "ext": {"type": "string", "description": "格式后缀，如 .pdf"},
                    "folder": {"type": "string", "description": "文件夹名（模糊匹配）"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read",
            "description": "读取指定路径文件的内容（支持 pdf/docx/txt/md）",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件的完整路径"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": "按内容语义检索，返回相关片段和来源（需先 ingest 建索引）",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "要检索的问题或关键词"},
                    "top_k": {"type": "integer", "description": "返回条数，默认 5"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask",
            "description": "基于本地资料回答问题（RAG），返回答案和来源",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "要回答的问题"},
                },
                "required": ["question"],
            },
        },
    },
]


def _execute_tool(name, args):
    """执行工具，返回结果字符串。"""
    try:
        if name == "cquery":
            from tools.catalog import query
            results = query(
                str(get_db_path() / "catalog.db"),
                name=args.get("name"), ext=args.get("ext"), folder=args.get("folder"),
                limit=20,
            )
            return json.dumps({"count": len(results), "results": results}, ensure_ascii=False)

        if name == "read":
            from tools.loader import load_file
            pages = load_file(args["path"])
            text = "\n\n".join(p["text"] for p in pages if p["text"])
            return text[:5000] if text else "（文件为空或无法解析）"

        if name == "search":
            from tools.indexer import _get_collection
            from tools.retriever import search
            collection = _get_collection(get_db_path())
            top_k = args.get("top_k") or get_top_k()
            results = search(args["query"], collection, top_k=top_k)
            return json.dumps(results, ensure_ascii=False)

        if name == "ask":
            from tools.indexer import _get_collection
            from tools.qa import ask
            collection = _get_collection(get_db_path())
            result = ask(args["question"], collection, top_k=get_top_k())
            return json.dumps(result, ensure_ascii=False)

        return f"未知工具: {name}"
    except Exception as e:
        return f"工具 {name} 执行出错: {e}"


def run_agent(question, max_steps=10):
    """agent 循环：把问题交给 DeepSeek，让它自动调用工具，直到给出最终答案。"""
    from openai import OpenAI

    llm = get_llm_config()
    if not llm["api_key"]:
        raise ValueError("未设置 DEEPSEEK_API_KEY，无法使用 agent。请填进 .env。")

    client = OpenAI(api_key=llm["api_key"], base_url=llm["base_url"])

    messages = [
        {
            "role": "system",
            "content": (
                "你是一个本地资料检索助手，可以调用工具来查找、读取本地文件。"
                "先理解用户需求，再选工具：找文件用 cquery，读内容用 read，"
                "按内容语义检索用 search，基于资料问答用 ask。"
                "最后用自然语言向用户报告结果。"
            ),
        },
        {"role": "user", "content": question},
    ]

    for _ in range(max_steps):
        resp = client.chat.completions.create(
            model=llm["model"],
            messages=messages,
            tools=TOOLS,
        )
        msg = resp.choices[0].message

        # 没有工具调用 → 就是最终答案
        if not msg.tool_calls:
            return msg.content or "（没有返回内容）"

        # 手动构造 assistant 消息（含 tool_calls），再逐个执行并回传结果
        messages.append({
            "role": "assistant",
            "content": msg.content,
            "tool_calls": [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in msg.tool_calls
            ],
        })
        for tc in msg.tool_calls:
            try:
                fn_args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                fn_args = {}
            print(f"[工具调用] {tc.function.name}({fn_args})", file=sys.stderr)
            result = _execute_tool(tc.function.name, fn_args)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

    return "（达到最大步数，仍未完成）"
