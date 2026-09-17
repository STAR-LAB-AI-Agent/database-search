"""文档加载模块：把 pdf / docx / txt / md / html 解析成统一的页面列表。

返回格式统一为 [{"page": int | None, "text": str}, ...]，page 为 None 表示非分页文档。
"""

import re
from pathlib import Path

import pdfplumber
from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

# 解码顺序：优先 UTF-8，再 GBK，再 UTF-16，最后按 UTF-8 忽略坏字节兜底。
_TEXT_ENCODINGS = ("utf-8", "gbk", "utf-16")

# HTML 中要丢弃的内容：<script>/<style> 块，以及所有标签。
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.S | re.I)
_TAG_RE = re.compile(r"<[^>]+>")


def _read_text(path: Path) -> str:
    """读文本文件，自动尝试多种编码，避免 GBK/UTF-16 文件乱码或报错。"""
    raw = path.read_bytes()
    for enc in _TEXT_ENCODINGS:
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return raw.decode("utf-8", errors="ignore")


def _strip_html(text: str) -> str:
    """去掉 HTML 标签与脚本/样式，只留正文。"""
    text = _SCRIPT_STYLE_RE.sub(" ", text)
    text = _TAG_RE.sub(" ", text)
    return text


def _load_text(path: Path, strip_html: bool = False):
    text = _read_text(path)
    if strip_html:
        text = _strip_html(text)

    if not text.strip():
        return []
    return [{"page": None, "text": text}]


def _iter_block_items(doc):
    """按文档真实顺序遍历段落和表格（python-docx 默认把两者分开，会丢失穿插顺序）。"""
    for child in doc.element.body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, doc)
        elif child.tag == qn("w:tbl"):
            yield Table(child, doc)


def _load_docx(path: Path):
    doc = Document(str(path))
    parts = []
    for block in _iter_block_items(doc):
        if isinstance(block, Paragraph):
            parts.append(block.text)
        elif isinstance(block, Table):
            for row in block.rows:
                for cell in row.cells:
                    parts.append(cell.text)

    text = "\n".join(parts)
    if not text.strip():
        return []
    return [{"page": None, "text": text}]


def _load_pdf(path: Path):
    pages = []
    with pdfplumber.open(str(path)) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                pages.append({"page": i, "text": text})
    return pages


def load_file(path: Path):
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".pdf":
        return _load_pdf(p)
    elif suffix == ".docx":
        return _load_docx(p)
    elif suffix == ".html":
        return _load_text(p, strip_html=True)
    elif suffix in (".txt", ".md"):
        return _load_text(p)
    else:
        raise ValueError(f"不支持的类型: {suffix}")
