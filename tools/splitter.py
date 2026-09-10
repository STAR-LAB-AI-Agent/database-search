


def split_text(text, page=None, chunk_size=500, chunk_overlap=50):
    #把一段文字切成固定长度、带重叠的小块
    text = text.strip()
    if not text:
        return []

    step = chunk_size - chunk_overlap
    if step < 1:
        step = 1  # 保险：防止重叠比块还大，导致原地踏步死循环

    chunks = []
    start = 0
    while start < len(text):
        chunk = text[start: start + chunk_size]
        chunks.append({"text": chunk, "page": page, "chunk_index": len(chunks)})
        start += step

    return chunks


def split_pages(pages, chunk_size=500, chunk_overlap=50):
    #处理 loader 的返回结果：每一页都切成块，拼成一个大列表
    chunks = []
    for item in pages:
        chunks.extend(
            split_text(
                item["text"],
                page=item["page"],
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
        )
    return chunks