"""PDF 编辑核心引擎（v0.3.0）。

设计要点
--------
1. **原子保存**：PyMuPDF 打开文件时会持有句柄，直接覆盖原文件会失败并可能
   产出半损坏文件。本模块统一走「临时文件 → ``os.replace``」的原子替换路径，
   保证任何时刻磁盘上的 PDF 都是完整可打开的。
2. **文档级 / 路径级双 API**：``*_doc(doc, ...)`` 直接原地修改已打开的文档，
   供界面「工作副本 + 撤销栈」使用；路径级函数是其薄封装，保持向后兼容。
3. **内存友好**：渲染直接由 ``Pixmap.samples`` 构造图像（免 PNG 编解码往返，
   实测 22ms → 4ms），并提供 ``release_render_cache()`` 释放 MuPDF 全局缓存；
   ``DocumentSession`` 让整篇文档只保留一个句柄，避免反复开关文件。

所有函数接收 ``pathlib.Path``，输出也写入 ``Path``。
"""

from __future__ import annotations

import os
import shutil
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

import pymupdf as fitz
from PIL import Image

__all__ = [
    # 会话
    "DocumentSession",
    "PdfError",
    "PdfPasswordRequired",
    "PdfPasswordError",
    # 基础
    "open_document",
    "save_document",
    "page_count",
    "page_size",
    "render_page_png",
    "render_page_image",
    "release_render_cache",
    # 结构编辑
    "merge_pdfs",
    "split_pdf",
    "rotate_pdf",
    "reorder_pdf",
    "delete_pages",
    "extract_pages",
    "insert_pages",
    "rotate_page",
    "move_page",
    "insert_blank_page",
    "set_page_size",
    # 水印 / 页码 / 页眉页脚
    "add_text_watermark",
    "add_image_watermark",
    "add_page_numbers",
    "add_header_footer",
    # 内容
    "extract_text",
    "extract_text_with_layout",
    "search_text",
    "find_tables",
    "extract_images",
    "export_pages_to_images",
    # 批注
    "ANNOT_KINDS",
    "add_annotation",
    "list_annotations",
    "delete_annotation",
    "clear_annotations",
    "apply_redaction",
    # 属性 / 书签 / 标签
    "get_metadata",
    "set_metadata",
    "get_toc",
    "set_toc",
    "add_bookmark",
    "delete_bookmark",
    "get_page_labels",
    "set_page_labels",
    # 优化 / 加密
    "compress_document",
    "set_encryption",
    "remove_encryption",
]

VERSION = "0.3.0"


# ====================================================================== 异常
class PdfError(Exception):
    """PDF 引擎业务异常基类。"""


class PdfPasswordRequired(PdfError):
    """文档已加密，需要提供打开口令。"""


class PdfPasswordError(PdfError):
    """口令错误。"""


# ================================================================ 内部工具
def _ensure_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _atomic_save(doc: fitz.Document, output_path: Path, **save_kwargs: Any) -> Path:
    """把 ``doc`` 原子写入 ``output_path``（临时文件 + os.replace）。"""
    output_path = Path(output_path)
    _ensure_dir(output_path)
    fd, tmp_name = tempfile.mkstemp(
        suffix=".pdf.tmp", prefix=".pdfedit-", dir=str(output_path.parent)
    )
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        doc.save(str(tmp), **save_kwargs)
        last_err: Exception | None = None
        for attempt in range(4):
            try:
                os.replace(tmp, output_path)
                return output_path
            except PermissionError as exc:  # 目标被其他程序占用
                last_err = exc
                time.sleep(0.25 * (attempt + 1))
        raise PdfError(
            f"无法写入目标文件（可能被其他程序占用）：{output_path}\n{last_err}"
        )
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def _default_permissions() -> int:
    """默认权限：允许打印/复制/批注/无障碍，禁止修改与整理页面。"""
    return (
        _perm("PDF_PERM_PRINT")
        | _perm("PDF_PERM_PRINT_HQ")
        | _perm("PDF_PERM_COPY")
        | _perm("PDF_PERM_ANNOTATE")
        | _perm("PDF_PERM_ACCESSIBILITY")
    )


def _perm(name: str) -> int:
    """兼容不同 PyMuPDF 版本取权限常量。"""
    val = getattr(fitz, name, None)
    if val is None:
        val = getattr(fitz, name.replace("PDF_PERM_", "PDF_PERM_"), 0)
    return int(val or 0)


def _check_pages(doc: fitz.Document, pages: Iterable[int]) -> list[int]:
    total = len(doc)
    pages = [int(p) for p in pages]
    bad = [p for p in pages if p < 1 or p > total]
    if bad:
        raise ValueError(f"无效页码 {bad}，总页数 {total}")
    return pages


@contextmanager
def _as_document(source: "fitz.Document | Path | str") -> Iterator[tuple[fitz.Document, bool]]:
    """把「已打开的文档」或「文件路径」统一成 ``(doc, owned)``。

    ``owned=True`` 表示文档是本函数打开的，退出时需要关闭；调用方据此
    决定是否 close，避免误关调用者自己的句柄。这样读取类 API 既能接收
    ``Path``（脚本用法），也能直接接收界面持有的 ``fitz.Document``
    （避免重复开关文件）。
    """
    if isinstance(source, fitz.Document):
        yield source, False
        return
    doc = open_document(source)
    try:
        yield doc, True
    finally:
        doc.close()


