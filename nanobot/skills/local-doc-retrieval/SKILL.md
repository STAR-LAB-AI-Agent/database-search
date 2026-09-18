---
name: local-doc-retrieval
description: 本地资料库检索。当用户想查找/搜索/检索本地文件或资料（找文件、有没有叫xx的、搜xx相关内容、复习资料、会议纪要、笔记、资料库有哪些文件等）时，必须使用本技能调用项目 cli.py 的 find/search/cquery/read/list 等命令来检索，而不是用 nanobot 自带的 find/grep/ls（那些只搜 nanobot 工作区，搜不到用户本地资料）。
always: true
---

# 本地资料检索（local-doc-retrieval）

把本机 PDF / Word / TXT / Markdown / HTML 建成可检索的资料库，通过命令行完成：
按文件名定位、按内容语义检索、资料库管理。数据全程本地，检索不联网。

> ⚠️ **最重要的一条**：当用户要查找、搜索、检索本地文件或资料时，**必须调用下面 `cli.py` 的命令**，**不要用 nanobot 自带的 `find` / `grep` / `ls`**——那些工具只搜索 nanobot 自己的工作区，搜不到用户的本地资料。用户的资料在 `cli.py` 配置的 `search_dirs` 里。

## 命令前缀（重要）

本项目 CLI 入口在 `{{PROJECT_DIR}}/cli.py`，用 Python 解释器 `{{PYTHON}}` 运行。
（`{{PROJECT_DIR}}` 与 `{{PYTHON}}` 由 `nanobot/setup.py` 安装时替换为实际绝对路径。）

所有命令统一形式（在任意目录下均可执行，CLI 会自己定位 config.json 与 db/）：

```
{{PYTHON}} {{PROJECT_DIR}}/cli.py <命令> [参数...] --json
```

- 加 `--json` 返回原始 JSON（便于解析）；不加则返回人类可读文本。
- 路径中的反斜杠或正斜杠均可；参数含空格时用双引号包起来。

## 命令一览

| 命令 | 参数 | 用途 |
|---|---|---|
| `search` | `<问句> [--top-k N] [--dir D]` | 按内容语义检索 top-k 片段（执行前自动同步索引） |
| `find` | `<关键词> [--dir D]` | 按文件名/所在文件夹模糊匹配定位文件 |
| `read` | `<路径>` | 读取指定文件的完整内容（支持 pdf/docx/txt/md/html） |
| `list` | 无 | 列出资料库中所有文件 |
| `stats` | 无 | 资料库统计（文件数/片段数/总大小） |
| `ingest` | `<路径>` | 导入文件或目录，建立/更新索引 |
| `sync` | 无 | 扫描搜索目录，同步新增/修改/删除的文件 |
| `catalog` | `[--dir D]` | 建立/更新元数据库（文件清单） |
| `cquery` | `[--name] [--ext] [--folder]` | 查询元数据库定位文件 |
| `cstats` | 无 | 元数据库统计（文件总数 + 各格式数量） |
| `remove` | `<文件名> --yes` | 从索引/向量库删除该文件（需 `--yes`，不删磁盘文件） |

## 何时用哪个命令（意图路由）

- 「找某个文件 / 有没有叫 xx 的文件」→ 先用 `find <关键词>` 或 `cquery --name <关键词>` 定位，再用 `read <路径>` 读内容。
- 「找和某主题相关的内容」→ `search "<问句>" --top-k N`。
- 「根据本地资料回答某个问题」→ 先 `search "<问题>"` 拿 top-k 片段，再**只依据这些片段**组织答案并注明来源（见下节）。
- 「看看库里有什么 / 统计一下」→ `list` / `stats`。
- 「导入新资料 / 刷新资料库」→ `ingest <路径>` / `sync`。
- 「删除某个文件」→ `remove <文件名> --yes`（**执行前必须向用户确认**）。

## 基于资料回答（RAG）

本项目 CLI 不内置 LLM，问答由你完成，步骤：

1. 调用 `search "<用户问题>" --top-k 5 --json` 检索相关片段。
2. 只根据返回的 `results`（`text` + `source` + `page`）组织答案。
3. 答案要注明来源文件名（`source`）和页码（`page`）。
4. 片段不足以回答时，直说「资料里没有相关信息」，不要编造。
5. 检索不到时，可把 `--top-k` 调大（如 10）再试一次。

## 结果格式（--json）

统一返回带缩进的 JSON，`action` 字段标明命令：

- `search` → `{"action":"search","count":N,"results":[{"text","source","page","score"}]}`
- `find` → `{"action":"find","count":N,"results":[{"path","name","size","mtime"}]}`
- `read` → `{"action":"read","path","text"}`
- `list` → `{"action":"list","files":[{"name","path","chunks","size","mtime"}]}`
- `stats` → `{"action":"stats","files","chunks","size_bytes"}`
- `cquery` → `{"action":"cquery","count":N,"results":[{"path","name","ext","folder"}]}`
- 出错 → `{"error":"..."}`

把 JSON 结果转述给用户时，给出「片段内容 + 来源文件 + 页码 + 相关度」，不要附上整篇原文。

## 安全与注意事项

- `remove` 必须带 `--yes` 才执行；执行前必须向用户确认（不可逆）。
- 不要读取或导入 `search_dirs` 白名单之外的路径（见项目 `config.json`）。
- 返回结果已是精简结构化数据，避免把整篇文档塞进上下文。
- `search` 依赖本地向量模型（BGE-M3 等），首次运行前需预下载模型到 HuggingFace 缓存。

## 示例

1. 用户：「帮我找关于注意力机制的资料」
   → `{{PYTHON}} {{PROJECT_DIR}}/cli.py search "注意力机制" --top-k 5 --json`

2. 用户：「有没有叫会议纪要的文件？」
   → `{{PYTHON}} {{PROJECT_DIR}}/cli.py find 会议纪要 --json`

3. 用户：「根据本地资料，什么是检索增强生成？」
   → 先 `{{PYTHON}} {{PROJECT_DIR}}/cli.py search "检索增强生成" --top-k 5 --json`，再依据片段作答并注明来源

4. 用户：「资料库里有哪些文件？」
   → `{{PYTHON}} {{PROJECT_DIR}}/cli.py list --json`

5. 用户：「把 旧资料.pdf 删掉」
   → 先确认，再 `{{PYTHON}} {{PROJECT_DIR}}/cli.py remove 旧资料.pdf --yes --json`
