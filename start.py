#!/usr/bin/env python3
"""AutoMedia 本地一键启动脚本.

这个脚本面向第一次拉起项目的开发者, 目标是尽量用一条命令完成:
1. 检查 FFmpeg / FFprobe
2. 安装前端依赖
3. 启动后端和前端开发服务
"""
import os
import platform
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

if sys.version_info < (3, 12):
    raise SystemExit("AutoMedia requires Python 3.12 or higher")

ROOT = Path(__file__).parent
FRONTEND = ROOT / "frontend"
COMMON_BINARY_DIRS = (
    Path("/opt/homebrew/bin"),
    Path("/usr/local/bin"),
    Path("/opt/local/bin"),
    Path.home() / ".local/bin",
)
PROJECT_BINARY_ROOT = ROOT / ".ffmpeg-tools" / "node_modules"


def _binary_candidates(binary_name):
    if platform.system().lower() == "windows" and not binary_name.lower().endswith((".exe", ".cmd", ".bat")):
        return (binary_name, f"{binary_name}.exe", f"{binary_name}.cmd", f"{binary_name}.bat")
    return (binary_name,)


def _find_winget_binary(binary_name, env):
    if platform.system().lower() != "windows":
        return None

    local_app_data = env.get("LOCALAPPDATA", "").strip()
    if not local_app_data:
        return None

    packages_dir = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
    if not packages_dir.exists():
        return None

    for candidate_name in _binary_candidates(binary_name):
        matches = sorted(packages_dir.glob(f"**/{candidate_name}"), reverse=True)
        for match in matches:
            if match.is_file():
                return str(match)

    return None


def _format_cmd(cmd):
    if isinstance(cmd, str):
        return cmd
    return shlex.join(cmd)


def run(cmd, cwd=None, check=True, env=None):
    print(f"  $ {_format_cmd(cmd)}")
    return subprocess.run(
        cmd,
        shell=isinstance(cmd, str),
        cwd=cwd,
        check=check,
        env=env,
    )


def build_runtime_env():
    env = os.environ.copy()
    path_entries = [entry for entry in env.get("PATH", "").split(os.pathsep) if entry]
    for directory in COMMON_BINARY_DIRS:
        directory_str = str(directory)
        if directory.exists() and directory_str not in path_entries:
            path_entries.insert(0, directory_str)
    env["PATH"] = os.pathsep.join(path_entries)
    return env


def _find_project_binary(binary_name):
    if not PROJECT_BINARY_ROOT.exists():
        return None

    for candidate_name in _binary_candidates(binary_name):
        direct_candidate = PROJECT_BINARY_ROOT / candidate_name
        if direct_candidate.is_file() and os.access(direct_candidate, os.X_OK):
            return str(direct_candidate)

        for candidate in sorted(PROJECT_BINARY_ROOT.glob(f"**/{candidate_name}")):
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)

    return None


def resolve_binary(binary_name, env):
    def _is_executable_file(path: Path) -> bool:
        return path.is_file() and os.access(path, os.X_OK)

    is_windows = platform.system().lower() == "windows"
    env_name = f"{binary_name.upper()}_PATH"
    configured = env.get(env_name, "").strip()
    if configured:
        candidate = Path(configured).expanduser()
        if _is_executable_file(candidate):
            return str(candidate)
        resolved = shutil.which(configured, path=env.get("PATH"))
        if resolved:
            return resolved
        if candidate.exists():
            raise RuntimeError(f"{env_name} 指向的 {binary_name} 不是可执行文件: {configured}")
        raise RuntimeError(f"{env_name} 指向的 {binary_name} 不存在: {configured}")

    for candidate_name in _binary_candidates(binary_name):
        resolved = shutil.which(candidate_name, path=env.get("PATH"))
        if resolved:
            return resolved

    if is_windows:
        winget_binary = _find_winget_binary(binary_name, env)
        if winget_binary:
            return winget_binary

    for candidate_name in _binary_candidates(binary_name):
        for directory in COMMON_BINARY_DIRS:
            candidate = directory / candidate_name
            if _is_executable_file(candidate):
                return str(candidate)

    project_binary = _find_project_binary(binary_name)
    if project_binary:
        return project_binary

    raise FileNotFoundError(f"未找到 {binary_name} 可执行文件")


