# AI 本地资料智能检索 Agent

一个基于 **DeepSeek + BGE 系列模型**的本地资料检索命令行工具，面向个人本地文件（PDF / Word / 文本 / Markdown / HTML）提供：

- **双通道检索**：按文件名定位 + 按内容语义检索
- **两阶段精排**：BGE-M3 向量粗检索 → bge-reranker 交叉编码精排
- **RAG 问答**：基于本地资料生成带来源的答案
- **智能体**：DeepSeek Function Calling 自动调用工具完成多步任务
- **增量索引**：只对新增/修改的文件重新向量化

数据全程保存在本地，无需联网（仅问答/智能体调用 DeepSeek API）。

---

## 系统架构

```
文件系统（F:/ 及配置的搜索目录）
        │
        │  loader 解析 + splitter 切块
        ▼
┌──────────────────────────────────────────────┐
│               indexer（增量同步）                │
│   对比磁盘文件的 mtime/size，只处理有变化的文件      │
└───────┬──────────────────┬───────────────────┘
        │ 写向量/切片        │ 写文件元数据
        ▼                   ▼
┌────────────────┐   ┌─────────────────────────┐
│   ChromaDB      │   │   SQLite（catalog.db）   │
│  向量 + 正文切片  │   │  文件名 / 格式 / 路径 / 时间 │
└───────┬────────┘   └───────────┬─────────────┘
        │                        │
        └───────────┬────────────┘
                    ▼
      ┌───────────────────────────────┐
      │       双通道 + 两阶段检索         │
      │  BGE-M3 粗检索 → bge-reranker 精排 │
      └───────────────┬───────────────┘
                      ▼
      ┌───────────────────────────────┐
      │   RAG 问答 / 智能体（agent）      │
      │          → DeepSeek LLM        │
      └───────────────────────────────┘
```

### 存储分层

| 存储 | 引擎 | 存什么 | 用途 |
|---|---|---|---|
| `db/chroma.sqlite3` | ChromaDB | 正文切片的向量 + 原文 + `source/page/chunk_index` | 语义检索 |
| `db/catalog.db` | SQLite | 文件元数据（路径/名称/格式/大小/修改时间） | 按名字/格式/文件夹定位文件 |
| `db/.index_state.json` | JSON | 每个文件的 `mtime/size/chunk_ids` 账本 | 增量索引（判断哪些文件变了） |

> 三者职责分离：换 embedding 模型只需重建 ChromaDB，文件清单（catalog）和账本不受影响。

---

## 技术栈

- **向量化**：`sentence-transformers` + `BAAI/bge-m3`
- **重排序**：`BAAI/bge-reranker-v2-m3`（CrossEncoder）
- **向量库**：`chromadb`（PersistentClient，本地持久化）
- **元数据库**：SQLite（标准库 `sqlite3`）
- **LLM**：DeepSeek（`deepseek-chat`，经 `openai` SDK 兼容接口调用）
- **文件解析**：`pdfplumber`（PDF）、`python-docx`（Word）、内置文本读取
- **CLI**：标准库 `argparse`，统一输出 JSON

---

## 目录结构

```
project/
├── cli.py                 # 命令行入口（12 个子命令）
├── config.json            # 运行配置（搜索目录、切块、模型、top_k 等）
├── .env.example           # 环境变量样例（复制为 .env 填入真实 Key）
├── requirements.txt       # 依赖清单
├── tools/                 # 核心模块
│   ├── config.py          #   配置读取与合并
│   ├── loader.py          #   文件解析（pdf/docx/txt/md/html）
│   ├── splitter.py        #   文本切块
│   ├── embeddings.py      #   BGE-M3 向量化
│   ├── indexer.py         #   增量索引同步
│   ├── retriever.py       #   检索 + 两阶段精排
│   ├── reranker.py        #   bge-reranker 交叉编码
│   ├── finder.py          #   文件名模糊检索
│   ├── catalog.py         #   元数据库（build/query/stats）
│   ├── qa.py              #   RAG 问答
│   ├── agent.py           #   智能体（Function Calling）
│   └── manage.py          #   库管理（list/remove/stats）
├── tests/                 # pytest 单元测试
├── db/                    # 运行时生成（向量库 + 元数据库 + 账本）
└── data/                  # 本地资料（默认不入库，见 .gitignore）
```

---

## 快速开始

### 1. 环境要求

- Python 3.11+
- 首次使用需联网下载模型（BGE-M3 与 bge-reranker-v2-m3，各约 2GB）

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 准备模型

代码以 `local_files_only=True` 加载模型，因此**需要先把两个模型下载到本地缓存**：

- `BAAI/bge-m3`
- `BAAI/bge-reranker-v2-m3`

国内网络可在 `.env` 里配置 HuggingFace 镜像端点 `HF_ENDPOINT` 后再下载。

### 4. 配置密钥

复制 `.env.example` 为 `.env`，填入真实 Key（仅 `ask` / `agent` 需要）：

```bash
cp .env.example .env
```

```dotenv
DEEPSEEK_API_KEY=sk-xxxx
HF_ENDPOINT=https://hf-mirror.com
```

### 5. 配置搜索目录

编辑 `config.json` 的 `storage.search_dirs`，指向你的资料目录（默认 `F:/`）：

