from pathlib import Path
from docx import Document
import pdfplumber

def _load_text(path:Path):
    try:
        text=path.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        text=path.read_text(encoding='gbk')

    if not text.strip():
        return []
    return [{"page":None,"text":text}]

def _load_docx(path:Path):
    doc = Document(str(path))
    parts = []
    for p in doc.paragraphs:
        parts.append(p.text)

    # 读取表格里的文字（很多表单类文档内容在表格里，段落读不到）
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                parts.append(cell.text)

    text = '\n'.join(parts)

    if not text.strip():
        return []
    return [{"page":None,"text":text}]

def _load_pdf(path:Path):
    pages=[]
    with pdfplumber.open(str(path)) as pdf:
        for i,page in enumerate(pdf.pages,start=1):
            text=page.extract_text() or ""
            if text.strip():
                pages.append({"page":i,"text":text})

    return pages

def load_file(path:Path):
    p=Path(path)
    suffix=p.suffix.lower()
    if suffix==".pdf":
        return _load_pdf(p)
    elif suffix in (".txt",".md",".html"):
        return _load_text(p)
    elif suffix=='.docx':
        return _load_docx(p)
    else:
        raise ValueError(f"不支持的类型: {suffix}")

