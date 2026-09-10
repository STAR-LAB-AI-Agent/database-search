import sys

from openai import OpenAI

from tools.config import get_llm_config, get_top_k
from tools.retriever import search_with_rerank

def ask(question, collection, top_k=None):
    """检索 + 生成：根据本地资料回答，返回答案和来源文件。"""
    if top_k is None:
        top_k = get_top_k()

    llm = get_llm_config()
    if not llm["api_key"]:
        raise ValueError("未设置 DEEPSEEK_API_KEY，无法使用问答功能。请把 Key 填进 .env 文件。")

    # 1. 检索相关片段
    hits = search_with_rerank(question, collection, top_k=top_k)
    if not hits:
        return {"answer": "资料库里没有找到相关内容。", "sources": []}

    # 2. 拼提示词
    context = "\n\n".join(
        f"[来源：{h['source']}，第 {h['page']} 页]\n{h['text']}" for h in hits
    )
    sources = sorted({h["source"] for h in hits})

    system_prompt = (
        "你是一个资料查询助手。请只根据下面提供的资料片段回答问题。"
        "如果资料里没有答案，就直说'资料里没有相关信息'，不要编造。"
    )
    user_prompt = f"资料片段：\n{context}\n\n问题：{question}"

    # 3. 调用 DeepSeek
    print("正在调用 DeepSeek 生成答案...", file=sys.stderr)
    client = OpenAI(
        api_key=llm["api_key"],
        base_url=llm["base_url"],
    )
    resp = client.chat.completions.create(
        model=llm["model"],
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
    )
    answer = resp.choices[0].message.content

    return {"answer": answer, "sources": sources}

