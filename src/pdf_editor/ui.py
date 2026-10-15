"""PDF 编辑器桌面界面 —— WPS PDF 风格。

布局：
    ┌─────────────────────────────────────────────┐
    │  菜单栏：文件  编辑  页面  插入  水印  帮助   │
    ├─────────────────────────────────────────────┤
    │  Ribbon 工具栏（按功能分组）                  │
    ├──────────┬──────────────────────────────────┤
    │ 页面缩略图│        页面预览区（可缩放）        │
    │ （左栏）  │                                  │
    ├──────────┴──────────────────────────────────┤
    │  状态栏：页码 / 缩放 / 提示                   │
    └─────────────────────────────────────────────┘

界面采用 WPS 蓝配色，左侧缩略图可点选页面，中间支持放大/缩小/翻页，
所有编辑操作均写入新文件，不改动原文件。
"""

from __future__ import annotations

import io
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, scrolledtext

import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from PIL import Image, ImageTk

from .pdf_engine import (
    merge_pdfs,
    split_pdf,
    rotate_pdf,
    reorder_pdf,
    add_text_watermark,
    add_image_watermark,
    extract_text,
    page_count,
    page_size,
    render_page_png,
    delete_pages,
    extract_pages,
    insert_pages,
    rotate_page,
)

# WPS 风格配色
CLR_BLUE = "#2B7BD6"          # 主色（WPS 蓝）
CLR_BLUE_DARK = "#1F5FA8"
CLR_BG = "#F3F5F8"            # 工作区背景
CLR_PANEL = "#FFFFFF"
CLR_BORDER = "#D8DEE6"
CLR_TEXT = "#2C3E50"
CLR_MUTED = "#7A8A9A"


