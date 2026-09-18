"""一键把「AI 本地资料检索」项目接入 nanobot（HKUDS 个人 AI 助手）。

任务书集成模式：nanobot + SKILL.md + Python Script/CLI
  - nanobot 作为「统一交互入口 + Skill 编排层」，负责理解用户意图；
  - SKILL.md（本目录 skills/local-doc-retrieval/）告诉 nanobot 何时、如何调用 CLI；
  - cli.py 承担所有确定性处理（检索/解析/入库），可独立运行与测试。

用法（在项目根目录执行）：
    python nanobot/setup.py

它做三件事：
  1. 用 pip 把 nanobot-ai 安装到 nanobot/.venv（独立虚拟环境，避免污染项目依赖）。
  2. 生成 ~/.nanobot/config.json，把 DeepSeek 配成默认模型（OpenAI 兼容接口）。
  3. 把 nanobot/skills/local-doc-retrieval 安装到 ~/.nanobot/workspace/skills/，
     并把 SKILL.md 里的 {{PROJECT_DIR}} / {{PYTHON}} 替换为实际绝对路径。

可选参数：
    --python PATH    运行 cli.py 的 Python（默认优先用项目 .venv/Scripts/python.exe）
    --no-install     跳过安装 nanobot（只做配置 + 装 Skill）
    --api-key KEY    直接指定 DeepSeek API Key（默认从项目 .env 或环境变量读取）
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
NANOBOT_DIR = Path(__file__).resolve().parent
SKILL_SRC = NANOBOT_DIR / "skills" / "local-doc-retrieval"
SKILL_NAME = "local-doc-retrieval"

DEEPSEEK_BASE = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-v4-pro"
# 国内默认用清华 PyPI 镜像，网络好的可传 --index-url https://pypi.org/simple 覆盖
DEFAULT_INDEX_URL = "https://pypi.tuna.tsinghua.edu.cn/simple"


def _project_python(override: str | None) -> str:
    """确定运行 cli.py 的 Python 解释器。"""
    if override:
        return override
    for cand in (
        PROJECT_DIR / ".venv" / "Scripts" / "python.exe",  # Windows
        PROJECT_DIR / ".venv" / "bin" / "python",          # Linux/macOS
    ):
        if cand.exists():
            return str(cand)
    return sys.executable


def _read_deepseek_key(api_key_arg: str | None) -> str:
    """从命令行参数、环境变量、项目 .env 依次读取 DeepSeek Key。"""
    if api_key_arg:
        return api_key_arg
    env_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if env_key:
        return env_key
    env_file = PROJECT_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("DEEPSEEK_API_KEY") and "=" in line:
                value = line.split("=", 1)[1].strip().strip('"').strip("'")
                if value and value != "sk-xxxx":
                    return value
    return ""


def _install_nanobot(index_url: str) -> tuple[str, Path]:
    """把 nanobot-ai 装到独立虚拟环境 nanobot/.venv，返回 (venv_python, nanobot_bin)。"""
    venv_dir = NANOBOT_DIR / ".venv"
    print(f"[1/3] 创建独立虚拟环境：{venv_dir}")
    if not (venv_dir / "Scripts" / "python.exe").exists() and not (venv_dir / "bin" / "python").exists():
        venv.EnvBuilder(with_pip=True).create(str(venv_dir))
    if os.name == "nt":
        py = str(venv_dir / "Scripts" / "python.exe")
        nanobot_bin = venv_dir / "Scripts" / "nanobot.exe"
    else:
        py = str(venv_dir / "bin" / "python")
        nanobot_bin = venv_dir / "bin" / "nanobot"

    cmd = [py, "-m", "pip", "install", "--upgrade"]
    if index_url:
        cmd += ["-i", index_url]
    cmd += ["nanobot-ai"]
    print("[1/3] 安装 nanobot-ai（可能需要几分钟，取决于网络）")
    subprocess.check_call(cmd)
    print(f"[1/3] 完成。nanobot 可执行文件：{nanobot_bin}")
    return py, nanobot_bin


def _write_config(api_key: str) -> Path:
    """生成 ~/.nanobot/config.json（DeepSeek）。"""
    home = Path.home()
    nanobot_home = home / ".nanobot"
    nanobot_home.mkdir(parents=True, exist_ok=True)
    config_path = nanobot_home / "config.json"

    key_field = api_key if api_key else "${DEEPSEEK_API_KEY}"
    config = {
        "providers": {
            "deepseek": {
                "apiKey": key_field,
                "apiBase": DEEPSEEK_BASE,
            }
        },
        "agents": {
            "defaults": {
                "model": DEEPSEEK_MODEL,
                "provider": "deepseek",
            }
        },
    }

    # 已有配置则不覆盖，避免冲掉用户手改的内容。
    if config_path.exists():
        print(f"[2/3] 已存在 {config_path}，跳过写入（如需 DeepSeek 请手动确认 providers 配置）。")
        return config_path

    config_path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[2/3] 已写入 {config_path}（模型 {DEEPSEEK_MODEL}）")
    if not api_key:
        print("      注意：未找到 DEEPSEEK_API_KEY，配置里用了 ${DEEPSEEK_API_KEY} 占位，")
        print("      请先 export DEEPSEEK_API_KEY=sk-xxx 再启动 nanobot，或重新运行 setup 传 --api-key。")
    return config_path


def _install_skill(python: str) -> Path:
    """把 Skill 装到 ~/.nanobot/workspace/skills/，并替换占位符。"""
    home = Path.home()
    dst = home / ".nanobot" / "workspace" / "skills" / SKILL_NAME
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True, exist_ok=True)

    src_skill = SKILL_SRC / "SKILL.md"
    text = src_skill.read_text(encoding="utf-8")
    text = text.replace("{{PROJECT_DIR}}", str(PROJECT_DIR).replace("\\", "/"))
    text = text.replace("{{PYTHON}}", python.replace("\\", "/"))

    (dst / "SKILL.md").write_text(text, encoding="utf-8")
    print(f"[3/3] 已安装 Skill：{dst / 'SKILL.md'}")
    return dst


def main() -> int:
    parser = argparse.ArgumentParser(description="接入 nanobot（nanobot + SKILL.md + CLI）")
    parser.add_argument("--python", help="运行 cli.py 的 Python 解释器路径")
    parser.add_argument("--no-install", action="store_true", help="跳过安装 nanobot")
    parser.add_argument("--api-key", help="DeepSeek API Key")
    parser.add_argument("--index-url", default=DEFAULT_INDEX_URL, help="pip 安装源（默认清华镜像）")
    args = parser.parse_args()

    cli_python = _project_python(args.python)
    api_key = _read_deepseek_key(args.api_key)

    print(f"项目目录：{PROJECT_DIR}")
    print(f"CLI 解释器：{cli_python}")

    if not args.no_install:
        _nanobot_py, nanobot_bin = _install_nanobot(args.index_url)
    else:
        nanobot_bin = "nanobot"  # 假设已在 PATH 里

    _write_config(api_key)
    _install_skill(cli_python)

    print("\n接入完成。接下来：")
    print(f"  1. 启动对话（交互式）：{nanobot_bin} agent")
    print(f"  2. 单轮提问：{nanobot_bin} agent -m \"帮我找关于注意力机制的资料\"")
    print(f"  3. 启动 WebUI：{nanobot_bin} webui")
    print("\n首次运行前请确认：")
    print("  - DEEPSEEK_API_KEY 已配置（config.json 或环境变量）；")
    print("  - 本地向量模型已预下载（BAAI/bge-m3 与 bge-reranker-v2-m3）；")
    print("  - 资料已入库（python cli.py ingest <目录>）或 search 会自动同步索引。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
