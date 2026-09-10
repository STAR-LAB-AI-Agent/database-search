"""测试用例：覆盖正常输入、边界情况和异常情况。

运行方式：在项目根目录执行 `pytest` 或 `python -m pytest`。
"""

import pytest

from tools.config import load_config, get_top_k, get_embedding_model
from tools.splitter import split_text, split_pages
from tools.loader import _load_text, load_file
from tools.finder import find
from tools.manage import remove_file, stats
from tools.retriever import search
from tools.indexer import _get_collection, sync_index


# ============ 配置（正常） ============

def test_load_config():
    """读配置，关键字段应存在。"""
    cfg = load_config()
    assert cfg["storage"]["db_path"] == "db"
    assert cfg["indexing"]["chunk_size"] > 0
    assert cfg["retrieval"]["top_k"] > 0


def test_get_top_k():
    """返回的 top_k 应是正整数。"""
    assert get_top_k() > 0


def test_get_embedding_model():
    """embedding 模型名应为非空字符串。"""
    assert isinstance(get_embedding_model(), str)
    assert get_embedding_model() != ""


# ============ 切块（正常 / 边界） ============

def test_split_text_normal():
    """正常切块：应切成多块，第一块内容正确。"""
    chunks = split_text("1234567890", chunk_size=5, chunk_overlap=2)
    assert len(chunks) > 1
    assert chunks[0]["text"] == "12345"


def test_split_text_empty():
    """边界：空文本返回空列表。"""
    assert split_text("") == []


def test_split_text_short():
    """边界：短文本（比块还短）返回单块。"""
    chunks = split_text("hello", chunk_size=100)
    assert len(chunks) == 1
    assert chunks[0]["text"] == "hello"


def test_split_pages_keeps_page():
    """切分多页时，页码应保留。"""
    pages = [{"page": 1, "text": "1234567890"}, {"page": 2, "text": "abcdefghij"}]
    chunks = split_pages(pages, chunk_size=5, chunk_overlap=2)
    assert chunks[0]["page"] == 1
    assert any(c["page"] == 2 for c in chunks)


# ============ 加载（正常 / 异常） ============

def test_load_text(tmp_path):
    """正常：读 txt 文件，page 应为 None。"""
    f = tmp_path / "测试.txt"
    f.write_text("你好世界", encoding="utf-8")
    pages = _load_text(f)
    assert pages[0]["text"] == "你好世界"
    assert pages[0]["page"] is None


def test_load_file_unsupported():
    """异常：不支持的后缀应抛 ValueError。"""
    with pytest.raises(ValueError):
        load_file("something.exe")


# ============ 文件名检索（正常 / 边界） ============

def test_find_substring(tmp_path):
    """正常：文件名包含关键词应命中。"""
    (tmp_path / "2024会议纪要.txt").write_text("x", encoding="utf-8")
    results = find("会议", [tmp_path])
    assert any("会议纪要" in r["name"] for r in results)


def test_find_no_match(tmp_path):
    """边界：无匹配返回空列表。"""
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    assert find("不存在的关键词", [tmp_path]) == []


# ============ 管理（安全 / 边界） ============

def test_remove_without_confirm(tmp_path):
    """安全：删除未加 --yes 应拒绝。"""
    result = remove_file(tmp_path, None, "x", confirm=False)
    assert result["removed"] is False


def test_stats_empty(tmp_path):
    """边界：空库统计应为 0。"""
    result = stats(str(tmp_path / "db"))
    assert result["files"] == 0
    assert result["chunks"] == 0


# ============ 检索 / 索引（空库，不触发模型下载） ============

def test_search_empty_collection(tmp_path):
    """边界：空库检索返回空列表，不报错。"""
    col = _get_collection(str(tmp_path / "db"))
    assert search("任意问题", col) == []


def test_sync_index_empty_dir(tmp_path):
    """边界：空目录同步，不新增不删除。"""
    result = sync_index([tmp_path], str(tmp_path / "db"))
    assert result["added"] == 0
    assert result["deleted"] == 0
