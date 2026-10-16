"""生成操作手册所需的全部图片（适配 v0.3.0 新版界面）。

A. 界面截图（Win32 PrintWindow 抓真实 tkinter 窗口）
   01_main_ui.png            主界面（Ribbon + 缩略图 + 预览 + 面板 + 状态栏）
   02_extract_text.png       「提取的文字」结果窗口
   03_operation_log.png      操作日志区特写
   11_thumbnail_panel.png    左侧缩略图面板特写（多选态）
   12_ribbon_pages.png       页面功能分区特写
   13_annot_panel.png        批注面板特写
   14_find_bar.png           查找栏（含区分大小写）
   15_properties.png         文档属性对话框
   16_encrypt.png            加密设置对话框

B. 功能效果图（用 pdf_engine 真实处理 PDF，再渲染页面拼图）
   04_merge_effect.png       合并（多文件 -> 单文件）
   05_split_effect.png       拆分（单文件 -> 多文件）
   06_rotate_effect.png      旋转 90°（前后对比）
   07_reorder_effect.png     重排（3,1,2）
   08_text_watermark.png     文字水印（中文 + 空格保真）
   09_image_watermark.png    图片水印（印章）
   17_page_number.png        页码 + 页眉页脚
   18_annotation.png         各类批注效果
   19_redaction.png          密文遮盖（脱敏）前后对比
   20_compress.png           压缩前后体积对比

C. 界面引导图
   10_main_ui_annotated.png  主界面分区标注
"""

from __future__ import annotations

import sys
import tempfile
import traceback
from pathlib import Path

import pymupdf as fitz
from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pdf_editor import pdf_engine as eng  # noqa: E402

OUT = PROJECT_ROOT / "docs" / "images"
TMP = PROJECT_ROOT / ".capture_work"
FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\simsun.ttc",
]


def font(size: int, bold: bool = False):
    order = FONT_CANDIDATES if not bold else FONT_CANDIDATES[1:] + FONT_CANDIDATES[:1]
    for f in order:
        if Path(f).exists():
            try:
                return ImageFont.truetype(f, size)
            except Exception:
                continue
    return ImageFont.load_default()


# ======================================================== 窗口抓取工具

def grab_window(win) -> Image.Image | None:
    """抓取 tkinter 顶层窗口像素（Windows PrintWindow）。"""
    import ctypes
    from ctypes import wintypes

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
    return Image.frombuffer("RGBA", (w, h), buffer, "raw", "BGRA", 0, 1).convert("RGB")


def pump(root, seconds: float = 0.5) -> None:
    """真实地跑一会儿事件循环，让 after() 延迟任务（缩略图、渲染）执行。"""
    import time

    end = time.time() + seconds
    while time.time() < end:
        root.update()
        root.update_idletasks()
        time.sleep(0.01)


def wait_idle(root, app, limit: float = 25.0) -> None:
    import time

    end = time.time() + limit
    while time.time() < end:
        root.update()
        if not app._tasks.busy:
            break
        time.sleep(0.02)
    pump(root, 0.2)


def snapshot(app, path: Path) -> bool:
    try:
        img = grab_window(app.root)
        if img is not None:
            img.save(path)
            print(f"   {path.name} {img.size}")
            return True
    except Exception as exc:
        print(f"   （{path.name} 抓图失败：{exc}）")
    return False


def _window_rect(win):
    """返回窗口的屏幕矩形（PrintWindow 抓图即以该矩形为原点）。"""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    hwnd = user32.GetParent(win.winfo_id()) or win.winfo_id()
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return rect


def _window_top(win) -> int:
    return _window_rect(win).top


