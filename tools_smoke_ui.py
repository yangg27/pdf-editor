"""界面冒烟测试：构建真实 UI、加载文档、执行各类操作并抓图验证。

该脚本在没有用户交互的情况下驱动 UI（通过直接调用命令方法），
用于在打包前确认界面能正常构建、渲染、编辑且不抛异常。

用法：
    .venv-sys/Scripts/python.exe tools_smoke_ui.py
"""

from __future__ import annotations

import sys
import tempfile
import traceback
from pathlib import Path

import pymupdf as fitz

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pdf_editor import pdf_engine as E  # noqa: E402


def make_pdf(path: Path, pages: int = 6, with_image: bool = False) -> Path:
    doc = fitz.open()
    for i in range(pages):
        pg = doc.new_page(width=595, height=842)
        pg.insert_text((72, 90), f"第 {i + 1} 页 / {pages}", fontname="china-s", fontsize=20)
        pg.insert_text((72, 130), "PDF Editor smoke test - hello world",
                       fontname="china-s", fontsize=11)
        for j in range(12):
            pg.insert_text((72, 180 + j * 22), f"这是一行示例正文内容 {j + 1}。",
                           fontname="china-s", fontsize=10)
        pg.draw_rect(fitz.Rect(72, 460, 523, 620), color=(0.2, 0.4, 0.8), width=1)
        if with_image and i == 0:
            from PIL import Image
            import io as _io
            buf = _io.BytesIO()
            Image.new("RGB", (120, 120), (200, 60, 60)).save(buf, "PNG")
            pg.insert_image(fitz.Rect(80, 480, 200, 600), stream=buf.getvalue())
    doc.save(path)
    doc.close()
    return path


def pump(root, seconds: float = 0.5) -> None:
    """真实地跑一会儿事件循环，让 after() 延迟任务（缩略图、渲染）有机会执行。"""
    import time

    end = time.time() + seconds
    while time.time() < end:
        root.update()
        root.update_idletasks()
        time.sleep(0.01)


def wait_idle(root, app, limit: float = 25.0) -> None:
    """等待后台任务完成，并继续泵事件循环。"""
    import time

    end = time.time() + limit
    while time.time() < end:
        root.update()
        if not app._tasks.busy:
            break
        time.sleep(0.02)
    pump(root, 0.2)


def snapshot(app, path: Path) -> None:
    """用 Win32 PrintWindow 抓取真实窗口（无交互桌面环境下同样有效）。"""
    try:
        img = grab_window(app.root)
        if img is not None:
            img.save(path)
            print(f"   截图已保存: {path.name} {img.size}")
    except Exception as exc:
        print(f"   （截图跳过：{exc}）")


def grab_window(win) -> "object | None":
    """抓取 tkinter 顶层窗口像素（Windows PrintWindow）。"""
    import ctypes
    from ctypes import wintypes

    import tkinter as tk

    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    win.update()
    win.update_idletasks()
    hwnd = user32.GetParent(win.winfo_id()) or win.winfo_id()
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w, h = rect.right - rect.left, rect.bottom - rect.top
    if w <= 1 or h <= 1:
        return None
    src = user32.GetWindowDC(hwnd)
    mem = gdi32.CreateCompatibleDC(src)
    bmp = gdi32.CreateCompatibleBitmap(src, w, h)
    gdi32.SelectObject(mem, bmp)
    PW_RENDERFULLCONTENT = 0x2
    ok = user32.PrintWindow(hwnd, mem, PW_RENDERFULLCONTENT)
    buffer = ctypes.create_string_buffer(w * h * 4)

    class BMIH(ctypes.Structure):
        _fields_ = [
            ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
            ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
            ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
            ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
            ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
            ("biClrImportant", wintypes.DWORD),
        ]

    bi = BMIH()
    bi.biSize = ctypes.sizeof(BMIH)
    bi.biWidth = w
    bi.biHeight = -h
    bi.biPlanes = 1
    bi.biBitCount = 32
    bi.biCompression = 0
    gdi32.GetDIBits(mem, bmp, 0, h, buffer, ctypes.byref(bi), 0)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(hwnd, src)
    if not ok:
        return None
    from PIL import Image

    return Image.frombuffer("RGBA", (w, h), buffer, "raw", "BGRA", 0, 1).convert("RGB")