def _cjk_fontfile() -> str | None:
    """返回可用的中文字体文件路径，找不到则返回 None。

    候选顺序按「ASCII 保真度」排列：部分 TrueType 字体集合（如
    ``msyh.ttc`` / 微软雅黑）在被 PyMuPDF 内嵌时，会把 ASCII 空格映射为
    不换行空格 ``U+00A0``、连字符映射为 ``U+2010``，导致生成的页码 /
    水印在「查找」和「复制文本」时匹配失败。``simhei.ttf`` /
    ``simsun.ttc`` 等单体或映射正确的字体不存在该问题，因此优先选用；
    列表顺序仍由 :func:`_font_ascii_safe` 二次校验兜底。
    """
    import sys

    candidates = [
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
        r"C:\Windows\Fonts\Deng.ttf",
        r"C:\Windows\Fonts\simkai.ttf",
        r"C:\Windows\Fonts\simfang.ttf",
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\msyhbd.ttc",
        r"C:\Windows\Fonts\msjh.ttc",
    ]
    if sys.platform == "darwin":
        candidates = [
            "/System/Library/Fonts/PingFang.ttc",
            "/Library/Fonts/Arial Unicode.ttf",
        ] + candidates
    else:
        candidates += [
            "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        ]
    for c in candidates:
        if Path(c).exists():
            return c
    return None


# ASCII 保真度缓存：fontfile -> bool
_ASCII_SAFE_CACHE: dict[str, bool] = {}

# 探测文本：覆盖最容易出问题的空格与连字符
_ASCII_PROBE = "A 1 - z"


def _font_ascii_safe(fontfile: str) -> bool:
    """校验字体内嵌后能否原样还原 ASCII 空格与连字符。

    少数字体（如微软雅黑 TTC）在 PyMuPDF 写 ToUnicode 表时会把 ``U+0020``
    写成 ``U+00A0``，从而使页码、水印、页眉页脚中的空格无法被搜索/复制。
    这里做一次极小规模的「写入 → 重新打开 → 读取」往返校验，
    结果按字体路径缓存，避免每次调用都付出代价。
    """
    cached = _ASCII_SAFE_CACHE.get(fontfile)
    if cached is not None:
        return cached
    ok = False
    try:
        fnt = fitz.Font(fontfile=fontfile)
        scratch = fitz.open()
        try:
            page = scratch.new_page(width=200, height=60)
            writer = fitz.TextWriter(page.rect)
            writer.append(fitz.Point(10, 40), _ASCII_PROBE, font=fnt, fontsize=10)
            writer.write_text(page)
            data = scratch.tobytes()
        finally:
            scratch.close()
        probe = fitz.open(stream=data, filetype="pdf")
        try:
            text = probe[0].get_text() if len(probe) else ""
        finally:
            probe.close()
        ok = _ASCII_PROBE in text
    except Exception:
        ok = False
    _ASCII_SAFE_CACHE[fontfile] = ok
    return ok


def _font_for(text: str) -> tuple[Any, str]:
    """按文本内容挑选字体，返回 (fitz.Font, 名字)。

    中文/非 ASCII 文本优先系统 CJK 字体，找不到则回退 PyMuPDF 内置
    ``china-s``，保证不乱码。系统字体还会做一次 ASCII 保真校验，
    确保写出的空格/连字符可被搜索与复制。
    """
    is_cjk = any(ord(ch) > 127 for ch in text)
    if is_cjk:
        f = _cjk_fontfile()
        if f and _font_ascii_safe(f):
            return fitz.Font(fontfile=f), "cjk"
        return fitz.Font("china-s"), "china-s"
    return fitz.Font("helv"), "helv"


# ==================================================================== 会话
class DocumentSession:
    """带工作副本与撤销/重做栈的文档会话。

    原文件在整个编辑过程中**始终不被触碰**：所有修改都发生在临时工作副本上，
    只有用户点击「保存」时才原子写回目标路径。每次修改前自动生成快照，
    因而天然具备撤销/重做能力。
    """

    def __init__(
        self,
        path: Path | str | None = None,
        password: str | None = None,
        *,
        max_undo_steps: int = 20,
        max_undo_bytes: int = 96 * 1024 * 1024,
    ):
        self.source: Path | None = None
        self.work_path: Path | None = None
        self.doc: fitz.Document | None = None
        self.password = password
        self.dirty = False
        self._undo: list[bytes] = []
        self._redo: list[bytes] = []
        self._undo_bytes = 0
        self.max_undo_steps = max_undo_steps
        self.max_undo_bytes = max_undo_bytes
        self._tmpdir: Path | None = None
        self._new_tmpdir()
        if path is not None:
            self.open(path, password)

    # ---------------------------------------------------------- 生命周期
    def _new_tmpdir(self) -> None:
        """为工作副本准备新的临时目录。"""
        self._tmpdir = Path(tempfile.mkdtemp(prefix="pdfedit-work-"))

    def open(self, path: Path | str, password: str | None = None) -> None:
        """打开文档（复制为工作副本，原文件只读不改）。"""
        self.close()
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"找不到文件: {path}")
        if self._tmpdir is None:
            self._new_tmpdir()
        # 先以源文件校验与解密
        probe = _open_raw(path)
        try:
            if probe.needs_pass:
                pw = password if password is not None else self.password
                if not pw:
                    raise PdfPasswordRequired(f"文档已加密，请输入打开口令：{path.name}")
                if not probe.authenticate(pw):
                    raise PdfPasswordError("口令错误，无法打开该 PDF")
            self.password = password if password is not None else self.password
            self.source = path
            work = self._tmpdir / path.name
            if probe.needs_pass:
                probe.save(str(work))  # 解密后写入工作副本
            else:
                probe.close()
                shutil.copyfile(path, work)
        finally:
            try:
                probe.close()
            except Exception:
                pass
        self.work_path = work
        self.doc = _open_raw(work)
        self.dirty = False
        self._clear_history()

    def close(self) -> None:
        """关闭句柄并清理工作副本目录（可再次 ``open`` 复用本会话）。"""
        if self.doc is not None:
            try:
                self.doc.close()
            except Exception:
                pass
            self.doc = None
        self.work_path = None
        if self._tmpdir is not None and self._tmpdir.exists():
            shutil.rmtree(self._tmpdir, ignore_errors=True)
            self._tmpdir = None
        release_render_cache()

    def reopen(self) -> None:
        """重新打开工作副本（丢失 MuPDF 内部状态时使用）。"""
        if self.work_path is None:
            return
        pos = self.doc.page_count if self.doc else 0
        if self.doc is not None:
            self.doc.close()
        self.doc = fitz.open(self.work_path)
        release_render_cache()

    @property
    def is_open(self) -> bool:
        return self.doc is not None

    @property
    def page_count(self) -> int:
        return len(self.doc) if self.doc else 0

    # ------------------------------------------------------------ 快照
    def _clear_history(self) -> None:
        self._undo.clear()
        self._redo.clear()
        self._undo_bytes = 0

    def push_undo(self) -> bool:
        """在修改前记录快照。返回 False 表示文档过大已放弃撤销能力。"""
        if self.doc is None:
            return False
        try:
            data = self.doc.tobytes(deflate=True, garbage=3)
        except Exception:
            return False
        if len(data) > self.max_undo_bytes:
            self._clear_history()
            return False
        self._undo.append(data)
        self._undo_bytes += len(data)
        while len(self._undo) > self.max_undo_steps or (
            self._undo_bytes > self.max_undo_bytes and len(self._undo) > 1
        ):
            self._undo_bytes -= len(self._undo.pop(0))
        self._redo.clear()
        self.dirty = True
        return True

    def _load_bytes(self, data: bytes) -> None:
        if self.doc is not None:
            self.doc.close()
        try:
            self.doc = fitz.open(stream=data, filetype="pdf")
        except Exception as exc:  # noqa: BLE001
            raise PdfError("撤销/重做时重建文档失败（快照已损坏）") from exc
        release_render_cache()

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self) -> bool:
        if not self._undo or self.doc is None:
            return False
        self._redo.append(self.doc.tobytes(deflate=True, garbage=3))
        self._load_bytes(self._undo.pop())
        self.dirty = True
        return True

    def redo(self) -> bool:
        if not self._redo or self.doc is None:
            return False
        self._undo.append(self.doc.tobytes(deflate=True, garbage=3))
        self._load_bytes(self._redo.pop())
        self.dirty = True
        return True

    def sync_work(self) -> None:
        """把内存中的文档内容刷新到工作副本（供需要路径的操作使用）。"""
        if self.doc is None or self.work_path is None:
            return
        staging = self.work_path.with_suffix(".staging.pdf")
        _atomic_save(self.doc, staging)
        try:
            self.doc.close()
        except Exception:
            pass
        os.replace(staging, self.work_path)
        self.doc = fitz.open(self.work_path)
        release_render_cache()

    # ------------------------------------------------------------ 保存
    def save(self, target: Path | str | None = None, **kwargs: Any) -> Path:
        """保存到 ``target``（默认原路径）。原文件仅在此时被原子替换。"""
        if self.doc is None:
            raise PdfError("没有已打开的文档")
        target = Path(target) if target else self.source
        if target is None:
            raise PdfError("未指定保存路径")
        same_as_source = (
            self.source is not None and target.resolve() == self.source.resolve()
        )
        save_document(self.doc, target, **kwargs)
        self.dirty = False
        if same_as_source:
            self._resync_work()
        return target

    def _resync_work(self) -> None:
        """覆盖原文件后，用最新内容重建工作副本（保持句柄一致）。"""
        if self.source is None:
            return
        if self.work_path is not None and self.doc is not None:
            try:
                self.doc.close()
            except Exception:
                pass
            self.doc = None
            try:
                shutil.copyfile(self.source, self.work_path)
            except OSError:
                pass
            self.doc = fitz.open(self.work_path)
            release_render_cache()

    # ------------------------------------------------------------ 上下文
    def __enter__(self) -> "DocumentSession":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


