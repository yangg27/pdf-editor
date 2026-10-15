"""打包脚本：生成单文件 exe 和绿色 zip。"""

from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent
DIST_DIR = PROJECT_ROOT / "dist"
BUILD_DIR = PROJECT_ROOT / "build"
EXE_NAME = "PDF编辑器.exe"


def clean():
    for d in [DIST_DIR, BUILD_DIR]:
        if d.exists():
            shutil.rmtree(d)


def build_exe() -> Path:
    clean()
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",
        "--windowed",
        "--name", "PDF编辑器",
        "--clean",
        "--noconfirm",
        str(PROJECT_ROOT / "main.py"),
    ]
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        raise RuntimeError("PyInstaller 打包失败")
    exe_path = DIST_DIR / EXE_NAME
    if not exe_path.exists():
        raise FileNotFoundError(f"找不到生成的 exe: {exe_path}")
    return exe_path


def build_zip(exe_path: Path) -> Path:
    zip_path = DIST_DIR / "pdf-editor-win10.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(exe_path, arcname=exe_path.name)
        # 添加示例与说明
        readme = PROJECT_ROOT / "README.md"
        if readme.exists():
            zf.write(readme, arcname="README.md")
    return zip_path


def main():
    exe_path = build_exe()
    zip_path = build_zip(exe_path)
    print(f"生成 exe: {exe_path}")
    print(f"生成 zip: {zip_path}")


if __name__ == "__main__":
    main()