def crop_widget(win, widget, img: Image.Image,
                pad_top: int = 0, pad_bottom: int = 6,
                pad_left: int = 0, pad_right: int = 4) -> Image.Image:
    """按控件的真实屏幕位置裁剪窗口截图。

    比按窗口尺寸比例估算可靠：面板位置会随 Ribbon 高度、是否显示查找栏
    而变化，硬编码比例在不同状态下会裁错区域。
    """
    rect = _window_rect(win)
    x0 = max(0, widget.winfo_rootx() - rect.left - pad_left)
    y0 = max(0, widget.winfo_rooty() - rect.top - pad_top)
    x1 = min(img.width, x0 + widget.winfo_width() + pad_left + pad_right)
    y1 = min(img.height, y0 + widget.winfo_height() + pad_top + pad_bottom)
    return img.crop((int(x0), int(y0), int(x1), int(y1)))


def patch_dialogs() -> None:
    """把模态对话框替换为非交互桩，使脚本可完全无人值守运行。"""
    from tkinter import filedialog, messagebox, simpledialog

    messagebox.showinfo = lambda t="", m="", **k: None
    messagebox.showwarning = lambda t="", m="", **k: None
    messagebox.showerror = lambda t="", m="", **k: None
    messagebox.askyesno = lambda t="", m="", **k: True
    messagebox.askyesnocancel = lambda t="", m="", **k: False
    simpledialog.askstring = lambda *a, **k: None
    filedialog.askopenfilename = lambda *a, **k: ""
    filedialog.askopenfilenames = lambda *a, **k: ()
    filedialog.asksaveasfilename = lambda *a, **k: ""
    filedialog.askdirectory = lambda *a, **k: ""


# ======================================================== 样例素材

def make_samples() -> Path:
    TMP.mkdir(parents=True, exist_ok=True)
    samples = TMP / "samples"
    samples.mkdir(parents=True, exist_ok=True)

    meta = [("年度报告.pdf", 3, "年度报告", (0.09, 0.35, 0.68)),
            ("合同附件.pdf", 2, "合同附件", (0.11, 0.55, 0.35)),
            ("附录.pdf", 2, "附录", (0.62, 0.33, 0.09))]
    for name, pages, title, color in meta:
        doc = fitz.open()
        for i in range(pages):
            page = doc.new_page(width=595, height=842)
            page.draw_rect(fitz.Rect(0, 0, 595, 90), color=color, fill=color)
            page.insert_text((40, 60), title, fontsize=26, color=(1, 1, 1),
                             fontname="china-s")
            page.insert_text((40, 160), f"第 {i + 1} 页 / 共 {pages} 页", fontsize=18,
                             fontname="china-s")
            page.insert_text((40, 205), "PDF 编辑器 示例文档", fontsize=13,
                             color=(0.4, 0.4, 0.4), fontname="china-s")
            for k in range(14):
                y = 260 + k * 32
                page.draw_line(fitz.Point(48, y), fitz.Point(547, y),
                               color=(0.85, 0.86, 0.88), width=1)
        doc.save(samples / name)
        doc.close()

    stamp = Image.new("RGBA", (240, 240), (0, 0, 0, 0))
    d = ImageDraw.Draw(stamp)
    d.ellipse((10, 10, 230, 230), outline=(200, 20, 20, 200), width=12)
    d.text((70, 100), "示例印章", fill=(200, 20, 20, 200), font=font(34))
    stamp.save(samples / "印章.png")
    return samples


# ======================================================== A. 界面截图

