"""打包脚本：生成单文件 exe 和绿色 zip。

要点：
- 使用 PyInstaller 的 ``--onefile --windowed``；
- 显式声明 ``tkinterdnd2`` 的数据文件（拖拽打开需要其 ``tkdnd`` 运行时），
  否则打包后的 exe 拖拽功能会静默失效；
- 显式声明常用隐藏导入（ttkbootstrap / PIL / pymupdf 的子模块），
  避免动态导入被漏分析；
- 若存在 ``assets/app.ico`` 则一并嵌入，作为窗口与任务栏图标。
"""

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
ICON_PATH = PROJECT_ROOT / "assets" / "app.ico"


def clean() -> None:
    for d in [DIST_DIR, BUILD_DIR]:
        if d.exists():
            shutil.rmtree(d)


def _tkinterdnd2_datas() -> list[tuple[str, str]]:
    """收集 tkinterdnd2 的 tkdnd 运行时目录（拖拽支持）。

    ``pyinstaller-hooks-contrib`` 自带 ``hook-tkinterdnd2``，会按当前平台
    只收集匹配的那一个子目录。若检测到该 hook 已存在则不做重复收集，
    避免重复数据导致打包体积膨胀与警告。
    """
    try:
        from PyInstaller.utils.hooks import get_package_paths  # noqa: F401
    except Exception:
        pass
    try:
        import _pyinstaller_hooks_contrib  # type: ignore

        hooks_dir = Path(_pyinstaller_hooks_contrib.__file__).parent / "stdhooks"
        if (hooks_dir / "hook-tkinterdnd2.py").exists():
            print("[build] 检测到内置 hook-tkinterdnd2，跳过手动收集")
            return []
    except Exception:
        pass

    datas: list[tuple[str, str]] = []
    try:
        import tkinterdnd2
    except Exception:
        return datas
    root = Path(tkinterdnd2.__file__).parent
    tkdnd = root / "tkdnd"
    for platform_dir in ("win-x64", "win-arm64", "win32", "osx-x64", "linux-x64"):
        src = tkdnd / platform_dir
        if src.is_dir():
            datas.append((str(src), f"tkinterdnd2/tkdnd/{platform_dir}"))
    for extra in root.glob("*.tcl"):
        datas.append((str(extra), "tkinterdnd2"))
    return datas


def build_exe() -> Path:
    clean()

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--windowed",
        "--name", "PDF编辑器",
        "--clean",
        "--noconfirm",
        # 隐藏导入：这些包大量使用动态导入，静态分析容易漏
        "--hidden-import", "tkinterdnd2",
        "--hidden-import", "ttkbootstrap",
        "--hidden-import", "pymupdf",
        "--hidden-import", "fitz",
        "--hidden-import", "PIL",
        "--hidden-import", "PIL.Image",
        "--hidden-import", "PIL.ImageTk",
        "--hidden-import", "PIL.ImageDraw",
        "--hidden-import", "PIL.ImageFont",
        "--collect-submodules", "pymupdf",
        # 源目录
        "--paths", str(PROJECT_ROOT / "src"),
    ]

    for src, dst in _tkinterdnd2_datas():
        sep = ";" if sys.platform.startswith("win") else ":"
        cmd += ["--add-data", f"{src}{sep}{dst}"]

    if ICON_PATH.exists():
        cmd += ["--icon", str(ICON_PATH)]

    cmd.append(str(PROJECT_ROOT / "main.py"))

    print("[build] " + " ".join(cmd[:8]) + " …")
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
        readme = PROJECT_ROOT / "README.md"
        if readme.exists():
            zf.write(readme, arcname="README.md")
        manual = PROJECT_ROOT / "docs" / "PDF编辑器操作手册.docx"
        if manual.exists():
            zf.write(manual, arcname="PDF编辑器操作手册.docx")
    return zip_path


def verify(exe_path: Path) -> None:
    """打包后自检：--version 必须可运行且与源码版本一致。"""
    sys.path.insert(0, str(PROJECT_ROOT / "src"))
    import pdf_editor  # noqa: PLC0415
    import re

    r = subprocess.run(
        [str(exe_path), "--version"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=180,
    )
    assert r.returncode == 0, f"exe 启动失败: {r.stderr}"
    print(f"[verify] {r.stdout.strip()}")
    assert "pdf-editor" in r.stdout, f"版本输出异常: {r.stdout}"
    assert pdf_editor.VERSION in r.stdout, (
        f"exe 版本与源码不一致：exe={r.stdout.strip()} 源码={pdf_editor.VERSION}"
    )
    size_mb = exe_path.stat().st_size / 1024 / 1024
    print(f"[verify] 版本一致，体积 {size_mb:.1f} MB")


def main() -> None:
    exe_path = build_exe()
    verify(exe_path)
    zip_path = build_zip(exe_path)
    print(f"生成 exe: {exe_path}")
    print(f"生成 zip: {zip_path}")


if __name__ == "__main__":
    main()