# ================================================================== 基础
def _open_raw(path: Path) -> "fitz.Document":
    """底层打开，把 PyMuPDF 的各类原始异常统一包装为 :class:`PdfError`。

    这样调用方（尤其是界面层）只需捕获 ``PdfError`` 即可，
    不会因为底层抛出 ``FileDataError`` / ``EmptyFileError`` 等
    未预料类型而导致程序崩溃。
    """
    try:
        return fitz.open(path)
    except Exception as exc:  # noqa: BLE001
        raise PdfError(f"无法打开 PDF（文件可能损坏或不是有效的 PDF）：{path.name}") from exc


def open_document(path: Path | str, password: str | None = None) -> fitz.Document:
    """打开 PDF（自动处理加密）。返回的文档支持 ``with`` 语句。"""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"找不到文件: {path}")
    if path.is_dir():
        raise PdfError(f"这是一个目录而非文件：{path}")
    doc = _open_raw(path)
    try:
        if doc.needs_pass:
            if not password:
                raise PdfPasswordRequired(f"文档已加密，请输入打开口令：{path.name}")
            if not doc.authenticate(password):
                raise PdfPasswordError("口令错误，无法打开该 PDF")
    except Exception:
        try:
            doc.close()
        except Exception:
            pass
        raise
    return doc


def save_document(
    doc: fitz.Document,
    output_path: Path | str,
    *,
    compress: bool = False,
    user_password: str | None = None,
    owner_password: str | None = None,
    permissions: int | None = None,
    garbage: int | None = None,
    deflate: bool = True,
) -> Path:
    """保存文档（原子写入）。

    - ``compress=True``：额外做对象清理与字体子集化，尽量减小体积。
    - ``user_password`` / ``owner_password``：写出加密 PDF。
    """
    kwargs: dict[str, Any] = {
        "garbage": 4 if compress else (garbage if garbage is not None else 3),
        "deflate": deflate,
        "clean": True,
        "deflate_images": compress,
        "deflate_fonts": compress,
    }
    if compress:
        try:
            doc.subset_fonts()
        except Exception:
            pass
    if user_password or owner_password:
        kwargs.update(
            encryption=fitz.PDF_ENCRYPT_AES_256,
            owner_pw=owner_password or user_password or "",
            user_pw=user_password or "",
            permissions=_default_permissions() if permissions is None else int(permissions),
        )
    return _atomic_save(doc, Path(output_path), **kwargs)


def page_count(input_path: Path | str, password: str | None = None) -> int:
    """返回 PDF 总页数。"""
    with open_document(input_path, password) as doc:
        return len(doc)


def page_size(input_path: Path | str, page: int = 1) -> tuple[float, float]:
    """返回指定页的 (宽, 高) 点值（1 开始）。"""
    with open_document(input_path) as doc:
        _check_pages(doc, [page])
        r = doc[page - 1].rect
        return r.width, r.height


def render_page_png(
    input_path: Path | str, page: int, *, zoom: float = 1.0, password: str | None = None
) -> bytes:
    """把指定页渲染为 PNG 字节流（兼容旧接口）。"""
    with open_document(input_path, password) as doc:
        _check_pages(doc, [page])
        return doc[page - 1].get_pixmap(matrix=fitz.Matrix(zoom, zoom)).tobytes("png")


def page_image(
    page: fitz.Page,
    zoom: float = 1.0,
    *,
    max_pixels: int = 12_000_000,
    alpha: bool = False,
) -> Image.Image:
    """把已打开的 ``fitz.Page`` 渲染为 PIL 图像。

    直接使用 ``Pixmap.samples`` 构造图像，省掉 PNG 编码/解码往返；
    并通过 ``max_pixels`` 限制单张预览的像素总量以控制内存。

    注意：像素数用 ``fitz.IRect`` 严格控制，避免 PIL 舍入导致
    ``max_pixels`` 被略微突破（1px 也可能触发断言/内存超限）。
    """
    rect = page.rect
    w = max(1.0, rect.width * zoom)
    h = max(1.0, rect.height * zoom)
    if max_pixels > 0 and w * h > max_pixels:
        scale = (max_pixels / (w * h)) ** 0.5
        w *= scale
        h *= scale
    # 先取整得到目标像素尺寸，再由像素尺寸反推矩阵。
    # 这样 pixmap 的宽高必然 <= max_pixels（int 向下取整），
    # 且不能用 clip —— clip 作用于未缩放的页面坐标系，会放大出更大的图。
    tw, th = max(1, int(w)), max(1, int(h))
    matrix = fitz.Matrix(tw / rect.width, th / rect.height)
    pix = page.get_pixmap(matrix=matrix, alpha=alpha)
    mode = "RGBA" if pix.alpha else ("RGB" if pix.n >= 3 else "L")
    if mode == "RGBA":
        return Image.frombytes("RGBA", (pix.width, pix.height), pix.samples)
    if mode == "RGB":
        return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    return Image.frombytes("L", (pix.width, pix.height), pix.samples)


def render_page_image(
    input_path: Path | str,
    page: int,
    *,
    zoom: float = 1.0,
    max_pixels: int = 12_000_000,
    password: str | None = None,
) -> Image.Image:
    """渲染指定页为 PIL 图像（打开 → 渲染 → 关闭）。"""
    with open_document(input_path, password) as doc:
        _check_pages(doc, [page])
        return page_image(doc[page - 1], zoom, max_pixels=max_pixels)


def release_render_cache() -> None:
    """释放 MuPDF 全局渲染缓存，降低常驻内存。"""
    try:
        fitz.TOOLS.store_shrink(100)
    except Exception:
        pass


# ============================================================ 结构编辑
def merge_pdfs(input_paths: Sequence[Path], output_path: Path) -> None:
    """合并多个 PDF 文件为一个。"""
    if not input_paths:
        raise ValueError("至少需要一个输入文件")
    merged = fitz.open()
    try:
        for p in input_paths:
            with open_document(p) as src:
                merged.insert_pdf(src)
        save_document(merged, output_path)
    finally:
        merged.close()


def merge_documents(docs: Sequence[fitz.Document]) -> fitz.Document:
    """把多个已打开的文档合并为一个新文档（不落盘）。"""
    merged = fitz.open()
    for d in docs:
        merged.insert_pdf(d)
    return merged


def split_pdf(
    input_path: Path, output_dir: Path, ranges: Sequence[tuple[int, int]]
) -> list[Path]:
    """按页码范围拆分 PDF。``ranges`` 为 ``[(起, 止), ...]``，页码 1 开始闭区间。"""
    if not Path(input_path).exists():
        raise FileNotFoundError(f"找不到文件: {input_path}")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_paths: list[Path] = []
    with open_document(input_path) as doc:
        total = len(doc)
        for idx, (start, end) in enumerate(ranges, start=1):
            if start < 1 or end > total or start > end:
                raise ValueError(f"无效页码范围 {start}-{end}，总页数 {total}")
            new_doc = fitz.open()
            new_doc.insert_pdf(doc, from_page=start - 1, to_page=end - 1)
            out_path = output_dir / f"{Path(input_path).stem}_part{idx}_{start}-{end}.pdf"
            save_document(new_doc, out_path)
            new_doc.close()
            out_paths.append(out_path)
    return out_paths