def capture_windows() -> None:
    from pdf_editor.ui import PDFEditorApp, _make_root

    samples = make_samples()
    root = _make_root()
    app = PDFEditorApp(root)
    root.geometry("1240x820+40+20")
    root.update()
    pump(root, 0.6)

    app.open_path(samples / "年度报告.pdf")
    wait_idle(root, app)
    pump(root, 1.2)
    app._log("已打开 年度报告.pdf，可在左侧缩略图点选页面")
    app._log("提示：滚轮或状态栏按钮可翻页；工具栏可缩小/放大/适应宽度")
    app._log("文字水印完成: 年度报告_watermarked.pdf")
    pump(root, 0.4)

    # 01 主界面
    snapshot(app, OUT / "01_main_ui.png")

    # 11 缩略图面板特写（多选态）
    app.select_all()
    pump(root, 0.3)
    img = grab_window(root)
    if img is not None:
        crop_widget(root, app.left, img, pad_left=0, pad_right=0,
                    pad_bottom=0).save(OUT / "11_thumbnail_panel.png")
        print("   11_thumbnail_panel.png")
    app.clear_selection()
    pump(root, 0.2)

    # 12 Ribbon 页面分组特写（菜单栏 + 分页签 + 按钮区）
    img = grab_window(root)
    if img is not None:
        rect = _window_rect(root)
        h = app._notebook.winfo_rooty() - rect.top + app._notebook.winfo_height()
        img.crop((0, 0, img.width, int(h) + 6)).save(OUT / "12_ribbon_pages.png")
        print("   12_ribbon_pages.png")

    # 14 查找栏（含"区分大小写"）
    app.toggle_find_bar(True)
    app.find_var.set("第")
    pump(root, 0.8)
    img = grab_window(root)
    if img is not None:
        crop_widget(root, app.find_bar, img, pad_top=4, pad_bottom=4,
                    pad_left=0, pad_right=0).save(OUT / "14_find_bar.png")
        print("   14_find_bar.png")
    app.toggle_find_bar(False)
    pump(root, 0.3)

    # 13 批注面板特写（先造几条批注）
    for kind, rect in (("highlight", (72, 170, 400, 200)),
                       ("rect", (72, 300, 300, 360)),
                       ("circle", (330, 300, 500, 360))):
        app._mutate(
            lambda d, k=kind, r=rect: eng.add_annotation(d, 1, k, r),
            f"{kind} 批注")
    app.show_catalog_tab()
    pump(root, 0.3)
    app._panel_nb.select(2)
    app.refresh_annotations()
    pump(root, 0.6)
    img = grab_window(root)
    if img is not None:
        crop_widget(root, app.panel, img, pad_left=0, pad_right=0,
                    pad_bottom=0).save(OUT / "13_annot_panel.png")
        print("   13_annot_panel.png")

    # 03 操作日志区特写（切回日志页）
    app._panel_nb.select(0)
    pump(root, 0.5)
    img = grab_window(root)
    if img is not None:
        crop_widget(root, app.panel, img, pad_left=0, pad_right=0,
                    pad_bottom=0).save(OUT / "03_operation_log.png")
        print("   03_operation_log.png")

    # 02 提取文字窗口（用真实引擎提取）
    _capture_extract_window(root, samples)

    # 15 / 16 对话框外观（离屏渲染，不依赖用户操作）
    _capture_dialog_preview(OUT / "15_properties.png", "文档属性", [
        ("标题", "2024 年度经营报告"),
        ("作者", "三一重工"),
        ("主题", "内部经营分析"),
        ("关键字", "pdf, 报告, 内部"),
    ])
    _capture_dialog_preview(OUT / "16_encrypt.png", "加密保护", [
        ("打开口令", "••••••••"),
        ("权限口令", "••••••••••"),
        ("允许打印", "是"),
        ("允许复制", "否"),
    ])

    root.destroy()


def _capture_extract_window(root, samples: Path) -> None:
    """构造「提取的文字」窗口并用真实提取结果填充。"""
    import tkinter as tk
    from tkinter import scrolledtext

    win = tk.Toplevel(root)
    win.title("提取的文字")
    win.geometry("720x520+240+160")
    win.configure(bg="#FFFFFF")
    tk.Label(win, text="提取的文字", bg="#2B7BD6", fg="white",
             font=("Microsoft YaHei", 11, "bold"), anchor="w",
             padx=12, pady=8).pack(fill=tk.X)
    box = scrolledtext.ScrolledText(win, font=("Consolas", 10), relief="flat")
    box.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
    try:
        box.insert(tk.END, eng.extract_text(samples / "年度报告.pdf"))
    except Exception:
        box.insert(tk.END, "（提取失败）")
    win.update()
    win.update_idletasks()
    img = grab_window(win)
    if img:
        img.save(OUT / "02_extract_text.png")
        print("   02_extract_text.png", img.size)
    win.destroy()


