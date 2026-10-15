"""生成操作手册所需的全部图片（适配 WPS 风格新版界面）。

A. 界面截图（PrintWindow 抓真实 tkinter 窗口）
   01_main_ui.png            主界面（Ribbon + 缩略图 + 预览 + 状态栏，已载入文档）
   02_extract_text.png       「提取的文字」结果窗口
   03_operation_log.png      操作日志区特写

B. 功能效果图（用 pdf_engine 真实处理 PDF，再用 fitz 渲染页面拼图）
   04_merge_effect.png       合并（多文件 -> 单文件）
   05_split_effect.png       拆分（单文件 -> 多文件）
   06_rotate_effect.png      旋转 90°（前后对比）
   07_reorder_effect.png     重排（3,1,2）
   08_text_watermark.png     文字水印（中文）
   09_image_watermark.png    图片水印（印章）

C. 界面引导图
   10_main_ui_annotated.png  主界面分区标注
"""

from __future__ import annotations

import ctypes
import shutil
import sys
from ctypes import wintypes
from pathlib import Path

import fitz
from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pdf_editor import pdf_engine as eng  # noqa: E402

OUT = PROJECT_ROOT / "docs" / "images"
TMP = PROJECT_ROOT / ".capture_work"
FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\msyhbd.ttc",
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


# ---------------- A. 界面截图 ----------------

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


def capture_hwnd(hwnd: int) -> Image.Image | None:
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w, h = rect.right - rect.left, rect.bottom - rect.top
    if w <= 0 or h <= 0:
        return None
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
        return None
    return Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1).convert("RGB")


def hwnd_of(win) -> int:
    return user32.GetParent(win.winfo_id()) or win.winfo_id()


def capture_windows():
    import tkinter as tk
    from tkinter import scrolledtext
    import ttkbootstrap as ttk
    from pdf_editor.ui import PDFEditorApp, CLR_BLUE

    samples = TMP / "samples"
    root = ttk.Window(themename="flatly")
    app = PDFEditorApp(root)
    root.geometry("1180x780+40+20")
    root.update()
    app.load_document(samples / "年度报告.pdf")
    # 让缩略图与预览有时间渲染
    for _ in range(6):
        root.update()
    app._log("已打开 年度报告.pdf，可在左侧缩略图点选页面")
    app._log("提示：滚轮或状态栏按钮可翻页；工具栏可缩小/放大/适应宽度")
    app._log("文字水印完成: 年度报告_watermarked.pdf")
    root.update()

    # 01 主界面
    img = capture_hwnd(hwnd_of(root))
    if img:
        img.save(OUT / "01_main_ui.png")
        print("01_main_ui.png", img.size)

    # 02 提取文字窗口
    win = ttk.Toplevel(root)
    win.title("提取的文字")
    win.geometry("720x520+220+140")
    win.configure(bg="#FFFFFF")
    header = tk.Label(win, text="提取的文字", bg="#2B7BD6", fg="white",
                      font=("Microsoft YaHei", 11, "bold"), anchor="w", padx=12, pady=8)
    header.pack(fill=tk.X)
    st = scrolledtext.ScrolledText(win, font=("Consolas", 10), relief="flat")
    st.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
    st.insert(tk.END,
              "年度报告\n第 1 页 / 共 3 页\nPDF 编辑器 示例文档\n\n"
              "年度报告\n第 2 页 / 共 3 页\nPDF 编辑器 示例文档\n\n"
              "年度报告\n第 3 页 / 共 3 页\nPDF 编辑器 示例文档\n\n"
              "（以上为 PDF 中提取出的全部文字内容，可框选复制）")
    win.update()
    win.update_idletasks()
    img2 = capture_hwnd(hwnd_of(win))
    if img2:
        img2.save(OUT / "02_extract_text.png")
        print("02_extract_text.png", img2.size)

    # 03 操作日志区特写（裁剪主界面右下角日志区域）
    root.update()
    img3 = capture_hwnd(hwnd_of(root))
    if img3:
        w, h = img3.size
        img3.crop((int(w * 0.145), int(h * 0.815), w - 4, h - 30)).save(OUT / "03_operation_log.png")
        print("03_operation_log.png")

    win.destroy()
    root.destroy()


# ---------------- B. 功能效果图 ----------------

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