def split_document(
    doc: fitz.Document, mode: str = "each", *, every: int = 1, ranges: Sequence[tuple[int, int]] = ()
) -> list[fitz.Document]:
    """按模式把一个文档拆成多个新文档。

    mode: ``each`` 每页一个 / ``every`` 每 N 页一个 / ``ranges`` 按给定范围。
    """
    total = len(doc)
    groups: list[tuple[int, int]] = []
    if mode == "ranges":
        groups = [tuple(r) for r in ranges]  # type: ignore[assignment]
    elif mode == "every":
        step = max(1, int(every))
        for start in range(0, total, step):
            groups.append((start + 1, min(start + step, total)))
    else:
        groups = [(i, i) for i in range(1, total + 1)]
    result = []
    for start, end in groups:
        if start < 1 or end > total or start > end:
            raise ValueError(f"无效页码范围 {start}-{end}，总页数 {total}")
        nd = fitz.open()
        nd.insert_pdf(doc, from_page=start - 1, to_page=end - 1)
        result.append(nd)
    return result


def rotate_pdf(
    input_path: Path, output_path: Path, angle: int, pages: Sequence[int] | None = None
) -> None:
    """旋转 PDF 页面。``angle`` 为 90/180/270（顺时针）；``pages=None`` 表示全部。"""
    with open_document(input_path) as doc:
        rotate_document(doc, angle, pages)
        save_document(doc, output_path)


def rotate_document(
    doc: fitz.Document, angle: int, pages: Sequence[int] | None = None
) -> None:
    """原地旋转页面。"""
    if angle % 90 != 0:
        raise ValueError("旋转角度必须是 90 的倍数")
    total = len(doc)
    target = list(pages) if pages else list(range(1, total + 1))
    _check_pages(doc, target)
    for p in target:
        pg = doc[p - 1]
        pg.set_rotation((pg.rotation + angle) % 360)


def reorder_pdf(input_path: Path, output_path: Path, order: Sequence[int]) -> None:
    """按指定顺序重排 PDF 页面。``order`` 必须是 1..N 的排列。"""
    with open_document(input_path) as doc:
        reorder_document(doc, order)
        save_document(doc, output_path)


def reorder_document(doc: fitz.Document, order: Sequence[int]) -> None:
    """原地重排页面。"""
    total = len(doc)
    if sorted(int(x) for x in order) != list(range(1, total + 1)):
        raise ValueError(f"order 必须是 1 到 {total} 的排列")
    doc.select([int(p) - 1 for p in order])


def delete_pages(input_path: Path, output_path: Path, pages: Sequence[int]) -> None:
    """删除指定页码（1 开始），输出为新文件。不允许删除全部页面。"""
    with open_document(input_path) as doc:
        delete_document_pages(doc, pages)
        save_document(doc, output_path)


def delete_document_pages(doc: fitz.Document, pages: Sequence[int]) -> None:
    """原地删除页面。"""
    total = len(doc)
    pages = _check_pages(doc, pages)
    if len(set(pages)) >= total:
        raise ValueError("不能删除全部页面")
    for p in sorted(set(pages), reverse=True):
        doc.delete_page(p - 1)


def extract_pages(input_path: Path, output_path: Path, pages: Sequence[int]) -> None:
    """提取指定页码另存为新 PDF，保持给定顺序。"""
    with open_document(input_path) as doc:
        new_doc = extract_document_pages(doc, pages)
        try:
            save_document(new_doc, output_path)
        finally:
            new_doc.close()


def extract_document_pages(doc: fitz.Document, pages: Sequence[int]) -> fitz.Document:
    """提取页面为新的独立文档。"""
    if not pages:
        raise ValueError("至少需要选择 1 页")
    pages = _check_pages(doc, pages)
    nd = fitz.open()
    for p in pages:
        nd.insert_pdf(doc, from_page=p - 1, to_page=p - 1)
    return nd


def insert_pages(
    input_path: Path, output_path: Path, source_path: Path, *, at: int = -1
) -> None:
    """把 ``source_path`` 的全部页面插入到 ``at`` 位置之后（``at=-1`` 末尾、``0`` 最前）。"""
    with open_document(input_path) as doc:
        with open_document(source_path) as src:
            insert_document(doc, src, at=at)
        save_document(doc, output_path)


def insert_document(doc: fitz.Document, src: fitz.Document, *, at: int = -1) -> None:
    """原地插入另一个文档的页面。``at`` 会被裁剪到合法范围。"""
    total = len(doc)
    pos = total if at is None or at < 0 else min(int(at), total)
    doc.insert_pdf(src, start_at=pos)


def rotate_page(input_path: Path, output_path: Path, page: int, angle: int) -> None:
    """旋转单页（1 开始）。``angle``：90/180/270（顺时针）。"""
    with open_document(input_path) as doc:
        rotate_document(doc, angle, [page])
        save_document(doc, output_path)


def move_page(input_path: Path, output_path: Path, page: int, to: int) -> None:
    """把第 ``page`` 页移动到第 ``to`` 页位置（1 开始）。"""
    with open_document(input_path) as doc:
        move_document_page(doc, page, to)
        save_document(doc, output_path)


def move_document_page(doc: fitz.Document, page: int, to: int) -> None:
    """原地移动页面：把第 ``page`` 页放到第 ``to`` 页的位置（均为 1 开始）。

    这里用 ``select`` 显式重排，而不是依赖 ``Document.move_page``——
    后者的 ``to`` 索引语义与「第几页」不一致（实测 ``move_page(0, 3)``
    会落到第 3 位而非第 4 位），容易让用户感到「移错了位置」。
    """
    _check_pages(doc, [page, to])
    order = list(range(1, len(doc) + 1))
    order.remove(page)
    order.insert(to - 1, page)
    doc.select([p - 1 for p in order])


def insert_blank_page(
    input_path: Path, output_path: Path, *, at: int = -1, size: str = "a4"
) -> None:
    """插入空白页。``size`` 支持 ``a4`` / ``a3`` / ``letter`` / ``same``。"""
    with open_document(input_path) as doc:
        insert_blank_document_page(doc, at=at, size=size)
        save_document(doc, output_path)


_PAGE_SIZES = {
    "a3": (842, 1191),
    "a4": (595, 842),
    "a5": (420, 595),
    "letter": (612, 792),
    "legal": (612, 1008),
}


def insert_blank_document_page(
    doc: fitz.Document, *, at: int = -1, size: str = "a4"
) -> int:
    """原地插入空白页，返回新页页码（1 开始）。"""
    total = len(doc)
    pos = total if at is None or at < 0 else min(max(int(at), 0), total)
    if size == "same" and total:
        r = doc[min(pos, total - 1)].rect
        w, h = r.width, r.height
    else:
        w, h = _PAGE_SIZES.get(str(size).lower(), _PAGE_SIZES["a4"])
    doc.new_page(pno=pos, width=w, height=h)
    return pos + 1