def _capture_dialog_preview(path: Path, title: str, rows: list[tuple[str, str]]) -> None:
    """离屏绘制对话框示意图（避免依赖真实模态窗口）。"""
    W, H = 560, 120 + len(rows) * 56
    img = Image.new("RGB", (W, H), (243, 246, 251))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, W - 1, H - 1), radius=10, outline=(203, 213, 225), width=2)
    d.rounded_rectangle((0, 0, W - 1, 46), radius=10, fill=(37, 99, 235))
    d.rectangle((0, 30, W - 1, 46), fill=(37, 99, 235))
    d.text((18, 13), title, fill=(255, 255, 255), font=font(16, bold=True))
    y = 66
    for k, v in rows:
        d.text((24, y + 6), k, fill=(51, 65, 85), font=font(14))
        d.rounded_rectangle((190, y, W - 24, y + 34), radius=6,
                            fill=(255, 255, 255), outline=(203, 213, 225), width=1)
        d.text((202, y + 7), v, fill=(30, 41, 59), font=font(14))
        y += 56
    d.rounded_rectangle((W - 200, H - 52, W - 100, H - 16), radius=8,
                        fill=(37, 99, 235))
    d.text((W - 182, H - 44), "确定", fill=(255, 255, 255), font=font(14))
    d.rounded_rectangle((W - 92, H - 52, W - 24, H - 16), radius=8,
                        fill=(226, 232, 240))
    d.text((W - 74, H - 44), "取消", fill=(51, 65, 85), font=font(14))
    img.save(path)
    print(f"   {path.name}")


# ======================================================== B. 功能效果图

def render_page(pdf: Path, index: int, width: int = 300) -> Image.Image:
    with fitz.open(pdf) as doc:
        page = doc[index]
        zoom = width / page.rect.width
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def label(img: Image.Image, text: str, pad: int = 8) -> Image.Image:
    bar = 34
    out = Image.new("RGB", (img.width + pad * 2, img.height + bar + pad), (245, 247, 250))
    out.paste(img, (pad, bar))
    d = ImageDraw.Draw(out)
    d.text((pad, 10), text, fill=(30, 41, 59), font=font(17))
    return out


def hstack(imgs: list[Image.Image], gap: int = 16, bg=(245, 247, 250)) -> Image.Image:
    h = max(i.height for i in imgs)
    w = sum(i.width for i in imgs) + gap * (len(imgs) - 1)
    out = Image.new("RGB", (w, h), bg)
    x = 0
    for i in imgs:
        out.paste(i, (x, 0))
        x += i.width + gap
    return out