```json
{
  "storage": {
    "search_dirs": ["F:/资料"],
    "extensions": [".pdf", ".docx", ".txt", ".md", ".html"],
    "max_file_size_mb": 50
  }
}
```

### 6. 导入资料并检索

```bash
# 导入某个文件或目录
python cli.py ingest "F:/资料/会议记录"

# 按内容语义检索
python cli.py search "网络安全应急响应流程"

# 基于资料问答（需 DeepSeek Key）
python cli.py ask "上次会议的关键建议有哪些？"
```

---

## 命令用法

统一入口：`python cli.py <命令> [参数...]`，输出格式为带缩进的 JSON。

| 命令 | 参数 | 说明 |
|---|---|---|
| `ingest` | `<路径>` | 导入一个文件或目录，建立/更新索引 |
| `find` | `<关键词>` `[--dir]` | 按文件名模糊匹配（子串 + 容错错别字） |
| `search` | `<问句>` `[--top-k]` `[--dir]` | 按内容语义检索 top-k 片段（自动先同步索引） |
| `ask` | `<问题>` `[--top-k]` | RAG 问答，返回答案 + 来源文件 |
| `read` | `<路径>` | 读取指定文件的完整内容 |
| `catalog` | `[--dir]` | 建立/更新元数据库（文件清单） |
| `cquery` | `[--name] [--ext] [--folder]` | 查询元数据库定位文件 |
| `cstats` | 无 | 元数据库统计（文件总数 + 各格式数量） |
| `list` | 无 | 列出索引中的文件 |
| `remove` | `<文件名>` `--yes` | 从索引/向量库删除该文件（**不删磁盘文件**，需 `--yes` 确认） |
| `stats` | 无 | 索引统计（文件数 / 块数 / 总大小） |
| `agent` | `<问题>` | 智能体：自动调用工具完成多步任务（需 DeepSeek Key） |

> `search` / `ask` 执行前会自动同步索引，无需手动 `ingest`。

### 示例

```bash
python cli.py find 会议纪要                          # 找文件名含"会议纪要"的文件
python cli.py search "输液反应怎么处理" --top-k 5     # 语义检索
python cli.py ask "什么是检索增强生成"                 # 基于资料问答
python cli.py cquery --ext .pdf                     # 列出所有 PDF
python cli.py read "F:/资料/报告.pdf"                # 读文件内容
python cli.py agent "帮我找去年的网络安全会议笔记并总结关键建议"
```

---

## 检索原理

### 双通道检索

| 通道 | 实现 | 适用场景 |
|---|---|---|
| 文件名定位 | `finder.py`（实时遍历）+ `catalog.py`（SQLite） | "有没有叫 xxx 的文件"、"这个文件夹里有哪些 PDF" |
| 内容语义 | `retriever.py`（ChromaDB 向量相似度） | "找出和某个主题相关的片段" |

### 两阶段精排

1. **粗检索**：问句经 BGE-M3 向量化，在 ChromaDB 中召回 `candidate_k=20` 个候选切片。
2. **精排**：候选切片交给 bge-reranker-v2-m3 交叉编码，按相关性重排取 `top_k`。

交叉编码器（CrossEncoder）把「问句 + 候选」成对送入模型，比纯向量相似度更精细，能显著提升排序质量。

### RAG 问答

```
检索（粗检索 + 精排） → 拼接上下文 → DeepSeek 生成 → 返回答案 + 来源
```

### 智能体（agent）

通过 DeepSeek Function Calling 暴露 4 个工具，让模型自主编排多步任务：

| 工具 | 作用 |
|---|---|
| `cquery` | 按名字/格式/文件夹在元数据库定位文件 |
| `read` | 读取指定文件内容 |
| `search` | 按内容语义检索 |
| `ask` | 基于资料 RAG 问答 |

---

## 配置说明（config.json）

| 字段 | 默认 | 说明 |
|---|---|---|
| `storage.search_dirs` | `["F:/"]` | 要索引的目录 |
| `storage.exclude_dirs` | `.venv` `.git` 等 | 扫描时跳过的目录 |
| `storage.extensions` | `.pdf .docx .txt .md .html` | 支持的格式 |
| `storage.max_file_size_mb` | `50` | 跳过超过该大小的文件 |
| `indexing.chunk_size` / `chunk_overlap` | `500` / `50` | 切块大小与重叠 |
| `indexing.embedding_model` | `BAAI/bge-m3` | 向量模型 |
| `retrieval.top_k` | `5` | 默认返回条数 |
| `retrieval.reranker_model` | `BAAI/bge-reranker-v2-m3` | 重排模型 |
| `llm.model` / `llm.base_url` | `deepseek-chat` | DeepSeek 模型与接口地址 |

---

## 注意事项

- **敏感数据不入库**：`.env`（含 API Key）和 `data/`（本地资料）均在 `.gitignore` 中排除，请勿将含个人隐私的原始文件提交到仓库。
- **换模型需重建索引**：更换 `embedding_model` 后必须删除 `db/` 重新索引，代码会检测模型不一致并报错。
- **`remove` 不删磁盘文件**：它只从向量库和索引账本中移除，不会动磁盘上的原始文件。
- **模型加载为本地模式**：代码使用 `local_files_only=True`，需先手动下载模型到 HuggingFace 缓存。

---

## 运行测试

```bash
pytest
```

测试覆盖配置读取、文本切块、文件解析、文件名检索、库管理与空库边界情况。
