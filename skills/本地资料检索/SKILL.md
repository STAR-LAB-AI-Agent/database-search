# 本地资料检索

## 使用场景

当用户想查找本地资料库中的文档时使用，包括：
- 按**文件名**找文件（find）
- 按**内容语义**检索相关片段（search）
- 基于本地资料**提问**（ask，需要 DeepSeek）
- 用**智能体**自动完成多步任务（agent，需要 DeepSeek）
- 管理资料库：导入、列出、删除、统计
- 建立/查询**元数据库**（catalog / cquery / cstats），按名字/格式/文件夹定位文件
- 按需**读取文件内容**（read）
- 在你认为用户给出的问题太过于模糊时，必要时选择向用户提问

## 参数

| 命令 | 参数 | 说明 |
|---|---|---|
| `ingest` | `<路径>` | 导入一个文件或目录到资料库 |
| `find` | `<关键词>` `--dir` | 按文件名模糊匹配（子串 + 容错错别字） |
| `search` | `<问句>` `--top-k` `--dir` | 按内容语义检索，返回 top-k 片段 |
| `ask` | `<问题>` `--top-k` | 基于资料问答（需 DeepSeek Key） |
| `list` | 无 | 列出库中所有文件 |
| `remove` | `<文件名>` `--yes` | 从索引/向量库删除该文件（不删磁盘文件，需 --yes 确认） |
| `stats` | 无 | 统计文件数、块数、大小 |
| `catalog` | `--dir` | 建立/更新元数据库（记录每个文件夹的文件名+格式） |
| `cquery` | `--name` `--ext` `--folder` | 查询元数据库；`--name` 匹配文件名，`--ext` 匹配格式，`--folder` 匹配文件夹 |
| `cstats` | 无 | 元数据库统计（文件总数 + 各格式数量） |
| `read` | `<路径>` | 读取指定文件的内容（支持 pdf/docx/txt/md/html） |
| `agent` | `<问题>` | 智能体：用 DeepSeek 自动调用工具完成多步任务 |

## 调用方式

在项目根目录执行：

```bash
python cli.py <命令> [参数...]
```

- 所有子命令统一输出带缩进的 JSON，`action` 字段标明命令。
- `search` 和 `ask` 执行前会自动同步索引，无需手动 ingest。
- 文件新增/删除后，`search`/`ask` 会自动同步；也可用 `ingest <路径>` 显式刷新；`list`/`stats` 显示的是当前索引。
- `remove` 只从索引/向量库移除，**不删除磁盘上的原始文件**；仍需 `--yes` 确认。
- 找文件建议先用 `cquery`/`find` 定位，再用 `read` 读内容。

## 结果格式

统一输出 JSON（带缩进），`action` 字段标明命令：

```json
{"action": "search", "count": 3, "results": [{"text": "...", "source": "xx.pdf", "page": 3, "score": 0.87}]}
{"action": "find", "count": 2, "results": [{"path": "F:/.../会议纪要.docx", "name": "会议纪要.docx", "size": 10240, "mtime": 123}]}
{"action": "ask", "answer": "……", "sources": ["xx.pdf"]}
{"action": "list", "files": [{"name": "xx.pdf", "path": "F:/.../xx.pdf", "chunks": 12, "size": 100, "mtime": 123}]}
{"action": "stats", "files": 5, "chunks": 320, "size_bytes": 1048576}
{"action": "remove", "name": "xx.pdf", "removed": true, "count": 1}
{"action": "ingest", "added": 3, "updated": 0, "deleted": 0, "skipped": 0}
{"action": "cquery", "count": 2, "results": [{"path": "F:/.../报告.pdf", "name": "报告.pdf", "ext": ".pdf", "folder": "F:/..."}]}
{"action": "cstats", "total": 7, "by_ext": {".docx": 3, ".pdf": 2}}
{"action": "read", "path": "F:/.../报告.pdf", "text": "文件内容..."}
{"action": "agent", "answer": "……"}
```

出错时返回：`{"error": "错误说明"}`。

## 示例

1. 用户：「帮我找关于注意力机制的资料」
   → `python cli.py search "注意力机制" --top-k 5`

2. 用户：「有没有叫会议纪要的文件？」
   → `python cli.py find 会议纪要`

3. 用户：「根据本地资料，什么是检索增强生成？」
   → `python cli.py ask "什么是检索增强生成"`

4. 用户：「资料库里有哪些文件？」
   → `python cli.py list`

5. 用户：「把 旧资料.pdf 删掉」
   → `python cli.py remove 旧资料.pdf --yes`

6. 用户：「这个文件夹里有哪些 PDF？」
   → `python cli.py cquery --ext .pdf`

7. 用户：「帮我看看 报告.pdf 里写了什么」
   → `python cli.py read "F:/.../报告.pdf"`

8. 用户：「资料库有更新，帮我刷新一下」
   → `python cli.py ingest "F:/资料"`

9. 用户：「综合多份资料回答一个需要多步检索的问题」
   → `python cli.py agent "……"`
