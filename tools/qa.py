"""问答模块：检索 + 生成。

当模型答复表明「资料不足、没有相关信息」时，会自动扩大检索范围、
把更多片段合并进上下文再重新生成，最多回退 max_rounds 轮。
"""

import sys

from openai import OpenAI

from tools.config import get_llm_config, get_top_k
from tools.retriever import search_with_rerank

# 模型表示「信息不够」时的常见措辞，命中则触发扩大检索补充上下文。
_NEED_MORE_HINTS = (
    "没有相关信息",
    "资料里没有",
    "资料中没有",
    "未找到",
    "信息不足",
    "无法回答",
)


def _needs_more(answer: str) -> bool:
    """判断模型是否表达了「资料不足以回答」。"""
    if not answer:
        return True
    return any(hint in answer for hint in _NEED_MORE_HINTS)


def _cite(h):
    """把单个检索片段格式化成带来源/页码的引用块。"""
    page = h.get("page")
    page_part = f"，第 {page} 页" if page else ""
    return f"[来源：{h['source']}{page_part}]\n{h['text']}"


def _generate(client, llm, question, hits):
    """把检索片段拼成提示词，调用 LLM 生成答案。"""
    context = "\n\n".join(_cite(h) for h in hits)

    system_prompt = (
        "你是一个资料查询助手。请只根据下面提供的资料片段回答问题。"
        "如果资料里没有答案，就直说'资料里没有相关信息'，不要编造。"
    )
    user_prompt = f"资料片段：\n{context}\n\n问题：{question}"

    resp = client.chat.completions.create(
        model=llm["model"],
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
    )
    return resp.choices[0].message.content or ""


def ask(question, collection, top_k=None, max_rounds=3):
    """检索 + 生成：模型反馈信息不足时逐轮扩大检索、补充上下文。"""
    if top_k is None:
        top_k = get_top_k()

    llm = get_llm_config()
    if not llm["api_key"]:
        raise ValueError("未设置 DEEPSEEK_API_KEY，无法使用问答功能。请把 Key 填进 .env 文件。")

    client = OpenAI(api_key=llm["api_key"], base_url=llm["base_url"])

    # 已累积的片段（按文本去重），逐轮只增不减，实现"添加上下文"。
    accumulated = {}
    current_top_k = top_k
    answer = ""
    rounds = 0

    for round_i in range(max_rounds):
        rounds = round_i + 1
        # 扩大候选池，让真正更相关的片段有机会进入 top-k。
        candidate_k = max(20, current_top_k * 4)
        new_hits = search_with_rerank(
            question, collection, top_k=current_top_k, candidate_k=candidate_k
        )

        added = 0
        for h in new_hits:
            if h["text"] not in accumulated:
                accumulated[h["text"]] = h
                added += 1

        if not accumulated:
            return {
                "answer": "资料库里没有找到相关内容。",
                "sources": [],
                "context_chunks": 0,
                "rounds": rounds,
            }

        hits = list(accumulated.values())
        print(f"[第 {rounds} 轮] 用 {len(hits)} 个片段生成答案...", file=sys.stderr)
        answer = _generate(client, llm, question, hits)

        # 模型觉得信息够了，或本轮没有新增片段可补 → 结束回退。
        if not _needs_more(answer) or added == 0:
            break

        print(
            f"模型反馈信息不足，扩大检索（top-k {current_top_k} → {current_top_k * 2}）补充上下文...",
            file=sys.stderr,
        )
        current_top_k *= 2

    sources = sorted({h["source"] for h in accumulated.values()})
    return {
        "answer": answer,
        "sources": sources,
        "context_chunks": len(accumulated),
        "rounds": rounds,
    }