def _prepend_binary_dirs(env, *binary_paths):
    path_entries = [entry for entry in env.get("PATH", "").split(os.pathsep) if entry]
    for binary_path in binary_paths:
        binary_dir = os.path.dirname(binary_path)
        if binary_dir and binary_dir not in path_entries:
            path_entries.insert(0, binary_dir)
    env["PATH"] = os.pathsep.join(path_entries)
    return env


def detect_ffmpeg_install_command(env=None):
    runtime_env = env or build_runtime_env()
    runtime_path = runtime_env.get("PATH")
    system = platform.system().lower()
    if system == "windows" and shutil.which("winget", path=runtime_path):
        return [
            "winget",
            "install",
            "--id",
            "Gyan.FFmpeg",
            "--exact",
            "--accept-source-agreements",
            "--accept-package-agreements",
            "--disable-interactivity",
        ], "winget"
    if system == "windows" and shutil.which("choco", path=runtime_path):
        return ["choco", "install", "ffmpeg", "-y"], "Chocolatey"
    if system == "darwin" and shutil.which("brew", path=runtime_path):
        return ["brew", "install", "ffmpeg"], "Homebrew"
    if system == "linux" and shutil.which("apt-get", path=runtime_path):
        return ["sudo", "apt-get", "install", "-y", "ffmpeg"], "apt-get"
    return None, None


def should_auto_install_ffmpeg():
    value = os.environ.get("AUTOMEDIA_AUTO_INSTALL_FFMPEG", "").strip().lower()
    return value in {"1", "true", "yes", "y", "on"}


def prompt_install_ffmpeg(installer_name):
    if not sys.stdin.isatty():
        return False
    answer = input(
        f"\n[依赖] 未检测到 ffmpeg / ffprobe，可使用 {installer_name} 自动安装。现在安装吗？ [Y/n] "
    ).strip().lower()
    return answer in {"", "y", "yes"}


def print_ffmpeg_help():
    print("\n[依赖] 未检测到 FFmpeg，过渡视频、音视频合成和拼接功能将无法使用。")
    print("请先安装 FFmpeg，或通过环境变量指定可执行文件路径：")
    print("  - macOS (Homebrew): brew install ffmpeg")
    print("  - Ubuntu / Debian: sudo apt-get install -y ffmpeg")
    print("  - 自定义路径: FFMPEG_PATH=/abs/path/ffmpeg FFPROBE_PATH=/abs/path/ffprobe")


def ensure_ffmpeg(env):
    """确保当前运行环境可找到 ffmpeg / ffprobe.

    若本机未安装, 会在可行时尝试引导或自动安装, 避免视频链路在运行后期才失败.
    """
    try:
        ffmpeg_path = resolve_binary("ffmpeg", env)
        ffprobe_path = resolve_binary("ffprobe", env)
    except FileNotFoundError:
        install_cmd, installer_name = detect_ffmpeg_install_command(env)
        if install_cmd and (should_auto_install_ffmpeg() or prompt_install_ffmpeg(installer_name)):
            print(f"\n[依赖] 正在通过 {installer_name} 安装 FFmpeg...")
            run(install_cmd, cwd=ROOT, env=env)
            env = build_runtime_env()
            ffmpeg_path = resolve_binary("ffmpeg", env)
            ffprobe_path = resolve_binary("ffprobe", env)
        else:
            print_ffmpeg_help()
            raise SystemExit(1) from None
    except RuntimeError as exc:
        print(f"\n[依赖] {exc}")
        raise SystemExit(1) from exc

    env["FFMPEG_PATH"] = ffmpeg_path
    env["FFPROBE_PATH"] = ffprobe_path
    _prepend_binary_dirs(env, ffmpeg_path, ffprobe_path)
    print(f"\n[依赖] FFmpeg 已就绪: {ffmpeg_path}")
    return env


def setup_frontend(env):
    print("\n[前端] 安装依赖...")
    run("npm install", cwd=FRONTEND, env=env)


def start():
    """启动本地开发环境.

    后端使用 uvicorn 热更新, 前端使用 Vite dev server.
    """
    env = ensure_ffmpeg(build_runtime_env())
    setup_frontend(env)

    print("\n[启动] 后端 :8000  前端 :5173\n")

    backend_proc = subprocess.Popen(
        "uv run uvicorn app.main:app --reload --reload-dir app",
        shell=True, cwd=ROOT, env=env,
    )
    frontend_proc = subprocess.Popen(
        "npm run dev",
        shell=True, cwd=FRONTEND, env=env,
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