def make_effect_images() -> None:
    s = make_samples()
    out_dir = TMP / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    files = [s / "年度报告.pdf", s / "合同附件.pdf", s / "附录.pdf"]

    # 04 合并
    merged = out_dir / "merged.pdf"
    eng.merge_pdfs(files, merged)
    with fitz.open(merged) as d:
        total = len(d)
    imgs = [label(render_page(merged, i, 240), f"合并后 第{i + 1}页")
            for i in range(min(total, 4))]
    hstack(imgs).save(OUT / "04_merge_effect.png")
    print(f"   04_merge_effect.png 共 {total} 页")

    # 05 拆分
    paths = eng.split_pdf(s / "年度报告.pdf", out_dir / "split", [(1, 1), (2, 3)])
    imgs = [label(render_page(p, 0, 240), f"{p.name}（{eng.page_count(p)} 页）")
            for p in paths]
    hstack(imgs).save(OUT / "05_split_effect.png")
    print("   05_split_effect.png")

    # 06 旋转前后
    rot = out_dir / "rotated.pdf"
    eng.rotate_pdf(s / "年度报告.pdf", rot, 90)
    before = label(render_page(s / "年度报告.pdf", 0, 220), "旋转前（纵向）")
    after = label(render_page(rot, 0, 330), "旋转 90° 后（横向）")
    hstack([before, after]).save(OUT / "06_rotate_effect.png")
    print("   06_rotate_effect.png")

    # 07 重排
    reo = out_dir / "reordered.pdf"
    eng.reorder_pdf(s / "年度报告.pdf", reo, [3, 1, 2])
    imgs = [label(render_page(reo, i, 200), f"新第{i + 1}页") for i in range(3)]
    hstack(imgs).save(OUT / "07_reorder_effect.png")
    print("   07_reorder_effect.png")

    # 08 文字水印（含空格与连字符，便于说明"可搜索"）
    tw = out_dir / "text_wm.pdf"
    eng.add_text_watermark(s / "合同附件.pdf", tw, "机密 - 内部资料")
    label(render_page(tw, 0, 320), "文字水印：机密 - 内部资料（可搜索/可复制）") \
        .save(OUT / "08_text_watermark.png")
    print("   08_text_watermark.png")

    # 09 图片水印
    iw = out_dir / "img_wm.pdf"
    eng.add_image_watermark(s / "合同附件.pdf", iw, s / "印章.png")
    label(render_page(iw, 0, 320), "图片水印（示例印章，可调透明度与缩放）") \
        .save(OUT / "09_image_watermark.png")
    print("   09_image_watermark.png")

    # 17 页码 + 页眉页脚（页脚靠左，避免与居中页码重叠）
    pn = out_dir / "pagenum.pdf"
    with eng.open_document(s / "年度报告.pdf") as doc:
        eng.page_numbers_document(doc, pattern="第 {page} 页 / 共 {total} 页")
        eng.header_footer_document(doc, header="三一重工 · 内部资料",
                                   footer="严禁外传 - {page}",
                                   footer_position="bottom-left")
        eng.save_document(doc, pn)
    label(render_page(pn, 1, 320),
          "页码（居中）+ 页眉（居中）+ 页脚（左对齐，互不遮挡）") \
        .save(OUT / "17_page_number.png")
    print("   17_page_number.png")

    # 18 各类批注
    an = out_dir / "annot.pdf"
    with eng.open_document(s / "年度报告.pdf") as doc:
        eng.add_annotation(doc, 1, "highlight", (48, 250, 400, 282))
        eng.add_annotation(doc, 1, "underline", (48, 282, 420, 314))
        eng.add_annotation(doc, 1, "rect", (440, 250, 545, 330), color=(0.85, 0.2, 0.2))
        eng.add_annotation(doc, 1, "text", (500, 250, 545, 290),
                           text="此处需要补充数据来源")
        eng.add_annotation(doc, 1, "stamp", (400, 420, 545, 480), stamp="Approved")
        eng.save_document(doc, an)
    label(render_page(an, 0, 340), "批注：高亮 / 下划线 / 矩形 / 便签 / 图章") \
        .save(OUT / "18_annotation.png")
    print("   18_annotation.png")

    # 19 密文遮盖前后
    red = out_dir / "redacted.pdf"
    with eng.open_document(pn) as doc:
        # pn 第 2 页底部含页脚文字，遮盖它做脱敏演示
        eng.apply_redaction(doc, 2, (40, 790, 560, 825), fill=(0, 0, 0))
        eng.save_document(doc, red)
    b = label(render_page(pn, 1, 260), "遮盖前")
    a = label(render_page(red, 1, 260), "密文遮盖后（内容已彻底移除）")
    hstack([b, a]).save(OUT / "19_redaction.png")
    print("   19_redaction.png")

    # 20 压缩前后对比
    big = out_dir / "big.pdf"
    doc = fitz.open()
    for i in range(4):
        page = doc.new_page(width=595, height=842)
        page.insert_text((48, 90), f"压缩测试 第 {i + 1} 页", fontname="china-s", fontsize=22)
        for k in range(40):
            page.insert_text((48, 140 + k * 16),
                             "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 " * 2,
                             fontsize=8)
    doc.save(big)
    doc.close()
    small = out_dir / "small.pdf"
    stats = eng.compress_document(big, small, dpi=110, quality=70)
    _bar_compare(OUT / "20_compress.png", stats,
                 "PDF 压缩：清理冗余对象 + 字体子集化 + 图像降采样")
    print(f"   20_compress.png {stats['before']}B -> {stats['after']}B "
          f"(-{stats['saved_percent']}%)")