class PDFEditorApp:
    def __init__(self, root: ttk.Window):
        self.root = root
        self.root.title("PDF 编辑器")
        self.root.geometry("1180x780")
        self.root.minsize(980, 640)
        self.root.configure(bg=CLR_BG)

        # 文档状态
        self.doc_path: Path | None = None
        self.total_pages: int = 0
        self.current_page: int = 1
        self.zoom: float = 1.0
        self._thumb_refs: list[ImageTk.PhotoImage] = []
        self._page_photo: ImageTk.PhotoImage | None = None

        self._build_menu()
        self._build_toolbar()
        self._build_body()
        self._build_statusbar()
        self._update_ui_state()

    # ------------------------------------------------------------------ 菜单
    def _build_menu(self):
        bar = tk.Menu(self.root, tearoff=0)

        m_file = tk.Menu(bar, tearoff=0)
        m_file.add_command(label="打开 PDF…", command=self.open_pdf, accelerator="Ctrl+O")
        m_file.add_command(label="合并 PDF…", command=self._merge)
        m_file.add_separator()
        m_file.add_command(label="退出", command=self.root.quit)
        bar.add_cascade(label="文件", menu=m_file)

        m_edit = tk.Menu(bar, tearoff=0)
        m_edit.add_command(label="提取文字…", command=self._extract_text)
        m_edit.add_command(label="另存为…", command=self._save_as)
        bar.add_cascade(label="编辑", menu=m_edit)

        m_page = tk.Menu(bar, tearoff=0)
        m_page.add_command(label="删除当前页", command=self._delete_current)
        m_page.add_command(label="提取选中页…", command=self._extract_selected)
        m_page.add_command(label="拆分…", command=self._split)
        m_page.add_command(label="重排…", command=self._reorder)
        m_page.add_separator()
        m_page.add_command(label="顺时针旋转 90°", command=lambda: self._rotate(90))
        m_page.add_command(label="旋转 180°", command=lambda: self._rotate(180))
        bar.add_cascade(label="页面", menu=m_page)

        m_ins = tk.Menu(bar, tearoff=0)
        m_ins.add_command(label="插入 PDF 到末尾…", command=lambda: self._insert(-1))
        m_ins.add_command(label="插入 PDF 到最前…", command=lambda: self._insert(0))
        m_ins.add_command(label="在当前页后插入…",
                          command=lambda: self._insert(self.current_page))
        bar.add_cascade(label="插入", menu=m_ins)

        m_wm = tk.Menu(bar, tearoff=0)
        m_wm.add_command(label="文字水印…", command=self._text_watermark)
        m_wm.add_command(label="图片水印…", command=self._image_watermark)
        bar.add_cascade(label="水印", menu=m_wm)

        m_help = tk.Menu(bar, tearoff=0)
        m_help.add_command(label="关于", command=self._about)
        bar.add_cascade(label="帮助", menu=m_help)

        self.root.config(menu=bar)
        self.root.bind_all("<Control-o>", lambda e: self.open_pdf())

    # --------------------------------------------------------------- Ribbon
    def _build_toolbar(self):
        ribbon = tk.Frame(self.root, bg=CLR_PANEL)
        ribbon.pack(fill=X)

        def group(title, buttons):
            g = tk.Frame(ribbon, bg=CLR_PANEL)
            g.pack(side=LEFT, padx=(10, 6), pady=6, anchor="n")
            row = tk.Frame(g, bg=CLR_PANEL)
            row.pack(anchor="center")
            for label, cmd in buttons:
                b = tk.Button(
                    row, text=label, command=cmd, relief="flat",
                    bg=CLR_PANEL, fg=CLR_TEXT, activebackground="#E8F0FB",
                    activeforeground=CLR_BLUE_DARK, cursor="hand2",
                    font=("Microsoft YaHei", 9), padx=8, pady=6, bd=0,
                    width=max(4, len(label) + 1),
                )
                b.pack(side=LEFT, padx=2)
                b.bind("<Enter>", lambda e, w=b: w.configure(bg="#E8F0FB"))
                b.bind("<Leave>", lambda e, w=b: w.configure(bg=CLR_PANEL))
            tk.Label(g, text=title, bg=CLR_PANEL, fg=CLR_MUTED,
                     font=("Microsoft YaHei", 8)).pack()
            tk.Frame(ribbon, bg=CLR_BORDER, width=1).pack(side=LEFT, fill=Y, pady=6)

        group("文件", [("打开", self.open_pdf), ("合并", self._merge), ("另存为", self._save_as)])
        group("页面", [("删除页", self._delete_current), ("提取页", self._extract_selected),
                       ("拆分", self._split), ("重排", self._reorder)])
        group("旋转", [("↻ 90°", lambda: self._rotate(90)),
                       ("↻ 180°", lambda: self._rotate(180))])
        group("插入", [("插入 PDF", lambda: self._insert(-1))])
        group("水印", [("文字水印", self._text_watermark), ("图片水印", self._image_watermark)])
        group("工具", [("提取文字", self._extract_text), ("缩放-", lambda: self.set_zoom(0.8)),
                       ("缩放+", lambda: self.set_zoom(1.25)), ("适应宽度", self.fit_width)])

    # ----------------------------------------------------------------- 主体
    def _build_body(self):
        body = tk.Frame(self.root, bg=CLR_BG)
        body.pack(fill=BOTH, expand=True)

        # 左栏：缩略图
        left = tk.Frame(body, bg=CLR_PANEL, width=200)
        left.pack(side=LEFT, fill=Y)
        left.pack_propagate(False)
        tk.Label(left, text="页面", bg=CLR_PANEL, fg=CLR_TEXT,
                 font=("Microsoft YaHei", 10, "bold")).pack(anchor=W, padx=10, pady=(8, 4))
        tk.Frame(left, bg=CLR_BORDER, height=1).pack(fill=X)

        self.thumb_canvas = tk.Canvas(left, bg=CLR_PANEL, highlightthickness=0)
        sb = ttk.Scrollbar(left, orient=VERTICAL, command=self.thumb_canvas.yview)
        self.thumb_canvas.configure(yscrollcommand=sb.set)
        sb.pack(side=RIGHT, fill=Y)
        self.thumb_canvas.pack(side=LEFT, fill=BOTH, expand=True)
        self.thumb_inner = tk.Frame(self.thumb_canvas, bg=CLR_PANEL)
        self.thumb_canvas.create_window((0, 0), window=self.thumb_inner, anchor="nw")
        self.thumb_inner.bind(
            "<Configure>",
            lambda e: self.thumb_canvas.configure(scrollregion=self.thumb_canvas.bbox("all")),
        )

        # 右栏：预览 + 日志
        right = tk.Frame(body, bg=CLR_BG)
        right.pack(side=LEFT, fill=BOTH, expand=True)

        self.canvas = tk.Canvas(right, bg="#9AA6B2", highlightthickness=0)
        self.canvas.pack(fill=BOTH, expand=True)
        self.canvas.bind("<Configure>", lambda e: self._render_page())
        self.canvas.bind("<MouseWheel>", self._on_wheel)

        # 日志区
        log_frame = tk.Frame(right, bg=CLR_PANEL, height=96)
        log_frame.pack(fill=X, side=BOTTOM)
        tk.Label(log_frame, text="操作日志", bg=CLR_PANEL, fg=CLR_MUTED,
                 font=("Microsoft YaHei", 8)).pack(anchor=W, padx=8)
        self.log = scrolledtext.ScrolledText(
            log_frame, height=4, state=tk.DISABLED, relief="flat",
            bg="#FBFCFE", fg=CLR_TEXT, font=("Consolas", 9))
        self.log.pack(fill=BOTH, expand=True, padx=6, pady=(0, 4))

    # ---------------------------------------------------------------- 状态栏
    def _build_statusbar(self):
        bar = tk.Frame(self.root, bg=CLR_BLUE_DARK, height=26)
        bar.pack(fill=X, side=BOTTOM)
        self.status_left = tk.Label(bar, text="就绪", bg=CLR_BLUE_DARK, fg="white",
                                    font=("Microsoft YaHei", 9), anchor="w")
        self.status_left.pack(side=LEFT, padx=10)

        self.page_var = tk.StringVar(value="第 0 / 0 页")
        tk.Label(bar, textvariable=self.page_var, bg=CLR_BLUE_DARK, fg="white",
                 font=("Microsoft YaHei", 9)).pack(side=RIGHT, padx=10)
        self.zoom_var = tk.StringVar(value="100%")
        tk.Label(bar, textvariable=self.zoom_var, bg=CLR_BLUE_DARK, fg="white",
                 font=("Microsoft YaHei", 9)).pack(side=RIGHT, padx=10)
        for txt, cmd in (("下一页", lambda: self.goto_page(self.current_page + 1)),
                         ("上一页", lambda: self.goto_page(self.current_page - 1))):
            tk.Button(bar, text=txt, command=cmd, relief="flat", bg=CLR_BLUE,
                      fg="white", activebackground=CLR_BLUE_DARK, activeforeground="white",
                      font=("Microsoft YaHei", 8), padx=8, bd=0).pack(side=RIGHT, padx=3, pady=2)

    # ---------------------------------------------------------------- 工具方法
    def _log(self, msg: str):
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, msg + "\n")
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def _status(self, msg: str):
        self.status_left.configure(text=msg)

    def _update_ui_state(self):
        self.page_var.set(f"第 {self.current_page} / {self.total_pages} 页"
                          if self.total_pages else "第 0 / 0 页")
        self.zoom_var.set(f"{int(self.zoom * 100)}%")

    def _need_doc(self) -> bool:
        if self.doc_path is None:
            messagebox.showinfo("提示", "请先打开一个 PDF 文件")
            return False
        return True

    # ---------------------------------------------------------------- 打开文件
    def open_pdf(self):
        p = filedialog.askopenfilename(title="打开 PDF", filetypes=[("PDF 文件", "*.pdf")])
        if not p:
            return
        self.load_document(Path(p))

    def load_document(self, path: Path):
        """打开指定 PDF（供外部/测试调用）。"""
        self.doc_path = Path(path)
        self.current_page = 1
        self.zoom = 1.0
        self._reload()

    def _reload(self):
        try:
            self.total_pages = page_count(self.doc_path)
        except Exception as e:
            messagebox.showerror("错误", str(e))
            return
        self.root.title(f"{self.doc_path.name} - PDF 编辑器")
        self._status(f"已打开：{self.doc_path.name}（共 {self.total_pages} 页）")
        self._log(f"打开文件: {self.doc_path}（{self.total_pages} 页）")
        self._build_thumbnails()
        self._render_page()
        self._update_ui_state()

    def _build_thumbnails(self):
        for w in self.thumb_inner.winfo_children():
            w.destroy()
        self._thumb_refs.clear()
        if not self.doc_path:
            return
        for i in range(1, self.total_pages + 1):
            try:
                data = render_page_png(self.doc_path, i, zoom=0.22)
                im = Image.open(io.BytesIO(data))
            except Exception:
                continue
            photo = ImageTk.PhotoImage(im)
            self._thumb_refs.append(photo)
            holder = tk.Frame(self.thumb_inner, bg=CLR_PANEL)
            holder.pack(fill=X, padx=6, pady=4)
            lbl = tk.Label(holder, image=photo, bg=CLR_PANEL, cursor="hand2",
                           bd=2, relief="solid")
            lbl.pack()
            lbl.bind("<Button-1>", lambda e, pg=i: self.goto_page(pg))
            tk.Label(holder, text=str(i), bg=CLR_PANEL, fg=CLR_MUTED,
                     font=("Microsoft YaHei", 8)).pack()

    def goto_page(self, page: int):
        if not self.doc_path or self.total_pages == 0:
            return
        page = max(1, min(page, self.total_pages))
        self.current_page = page
        self._render_page()
        self._update_ui_state()

    def set_zoom(self, factor: float):
        if not self.doc_path:
            return
        self.zoom = max(0.2, min(self.zoom * factor, 5.0))
        self._render_page()
        self._update_ui_state()

    def fit_width(self):
        if not self.doc_path:
            return
        try:
            w, _ = page_size(self.doc_path, self.current_page)
        except Exception:
            return
        avail = max(self.canvas.winfo_width() - 40, 200)
        self.zoom = max(0.2, min(avail / w, 5.0))
        self._render_page()
        self._update_ui_state()

    def _render_page(self):
        self.canvas.delete("all")
        if not self.doc_path or self.total_pages == 0:
            self.canvas.create_text(
                max(self.canvas.winfo_width() // 2, 200), 200,
                text="打开一个 PDF 文件后在此预览",
                fill="#E8EEF5", font=("Microsoft YaHei", 14))
            return
        try:
            data = render_page_png(self.doc_path, self.current_page, zoom=self.zoom)
            im = Image.open(io.BytesIO(data))
        except Exception as e:
            self._log(f"渲染失败: {e}")
            return
        self._page_photo = ImageTk.PhotoImage(im)
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        # 水平居中；若页面高度小于视口则垂直居中，否则顶部对齐
        x = cw // 2
        y = ch // 2 if im.height + 40 <= ch else im.height // 2 + 20
        self.canvas.create_rectangle(x - im.width // 2 - 2, y - im.height // 2 - 2,
                                     x + im.width // 2 + 2, y + im.height // 2 + 2,
                                     fill="#FFFFFF", outline=CLR_BORDER)
        self.canvas.create_image(x, y, image=self._page_photo)
        self._status(f"第 {self.current_page} 页 / 共 {self.total_pages} 页　"
                     f"缩放 {int(self.zoom * 100)}%")

    def _on_wheel(self, event):
        """滚轮：上下翻页。"""
        if not self.doc_path:
            return
        if event.delta < 0:
            self.goto_page(self.current_page + 1)
        else:
            self.goto_page(self.current_page - 1)

    # ---------------------------------------------------------------- 功能操作
    def _save_path(self, title: str, default_name: str) -> Path | None:
        p = filedialog.asksaveasfilename(
            title=title, defaultextension=".pdf", initialfile=default_name,
            filetypes=[("PDF 文件", "*.pdf")])
        return Path(p) if p else None

    def _after_edit(self, out: Path, msg: str):
        self._log(f"{msg}: {out}")
        self._status(f"{msg} → {out.name}")
        self.doc_path = out
        self._reload()

    def _merge(self):
        paths = filedialog.askopenfilenames(title="选择要合并的 PDF（按选择顺序）",
                                            filetypes=[("PDF 文件", "*.pdf")])
        if not paths or len(paths) < 2:
            messagebox.showwarning("提示", "合并至少需要选择 2 个文件")
            return
        out = self._save_path("合并输出", "merged.pdf")
        if not out:
            return
        try:
            merge_pdfs([Path(p) for p in paths], out)
            self._after_edit(out, "合并完成")
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def _save_as(self):
        if not self._need_doc():
            return
        out = self._save_path("另存为", f"{self.doc_path.stem}_副本.pdf")
        if not out:
            return
        try:
            import shutil
            shutil.copyfile(self.doc_path, out)
            self._log(f"另存为: {out}")
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def _delete_current(self):
        if not self._need_doc():
            return
        if self.total_pages <= 1:
            messagebox.showwarning("提示", "至少保留一页")
            return
        if not messagebox.askyesno("确认", f"确定删除第 {self.current_page} 页？"):
            return
        out = self._save_path("删除页面输出", f"{self.doc_path.stem}_del.pdf")
        if not out:
            return
        try:
            page_no = self.current_page
            delete_pages(self.doc_path, out, [page_no])
            self._after_edit(out, f"已删除第 {page_no} 页")
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def _extract_selected(self):
        if not self._need_doc():
            return
        s = simpledialog.askstring(
            "提取页面",
            f"输入要提取的页码（1-{self.total_pages}，逗号分隔）\n例如：1,3,5",
            initialvalue=str(self.current_page))
        if not s:
            return
        try:
            pages = [int(x.strip()) for x in s.split(",") if x.strip()]
        except ValueError:
            messagebox.showerror("错误", "页码格式不正确")
            return
        out = self._save_path("提取页面输出", f"{self.doc_path.stem}_extract.pdf")
        if not out:
            return
        try:
            extract_pages(self.doc_path, out, pages)
            self._after_edit(out, f"已提取 {len(pages)} 页")
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def _rotate(self, angle: int):
        if not self._need_doc():
            return
        if not messagebox.askyesno("确认", f"将第 {self.current_page} 页旋转 {angle}°？"):
            return
        out = self._save_path("旋转输出", f"{self.doc_path.stem}_rotated.pdf")
        if not out:
            return
        try:
            page_no = self.current_page
            rotate_page(self.doc_path, out, page_no, angle)
            self._after_edit(out, f"第 {page_no} 页已旋转 {angle}°")
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def _insert(self, at: int):
        if not self._need_doc():
            return
        src = filedialog.askopenfilename(title="选择要插入的 PDF",
                                         filetypes=[("PDF 文件", "*.pdf")])
        if not src:
            return
        out = self._save_path("插入输出", f"{self.doc_path.stem}_inserted.pdf")
        if not out:
            return
        try:
            insert_pages(self.doc_path, out, Path(src), at=at)
            self._after_edit(out, "插入完成")
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def _split(self):
        if not self._need_doc():
            return
        s = simpledialog.askstring(
            "拆分 PDF",
            f"输入拆分范围（总页数 {self.total_pages}）\n格式：起-止，多段用逗号分隔，如 1-3,4-6",
            initialvalue=f"1-{self.total_pages}")
        if not s:
            return
        try:
            ranges = []
            for part in s.split(","):
                a, b = part.split("-")
                ranges.append((int(a), int(b)))
        except ValueError:
            messagebox.showerror("错误", "范围格式不正确，应为 1-3,4-6")
            return
        out_dir = filedialog.askdirectory(title="选择输出目录")
        if not out_dir:
            return
        try:
            paths = split_pdf(self.doc_path, Path(out_dir), ranges)
            self._log(f"拆分完成，生成 {len(paths)} 个文件")
            for p in paths:
                self._log(f"  {p}")
            self._status(f"拆分完成，生成 {len(paths)} 个文件")
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def _reorder(self):
        if not self._need_doc():
            return
        s = simpledialog.askstring(
            "重排页面",
            f"输入新的页序（1-{self.total_pages} 的排列）\n例如：3,1,2",
            initialvalue=",".join(str(i) for i in range(1, self.total_pages + 1)))
        if not s:
            return
        try:
            order = [int(x.strip()) for x in s.split(",") if x.strip()]
        except ValueError:
            messagebox.showerror("错误", "页序格式不正确")
            return
        out = self._save_path("重排输出", f"{self.doc_path.stem}_reordered.pdf")
        if not out:
            return
        try:
            reorder_pdf(self.doc_path, out, order)
            self._after_edit(out, "重排完成")
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def _text_watermark(self):
        if not self._need_doc():
            return
        text = simpledialog.askstring("文字水印", "输入水印文字（支持中文）", initialvalue="机密")
        if not text:
            return
        out = self._save_path("水印输出", f"{self.doc_path.stem}_watermarked.pdf")
        if not out:
            return
        try:
            add_text_watermark(self.doc_path, out, text)
            self._after_edit(out, "文字水印完成")
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def _image_watermark(self):
        if not self._need_doc():
            return
        img = filedialog.askopenfilename(title="选择水印图片",
                                         filetypes=[("图片", "*.png;*.jpg;*.jpeg")])
        if not img:
            return
        out = self._save_path("图片水印输出", f"{self.doc_path.stem}_img_watermarked.pdf")
        if not out:
            return
        try:
            add_image_watermark(self.doc_path, out, Path(img))
            self._after_edit(out, "图片水印完成")
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def _extract_text(self):
        if not self._need_doc():
            return
        try:
            text = extract_text(self.doc_path)
        except Exception as e:
            messagebox.showerror("错误", str(e))
            return
        win = ttk.Toplevel(self.root)
        win.title("提取的文字")
        win.geometry("760x540")
        st = scrolledtext.ScrolledText(win, font=("Consolas", 10))
        st.pack(fill=BOTH, expand=True)
        st.insert(tk.END, text)
        self._log(f"提取文字完成，共 {len(text)} 字符")
        self._status(f"提取文字完成，共 {len(text)} 字符")

    def _about(self):
        messagebox.showinfo(
            "关于",
            "PDF 编辑器 v0.2.0\n\n"
            "界面参照 WPS PDF 设计，支持页面预览、缩略图导航、缩放翻页。\n"
            "功能：合并 / 拆分 / 旋转 / 重排 / 删除页 / 提取页 / 插入页 / 水印 / 提取文字\n"
            "全离线运行，不改动原文件。")


def main():
    root = ttk.Window(themename="flatly")
    PDFEditorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()