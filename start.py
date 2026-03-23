#!/usr/bin/env python3.12
"""一键启动 AutoMedia 前后端"""
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent
FRONTEND = ROOT / "frontend"


def run(cmd, cwd=None, check=True):
    print(f"  $ {cmd}")
    return subprocess.run(cmd, shell=True, cwd=cwd, check=check)


def setup_frontend():
    print("\n[前端] 安装依赖...")
    run("npm install", cwd=FRONTEND)


def start():
    setup_frontend()

    print("\n[启动] 后端 :8000  前端 :5173\n")

    backend_proc = subprocess.Popen(
        "uv run uvicorn app.main:app --reload",
        shell=True, cwd=ROOT,
    )
    frontend_proc = subprocess.Popen(
        "npm run dev",
        shell=True, cwd=FRONTEND,
    )

    try:
        backend_proc.wait()
        frontend_proc.wait()
    except KeyboardInterrupt:
        print("\n正在关闭...")
        backend_proc.terminate()
        frontend_proc.terminate()


if __name__ == "__main__":
    start()