def set_page_size(
    input_path: Path, output_path: Path, size: str, *, pages: Sequence[int] | None = None
) -> None:
    """统一页面尺寸（修改 MediaBox，不缩放内容）。"""
    with open_document(input_path) as doc:
        set_document_page_size(doc, size, pages)
        save_document(doc, output_path)


def set_document_page_size(
    doc: fitz.Document, size: str, pages: Sequence[int] | None = None
) -> None:
    """原地修改页面尺寸。"""
    if str(size).lower() not in _PAGE_SIZES:
        raise ValueError(f"不支持的页面尺寸: {size}")
    w, h = _PAGE_SIZES[str(size).lower()]
    total = len(doc)
    for p in (_check_pages(doc, pages) if pages else range(1, total + 1)):
        doc[p - 1].set_mediabox(fitz.Rect(0, 0, w, h))


# ======================================================= 水印 / 页码
def add_text_watermark(
    input_path: Path,
    output_path: Path,
    text: str,
    *,
    opacity: float = 0.3,
    angle: int = 45,
    font_size: int = 48,
    color: tuple[float, float, float] = (0.5, 0.5, 0.5),
    pages: Sequence[int] | None = None,
) -> None:
    """为页面添加居中文字水印（支持中文与任意角度）。"""
    with open_document(input_path) as doc:
        text_watermark_document(
            doc, text, opacity=opacity, angle=angle, font_size=font_size,
            color=color, pages=pages,
        )
        save_document(doc, output_path)


def text_watermark_document(
    doc: fitz.Document,
    text: str,
    *,
    opacity: float = 0.3,
    angle: int = 45,
    font_size: int = 48,
    color: tuple[float, float, float] = (0.5, 0.5, 0.5),
    pages: Sequence[int] | None = None,
) -> None:
    """原地添加文字水印。

    通过在原点试排一次取得精确包围盒，把文字中心对齐到页面中心，
    再用 ``morph`` 旋转矩阵实现任意角度斜水印（不依赖 90° 取整）。
    """
    if not text:
        raise ValueError("水印文字不能为空")
    total = len(doc)
    target = _check_pages(doc, pages) if pages else list(range(1, total + 1))
    fnt, _ = _font_for(text)  # 字体对象复用，避免逐页重复加载
    for p in target:
        page = doc[p - 1]
        rect = page.rect
        cx, cy = rect.x0 + rect.width / 2, rect.y0 + rect.height / 2
        probe = fitz.TextWriter(rect)
        probe.append(fitz.Point(0, 0), text, font=fnt, fontsize=font_size)
        box = probe.text_rect
        bx = (box.x0 + box.x1) / 2
        by = (box.y0 + box.y1) / 2
        tw = fitz.TextWriter(rect, opacity=opacity)
        tw.append(fitz.Point(cx - bx, cy - by), text, font=fnt, fontsize=font_size)
        morph = (fitz.Point(cx, cy), fitz.Matrix(angle)) if angle % 360 else None
        tw.write_text(page, color=color, morph=morph)


def add_image_watermark(
    input_path: Path,
    output_path: Path,
    image_path: Path,
    *,
    opacity: float = 0.3,
    scale: float = 0.4,
    angle: int = 0,
    pages: Sequence[int] | None = None,
) -> None:
    """为页面添加图片水印（居中，可调不透明度/大小/旋转）。"""
    with open_document(input_path) as doc:
        image_watermark_document(
            doc, image_path, opacity=opacity, scale=scale, angle=angle, pages=pages
        )
        save_document(doc, output_path)


def image_watermark_document(
    doc: fitz.Document,
    image_path: Path,
    *,
    opacity: float = 0.3,
    scale: float = 0.4,
    angle: int = 0,
    pages: Sequence[int] | None = None,
) -> None:
    """原地添加图片水印。

    PyMuPDF 的 ``insert_image`` 不接受透明度参数，因此先用 Pillow 把图片
    的 alpha 通道按 ``opacity`` 缩放，再以流的形式嵌入，从而真正生效。
    """
    image_path = Path(image_path)
    if not image_path.exists():
        raise FileNotFoundError(f"找不到图片: {image_path}")
    img = Image.open(image_path).convert("RGBA")
    alpha = img.split()[3].point(lambda a: int(a * max(0.0, min(opacity, 1.0))))
    img.putalpha(alpha)
    if angle:
        img = img.rotate(angle, expand=True, resample=Image.BICUBIC)
    import io as _io

    buf = _io.BytesIO()
    img.save(buf, format="PNG")
    data = buf.getvalue()
    img.close()
    buf.close()

    total = len(doc)
    target = _check_pages(doc, pages) if pages else list(range(1, total + 1))
    for p in target:
        page = doc[p - 1]
        rect = page.rect
        w = rect.width * max(0.05, min(scale, 1.0))
        h = w * (img.height / img.width) if img.width else w
        if h > rect.height * 0.95:
            h = rect.height * 0.95
            w = h * (img.width / img.height)
        box = fitz.Rect(
            rect.x0 + (rect.width - w) / 2,
            rect.y0 + (rect.height - h) / 2,
            rect.x0 + (rect.width + w) / 2,
            rect.y0 + (rect.height + h) / 2,
        )
        page.insert_image(box, stream=data, overlay=True)


_POSITIONS = (
    "top-left", "top-center", "top-right",
    "bottom-left", "bottom-center", "bottom-right",
    "center",
)


def _stamp_single_line(
    page: fitz.Page, text: str, position: str, font_size: int,
    color: tuple[float, float, float], margin: float,
) -> None:
    """在页面的指定位置写一行文字（用于页码 / 页眉页脚）。"""
    fnt, _ = _font_for(text)
    probe = fitz.TextWriter(page.rect)
    probe.append(fitz.Point(0, 0), text, font=fnt, fontsize=font_size)
    tb = probe.text_rect
    text_width = fnt.text_length(text, fontsize=font_size)
    text_height = tb.y1 - tb.y0
    x0, y0, x1, y1 = page.rect.x0, page.rect.y0, page.rect.x1, page.rect.y1

    if position.endswith("left"):
        x = x0 + margin
    elif position.endswith("right"):
        x = x1 - margin - text_width
    else:
        x = (x0 + x1) / 2 - text_width / 2

    if position.startswith("top"):
        y = y0 + margin + text_height
    elif position.startswith("bottom"):
        y = y1 - margin
    else:
        y = (y0 + y1) / 2 + text_height / 2

    writer = fitz.TextWriter(page.rect)
    writer.append(fitz.Point(x, y), text, font=fnt, fontsize=font_size)
    writer.write_text(page, color=color)


def add_page_numbers(
    input_path: Path,
    output_path: Path,
    *,
    pattern: str = "第 {page} 页 / 共 {total} 页",
    position: str = "bottom-center",
    start: int = 1,
    font_size: int = 10,
    color: tuple[float, float, float] = (0.25, 0.25, 0.25),
    margin: float = 28,
    skip_first: bool = False,
    pages: Sequence[int] | None = None,
) -> None:
    """插入页码。``pattern`` 支持 ``{page}`` / ``{total}`` 占位符。"""
    with open_document(input_path) as doc:
        page_numbers_document(
            doc, pattern=pattern, position=position, start=start,
            font_size=font_size, color=color, margin=margin,
            skip_first=skip_first, pages=pages,
        )
        save_document(doc, output_path)


