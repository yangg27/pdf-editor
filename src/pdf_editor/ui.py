"""PDF 编辑器桌面 UI。"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext
from typing import List

import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from .pdf_engine import (
    merge_pdfs,
    split_pdf,
    rotate_pdf,
    reorder_pdf,
    add_text_watermark,
    add_image_watermark,
    extract_text,
)


class PDFEditorApp:
    def __init__(self, root: ttk.Window):
        self.root = root
        self.root.title("PDF 编辑器")
        self.root.geometry("900x700")

        self.files: List[Path] = []

        self._build_toolbar()
        self._build_file_list()
        self._build_log()

    def _build_toolbar(self):
        toolbar = ttk.Frame(self.root, padding=10)
        toolbar.pack(fill=X)

        ttk.Button(toolbar, text="添加文件", command=self._add_files).pack(side=LEFT, padx=2)
        ttk.Button(toolbar, text="清空", command=self._clear_files).pack(side=LEFT, padx=2)
        ttk.Button(toolbar, text="合并", command=self._merge).pack(side=LEFT, padx=2)
        ttk.Button(toolbar, text="拆分", command=self._split).pack(side=LEFT, padx=2)
        ttk.Button(toolbar, text="旋转", command=self._rotate).pack(side=LEFT, padx=2)
        ttk.Button(toolbar, text="重排", command=self._reorder).pack(side=LEFT, padx=2)
        ttk.Button(toolbar, text="文字水印", command=self._text_watermark).pack(side=LEFT, padx=2)
        ttk.Button(toolbar, text="图片水印", command=self._image_watermark).pack(side=LEFT, padx=2)
        ttk.Button(toolbar, text="提取文字", command=self._extract_text).pack(side=LEFT, padx=2)

    def _build_file_list(self):
        frame = ttk.Frame(self.root, padding=10)
        frame.pack(fill=BOTH, expand=True)

        ttk.Label(frame, text="文件列表（第一个文件用于拆分/旋转/重排/水印/提取文字）").pack(anchor=W)
        self.listbox = tk.Listbox(frame, selectmode=tk.EXTENDED)
        self.listbox.pack(fill=BOTH, expand=True)

        # 重排顺序输入
        ttk.Label(frame, text="重排顺序（逗号分隔页码，如 3,1,2）：").pack(anchor=W, pady=(10, 0))
        self.order_var = ttk.StringVar()
        ttk.Entry(frame, textvariable=self.order_var).pack(fill=X)

        # 拆分范围输入
        ttk.Label(frame, text="拆分范围（如 1-3,4-6）：").pack(anchor=W, pady=(10, 0))
        self.split_var = ttk.StringVar()
        ttk.Entry(frame, textvariable=self.split_var).pack(fill=X)

        # 文字水印输入
        ttk.Label(frame, text="文字水印内容：").pack(anchor=W, pady=(10, 0))
        self.watermark_var = ttk.StringVar(value="机密")
        ttk.Entry(frame, textvariable=self.watermark_var).pack(fill=X)

    def _build_log(self):
        frame = ttk.Frame(self.root, padding=10)
        frame.pack(fill=BOTH, expand=False)
        ttk.Label(frame, text="日志").pack(anchor=W)
        self.log = scrolledtext.ScrolledText(frame, height=10, state=tk.DISABLED)
        self.log.pack(fill=BOTH, expand=True)

    def _log(self, msg: str):
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, msg + "\n")
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def _add_files(self):
        paths = filedialog.askopenfilenames(filetypes=[("PDF 文件", "*.pdf")])
        for p in paths:
            path = Path(p)
            if path not in self.files:
                self.files.append(path)
                self.listbox.insert(tk.END, str(path))
        self._log(f"已添加 {len(paths)} 个文件")

    def _clear_files(self):
        self.files.clear()
        self.listbox.delete(0, tk.END)
        self._log("已清空文件列表")

    def _selected_or_first(self) -> Path:
        selection = self.listbox.curselection()
        if selection:
            return self.files[selection[0]]
        if self.files:
            return self.files[0]
        raise ValueError("请先添加 PDF 文件")

    def _save_path(self, title: str, default_name: str) -> Path:
        p = filedialog.asksaveasfilename(
            title=title,
            defaultextension=".pdf",
            initialfile=default_name,
            filetypes=[("PDF 文件", "*.pdf")],
        )
        if not p:
            raise ValueError("未选择输出路径")
        return Path(p)

    def _merge(self):
        if len(self.files) < 2:
            messagebox.showwarning("提示", "合并至少需要 2 个文件")
            return
        try:
            out = self._save_path("合并输出", "merged.pdf")
            merge_pdfs(self.files, out)
            self._log(f"合并完成: {out}")
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def _split(self):
        try:
            src = self._selected_or_first()
            ranges_str = self.split_var.get().strip()
            if not ranges_str:
                messagebox.showwarning("提示", "请输入拆分范围，如 1-3,4-6")
                return
            ranges = []
            for part in ranges_str.split(","):
                start, end = part.split("-")
                ranges.append((int(start), int(end)))
            out_dir = filedialog.askdirectory(title="选择输出目录")
            if not out_dir:
                return
            out_paths = split_pdf(src, Path(out_dir), ranges)
            self._log(f"拆分完成，生成 {len(out_paths)} 个文件")
            for p in out_paths:
                self._log(f"  {p}")
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def _rotate(self):
        try:
            src = self._selected_or_first()
            out = self._save_path("旋转输出", f"{src.stem}_rotated.pdf")
            rotate_pdf(src, out, 90)
            self._log(f"旋转完成: {out}")
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def _reorder(self):
        try:
            src = self._selected_or_first()
            order_str = self.order_var.get().strip()
            if not order_str:
                messagebox.showwarning("提示", "请输入重排顺序")
                return
            order = [int(x.strip()) for x in order_str.split(",")]
            out = self._save_path("重排输出", f"{src.stem}_reordered.pdf")
            reorder_pdf(src, out, order)
            self._log(f"重排完成: {out}")
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def _text_watermark(self):
        try:
            src = self._selected_or_first()
            text = self.watermark_var.get().strip()
            if not text:
                messagebox.showwarning("提示", "请输入水印文字")
                return
            out = self._save_path("水印输出", f"{src.stem}_watermarked.pdf")
            add_text_watermark(src, out, text)
            self._log(f"文字水印完成: {out}")
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def _image_watermark(self):
        try:
            src = self._selected_or_first()
            img = filedialog.askopenfilename(filetypes=[("图片", "*.png;*.jpg;*.jpeg")])
            if not img:
                return
            out = self._save_path("图片水印输出", f"{src.stem}_img_watermarked.pdf")
            add_image_watermark(src, out, Path(img))
            self._log(f"图片水印完成: {out}")
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def _extract_text(self):
        try:
            src = self._selected_or_first()
            text = extract_text(src)
            win = ttk.Toplevel(self.root)
            win.title("提取的文字")
            win.geometry("700x500")
            st = scrolledtext.ScrolledText(win)
            st.pack(fill=BOTH, expand=True)
            st.insert(tk.END, text)
            self._log(f"提取文字完成，长度 {len(text)}")
        except Exception as e:
            messagebox.showerror("错误", str(e))


def main():
    root = ttk.Window(themename="flatly")
    PDFEditorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
