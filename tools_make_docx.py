"""把操作手册 HTML 转换为 Word 文档（.docx）。

优先使用本机 Microsoft Word 的 COM 接口（通过 PowerShell 调用），
可最大程度保留原有排版与内嵌图片；若 Word 不可用则给出明确提示。

用法：
    .venv-sys/Scripts/python.exe tools_make_docx.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).parent
HTML = PROJECT / "docs" / "manual.html"
DOCX = PROJECT / "docs" / "PDF编辑器操作手册.docx"


PS_SCRIPT = r"""
param([string]$Html, [string]$Docx)
$ErrorActionPreference = 'Stop'
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try {
    $doc = $word.Documents.Open($Html, $false, $false)
    try { $doc.Fields.Update() | Out-Null } catch {}
    $doc.SaveAs2($Docx, 16)
    $doc.Close(0)
    Write-Output "OK"
} finally {
    try { $word.Quit() } catch {}
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
}
"""


def convert() -> bool:
    if not HTML.exists():
        print(f"找不到 HTML：{HTML}")
        return False

    script = PROJECT / ".convert_manual.ps1"
    script.write_text(PS_SCRIPT, encoding="utf-8-sig")
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive",
             "-ExecutionPolicy", "Bypass", "-File", str(script),
             "-Html", str(HTML), "-Docx", str(DOCX)],
            capture_output=True, text=True, timeout=300,
        )
        out = (r.stdout or "") + (r.stderr or "")
        if "OK" not in out or not DOCX.exists():
            print("转换失败：")
            print(out.strip()[:2000])
            return False
        print(f"生成: {DOCX}  ({DOCX.stat().st_size / 1024:.0f} KB)")
        return True
    finally:
        script.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(0 if convert() else 1)