def page_numbers_document(
    doc: fitz.Document,
    *,
    pattern: str = "第 {page} 页 / 共 {total} 页",
    position: str = "bottom-center",
    start: int = 1,
    font_size: int = 10,
    color: tuple[float, float, float] = (0.25, 0.25, 0.25),
    margin: float = 28,
    skip_first: bool = False,
    pages: Sequence[int] | None = None,
) -> None:
    """原地插入页码。"""
    if position not in _POSITIONS:
        raise ValueError(f"不支持的位置: {position}")
    total = len(doc)
    target = _check_pages(doc, pages) if pages else list(range(1, total + 1))
    for i, p in enumerate(target):
        if skip_first and i == 0:
            continue
        txt = pattern.replace("{page}", str(start + i)).replace("{total}", str(total))
        _stamp_single_line(doc[p - 1], txt, position, font_size, color, margin)


def add_header_footer(
    input_path: Path,
    output_path: Path,
    *,
    header: str | None = None,
    footer: str | None = None,
    font_size: int = 9,
    color: tuple[float, float, float] = (0.35, 0.35, 0.35),
    margin: float = 24,
    header_position: str = "top-center",
    footer_position: str = "bottom-center",
) -> None:
    """批量添加页眉/页脚。支持 ``{page}`` / ``{total}`` / ``{name}`` 占位符。"""
    with open_document(input_path) as doc:
        header_footer_document(
            doc, header=header, footer=footer, font_size=font_size,
            color=color, margin=margin, name=Path(input_path).name,
            header_position=header_position, footer_position=footer_position,
        )
        save_document(doc, output_path)


def header_footer_document(
    doc: fitz.Document,
    *,
    header: str | None = None,
    footer: str | None = None,
    font_size: int = 9,
    color: tuple[float, float, float] = (0.35, 0.35, 0.35),
    margin: float = 24,
    name: str = "",
    header_position: str = "top-center",
    footer_position: str = "bottom-center",
) -> None:
    """原地添加页眉/页脚。

    ``header_position`` / ``footer_position`` 可取 ``top``/``bottom`` 与
    ``left``/``center``/``right`` 的组合（如 ``bottom-left``）。
    当页脚与页码同时使用时，把页脚设为 ``bottom-left`` 或 ``bottom-right``
    可避免两者在同一位置重叠。
    """
    if header_position not in _POSITIONS:
        raise ValueError(f"不支持的页眉位置: {header_position}")
    if footer_position not in _POSITIONS:
        raise ValueError(f"不支持的页脚位置: {footer_position}")
    total = len(doc)
    for i in range(1, total + 1):
        page = doc[i - 1]
        for text, position in ((header, header_position), (footer, footer_position)):
            if not text:
                continue
            txt = (
                text.replace("{page}", str(i))
                .replace("{total}", str(total))
                .replace("{name}", name)
            )
            _stamp_single_line(page, txt, position, font_size, color, margin)


# ================================================================== 内容
def extract_text(input_path: Path, pages: Sequence[int] | None = None) -> str:
    """提取 PDF 纯文本。"""
    with open_document(input_path) as doc:
        return extract_document_text(doc, pages)


def extract_document_text(
    doc: fitz.Document, pages: Sequence[int] | None = None
) -> str:
    """提取已打开文档的纯文本。"""
    total = len(doc)
    target = _check_pages(doc, pages) if pages else list(range(1, total + 1))
    parts = [doc[p - 1].get_text("text") for p in target]
    return "\n".join(parts)


def extract_text_with_layout(
    input_path: Path, pages: Sequence[int] | None = None
) -> str:
    """按版面（保留大致空白与换行）提取文本，适合表格/排版类文档。"""
    with open_document(input_path) as doc:
        total = len(doc)
        target = _check_pages(doc, pages) if pages else list(range(1, total + 1))
        parts = []
        for p in target:
            parts.append(f"===== 第 {p} 页 =====\n" + doc[p - 1].get_text("text"))
        return "\n".join(parts)


def extract_pages_to_files(
    input_path: Path, out_dir: Path, pages: Sequence[int] | None = None
) -> list[Path]:
    """把每页文本导出为独立的 .txt 文件。"""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(input_path).stem
    written: list[Path] = []
    with open_document(input_path) as doc:
        total = len(doc)
        target = _check_pages(doc, pages) if pages else list(range(1, total + 1))
        for p in target:
            f = out_dir / f"{stem}_p{p:03d}.txt"
            f.write_text(doc[p - 1].get_text("text"), encoding="utf-8")
            written.append(f)
    return written


@dataclass
class SearchHit:
    """一处搜索结果。"""

    page: int
    rects: list[tuple[float, float, float, float]] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.rects)


def _search_case_sensitive(
    page: "fitz.Page", needle: str, limit: int
) -> list[fitz.Rect]:
    """在单页内做**区分大小写**的精确查找。

    PyMuPDF 的 ``Page.search_for()`` 固定大小写不敏感且无开关可调，
    因此这里退回到字符级匹配：``get_text("rawdict")`` 能拿到每个字符的
    包围盒，按 span 文本做 ``str.find`` 即可得到精确命中位置。
    代价略高于 ``search_for``，仅在用户显式要求区分大小写时启用。
    """
    out: list[fitz.Rect] = []
    if not needle:
        return out
    try:
        raw = page.get_text("rawdict")
    except Exception:
        return out
    for block in raw.get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                chars = span.get("chars") or []
                if len(chars) < len(needle):
                    continue
                span_text = "".join(ch.get("c", "") for ch in chars)
                start = 0
                while True:
                    idx = span_text.find(needle, start)
                    if idx < 0:
                        break
                    seg = chars[idx: idx + len(needle)]
                    try:
                        rect = fitz.Rect(seg[0]["bbox"])
                        for ch in seg[1:]:
                            rect |= fitz.Rect(ch["bbox"])
                    except Exception:
                        start = idx + 1
                        continue
                    out.append(rect)
                    start = idx + 1
                    if len(out) >= limit:
                        return out
    return out


def search_text(
    doc: "fitz.Document | Path | str",
    needle: str,
    *,
    pages: Sequence[int] | None = None,
    max_hits: int = 800,
    ignore_case: bool = True,
) -> list[SearchHit]:
    """在文档中查找文本，返回每页的命中矩形（用于高亮定位）。

    ``ignore_case=True`` 走 PyMuPDF 原生查找（快，且能跨断词连字）；
    ``ignore_case=False`` 走字符级精确匹配（真正区分大小写）。
    """
    if not needle:
        return []
    with _as_document(doc) as (document, _):
        total = len(document)
        target = list(pages) if pages else list(range(1, total + 1))
        hits: list[SearchHit] = []
        found = 0
        for p in target:
            if p < 1 or p > total:
                continue
            if ignore_case:
                try:
                    rects = document[p - 1].search_for(
                        needle, flags=fitz.TEXT_DEHYPHENATE
                    )
                except Exception:
                    rects = []
            else:
                rects = _search_case_sensitive(
                    document[p - 1], needle, max_hits - found
                )
            if rects:
                packed = [(r.x0, r.y0, r.x1, r.y1) for r in rects]
                hits.append(SearchHit(page=p, rects=packed))
                found += len(packed)
                if found >= max_hits:
                    break
        return hits


