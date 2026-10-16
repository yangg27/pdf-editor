#!/usr/bin/env python3
"""PDF 编辑器入口。

用法：
    PDF编辑器.exe                  # 启动图形界面（源码运行：python main.py）
    PDF编辑器.exe --version        # 打印版本
    PDF编辑器.exe --help           # 打印帮助
    PDF编辑器.exe <file.pdf>       # 直接打开指定文件
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

VERSION = "0.3.0"


def _out(text: str) -> None:
    """把 CLI 文本以 UTF-8 写到标准输出。

    打包为 windowed exe 后，``sys.stdout`` 默认按系统 ANSI 代码页
    （简体中文 Windows 为 GBK）编码，中文帮助信息在控制台会变成乱码。
    这里直接写 UTF-8 字节，保证跨控制台一致可读。
    """
    data = (text if text.endswith("\n") else text + "\n").encode("utf-8")
    buf = getattr(sys.stdout, "buffer", None)
    if buf is not None:
        try:
            buf.write(data)
            buf.flush()
            return
        except Exception:
            pass
    try:
        sys.stdout.write(data.decode("utf-8", "replace"))
    except Exception:
        pass


def _cli() -> int:
    args = [a for a in sys.argv[1:]]
    if any(a in ("--version", "-v", "-V") for a in args):
        _out(f"pdf-editor {VERSION}")
        return 0
    if any(a in ("--help", "-h") for a in args):
        _out(__doc__)
        return 0
    return -1


if __name__ == "__main__":
    code = _cli()
    if code >= 0:
        sys.exit(code)
    files = [a for a in sys.argv[1:] if not a.startswith("-")]
    # 延迟导入：--version 等纯 CLI 场景无需加载 GUI 依赖，启动更快
    from pdf_editor.ui import main

    main(files[0] if files else None)