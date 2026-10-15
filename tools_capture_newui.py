"""为新版 WPS 风格 UI 截图（PrintWindow）。"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

PROJECT = Path(__file__).parent
sys.path.insert(0, str(PROJECT / "src"))

OUT = PROJECT / "docs" / "images"
WORK = PROJECT / ".capture_work"

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
PW_RENDERFULLCONTENT = 0x00000002


class BMIH(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


def hwnd_of(win) -> int:
    return user32.GetParent(win.winfo_id()) or win.winfo_id()


def capture(win, path: Path) -> bool:
    win.update_idletasks()
    win.update()
    hwnd = hwnd_of(win)
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w, h = rect.right - rect.left, rect.bottom - rect.top
    if w <= 0 or h <= 0:
        return False
    src = user32.GetWindowDC(hwnd)
    mem = gdi32.CreateCompatibleDC(src)
    bmp = gdi32.CreateCompatibleBitmap(src, w, h)
    old = gdi32.SelectObject(mem, bmp)
    for _ in range(3):
        user32.PrintWindow(hwnd, mem, PW_RENDERFULLCONTENT)
    bmi = BMIH()
    bmi.biSize = ctypes.sizeof(BMIH)
    bmi.biWidth, bmi.biHeight = w, -h
    bmi.biPlanes, bmi.biBitCount, bmi.biCompression = 1, 32, 0
    buf = ctypes.create_string_buffer(w * h * 4)
    ok = gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bmi), 0)
    gdi32.SelectObject(mem, old)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(hwnd, src)
    if not ok:
        return False
    img = Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1).convert("RGB")
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    print(f"  saved {path.name} ({img.width}x{img.height})")
    return True


def main():
    import tkinter as tk
    import ttkbootstrap as ttk
    from pdf_editor.ui import PDFEditorApp

    sample = WORK / "samples" / "年度报告.pdf"
    if not sample.exists():
        print("缺少示例文件，请先运行 tools_capture_ui.py")
        return

    root = ttk.Window(themename="flatly")
    app = PDFEditorApp(root)
    root.geometry("1180x780+40+20")
    root.update()
    app.load_document(sample)
    root.update()
    root.after(500, lambda: (capture(root, OUT / "20_new_main_ui.png"), root.quit()))
    root.mainloop()
    print("done")


if __name__ == "__main__":
    main()