def _bar_compare(path: Path, stats: dict, title: str) -> None:
    W, H = 620, 260
    img = Image.new("RGB", (W, H), (245, 247, 250))
    d = ImageDraw.Draw(img)
    d.text((20, 18), title, fill=(30, 41, 59), font=font(16, bold=True))
    before, after = stats["before"], stats["after"]
    mx = max(before, 1)
    y = 78
    for text, val, color in (("压缩前", before, (148, 163, 184)),
                             ("压缩后", after, (37, 99, 235))):
        d.text((24, y + 6), text, fill=(51, 65, 85), font=font(14))
        bw = int((W - 220) * val / mx)
        d.rounded_rectangle((110, y, 110 + max(bw, 4), y + 30), radius=6, fill=color)
        d.text((120 + max(bw, 4), y + 6), f"{val:,} 字节", fill=(51, 65, 85), font=font(13))
        y += 52
    d.rounded_rectangle((24, y + 14, W - 24, y + 66), radius=8,
                        fill=(219, 234, 254))
    d.text((40, y + 28),
           f"体积减少 {before - after:,} 字节，压缩率 {stats['saved_percent']}%",
           fill=(29, 78, 216), font=font(15, bold=True))
    img.save(path)


# ======================================================== C. 界面引导图

def annotate_main_ui() -> None:
    """在新版主界面截图上标注 5 大功能区。"""
    src = OUT / "01_main_ui.png"
    if not src.exists():
        print("   （未找到 01_main_ui.png，跳过）")
        return
    img = Image.open(src).convert("RGB")
    d = ImageDraw.Draw(img)
    f = font(18, bold=True)
    w, h = img.size

    marks = [
        ("① 菜单栏 + Ribbon 工具栏：按「开始/页面/批注/水印/工具/视图」分组", 20, 34),
        ("② 左侧页面缩略图：点选 / Ctrl 多选 / 右键菜单", 18, int(h * 0.28)),
        ("③ 预览区：滚轮翻页、Ctrl+滚轮缩放、拖拽平移", int(w * 0.34), int(h * 0.36)),
        ("④ 底部面板：操作日志 / 目录书签 / 批注", int(w * 0.22), int(h * 0.79)),
        ("⑤ 状态栏：页码 / 缩放 / 翻页 / 跳转", int(w * 0.24), h - 30),
    ]
    for txt, x, y in marks:
        bbox = d.textbbox((x, y), txt, font=f)
        d.rectangle((bbox[0] - 8, bbox[1] - 6, min(bbox[2] + 8, w - 4), bbox[3] + 6),
                    fill=(37, 99, 235))
        d.text((x, y), txt, fill=(255, 255, 255), font=f)
    img.save(OUT / "10_main_ui_annotated.png")
    print("   10_main_ui_annotated.png")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    patch_dialogs()
    failures: list[str] = []

    for name, fn in (("生成界面截图", capture_windows),
                     ("生成功能效果图", make_effect_images),
                     ("生成界面引导图", annotate_main_ui)):
        print(f"== {name} ==")
        try:
            fn()
        except Exception as exc:
            failures.append(f"{name}: {exc}")
            traceback.print_exc()

    print()
    if failures:
        print("存在失败项：")
        for f in failures:
            print("  -", f)
        return 1
    print("完成，输出目录:", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())