def make_samples():
    TMP.mkdir(parents=True, exist_ok=True)
    samples = TMP / "samples"
    if samples.exists():
        shutil.rmtree(samples)
    samples.mkdir(parents=True)

    meta = [("年度报告.pdf", 3, "年度报告", (0.09, 0.35, 0.68)),
            ("合同附件.pdf", 2, "合同附件", (0.11, 0.55, 0.35)),
            ("附录.pdf", 2, "附录", (0.62, 0.33, 0.09))]
    for name, pages, label_txt, color in meta:
        doc = fitz.open()
        for i in range(pages):
            page = doc.new_page(width=595, height=842)
            page.draw_rect(fitz.Rect(0, 0, 595, 90), color=color, fill=color)
            page.insert_text((40, 60), label_txt, fontsize=26, color=(1, 1, 1),
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


def make_effect_images():
    s = make_samples()
    files = [s / "年度报告.pdf", s / "合同附件.pdf", s / "附录.pdf"]

    # 04 合并
    merged = TMP / "out" / "merged.pdf"
    eng.merge_pdfs(files, merged)
    with fitz.open(merged) as d:
        total = len(d)
    imgs = [label(render_page(merged, i, 240), f"合并后 第{i + 1}页") for i in range(min(total, 4))]
    hstack(imgs).save(OUT / "04_merge_effect.png")
    print("04_merge_effect.png 共", total, "页")

    # 05 拆分
    split_dir = TMP / "out" / "split"
    paths = eng.split_pdf(s / "年度报告.pdf", split_dir, [(1, 1), (2, 3)])
    imgs = [label(render_page(p, 0, 240), f"{p.name}") for p in paths]
    hstack(imgs).save(OUT / "05_split_effect.png")
    print("05_split_effect.png")

    # 06 旋转（前后对比）
    rot = TMP / "out" / "rotated.pdf"
    eng.rotate_pdf(s / "年度报告.pdf", rot, 90)
    before = label(render_page(s / "年度报告.pdf", 0, 220), "旋转前（纵向）")
    after = label(render_page(rot, 0, 330), "旋转 90° 后（横向）")
    hstack([before, after]).save(OUT / "06_rotate_effect.png")
    print("06_rotate_effect.png")

    # 07 重排
    reo = TMP / "out" / "reordered.pdf"
    eng.reorder_pdf(s / "年度报告.pdf", reo, [3, 1, 2])
    imgs = [label(render_page(reo, i, 200), f"新第{i + 1}页") for i in range(3)]
    hstack(imgs).save(OUT / "07_reorder_effect.png")
    print("07_reorder_effect.png")

    # 08 文字水印
    tw = TMP / "out" / "text_wm.pdf"
    eng.add_text_watermark(s / "合同附件.pdf", tw, "机密 - 内部资料")
    img = label(render_page(tw, 0, 320), "文字水印：机密 - 内部资料")
    img.save(OUT / "08_text_watermark.png")
    print("08_text_watermark.png")

    # 09 图片水印
    iw = TMP / "out" / "img_wm.pdf"
    eng.add_image_watermark(s / "合同附件.pdf", iw, s / "印章.png")
    img = label(render_page(iw, 0, 320), "图片水印（示例印章）")
    img.save(OUT / "09_image_watermark.png")
    print("09_image_watermark.png")


# ---------------- C. 界面引导图 ----------------

def annotate_main_ui():
    """在新版主界面截图上标注 5 大功能区。"""
    src = OUT / "01_main_ui.png"
    if not src.exists():
        return
    img = Image.open(src).convert("RGB")
    d = ImageDraw.Draw(img)
    f = font(18, bold=True)

    # 依据 1180x780 布局估算区域锚点
    marks = [
        ("① Ribbon 工具栏：按功能分组的操作按钮", 210, 60),
        ("② 页面缩略图导航：点选任意页", 24, 205),
        ("③ 页面预览区：滚轮翻页、可缩放", 470, 300),
        ("④ 操作日志：实时显示每步结果", 300, 690),
        ("⑤ 状态栏：页码 / 缩放 / 翻页按钮", 300, 752),
    ]
    for txt, x, y in marks:
        bbox = d.textbbox((x, y), txt, font=f)
        d.rectangle((bbox[0] - 8, bbox[1] - 6, bbox[2] + 8, bbox[3] + 6),
                    fill=(37, 99, 235))
        d.text((x, y), txt, fill=(255, 255, 255), font=f)
    img.save(OUT / "10_main_ui_annotated.png")
    print("10_main_ui_annotated.png")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    print("== 生成界面截图 ==")
    capture_windows()
    print("== 生成功能效果图 ==")
    make_effect_images()
    print("== 生成界面引导图 ==")
    annotate_main_ui()
    print("完成，输出目录:", OUT)