def find_tables(
    doc: "fitz.Document | Path | str", pages: Sequence[int] | None = None
) -> list[dict[str, Any]]:
    """识别文档中的表格，返回 ``[{page, rows: [[cell, ...]]}, ...]``。"""
    with _as_document(doc) as (document, _):
        total = len(document)
        target = list(pages) if pages else list(range(1, total + 1))
        out: list[dict[str, Any]] = []
        for p in target:
            if p < 1 or p > total:
                continue
            try:
                finder = document[p - 1].find_tables()
            except Exception:
                continue
            for t in getattr(finder, "tables", []):
                try:
                    rows = t.extract()
                except Exception:
                    continue
                if rows:
                    out.append({"page": p, "rows": rows})
        return out


def extract_images(
    doc: "fitz.Document | Path | str", out_dir: Path, *, min_size: int = 32
) -> list[Path]:
    """提取文档中的位图图像到目录，返回写出文件列表。"""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    seen: set[int] = set()
    with _as_document(doc) as (document, _):
        for pno in range(len(document)):
            for img in document.get_page_images(pno, full=True):
                xref = img[0]
                if xref in seen:
                    continue
                seen.add(xref)
                try:
                    info = document.extract_image(xref)
                except Exception:
                    continue
                data = info.get("image")
                if not data:
                    continue
                if info.get("width", 0) < min_size and info.get("height", 0) < min_size:
                    continue
                ext = info.get("ext", "png")
                f = out_dir / f"image_p{pno + 1}_x{xref}.{ext}"
                f.write_bytes(data)
                written.append(f)
    return written


def export_pages_to_images(
    doc: "fitz.Document | Path | str",
    out_dir: Path,
    *,
    pages: Sequence[int] | None = None,
    fmt: str = "png",
    dpi: int = 150,
    jpeg_quality: int = 85,
    progress: Any = None,
) -> list[Path]:
    """把页面导出为图片文件（png / jpg / webp）。"""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fmt = fmt.lower().lstrip(".")
    if fmt == "jpg":
        fmt = "jpeg"
    zoom = max(0.1, dpi / 72.0)
    written: list[Path] = []
    with _as_document(doc) as (document, _):
        total = len(document)
        target = list(pages) if pages else list(range(1, total + 1))
        for i, p in enumerate(target):
            if p < 1 or p > total:
                continue
            img = page_image(document[p - 1], zoom, max_pixels=0, alpha=False)
            if fmt in ("jpeg", "jpg") and img.mode != "RGB":
                img = img.convert("RGB")
            f = out_dir / f"page_{p:04d}.{'jpg' if fmt in ('jpeg', 'jpg') else fmt}"
            if fmt in ("jpeg", "jpg"):
                img.save(f, "JPEG", quality=jpeg_quality, optimize=True)
            else:
                img.save(f, fmt.upper())
            img.close()
            written.append(f)
            if progress:
                progress(i + 1, len(target))
    release_render_cache()
    return written


# ================================================================== 批注
ANNOT_KINDS = {
    "highlight": "高亮",
    "underline": "下划线",
    "strikeout": "删除线",
    "squiggly": "波浪线",
    "text": "便签",
    "freetext": "文本框",
    "rect": "矩形",
    "circle": "椭圆",
    "stamp": "图章",
    "ink": "手绘",
}


def add_annotation(
    doc: fitz.Document,
    page: int,
    kind: str,
    rect: tuple[float, float, float, float] | fitz.Rect | fitz.Point,
    *,
    text: str | None = None,
    color: tuple[float, float, float] = (1.0, 0.85, 0.0),
    stroke: tuple[float, float, float] | None = None,
    opacity: float = 1.0,
    width: float = 1.0,
    font_size: int = 11,
    stamp: str = "Draft",
    points: Sequence[Sequence[float]] | None = None,
) -> int:
    """添加批注，返回批注 xref。

    ``kind`` 取值见 :data:`ANNOT_KINDS`。``rect`` 为页面坐标矩形；
    ``ink`` 类型改用 ``points``（笔画折线列表）。
    """
    _check_pages(doc, [page])
    pg = doc[page - 1]
    kind = kind.lower()
    if kind in ("highlight", "underline", "strikeout", "squiggly"):
        if not isinstance(rect, fitz.Rect):
            rect = fitz.Rect(*rect)  # type: ignore[arg-type]
        fn = {
            "highlight": pg.add_highlight_annot,
            "underline": pg.add_underline_annot,
            "strikeout": pg.add_strikeout_annot,
            "squiggly": pg.add_squiggly_annot,
        }[kind]
        annot = fn(rect)
    elif kind == "text":
        if not isinstance(rect, fitz.Point):
            r = rect if isinstance(rect, fitz.Rect) else fitz.Rect(*rect)  # type: ignore[arg-type]
            rect = fitz.Point(r.x0 + 12, r.y0 + 12)
        annot = pg.add_text_annot(rect, text or "备注")  # type: ignore[arg-type]
    elif kind == "freetext":
        if not isinstance(rect, fitz.Rect):
            rect = fitz.Rect(*rect)  # type: ignore[arg-type]
        annot = pg.add_freetext_annot(rect, text or "", fontsize=font_size)
    elif kind == "rect":
        if not isinstance(rect, fitz.Rect):
            rect = fitz.Rect(*rect)  # type: ignore[arg-type]
        annot = pg.add_rect_annot(rect)
    elif kind == "circle":
        if not isinstance(rect, fitz.Rect):
            rect = fitz.Rect(*rect)  # type: ignore[arg-type]
        annot = pg.add_circle_annot(rect)
    elif kind == "stamp":
        if not isinstance(rect, fitz.Rect):
            rect = fitz.Rect(*rect)  # type: ignore[arg-type]
        annot = pg.add_stamp_annot(rect, stamp=_stamp_index(stamp))
    elif kind == "ink":
        if not points:
            raise ValueError("手绘批注需要 points 参数")
        strokes = [[(float(pt[0]), float(pt[1])) for pt in stroke_] for stroke_ in points]
        annot = pg.add_ink_annot(strokes)
    else:
        raise ValueError(f"不支持的批注类型: {kind}")

    if kind in ("rect", "circle", "ink"):
        annot.set_colors(stroke=stroke or color)
        annot.set_border(width=width)
    else:
        try:
            annot.set_colors(stroke=color)
        except Exception:
            pass
    try:
        annot.set_opacity(max(0.05, min(opacity, 1.0)))
    except Exception:
        pass
    if text and kind not in ("text", "freetext"):
        annot.set_info(content=text)
    try:
        annot.update()
    except Exception:
        pass
    return annot.xref


def _stamp_index(name: str) -> int:
    """把图章名称映射到 PyMuPDF 内置图章编号。"""
    names = {
        "draft": 3, "approved": 2, "experimental": 1, "notapproved": 4,
        "as is": 5, "expired": 6, "notforpublicrelease": 7, "confidential": 8,
        "final": 9, "sold": 10, "departmental": 11, "forcomment": 12,
        "topsecret": 13, "forpublicrelease": 14, "评价": 9,
    }
    return names.get(name.strip().lower(), 3)


def list_annotations(doc: fitz.Document, page: int) -> list[dict[str, Any]]:
    """列出某页的全部批注。

    注意：PyMuPDF 的 ``Annot`` 依赖其所属 ``Page`` 对象存活。若写成
    ``for annot in doc[p].annots()``，临时 Page 会在循环前被回收，
    导致读取 ``annot.type`` / ``annot.rect`` 时抛
    ``annotation not bound to any page``。因此这里显式持有 page 引用。
    """
    _check_pages(doc, [page])
    pg = doc[page - 1]
    out: list[dict[str, Any]] = []
    for annot in list(pg.annots() or []):
        info = annot.info or {}
        out.append(
            {
                "xref": annot.xref,
                "type": annot.type[1],
                "type_code": annot.type[0],
                "rect": tuple(annot.rect),
                "content": info.get("content", ""),
                "author": info.get("title", ""),
                "opacity": round(float(annot.opacity or 1.0), 3),
            }
        )
    del pg  # 保持引用直到全部字段读取完毕
    return out