def patch_dialogs() -> None:
    """把模态对话框替换为非交互桩，使测试可以完全无人值守地跑完。

    同时记录被调用的对话框，便于确认代码走到了预期的分支。
    """
    from tkinter import filedialog, messagebox, simpledialog

    calls: list[tuple[str, str]] = []

    messagebox.showinfo = lambda t="", m="", **k: calls.append(("info", f"{t}:{m}"))
    messagebox.showwarning = lambda t="", m="", **k: calls.append(("warn", f"{t}:{m}"))
    messagebox.showerror = lambda t="", m="", **k: calls.append(("error", f"{t}:{m}"))
    messagebox.askyesno = lambda t="", m="", **k: (calls.append(("askyesno", f"{t}:{m}")), True)[1]
    messagebox.askyesnocancel = lambda t="", m="", **k: (calls.append(("askync", f"{t}:{m}")), False)[1]
    simpledialog.askstring = lambda *a, **k: None
    filedialog.askopenfilename = lambda *a, **k: ""
    filedialog.askopenfilenames = lambda *a, **k: ()
    filedialog.asksaveasfilename = lambda *a, **k: ""
    filedialog.askdirectory = lambda *a, **k: ""

    globals()["DIALOG_CALLS"] = calls


def main() -> int:
    patch_dialogs()
    tmp = Path(tempfile.mkdtemp(prefix="pdf-ui-"))
    outdir = PROJECT_ROOT / "docs" / "images"
    outdir.mkdir(parents=True, exist_ok=True)
    src = make_pdf(tmp / "sample.pdf", 6)
    other = make_pdf(tmp / "other.pdf", 3, with_image=True)

    from pdf_editor.ui import PDFEditorApp, _make_root  # noqa: E402

    root = _make_root()
    app = PDFEditorApp(root)
    root.update()

    failures: list[str] = []

    def step(name: str, fn) -> None:
        try:
            fn()
            pump(root, 0.35)
            print(f"[OK] {name}")
        except Exception as exc:
            failures.append(f"{name}: {exc}")
            print(f"[FAIL] {name}: {exc}")
            traceback.print_exc()

    step("构建界面", lambda: None)

    # 直接加载（跳过文件对话框）
    step("打开文档", lambda: app.open_path(src))
    wait_idle(root, app)
    n_thumb = len(app._thumb_widgets)
    print(f"   页数={app._page_count} 尺寸={app._dims[:2]} 缩略图控件={n_thumb}")
    if n_thumb == 0:
        failures.append("打开文档后缩略图面板为空")
    snapshot(app, outdir / "_smoke_01_open.png")

    step("翻页", lambda: app.goto_page(3))
    snapshot(app, outdir / "_smoke_02_page3.png")
    step("缩放到 1.5x", lambda: (setattr(app, "_zoom_mode", "custom"), app.zoom_step(1.5)))
    snapshot(app, outdir / "_smoke_03_zoom.png")
    step("适应宽度", app.fit_width)

    step("旋转当前页", lambda: app.rotate(90))
    step("撤销", app.undo)
    step("重做", app.redo)
    step("插入空白页", lambda: app._mutate(
        lambda d: E.insert_blank_document_page(d, at=1, size="a4"), "插入空白页"))
    step("复制当前页", app.duplicate_page)
    step("移动页 1->4", lambda: (app.goto_page(1), app.move_abs(4)))
    step("全选页面", app.select_all)
    step("清除选择", app.clear_selection)
    step("提取页（静默）", lambda: app._mutate(
        lambda d: None, "noop"))
    step("统一 A4", lambda: app.set_size("a4"))
    step("文字水印", lambda: app._mutate(
        lambda d: E.text_watermark_document(d, "机密 - 三一重工", angle=45, opacity=0.3),
        "文字水印"))
    snapshot(app, outdir / "_smoke_04_watermark.png")
    step("页码", lambda: app._mutate(
        lambda d: E.page_numbers_document(d, pattern="第 {page} 页 / 共 {total} 页"),
        "页码"))
    step("页眉页脚", lambda: app._mutate(
        lambda d: E.header_footer_document(d, header="{name}", footer="第 {page} 页"),
        "页眉页脚"))
    step("高亮批注", lambda: app._apply_annot("highlight", (72, 170, 400, 200)))
    step("矩形批注", lambda: app._apply_annot("rect", (72, 300, 300, 360)))
    step("椭圆批注", lambda: app._apply_annot("circle", (330, 300, 500, 360)))
    step("图章批注", lambda: app._mutate(
        lambda d: E.add_annotation(d, app.current_page, "stamp",
                                   (360, 640, 500, 760), stamp="Approved"), "图章"))
    step("手绘批注", lambda: app._mutate(
        lambda d: E.add_annotation(d, app.current_page, "ink", (0, 0, 0, 0),
                                   points=[[(100, 400), (160, 430), (220, 410)]]), "手绘"))
    snapshot(app, outdir / "_smoke_05_annot.png")

    step("刷新批注列表", app.refresh_annotations)
    n_ann = len(app.annots.get_children())
    print(f"   批注行数={n_ann}")
    if n_ann != 5:
        failures.append(f"批注列表应有 5 行，实际 {n_ann} 行")
    step("批注列表跳转", lambda: (app.annots.selection_set(app.annots.get_children()[0]),
                              app._annot_goto(None)))
    step("删除所选批注", app.delete_annotation_selected)
    step("刷新批注列表", app.refresh_annotations)
    n_ann = len(app.annots.get_children())
    print(f"   删除后批注行数={n_ann}（应为 4）")
    if n_ann != 4:
        failures.append(f"删除批注后应有 4 行，实际 {n_ann} 行")

    step("清除本页批注", lambda: app.clear_page_annots())
    step("刷新批注列表", app.refresh_annotations)
    print(f"   清除本页后批注行数={len(app.annots.get_children())}")
    step("添加书签", lambda: app._mutate(
        lambda d: E.add_bookmark(d, "第一章", 1), "书签"))
    step("刷新目录", app.refresh_catalog)
    n_cat = len(app.catalog.get_children())
    print(f"   目录行数={n_cat}")
    if n_cat != 1:
        failures.append(f"书签目录应有 1 行，实际 {n_cat} 行")

    step("新增第二个书签", lambda: app._mutate(
        lambda d: E.add_bookmark(d, "第二章", 3), "书签2"))
    step("刷新目录", app.refresh_catalog)
    n_cat = len(app.catalog.get_children())
    print(f"   目录行数={n_cat}")
    if n_cat != 2:
        failures.append(f"书签目录应有 2 行，实际 {n_cat} 行")

    step("删除第一个书签", lambda: app._mutate(
        lambda d: E.delete_bookmark(d, 0), "删除书签"))
    step("刷新目录", app.refresh_catalog)
    n_cat = len(app.catalog.get_children())
    print(f"   目录行数={n_cat}（应为 1）")
    if n_cat != 1:
        failures.append(f"删除书签后应有 1 行，实际 {n_cat} 行")

    step("双击目录跳转", lambda: (app.catalog.selection_set(app.catalog.get_children()[0]),
                              app._catalog_goto(None)))
    print(f"   跳转后页码={app.current_page}")
    step("面板切换", lambda: (app.show_catalog_tab(), app._panel_nb.select(2)))
    snapshot(app, outdir / "_smoke_06_panels.png")

    step("查找框", lambda: (app.toggle_find_bar(True), app.find_var.set("hello"),
                          app.find_next()))
    print(f"   查找命中页={[h.page for h in app._find_hits]}")
    snapshot(app, outdir / "_smoke_07_find.png")
    step("查找上一个", app.find_prev)
    step("关闭查找", lambda: app.toggle_find_bar(False))

    step("缩略图滚动", lambda: (app.thumb_canvas.yview_moveto(0.5),
                             app._sync_thumbs()))
    pump(root, 0.4)
    print(f"   已创建缩略图控件={len(app._thumb_widgets)}")

    step("插入另一个 PDF", lambda: app._mutate(
        lambda d: (lambda s: (E.insert_document(d, s.doc, at=2), s.close()))(
            E.DocumentSession(other)), "插入 PDF"))
    step("删除当前页", lambda: (app.goto_page(2), app._mutate(
        lambda d: E.delete_document_pages(d, [2]), "删除页")))
    step("重排", lambda: app._mutate(
        lambda d: E.reorder_document(d, list(range(app._page_count, 0, -1))), "重排"))

    step("文档属性", lambda: app._mutate(
        lambda d: E.set_document_metadata(d, {"title": "测试文档", "author": "三一"}),
        "属性"))
    step("关闭文档", app.close_document)
    snapshot(app, outdir / "_smoke_08_closed.png")

    step("再次打开", lambda: app.open_path(src))
    wait_idle(root, app)

    step("保存到新文件", lambda: app.session.save(tmp / "out.pdf"))
    pump(root, 0.2)
    print(f"   输出文件存在={ (tmp / 'out.pdf').exists() }")

    # 无对话框环境下的事件循环压力测试
    step("连续翻页", lambda: [app.goto_page(p) for p in (1, 4, 2, 6, 3)])
    step("反复缩放", lambda: [app.zoom_step(1.15), app.zoom_step(1 / 1.15),
                            app.fit_page(), app.fit_width()])

    # 内存与缓存指标
    try:
        print(f"   预览缓存={len(app._preview_cache)} 张，缩略图缓存={len(app._thumb_cache)} 张")
    except Exception:
        pass

    try:
        app.session.close()
        root.destroy()
    except Exception:
        pass

    print()
    calls = globals().get("DIALOG_CALLS", [])
    errs = [c for c in calls if c[0] == "error"]
    if errs:
        print(f"测试期间出现 {len(errs)} 次错误弹窗（说明有操作失败）：")
        for _, m in errs:
            print("  ! " + m)
        failures.extend(m for _, m in errs)
    if failures:
        print(f"界面冒烟测试存在 {len(failures)} 项失败：")
        for f in failures:
            print("  - " + f)
        return 1
    print("UI SMOKE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())