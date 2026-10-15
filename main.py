#!/usr/bin/env python3
"""PDF 编辑器入口。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("--version", "-v"):
        print("pdf-editor 0.2.0")
        sys.exit(0)
    from pdf_editor.ui import main
    main()