def delete_annotation(doc: fitz.Document, page: int, xref: int) -> bool:
    """删除指定批注。"""
    _check_pages(doc, [page])
    pg = doc[page - 1]
    for annot in list(pg.annots() or []):
        if annot.xref == xref:
            pg.delete_annot(annot)
            return True
    return False


def clear_annotations(doc: fitz.Document, *, pages: Sequence[int] | None = None) -> int:
    """清空批注，返回删除数量。"""
    total = len(doc)
    target = _check_pages(doc, pages) if pages else list(range(1, total + 1))
    removed = 0
    for p in target:
        pg = doc[p - 1]
        for annot in list(pg.annots() or []):
            pg.delete_annot(annot)
            removed += 1
    return removed


def apply_redaction(
    doc: fitz.Document,
    page: int,
    rect: tuple[float, float, float, float] | fitz.Rect,
    *,
    fill: tuple[float, float, float] = (0, 0, 0),
) -> None:
    """涂黑并**真正移除**该区域内容（不可恢复），用于脱敏。"""
    _check_pages(doc, [page])
    if not isinstance(rect, fitz.Rect):
        rect = fitz.Rect(*rect)
    pg = doc[page - 1]
    pg.add_redact_annot(rect, fill=fill)
    pg.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS)


# ============================================== 属性 / 书签 / 页面标签
def get_metadata(source: "fitz.Document | Path | str") -> dict[str, str]:
    """读取文档属性（标题/作者/主题/关键词等）。"""
    with _as_document(source) as (doc, _):
        md = doc.metadata or {}
    keys = ("title", "author", "subject", "keywords", "creator", "producer",
            "creationDate", "modDate", "format")
    return {k: (md.get(k) or "") for k in keys}


def set_metadata(
    input_path: Path, output_path: Path, values: dict[str, str]
) -> None:
    """写入文档属性。"""
    with open_document(input_path) as doc:
        set_document_metadata(doc, values)
        save_document(doc, output_path)


def set_document_metadata(doc: fitz.Document, values: dict[str, str]) -> None:
    """原地写入文档属性（只覆盖传入的字段）。"""
    md = dict(doc.metadata or {})
    for k in ("title", "author", "subject", "keywords", "creator", "producer"):
        if k in values and values[k] is not None:
            md[k] = values[k]
    doc.set_metadata(md)


def get_toc(source: "fitz.Document | Path | str") -> list[list[Any]]:
    """读取书签目录，返回 ``[[层级, 标题, 页码], ...]``。"""
    with _as_document(source) as (doc, _):
        return [list(x) for x in (doc.get_toc() or [])]


def set_toc(input_path: Path, output_path: Path, toc: Sequence[Sequence[Any]]) -> None:
    """写入书签目录。"""
    with open_document(input_path) as doc:
        set_document_toc(doc, toc)
        save_document(doc, output_path)


def set_document_toc(doc: fitz.Document, toc: Sequence[Sequence[Any]]) -> None:
    """原地写入书签目录。"""
    items = [[int(lv), str(t), int(p)] for lv, t, p in toc]  # type: ignore[misc]
    doc.set_toc(items)


def add_bookmark(
    doc: fitz.Document, title: str, page: int, *, level: int = 1
) -> list[list[Any]]:
    """追加一个书签并返回最新目录。"""
    _check_pages(doc, [page])
    toc = [list(x) for x in (doc.get_toc() or [])]
    toc.append([max(1, min(int(level), 6)), title, page])
    doc.set_toc([[int(a), str(b), int(c)] for a, b, c in toc])
    return toc


def delete_bookmark(doc: fitz.Document, index: int) -> list[list[Any]]:
    """按索引删除书签（0 开始），返回最新目录。"""
    toc = [list(x) for x in (doc.get_toc() or [])]
    if 0 <= index < len(toc):
        toc.pop(index)
        doc.set_toc([[int(a), str(b), int(c)] for a, b, c in toc])
    return toc


def get_page_labels(source: "fitz.Document | Path | str") -> list[dict[str, Any]]:
    """读取页码标签规则。"""
    with _as_document(source) as (doc, _):
        return list(doc.get_page_labels() or [])


def set_page_labels(
    input_path: Path, output_path: Path, labels: Sequence[dict[str, Any]]
) -> None:
    """写入页码标签（如用罗马数字/前缀编号）。"""
    with open_document(input_path) as doc:
        doc.set_page_labels([dict(x) for x in labels])
        save_document(doc, output_path)


# ======================================================== 优化 / 加密
def compress_document(
    input_path: Path,
    output_path: Path,
    *,
    dpi: int = 120,
    quality: int = 75,
    convert_gray: bool = False,
) -> dict[str, int]:
    """压缩 PDF：清理冗余对象 + 字体子集化 + 图像降采样。

    返回 ``{before, after, saved_percent}``。
    """
    input_path = Path(input_path)
    before = input_path.stat().st_size
    with open_document(input_path) as doc:
        try:
            doc.rewrite_images(
                dpi_threshold=dpi, dpi_target=dpi, quality=quality,
                set_to_gray=convert_gray,
            )
        except TypeError:
            try:
                doc.rewrite_images(dpi_threshold=dpi, dpi_target=dpi, quality=quality)
            except Exception:
                pass
        except Exception:
            pass
        save_document(doc, output_path, compress=True)
    after = Path(output_path).stat().st_size
    saved = 0 if before <= 0 else max(0, round((before - after) * 100 / before))
    return {"before": before, "after": after, "saved_percent": saved}


def set_encryption(
    input_path: Path,
    output_path: Path,
    *,
    user_password: str | None = None,
    owner_password: str | None = None,
    allow_print: bool = True,
    allow_copy: bool = True,
    allow_modify: bool = False,
    allow_annotate: bool = True,
) -> None:
    """给 PDF 添加打开口令与权限限制。"""
    perms = _perm("PDF_PERM_ACCESSIBILITY")
    if allow_print:
        perms |= _perm("PDF_PERM_PRINT") | _perm("PDF_PERM_PRINT_HQ")
    if allow_copy:
        perms |= _perm("PDF_PERM_COPY")
    if allow_modify:
        perms |= _perm("PDF_PERM_MODIFY") | _perm("PDF_PERM_ASSEMBLE")
    if allow_annotate:
        perms |= _perm("PDF_PERM_ANNOTATE") | _perm("PDF_PERM_FORM")
    with open_document(input_path) as doc:
        save_document(
            doc, output_path,
            user_password=user_password, owner_password=owner_password,
            permissions=perms,
        )


def remove_encryption(
    input_path: Path, output_path: Path, *, password: str | None = None
) -> None:
    """解除 PDF 口令限制（需提供正确口令）。"""
    with open_document(input_path, password) as doc:
        save_document(doc, output_path)


def is_encrypted(input_path: Path | str) -> bool:
    """判断文件是否加密。"""
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"找不到文件: {path}")
    doc = _open_raw(path)
    try:
        return bool(doc.needs_pass or doc.is_encrypted)
    finally:
        doc.close()