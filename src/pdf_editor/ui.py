"""PDF 编辑器桌面界面 —— WPS 风格（v0.3.1）。

布局
----
    ┌──────────────────────────────────────────────────────────────┐
    │ 菜单栏：文件 编辑 视图 页面 插入 水印 批注 工具 帮助            │
    ├──────────────────────────────────────────────────────────────┤
    │ Ribbon（分页签 + 分组图标按钮：开始/页面/插入/批注/水印/工具/视图）│
    ├───────────┬──────────────────────────────────────────────────┤
    │ 页面缩略图 │ 查找栏（可折叠）                                   │
    │ （虚拟化   │ ┌──────────────────────────────────────────────┐ │
    │  多选/右键）│ │ 预览区：缩放 / 滚动 / 框选批注 / 拖拽平移       │ │
    │           │ └──────────────────────────────────────────────┘ │
    │           ├──────────────────────────────────────────────────┤
    │           │ 面板：操作日志 | 目录书签 | 批注                    │
    ├───────────┴──────────────────────────────────────────────────┤
    │ 状态栏：状态文本 / 进度条 / 缩放 / 页码 / 翻页                    │
    └──────────────────────────────────────────────────────────────┘

关键设计
--------
* **工作副本 + 撤销栈**：所有编辑都作用于内存中的工作副本（``DocumentSession``），
  原文件在「保存」前不被触碰；每次修改前自动快照，因此支持撤销/重做。
* **句柄复用**：预览与缩略图直接从已打开的文档渲染，不再反复开关文件
  （实测单页渲染 22ms → 4ms）。
* **虚拟化缩略图**：只创建可视区域内的缩略图控件，并带 LRU 缓存，千页文档也流畅。
* **后台任务**：打开/导出/压缩/查找等耗时操作放入守护线程，界面不假死。
* **全局异常兜底**：所有命令统一捕获异常并记入日志，不会把界面带崩。
"""

from __future__ import annotations

import json
import tkinter as tk
from collections import OrderedDict
from collections.abc import Sequence
from functools import wraps
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, simpledialog
from tkinter import ttk as _ttk
from typing import Any

import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from PIL import Image, ImageDraw, ImageTk

from . import icons
from .theme import (
    BG, BLUE, BLUE_DARK, BLUE_HOVER, BLUE_LIGHT, BORDER, BORDER_SOFT,
    CANVAS_BG, ERROR, FIND_HL, GROUP_ACCENT, OK, PANEL, SEL_SOFT, TEXT,
    TEXT_FAINT, TEXT_MUTED, WARN, apply_styles, flat_button, font, mono,
)
from .pdf_engine import (
    ANNOT_KINDS, DocumentSession, PdfError, PdfPasswordError,
    PdfPasswordRequired, add_annotation, add_bookmark, add_header_footer,
    add_image_watermark, add_page_numbers, add_text_watermark,
    apply_redaction, clear_annotations, compress_document, delete_annotation,
    delete_bookmark, delete_document_pages, export_pages_to_images,
    extract_document_pages, extract_document_text, extract_images,
    extract_pages_to_files, find_tables, get_metadata, get_toc,
    header_footer_document, image_watermark_document, insert_blank_document_page,
    insert_document, is_encrypted, list_annotations, merge_pdfs,
    move_document_page, page_image, page_numbers_document, release_render_cache,
    remove_encryption, reorder_document, rotate_document, search_text,
    set_document_metadata, set_document_page_size, set_encryption,
    split_document, text_watermark_document,
)
from .tasks import TaskRunner

APP_VERSION = "0.3.1"
CONFIG_PATH = Path.home() / ".pdf_editor" / "config.json"
LOG_PATH = Path.home() / ".pdf_editor" / "error.log"


def _crash_log(text: str) -> None:
    """记录诊断信息。

    打包为 windowed exe 后没有控制台，``sys.stdout`` 可能是 ``None``，
    直接 ``print`` 会让错误处理器自身抛异常（二次崩溃）。因此这里
    一律先尝试标准输出，再兜底写入用户目录下的日志文件。
    """
    try:
        print(text, flush=True)
    except Exception:
        pass
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(text if text.endswith("\n") else text + "\n")
    except Exception:
        pass

# 缩略图参数
THUMB_W = 148
THUMB_MAX_H = 214
THUMB_LABEL_H = 20
THUMB_PAD = 10

# 预览渲染像素上限（单张），控制内存占用
PREVIEW_MAX_PIXELS = 6_000_000
PREVIEW_CACHE_MAX = 6
THUMB_CACHE_MAX = 200

# 标注工具 -> 引擎批注类型
ANNOT_TOOLS = {
    "highlight": ("highlight", "高亮", "#FFD54A"),
    "underline": ("underline", "下划线", "#2B7BD6"),
    "strikeout": ("strikeout", "删除线", "#D9534F"),
    "squiggly": ("squiggly", "波浪线", "#3C9D5B"),
    "rect": ("rect", "矩形", "#D9534F"),
    "circle": ("circle", "椭圆", "#2B7BD6"),
    "stamp": ("stamp", "图章", "#C77A2B"),
}


def guarded(fn):
    """命令装饰器：统一拦截异常 + 忙碌保护，保证界面不会崩溃。"""

    @wraps(fn)
    def wrapper(self, *args, **kwargs):
        if self._tasks.busy and getattr(fn, "_allow_busy", False) is False:
            self._status("有任务正在进行，请稍候…")
            return None
        try:
            return fn(self, *args, **kwargs)
        except (PdfPasswordRequired, PdfPasswordError) as exc:
            self._error_dialog("口令问题", str(exc))
        except PdfError as exc:
            self._error_dialog("操作失败", str(exc))
        except Exception as exc:  # noqa: BLE001 — 兜底，避免界面崩溃
            self._unexpected(fn.__name__, exc)
        return None

    return wrapper


def _shift_selection(anchor: int, page: int) -> set[int]:
    """Shift 连选：返回 anchor 到 page 之间的所有页码（注意尾部 0 号位）。"""
    lo, hi = sorted((anchor, page))
    return set(range(lo, hi + 1))


# 惰性尺寸表预采样页数：足以推算出统一的单元格高度，避免打开时遍历全部页。
_DIMS_PROBE = 24


class _PageDims(Sequence):
    """按页惰性读取页面尺寸的序列。

    打开文档时若一次性读取全部页面的 ``rect``，代价随页数线性增长
    （实测 300 页需 167 ms，而前 30 页仅需 1.3 ms）。绝大多数场景只用到
    当前页与可见缩略图（约十余页），因此这里改为按需读取并缓存。

    对外的行为与普通 ``list[tuple[float, float]]`` 保持一致：
    支持索引、切片、``len()``、``in`` 与迭代。
    """

    __slots__ = ("_doc", "_count", "_cache", "_cells")

    def __init__(self, doc: Any, count: int):
        self._doc = doc
        self._count = int(count)
        self._cache: dict[int, tuple[float, float]] = {}
        self._cells: tuple[float, float] = self._probe()

    # ---------------------------------------------------------- 内部
    def _probe(self) -> tuple[float, float]:
        """采样少量页面，用于快速估算统一的缩略图单元格高度。

        只取「大小一致」的常规文档的前若干页；若前若干页尺寸完全一致，
        则认为整篇同尺寸，用该值即可，无需继续扫描。
        """
        dims = [self._at(i) for i in range(min(_DIMS_PROBE, self._count))]
        if not dims:
            return (595.0, 842.0)  # A4 兜底
        first = dims[0]
        if all(abs(w - first[0]) < 0.5 and abs(h - first[1]) < 0.5 for w, h in dims):
            return first
        # 尺寸不一致：按采样中的极值给一个保守值（避免单元格高度抖动）
        max_h = max(h for _, h in dims)
        return (first[0], max_h)

    def _at(self, idx: int) -> tuple[float, float]:
        cached = self._cache.get(idx)
        if cached is not None:
            return cached
        try:
            r = self._doc[idx].rect
            val = (float(r.width), float(r.height))
        except Exception:
            val = self._cells
        self._cache[idx] = val
        return val

    def invalidate(self) -> None:
        """页面结构发生变化后清空缓存（保留采样用于布局估算）。"""
        self._cache.clear()

    @property
    def estimated(self) -> tuple[float, float]:
        """代表性页面尺寸（供布局估算使用，不触发全量读取）。"""
        return self._cells

    # ----------------------------------------------------- Sequence 协议
    def __len__(self) -> int:
        return self._count

    def __getitem__(self, idx):
        if isinstance(idx, slice):
            return [self._at(i) for i in range(*idx.indices(self._count))]
        if idx < 0:
            idx += self._count
        if not (0 <= idx < self._count):
            raise IndexError(idx)
        return self._at(idx)

    def __iter__(self):
        for i in range(self._count):
            yield self._at(i)

    def __contains__(self, value: object) -> bool:
        return any(d == value for d in self)

    def __bool__(self) -> bool:
        return self._count > 0

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f"<_PageDims count={self._count} cached={len(self._cache)}>"


class PDFEditorApp:
    def __init__(self, root: ttk.Window):
        self.root = root
        self._tasks = TaskRunner(root)
        self._tasks.on_state_change(self._on_task_state)
        apply_styles(root)

        self.session = DocumentSession()
        self.doc_path: Path | None = None

        # 文档视图状态
        self._page_count = 0
        self._dims: Sequence[tuple[float, float]] = []
        self.zoom: float = 1.0
        self._zoom_mode: str = "fit_width"   # custom / fit_width / fit_page
        self.current_page: int = 1
        self.selection: set[int] = set()
        self._scroll_x = 0.0
        self._scroll_y = 0.0
        self._view_origin = (0.0, 0.0)       # 页面在画布中的左上角
        self._view_scale = 1.0               # 实际渲染缩放

        # 缓存
        self._preview_cache: OrderedDict[tuple, Image.Image] = OrderedDict()
        self._thumb_cache: OrderedDict[tuple, ImageTk.PhotoImage] = OrderedDict()
        self._photo_ref: ImageTk.PhotoImage | None = None
        self._thumb_widgets: dict[int, list[tk.Widget]] = {}
        self._thumb_cell_h = THUMB_MAX_H + THUMB_LABEL_H + THUMB_PAD
        self._thumb_queue: list[int] = []
        self._thumb_pumping = False
        self._sel_anchor: int | None = None

        # 交互状态
        self._annot_tool: str | None = None
        self._drag_start: tuple[float, float] | None = None
        self._ink_points: list[float] = []
        self._drag_id: int | None = None
        self._pan_start: tuple[float, float] | None = None
        self._find_hits: list = []
        self._find_index = -1
        self._find_visible = False
        self._render_job: str | None = None
        self._thumb_sync_job: str | None = None

        self.recent: list[str] = []
        self._load_config()

        self._build_menu()
        self._build_ribbon()
        self._build_body()
        self._build_statusbar()
        self._bind_keys()

        root.report_callback_exception = self._tk_exception
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._set_icon()
        self._apply_geometry()
        self._update_ui_state()
        self._log(f"PDF 编辑器 v{APP_VERSION} 已启动")

    # =============================================================== 配置
    def _load_config(self) -> None:
        try:
            cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            self.recent = [x for x in cfg.get("recent", []) if Path(x).exists()][:12]
            self._geom = cfg.get("geometry")
        except Exception:
            self.recent = []
            self._geom = None

    def _save_config(self) -> None:
        try:
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            CONFIG_PATH.write_text(
                json.dumps(
                    {"recent": self.recent[:12], "geometry": self.root.geometry()},
                    ensure_ascii=False, indent=2,
                ),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _apply_geometry(self) -> None:
        geom = getattr(self, "_geom", None)
        if geom:
            try:
                self.root.geometry(geom)
                return
            except Exception:
                pass
        self.root.geometry("1240x820")
        self.root.minsize(1000, 660)

    def _set_icon(self) -> None:
        try:
            photo = icons.icon("pdf", BLUE, 32)
            if photo:
                self._icon_ref = photo
                self.root.iconphoto(True, photo)
        except Exception:
            pass

    def _remember(self, path: Path) -> None:
        p = str(path)
        if p in self.recent:
            self.recent.remove(p)
        self.recent.insert(0, p)
        del self.recent[12:]
        self._rebuild_recent_menu()

    # =============================================================== 菜单
    def _build_menu(self) -> None:
        bar = tk.Menu(self.root, tearoff=0)

        self._m_recent = tk.Menu(bar, tearoff=0)
        m_file = tk.Menu(bar, tearoff=0)
        m_file.add_command(label="打开…", accelerator="Ctrl+O", command=self.open_pdf)
        m_file.add_cascade(label="最近打开", menu=self._m_recent)
        m_file.add_separator()
        m_file.add_command(label="保存", accelerator="Ctrl+S", command=self.save)
        m_file.add_command(label="另存为…", accelerator="Ctrl+Shift+S", command=self.save_as)
        m_file.add_separator()
        m_file.add_command(label="合并 PDF…", command=self.merge_dialog)
        m_file.add_command(label="拆分 PDF…", command=self.split_dialog)
        m_file.add_separator()
        m_file.add_command(label="压缩优化…", command=self.compress_dialog)
        m_file.add_command(label="添加密码…", command=self.encrypt_dialog)
        m_file.add_command(label="解除密码…", command=self.decrypt_dialog)
        m_file.add_separator()
        m_file.add_command(label="关闭文档", command=self.close_document)
        m_file.add_command(label="退出", accelerator="Ctrl+Q", command=self._on_close)
        bar.add_cascade(label="文件", menu=m_file)

        m_edit = tk.Menu(bar, tearoff=0)
        m_edit.add_command(label="撤销", accelerator="Ctrl+Z", command=self.undo)
        m_edit.add_command(label="重做", accelerator="Ctrl+Y", command=self.redo)
        m_edit.add_separator()
        m_edit.add_command(label="复制当前页到末尾", command=self.duplicate_page)
        m_edit.add_command(label="删除当前页", command=self.delete_current)
        m_edit.add_command(label="删除选中页", command=self.delete_selected)
        m_edit.add_separator()
        m_edit.add_command(label="全选页面", accelerator="Ctrl+A", command=self.select_all)
        m_edit.add_command(label="清除选择", command=self.clear_selection)
        bar.add_cascade(label="编辑", menu=m_edit)

        m_view = tk.Menu(bar, tearoff=0)
        m_view.add_command(label="放大", accelerator="Ctrl++", command=lambda: self.zoom_step(1.15))
        m_view.add_command(label="缩小", accelerator="Ctrl+-", command=lambda: self.zoom_step(1 / 1.15))
        m_view.add_command(label="实际大小", accelerator="Ctrl+0", command=self.zoom_reset)
        m_view.add_command(label="适应宽度", command=self.fit_width)
        m_view.add_command(label="适应页面", command=self.fit_page)
        m_view.add_separator()
        m_view.add_command(label="上一页", accelerator="PgUp", command=lambda: self.goto_page(self.current_page - 1))
        m_view.add_command(label="下一页", accelerator="PgDn", command=lambda: self.goto_page(self.current_page + 1))
        m_view.add_command(label="跳转到页…", accelerator="Ctrl+G", command=self.goto_dialog)
        bar.add_cascade(label="视图", menu=m_view)

        m_page = tk.Menu(bar, tearoff=0)
        m_page.add_command(label="插入空白页", command=self.insert_blank)
        m_page.add_command(label="提取选中页…", command=self.extract_selected)
        m_page.add_command(label="重排页面…", command=self.reorder_dialog)
        m_page.add_separator()
        m_page.add_command(label="上移当前页", command=lambda: self.move_rel(-1))
        m_page.add_command(label="下移当前页", command=lambda: self.move_rel(1))
        m_page.add_command(label="移到最前", command=lambda: self.move_abs(1))
        m_page.add_command(label="移到末尾", command=lambda: self.move_abs(0))
        m_page.add_separator()
        m_page.add_command(label="右转 90°", command=lambda: self.rotate(90))
        m_page.add_command(label="左转 90°", command=lambda: self.rotate(-90))
        m_page.add_command(label="旋转 180°", command=lambda: self.rotate(180))
        m_page.add_separator()
        m_page.add_command(label="统一为 A4", command=lambda: self.set_size("a4"))
        m_page.add_command(label="统一为 Letter", command=lambda: self.set_size("letter"))
        bar.add_cascade(label="页面", menu=m_page)

        m_ins = tk.Menu(bar, tearoff=0)
        m_ins.add_command(label="插入 PDF 到末尾…", command=lambda: self.insert_pdf(-1))
        m_ins.add_command(label="插入 PDF 到最前…", command=lambda: self.insert_pdf(0))
        m_ins.add_command(label="在当前页后插入…", command=lambda: self.insert_pdf(self.current_page))
        m_ins.add_separator()
        m_ins.add_command(label="插入页码…", command=self.page_number_dialog)
        m_ins.add_command(label="页眉 / 页脚…", command=self.header_footer_dialog)
        bar.add_cascade(label="插入", menu=m_ins)

        m_wm = tk.Menu(bar, tearoff=0)
        m_wm.add_command(label="文字水印…", command=self.text_watermark_dialog)
        m_wm.add_command(label="图片水印…", command=self.image_watermark_dialog)
        bar.add_cascade(label="水印", menu=m_wm)

        m_an = tk.Menu(bar, tearoff=0)
        for key, (_, label, _) in ANNOT_TOOLS.items():
            m_an.add_command(label=f"添加{label}", command=lambda k=key: self.toggle_annot(k))
        m_an.add_separator()
        m_an.add_command(label="添加便签", command=lambda: self.toggle_annot("text"))
        m_an.add_command(label="添加文本框", command=lambda: self.toggle_annot("freetext"))
        m_an.add_command(label="涂黑脱敏", command=lambda: self.toggle_annot("redact"))
        m_an.add_separator()
        m_an.add_command(label="取消标注模式", command=self.cancel_annot)
        m_an.add_command(label="清除本页批注", command=self.clear_page_annots)
        m_an.add_command(label="清除全部批注", command=self.clear_all_annots)
        bar.add_cascade(label="批注", menu=m_an)

        m_tool = tk.Menu(bar, tearoff=0)
        m_tool.add_command(label="查找…", accelerator="Ctrl+F", command=self.toggle_find_bar)
        m_tool.add_separator()
        m_tool.add_command(label="提取文字…", command=self.extract_text_dialog)
        m_tool.add_command(label="导出全部文本…", command=self.export_text_dialog)
        m_tool.add_command(label="导出页面为图片…", command=self.export_images_dialog)
        m_tool.add_command(label="提取嵌入图片…", command=self.extract_images_dialog)
        m_tool.add_separator()
        m_tool.add_command(label="识别表格", command=self.tables_dialog)
        m_tool.add_separator()
        m_tool.add_command(label="文档属性…", command=self.properties_dialog)
        m_tool.add_command(label="添加书签…", command=self.add_bookmark_dialog)
        bar.add_cascade(label="工具", menu=m_tool)

        m_help = tk.Menu(bar, tearoff=0)
        m_help.add_command(label="快捷键", command=self._shortcuts)
        m_help.add_command(label="关于", command=self._about)
        bar.add_cascade(label="帮助", menu=m_help)

        self.root.config(menu=bar)
        self._rebuild_recent_menu()

    def _rebuild_recent_menu(self) -> None:
        self._m_recent.delete(0, "end")
        if not self.recent:
            self._m_recent.add_command(label="（暂无记录）", state="disabled")
            return
        for p in self.recent:
            self._m_recent.add_command(
                label=Path(p).name + f"   —   {Path(p).parent}",
                command=lambda q=p: self.open_path(Path(q)),
            )
        self._m_recent.add_separator()
        self._m_recent.add_command(label="清除记录", command=self._clear_recent)

    def _clear_recent(self) -> None:
        self.recent = []
        self._rebuild_recent_menu()
        self._save_config()

    # ============================================================= Ribbon
    def _build_ribbon(self) -> None:
        holder = tk.Frame(self.root, bg=PANEL, highlightthickness=0)
        holder.pack(fill=X)
        self._notebook = _ttk.Notebook(holder)
        self._notebook.pack(fill=X, padx=0, pady=0)

        tabs: list[tuple[str, list[tuple[str, list[tuple[str, str, object]]]]]] = [
            ("开始", [
                ("文件", [
                    ("open", "打开", self.open_pdf),
                    ("save", "保存", self.save),
                    ("merge", "合并", self.merge_dialog),
                    ("compress", "压缩", self.compress_dialog),
                ]),
                ("编辑", [
                    ("undo", "撤销", self.undo),
                    ("redo", "重做", self.redo),
                    ("copy", "复制页", self.duplicate_page),
                    ("delete", "删除页", self.delete_current),
                ]),
                ("旋转", [
                    ("rotate_ccw", "左转", lambda: self.rotate(-90)),
                    ("rotate_cw", "右转", lambda: self.rotate(90)),
                    ("rotate180", "180°", lambda: self.rotate(180)),
                ]),
                ("视图", [
                    ("zoom_out", "缩小", lambda: self.zoom_step(1 / 1.15)),
                    ("zoom_in", "放大", lambda: self.zoom_step(1.15)),
                    ("fit_width", "适宽", self.fit_width),
                    ("fit_page", "整页", self.fit_page),
                ]),
                ("查找", [("find", "查找", self.toggle_find_bar)]),
            ]),
            ("页面", [
                ("页面", [
                    ("blank", "空白页", self.insert_blank),
                    ("extract", "提取页", self.extract_selected),
                    ("split", "拆分", self.split_dialog),
                    ("properties", "重排", self.reorder_dialog),
                ]),
                ("移动", [
                    ("up", "上移", lambda: self.move_rel(-1)),
                    ("down", "下移", lambda: self.move_rel(1)),
                ]),
                ("尺寸", [
                    ("page_num", "A4", lambda: self.set_size("a4")),
                    ("page_num", "Letter", lambda: self.set_size("letter")),
                ]),
                ("插入", [("insert", "插入PDF", lambda: self.insert_pdf(-1))]),
            ]),
            ("批注", [
                ("标记", [
                    ("highlight", "高亮", lambda: self.toggle_annot("highlight")),
                    ("underline", "下划线", lambda: self.toggle_annot("underline")),
                    ("strikeout", "删除线", lambda: self.toggle_annot("strikeout")),
                ]),
                ("形状", [
                    ("rect", "矩形", lambda: self.toggle_annot("rect")),
                    ("circle", "椭圆", lambda: self.toggle_annot("circle")),
                    ("stamp", "图章", lambda: self.toggle_annot("stamp")),
                    ("ink", "手绘", lambda: self.toggle_annot("ink")),
                ]),
                ("文字", [
                    ("note", "便签", lambda: self.toggle_annot("text")),
                    ("text", "文本框", lambda: self.toggle_annot("freetext")),
                ]),
                ("管理", [
                    ("delete", "清除本页", self.clear_page_annots),
                    ("unlock", "涂黑脱敏", lambda: self.toggle_annot("redact")),
                    ("bookmark", "加书签", self.add_bookmark_dialog),
                ]),
            ]),
            ("水印", [
                ("水印", [
                    ("wm_text", "文字水印", self.text_watermark_dialog),
                    ("wm_image", "图片水印", self.image_watermark_dialog),
                ]),
                ("页码", [
                    ("page_num", "插入页码", self.page_number_dialog),
                    ("header", "页眉页脚", self.header_footer_dialog),
                ]),
            ]),
            ("工具", [
                ("内容", [
                    ("text", "提取文字", self.extract_text_dialog),
                    ("export_img", "导出图片", self.export_images_dialog),
                    ("export_img", "导出文本", self.export_text_dialog),
                    ("merge", "提取图片", self.extract_images_dialog),
                ]),
                ("安全", [
                    ("lock", "加密码", self.encrypt_dialog),
                    ("unlock", "解密码", self.decrypt_dialog),
                    ("compress", "压缩优化", self.compress_dialog),
                ]),
                ("文档", [
                    ("properties", "文档属性", self.properties_dialog),
                    ("bookmark", "书签目录", self.show_catalog_tab),
                    ("info", "表格识别", self.tables_dialog),
                ]),
            ]),
            ("视图", [
                ("缩放", [
                    ("zoom_in", "放大", lambda: self.zoom_step(1.15)),
                    ("zoom_out", "缩小", lambda: self.zoom_step(1 / 1.15)),
                    ("fit_width", "适应宽度", self.fit_width),
                    ("fit_page", "适应页面", self.fit_page),
                ]),
                ("面板", [
                    ("pdf", "缩略图", self.toggle_thumbs),
                    ("note", "信息面板", self.toggle_panel),
                ]),
                ("导航", [
                    ("up", "上一页", lambda: self.goto_page(self.current_page - 1)),
                    ("down", "下一页", lambda: self.goto_page(self.current_page + 1)),
                    ("recent", "跳转", self.goto_dialog),
                ]),
            ]),
        ]

        for tab_name, groups in tabs:
            page = tk.Frame(self._notebook, bg=PANEL)
            self._notebook.add(page, text=tab_name)
            for gname, buttons in groups:
                self._ribbon_group(page, gname, buttons)

    def _ribbon_group(self, parent: tk.Misc, title: str,
                      buttons: list[tuple[str, str, object]]) -> None:
        g = tk.Frame(parent, bg=PANEL)
        g.pack(side=LEFT, padx=(8, 4), pady=(6, 3), anchor="n")
        row = tk.Frame(g, bg=PANEL)
        row.pack(anchor="center")
        accent = GROUP_ACCENT.get(title, BLUE)
        for name, label, cmd in buttons:
            holder = tk.Frame(row, bg=PANEL)
            holder.pack(side=LEFT, padx=2)
            photo = icons.icon(name, accent, 24)
            b = tk.Button(
                holder, text=" " + label, image=photo, compound="top", command=cmd,
                relief="flat", bd=0, bg=PANEL, fg=TEXT, cursor="hand2",
                activebackground=BLUE_LIGHT, activeforeground=BLUE_DARK,
                font=font(8), padx=6, pady=3, highlightthickness=0,
            )
            b.image = photo  # 持有引用，避免被回收
            b.pack()
            b.bind("<Enter>", lambda e, w=b: w.configure(bg=BLUE_LIGHT))
            b.bind("<Leave>", lambda e, w=b: w.configure(bg=PANEL))
        tk.Label(g, text=title, bg=PANEL, fg=TEXT_FAINT,
                 font=font(8)).pack(pady=(1, 0))
        tk.Frame(parent, bg=BORDER_SOFT, width=1).pack(side=LEFT, fill=Y, pady=8)

    # =============================================================== 主体
    def _build_body(self) -> None:
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill=BOTH, expand=True)

        # ---- 左：缩略图面板
        self.left = tk.Frame(body, bg=PANEL, width=THUMB_W + 30)
        self.left.pack(side=LEFT, fill=Y)
        self.left.pack_propagate(False)

        head = tk.Frame(self.left, bg=PANEL)
        head.pack(fill=X)
        tk.Label(head, text="页面", bg=PANEL, fg=TEXT,
                 font=font(10, True)).pack(side=LEFT, padx=10, pady=(8, 6))
        self.thumb_count_lbl = tk.Label(head, text="", bg=PANEL, fg=TEXT_MUTED,
                                        font=font(8))
        self.thumb_count_lbl.pack(side=RIGHT, padx=10)
        tk.Frame(self.left, bg=BORDER_SOFT, height=1).pack(fill=X)

        wrap = tk.Frame(self.left, bg=PANEL)
        wrap.pack(fill=BOTH, expand=True)
        self.thumb_canvas = tk.Canvas(wrap, bg=PANEL, highlightthickness=0, bd=0)
        sb = _ttk.Scrollbar(wrap, orient=VERTICAL, command=self.thumb_canvas.yview)
        self.thumb_canvas.configure(yscrollcommand=self._on_thumb_scroll)
        sb.pack(side=RIGHT, fill=Y)
        self.thumb_canvas.pack(side=LEFT, fill=BOTH, expand=True)
        self.thumb_canvas.bind("<Configure>", lambda e: self._schedule_thumb_sync())
        self.thumb_canvas.bind("<MouseWheel>", self._thumb_wheel)
        self.thumb_canvas.bind("<Button-4>", lambda e: self.thumb_canvas.yview_scroll(-3, "units"))
        self.thumb_canvas.bind("<Button-5>", lambda e: self.thumb_canvas.yview_scroll(3, "units"))

        # ---- 右：预览 + 面板
        right = tk.Frame(body, bg=BG)
        right.pack(side=LEFT, fill=BOTH, expand=True)
        self.right = right

        self._build_find_bar(right)

        self.canvas = tk.Canvas(right, bg=CANVAS_BG, highlightthickness=0, bd=0)
        self.canvas.pack(fill=BOTH, expand=True)
        self.canvas.bind("<Configure>", lambda e: self._schedule_render())
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Shift-MouseWheel>", self._on_hwheel)
        self.canvas.bind("<Button-4>", lambda e: self._scroll_by(-60, 0))
        self.canvas.bind("<Button-5>", lambda e: self._scroll_by(60, 0))
        self.canvas.bind("<Button-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Button-2>", self._on_pan_start)
        self.canvas.bind("<B2-Motion>", self._on_pan_move)
        self.canvas.bind("<ButtonRelease-2>", lambda e: setattr(self, "_pan_start", None))
        self.canvas.bind("<Enter>", lambda e: self.canvas.focus_set())

        self._build_panel(right)

    def _build_find_bar(self, parent: tk.Misc) -> None:
        self.find_bar = tk.Frame(parent, bg=BLUE_LIGHT, height=34)
        inner = tk.Frame(self.find_bar, bg=BLUE_LIGHT)
        inner.pack(fill=X, padx=8, pady=4)
        tk.Label(inner, text="查找", bg=BLUE_LIGHT, fg=TEXT_MUTED,
                 font=font(9)).pack(side=LEFT)
        self.find_var = tk.StringVar()
        self.find_entry = _ttk.Entry(inner, textvariable=self.find_var, width=26)
        self.find_entry.pack(side=LEFT, padx=6)
        self.find_entry.bind("<Return>", lambda e: self.find_next())
        self.find_entry.bind("<Escape>", lambda e: self.toggle_find_bar(False))
        flat_button(inner, "上一个", self.find_prev, bg=BLUE_LIGHT,
                    hover=BLUE_HOVER, padx=8, pady=2).pack(side=LEFT, padx=2)
        flat_button(inner, "下一个", self.find_next, bg=BLUE_LIGHT,
                    hover=BLUE_HOVER, padx=8, pady=2).pack(side=LEFT, padx=2)
        self.find_case_var = tk.BooleanVar(value=False)
        case_chk = tk.Checkbutton(
            inner, text="区分大小写", variable=self.find_case_var,
            bg=BLUE_LIGHT, fg=TEXT_MUTED, activebackground=BLUE_LIGHT,
            activeforeground=TEXT, selectcolor=BLUE_LIGHT,
            font=font(9), bd=0, highlightthickness=0,
            command=self._refind,
        )
        case_chk.pack(side=LEFT, padx=8)
        self.find_info = tk.Label(inner, text="", bg=BLUE_LIGHT, fg=TEXT_MUTED,
                                  font=font(9))
        self.find_info.pack(side=LEFT, padx=10)
        flat_button(inner, "✕", lambda: self.toggle_find_bar(False), bg=BLUE_LIGHT,
                    hover=BLUE_HOVER, padx=6, pady=2).pack(side=RIGHT)
        # 默认隐藏

    def _build_panel(self, parent: tk.Misc) -> None:
        self.panel = tk.Frame(parent, bg=PANEL, height=148)
        self.panel.pack(fill=X, side=BOTTOM)
        self.panel.pack_propagate(False)

        nb = _ttk.Notebook(self.panel)
        self._panel_nb = nb
        nb.pack(fill=BOTH, expand=True)

        # 日志
        log_page = tk.Frame(nb, bg=PANEL)
        nb.add(log_page, text="  操作日志  ")
        self.log = tk.Text(log_page, height=5, state=tk.DISABLED, relief="flat",
                           bg="#FBFCFE", fg=TEXT, font=mono(9), wrap="none",
                           highlightthickness=0)
        lsb = _ttk.Scrollbar(log_page, orient=VERTICAL, command=self.log.yview)
        self.log.configure(yscrollcommand=lsb.set)
        lsb.pack(side=RIGHT, fill=Y)
        self.log.pack(fill=BOTH, expand=True, padx=(4, 0), pady=2)

        # 目录 / 书签
        cat_page = tk.Frame(nb, bg=PANEL)
        nb.add(cat_page, text="  目录书签  ")
        bar = tk.Frame(cat_page, bg=PANEL)
        bar.pack(fill=X, pady=2, padx=4)
        flat_button(bar, "添加书签", self.add_bookmark_dialog, padx=8, pady=2).pack(side=LEFT, padx=2)
        flat_button(bar, "删除所选", self.delete_bookmark_selected, padx=8, pady=2).pack(side=LEFT, padx=2)
        flat_button(bar, "刷新", self.refresh_catalog, padx=8, pady=2).pack(side=LEFT, padx=2)
        self.catalog = _ttk.Treeview(cat_page, columns=("lv", "title", "page"),
                                     show="headings", height=4)
        self.catalog.heading("lv", text="层级")
        self.catalog.heading("title", text="标题")
        self.catalog.heading("page", text="页")
        self.catalog.column("lv", width=50, anchor="center")
        self.catalog.column("title", width=320)
        self.catalog.column("page", width=60, anchor="center")
        self.catalog.pack(fill=BOTH, expand=True, padx=4, pady=(0, 4))
        self.catalog.bind("<Double-1>", self._catalog_goto)

        # 批注
        an_page = tk.Frame(nb, bg=PANEL)
        nb.add(an_page, text="  批注  ")
        bar2 = tk.Frame(an_page, bg=PANEL)
        bar2.pack(fill=X, pady=2, padx=4)
        flat_button(bar2, "刷新", self.refresh_annotations, padx=8, pady=2).pack(side=LEFT, padx=2)
        flat_button(bar2, "定位", self.locate_annotation_selected, padx=8, pady=2).pack(side=LEFT, padx=2)
        flat_button(bar2, "删除所选", self.delete_annotation_selected, padx=8, pady=2).pack(side=LEFT, padx=2)
        flat_button(bar2, "全部清除", self.clear_all_annots, padx=8, pady=2).pack(side=LEFT, padx=2)
        self.annots = _ttk.Treeview(an_page, columns=("pg", "type", "content", "kind"),
                                    show="headings", height=4)
        self.annots.heading("pg", text="页")
        self.annots.heading("type", text="类型")
        self.annots.heading("content", text="内容")
        self.annots.heading("kind", text="说明")
        self.annots.column("pg", width=44, anchor="center")
        self.annots.column("type", width=86, anchor="center")
        self.annots.column("content", width=250)
        self.annots.column("kind", width=70, anchor="center")
        self.annots.pack(fill=BOTH, expand=True, padx=4, pady=(0, 4))
        self.annots.bind("<Double-1>", self._annot_goto)

        self._panel_nb = nb

    # ============================================================= 状态栏
    def _build_statusbar(self) -> None:
        bar = tk.Frame(self.root, bg=BLUE_DARK, height=28)
        bar.pack(fill=X, side=BOTTOM)
        bar.pack_propagate(False)

        self.status_left = tk.Label(bar, text="就绪", bg=BLUE_DARK, fg="white",
                                    font=font(9), anchor="w")
        self.status_left.pack(side=LEFT, padx=10)

        self.progress = _ttk.Progressbar(bar, mode="determinate", length=170,
                                        maximum=100)
        self.progress.pack(side=LEFT, padx=8, pady=5)
        self.progress.pack_forget()

        self.zoom_var = tk.StringVar(value="100%")
        tk.Label(bar, textvariable=self.zoom_var, bg=BLUE_DARK, fg="white",
                 font=font(9)).pack(side=RIGHT, padx=8)
        self.page_var = tk.StringVar(value="第 0 / 0 页")
        tk.Label(bar, textvariable=self.page_var, bg=BLUE_DARK, fg="white",
                 font=font(9)).pack(side=RIGHT, padx=8)

        for txt, cmd in (("下一页", lambda: self.goto_page(self.current_page + 1)),
                         ("上一页", lambda: self.goto_page(self.current_page - 1))):
            b = tk.Button(bar, text=txt, command=cmd, relief="flat", bg=BLUE,
                          fg="white", activebackground=BLUE_DARK,
                          activeforeground="white", font=font(8), padx=8, bd=0,
                          cursor="hand2", highlightthickness=0)
            b.pack(side=RIGHT, padx=3, pady=3)

        # 页码跳转
        self.jump_var = tk.StringVar(value="1")
        e = _ttk.Entry(bar, textvariable=self.jump_var, width=4)
        e.pack(side=RIGHT, padx=(2, 6))
        e.bind("<Return>", lambda ev: self._jump_entry())
        tk.Label(bar, text="跳至", bg=BLUE_DARK, fg="white",
                 font=font(8)).pack(side=RIGHT, padx=(6, 2))

    # ============================================================== 快捷键
    def _bind_keys(self) -> None:
        b = self.root.bind_all
        b("<Control-o>", lambda e: self.open_pdf())
        b("<Control-s>", lambda e: self.save())
        b("<Control-Shift-S>", lambda e: self.save_as())
        b("<Control-z>", lambda e: self.undo())
        b("<Control-y>", lambda e: self.redo())
        b("<Control-a>", lambda e: self.select_all())
        b("<Control-f>", lambda e: self.toggle_find_bar())
        b("<Control-g>", lambda e: self.goto_dialog())
        b("<Control-q>", lambda e: self._on_close())
        b("<Control-plus>", lambda e: self.zoom_step(1.15))
        b("<Control-equal>", lambda e: self.zoom_step(1.15))
        b("<Control-minus>", lambda e: self.zoom_step(1 / 1.15))
        b("<Control-Key-0>", lambda e: self.zoom_reset())
        b("<Prior>", lambda e: self.goto_page(self.current_page - 1))
        b("<Next>", lambda e: self.goto_page(self.current_page + 1))
        b("<Home>", lambda e: self.goto_page(1))
        b("<End>", lambda e: self.goto_page(self._page_count))
        b("<Escape>", lambda e: self._on_escape())
        b("<F3>", lambda e: self.find_next())
        b("<Left>", lambda e: self.goto_page(self.current_page - 1))
        b("<Right>", lambda e: self.goto_page(self.current_page + 1))

    def _on_escape(self) -> None:
        if self._annot_tool:
            self.cancel_annot()
        elif self._find_visible:
            self.toggle_find_bar(False)

    # ============================================================== 日志
    def _log(self, msg: str) -> None:
        try:
            self.log.configure(state=tk.NORMAL)
            self.log.insert(tk.END, msg + "\n")
            # 限制日志行数，避免长时间运行后内存增长
            if int(self.log.index("end-1c").split(".")[0]) > 800:
                self.log.delete("1.0", "200.0")
            self.log.see(tk.END)
            self.log.configure(state=tk.DISABLED)
        except Exception:
            pass

    def _status(self, msg: str) -> None:
        try:
            self.status_left.configure(text=msg)
        except Exception:
            pass

    def _warn(self, msg: str) -> None:
        self._status(msg)
        self._log("⚠ " + msg)
        messagebox.showwarning("提示", msg)

    def _error_dialog(self, title: str, msg: str) -> None:
        self._status(msg)
        self._log("✗ " + msg)
        messagebox.showerror(title, msg)

    def _unexpected(self, where: str, exc: BaseException) -> None:
        import traceback

        tb = traceback.format_exc()
        self._log(f"✗ 内部错误（{where}）：{exc}")
        _crash_log(tb)
        messagebox.showerror(
            "出现意外错误",
            f"操作「{where}」未能完成：\n\n{exc}\n\n"
            "文档本身未受影响，可继续使用。详细信息已记入操作日志。",
        )

    def _tk_exception(self, exc_type, exc_value, exc_tb) -> None:
        import traceback

        detail = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        _crash_log(detail)
        self._log(f"✗ 界面异常：{exc_value}")
        try:
            messagebox.showerror("界面异常", f"{exc_value}\n\n程序会尽力继续运行。")
        except Exception:
            pass

    # ========================================================== 任务状态
    def _on_task_state(self, busy: bool, name: str | None) -> None:
        try:
            if busy:
                self._status(f"正在{name}…")
                self.progress.configure(mode="indeterminate")
                self.progress.pack(side=LEFT, padx=8, pady=5)
                self.progress.start(60)
            else:
                self.progress.stop()
                self.progress.pack_forget()
                self._update_ui_state()
        except Exception:
            pass

    # ============================================================ 打开文档
    @guarded
    def open_pdf(self) -> None:
        p = filedialog.askopenfilename(
            title="打开 PDF", filetypes=[("PDF 文件", "*.pdf"), ("所有文件", "*.*")])
        if p:
            self.open_path(Path(p))

    @guarded
    def open_path(self, path: Path) -> None:
        """打开指定 PDF（支持加密文档询问口令）。"""
        if not Path(path).exists():
            self._warn(f"文件不存在：{path}")
            return
        if self.session.is_open and self.session.dirty:
            if not messagebox.askyesno("未保存的修改", "当前文档有未保存的修改，仍要打开新文件吗？"):
                return

        password: str | None = None
        try:
            if is_encrypted(path):
                password = simpledialog.askstring(
                    "需要口令", f"该 PDF 已加密，请输入打开口令：\n{Path(path).name}",
                    show="•", parent=self.root)
                if password is None:
                    return
        except Exception:
            password = None

        def job(progress):
            progress(0, 0, "打开")
            sess = DocumentSession(path, password)
            # 惰性尺寸表：只采样少量页用于布局估算，不再遍历全部页面
            # （300 页文档的全量读取需 ~167 ms，采样仅 ~1.3 ms）。
            dims = _PageDims(sess.doc, sess.page_count)
            return sess, dims

        def done(result):
            sess, dims = result
            if self.session.is_open:
                self.session.close()
            self.session = sess
            self.doc_path = sess.source
            self._dims = dims
            self._page_count = len(dims)
            self.current_page = 1
            self.selection.clear()
            self._scroll_x = self._scroll_y = 0
            self._preview_cache.clear()
            self._thumb_cache.clear()
            self._compute_thumb_cell()
            self._zoom_mode = "fit_width"
            self._find_hits = []
            if self._find_visible:
                self.find_info.configure(text="")
            self._remember(Path(path))
            self._log(f"打开文件：{path}（{self._page_count} 页）")
            self._status(f"已打开 {Path(path).name}")
            self._invalidate_thumbs()
            self._refresh_panels()
            self._render_page(force=True)
            self._update_ui_state()
            self._save_config()
            # 打开后必须主动触发一次缩略图构建：画布尺寸没变化时
            # tkinter 不会发出 <Configure>，否则左栏会一直空着。
            self._schedule_thumb_sync(10)

        self._tasks.submit("打开文档", job, done, on_error=self._task_error)

    def _task_error(self, exc: BaseException, tb: str) -> None:
        _crash_log(tb)
        if isinstance(exc, (PdfPasswordRequired, PdfPasswordError)):
            self._error_dialog("口令问题", str(exc))
        else:
            self._error_dialog("操作失败", str(exc))

    @guarded
    def close_document(self) -> None:
        if not self.session.is_open:
            return
        if self.session.dirty and not messagebox.askyesno(
            "未保存的修改", "当前文档有未保存的修改，仍要关闭吗？"
        ):
            return
        self.session.close()
        self.doc_path = None
        self._page_count = 0
        self._dims = []
        self.current_page = 1
        self.selection.clear()
        self._preview_cache.clear()
        self._thumb_cache.clear()
        self._find_hits = []
        self._invalidate_thumbs()
        self._refresh_panels()
        self.root.title("PDF 编辑器")
        self.canvas.delete("all")
        self._render_empty()
        self._update_ui_state()
        self._log("已关闭文档")

    # ============================================================ 状态刷新
    def _update_ui_state(self) -> None:
        if self._page_count:
            self.page_var.set(f"第 {self.current_page} / {self._page_count} 页")
            self.jump_var.set(str(self.current_page))
        else:
            self.page_var.set("第 0 / 0 页")
            self.jump_var.set("")
        self.zoom_var.set(f"{int(self.zoom * 100)}%")
        star = " *" if self.session.is_open and self.session.dirty else ""
        name = self.doc_path.name if self.doc_path else "PDF 编辑器"
        self.root.title(f"{name}{star} - PDF 编辑器 v{APP_VERSION}")
        n_sel = len(self.selection)
        self.thumb_count_lbl.configure(
            text=f"共 {self._page_count} 页" + (f" · 选中 {n_sel}" if n_sel else "")
        )

    def _render_empty(self) -> None:
        self.canvas.delete("all")
        w = max(self.canvas.winfo_width(), 400)
        h = max(self.canvas.winfo_height(), 300)
        self.canvas.create_text(w // 2, h // 2 - 24, text="拖入 PDF 文件，或点击「打开」",
                                fill="#EAF0F6", font=font(15, True))
        self.canvas.create_text(w // 2, h // 2 + 8,
                                text="支持 合并 · 拆分 · 旋转 · 重排 · 水印 · 批注 · 加密",
                                fill="#C8D4E0", font=font(10))

    # ============================================================== 缩略图
    def _compute_thumb_cell(self) -> None:
        if not self._dims:
            self._thumb_cell_h = THUMB_MAX_H + THUMB_LABEL_H + THUMB_PAD
            return
        # 用惰性尺寸表的采样值估算，避免为了布局而遍历全部页面
        if isinstance(self._dims, _PageDims):
            w, h = self._dims.estimated
            ratio = (h / w) if w > 0 else 1.414
        else:
            ratios = [h / w for w, h in self._dims if w > 0]
            ratio = max(ratios) if ratios else 1.414
        ratio = min(max(ratio, 0.6), 1.6)
        self._thumb_cell_h = int(THUMB_W * ratio) + THUMB_LABEL_H + THUMB_PAD

    def _invalidate_thumbs(self) -> None:
        self._thumb_queue.clear()
        self._thumb_pumping = False
        for widgets in self._thumb_widgets.values():
            for w in widgets:
                w.destroy()
        self._thumb_widgets.clear()
        self.thumb_canvas.delete("all")
        self._thumb_cache.clear()
        icons.clear_cache()
        self.thumb_canvas.configure(scrollregion=(0, 0, THUMB_W + 20,
                                                  self._page_count * self._thumb_cell_h + 12))

    def _on_thumb_scroll(self, first: str, last: str) -> None:
        try:
            self.thumb_canvas.yview_moveto(first)
        except Exception:
            pass
        self._schedule_thumb_sync()

    def _thumb_wheel(self, event) -> None:
        self.thumb_canvas.yview_scroll(-3 if event.delta > 0 else 3, "units")
        self._schedule_thumb_sync()

    def _schedule_thumb_sync(self, delay: int = 30) -> None:
        """安排一次缩略图同步（合并连续请求，避免频繁重建控件）。"""
        if self._thumb_sync_job:
            try:
                self.root.after_cancel(self._thumb_sync_job)
            except Exception:
                pass
        self._thumb_sync_job = self.root.after(delay, self._sync_thumbs)

    def _visible_thumb_range(self) -> tuple[int, int]:
        if self._page_count == 0:
            return 0, 0
        view_h = max(self.thumb_canvas.winfo_height(), 1)
        try:
            top = self.thumb_canvas.canvasy(0)
        except Exception:
            top = 0
        cell = max(self._thumb_cell_h, 1)
        first = max(0, int(top // cell) - 1)
        # 窗口刚建立时 winfo_height() 可能还是 1，至少预建几页避免左栏空着
        visible = max(view_h // cell, 6)
        last = min(self._page_count, first + visible + 3)
        return first, last

    def _sync_thumbs(self) -> None:
        self._thumb_sync_job = None
        if self._page_count == 0 or not self.session.is_open:
            return
        first, last = self._visible_thumb_range()
        # 1) 回收不可见控件
        for idx in list(self._thumb_widgets):
            if idx < first - 4 or idx >= last + 4:
                for w in self._thumb_widgets.pop(idx):
                    w.destroy()
        # 2) 创建可见控件（每次限量，避免卡顿）
        budget = 10
        to_make = [i for i in range(first, last) if i not in self._thumb_widgets]
        for idx in to_make[:budget]:
            self._create_thumb(idx)
        if len(to_make) > budget:
            self._thumb_sync_job = self.root.after(24, self._sync_thumbs)
        self._start_thumb_pump()
        # 3) 刷新选中态
        for idx, widgets in self._thumb_widgets.items():
            self._paint_thumb_state(idx, widgets)

    def _thumb_image(self, idx: int) -> Image.Image | None:
        key = (idx, THUMB_W)
        im = self._thumb_cache.get(key)
        if im is not None:
            self._thumb_cache.move_to_end(key)
            return im  # type: ignore[return-value]
        if not self.session.is_open or idx >= self._page_count:
            return None
        zoom = THUMB_W / max(self._dims[idx][0], 1)
        try:
            img = page_image(self.session.doc[idx], zoom, max_pixels=0)
        except Exception as exc:
            self._log(f"缩略图渲染失败（第 {idx + 1} 页）：{exc}")
            return None
        if img.height > THUMB_MAX_H:
            img = img.resize(
                (max(1, int(img.width * THUMB_MAX_H / img.height)), THUMB_MAX_H),
                Image.LANCZOS,
            )
        photo = ImageTk.PhotoImage(img)
        self._thumb_cache[key] = photo  # type: ignore[assignment]
        while len(self._thumb_cache) > THUMB_CACHE_MAX:
            self._thumb_cache.popitem(last=False)
        try:
            img.close()
        except Exception:
            pass
        return photo  # type: ignore[return-value]

    def _thumb_placeholder(self) -> ImageTk.PhotoImage | None:
        if getattr(self, "_ph_holder", None) is None:
            im = Image.new("RGB", (THUMB_W, int(THUMB_W * 1.414)), "#F4F6F9")
            d = ImageDraw.Draw(im)
            d.rectangle((0, 0, im.width - 1, im.height - 1), outline="#E1E6EC")
            self._ph_holder = ImageTk.PhotoImage(im)
        return self._ph_holder

    def _create_thumb(self, idx: int) -> None:
        cell = self._thumb_cell_h
        y = 6 + idx * cell
        # 先放占位图，保证滚动到底时立刻有内容，随后再补真实缩略图
        frame = tk.Frame(self.thumb_canvas, bg=PANEL,
                         width=THUMB_W + 16, height=cell - 4)
        self.thumb_canvas.create_window(
            (THUMB_W // 2 + 10, y + (cell - THUMB_PAD) // 2), window=frame,
            anchor="center", tags=("thumb", f"thumb-{idx + 1}"))
        img = self._thumb_image(idx)
        if img is None and not self._page_ready(idx):
            img = self._thumb_placeholder()
            self._thumb_queue.append(idx)
        lbl = tk.Label(frame, image=img, bg=PANEL, bd=1, relief="solid",
                       cursor="hand2", highlightthickness=0)
        lbl.image = img
        lbl.pack(pady=(0, 1))
        num = tk.Label(frame, text=str(idx + 1), bg=PANEL, fg=TEXT_MUTED,
                       font=font(8), cursor="hand2")
        num.pack()
        widgets = [frame, lbl, num]
        for w in widgets:
            w.bind("<Button-1>", lambda e, i=idx: self._thumb_click(e, i))
            w.bind("<Button-3>", lambda e, i=idx: self._thumb_menu(e, i))
            w.bind("<MouseWheel>", self._thumb_wheel)
        self._thumb_widgets[idx] = widgets
        self._paint_thumb_state(idx, widgets)

    def _page_ready(self, idx: int) -> bool:
        try:
            return len(self.session.doc[idx].get_contents()) > 0
        except Exception:
            return True

    def _start_thumb_pump(self) -> None:
        """启动缩略图补齐队列（每次空闲只渲染一张，避免卡顿）。"""
        if self._thumb_queue and not self._thumb_pumping:
            self._thumb_pumping = True
            self.root.after(60, self._pump_thumb_queue)

    def _pump_thumb_queue(self) -> None:
        if not self._thumb_queue:
            self._thumb_pumping = False
            return
        idx = self._thumb_queue.pop(0)
        widgets = self._thumb_widgets.get(idx)
        if widgets:
            img = self._thumb_image(idx)
            if img is not None:
                try:
                    widgets[1].configure(image=img)
                    widgets[1].image = img
                except Exception:
                    pass
        self.root.after(50, self._pump_thumb_queue)

    def _paint_thumb_state(self, idx: int, widgets: list[tk.Widget]) -> None:
        page = idx + 1
        selected = page in self.selection
        if selected:
            border, bgc, fg = BLUE, SEL_SOFT, BLUE_DARK
        elif page == self.current_page:
            border, bgc, fg = BLUE_DARK, BLUE_LIGHT, BLUE_DARK
        else:
            border, bgc, fg = BORDER, PANEL, TEXT_MUTED
        try:
            widgets[1].configure(bd=2 if (selected or page == self.current_page) else 1,
                                 relief="solid", highlightbackground=border)
            widgets[1].master.configure(bg=bgc)
            widgets[2].configure(bg=bgc, fg=fg,
                                 font=font(8, selected or page == self.current_page))
        except Exception:
            pass

    def _thumb_click(self, event, idx: int) -> None:
        page = idx + 1
        ctrl = bool(event.state & 0x0004)
        shift = bool(event.state & 0x0001)
        if ctrl:
            if page in self.selection:
                self.selection.discard(page)
            else:
                self.selection.add(page)
        elif shift and self.selection:
            self.selection = _shift_selection(
                self._sel_anchor or self.current_page, page)
        else:
            self.selection = {page}
            self._sel_anchor = page
        self.goto_page(page)
        self._update_ui_state()

    def _thumb_menu(self, event, idx: int) -> None:
        page = idx + 1
        if page not in self.selection:
            self.selection = {page}
        self.goto_page(page)
        m = tk.Menu(self.root, tearoff=0)
        m.add_command(label=f"第 {page} 页", state="disabled")
        m.add_separator()
        m.add_command(label="提取选中页…", command=self.extract_selected)
        m.add_command(label="删除选中页", command=self.delete_selected)
        m.add_command(label="复制页到末尾", command=self.duplicate_page)
        m.add_command(label="旋转选中页 +90°", command=lambda: self.rotate(90))
        m.add_command(label="旋转选中页 -90°", command=lambda: self.rotate(-90))
        m.add_separator()
        m.add_command(label="移到最前", command=lambda: self.move_abs(1))
        m.add_command(label="移到末尾", command=lambda: self.move_abs(0))
        m.add_separator()
        m.add_command(label="添加书签…", command=self.add_bookmark_dialog)
        m.add_command(label="全选页面", command=self.select_all)
        m.add_command(label="清除选择", command=self.clear_selection)
        try:
            m.tk_popup(event.x_root, event.y_root)
        finally:
            m.grab_release()

    def toggle_thumbs(self) -> None:
        if self.left.winfo_ismapped():
            self.left.pack_forget()
            self._log("已隐藏缩略图面板")
        else:
            self.left.pack(side=LEFT, fill=Y, before=self.right)
            self._schedule_thumb_sync()
            self._log("已显示缩略图面板")

    def toggle_panel(self) -> None:
        if self.panel.winfo_ismapped():
            self.panel.pack_forget()
        else:
            self.panel.pack(fill=X, side=BOTTOM)
            self._schedule_render()

    def show_catalog_tab(self) -> None:
        self._panel_nb.select(1)
        self.refresh_catalog()

    # =============================================================== 预览
    def _schedule_render(self, delay: int = 90) -> None:
        if self._render_job:
            try:
                self.root.after_cancel(self._render_job)
            except Exception:
                pass
        self._render_job = self.root.after(delay, self._render_page)

    def _viewport(self) -> tuple[int, int]:
        return max(self.canvas.winfo_width(), 1), max(self.canvas.winfo_height(), 1)

    def _fit_zoom(self, mode: str) -> float:
        if not self._dims:
            return 1.0
        w, h = self._dims[min(self.current_page - 1, len(self._dims) - 1)]
        vw, vh = self._viewport()
        if mode == "fit_width":
            return max(0.05, (vw - 56) / max(w, 1))
        return max(0.05, min((vw - 56) / max(w, 1), (vh - 56) / max(h, 1)))

    def _effective_scale(self, page_idx: int, zoom: float) -> float:
        """考虑像素上限后的实际渲染缩放。"""
        if page_idx >= len(self._dims):
            return zoom
        w, h = self._dims[page_idx]
        area = max(w * h * zoom * zoom, 1)
        if area > PREVIEW_MAX_PIXELS:
            return zoom * (PREVIEW_MAX_PIXELS / area) ** 0.5
        return zoom

    def _render_page(self, force: bool = False) -> None:
        self._render_job = None
        if not self.session.is_open or self._page_count == 0:
            self._render_empty()
            return

        if self._zoom_mode != "custom" or force:
            if self._zoom_mode != "custom":
                self.zoom = self._fit_zoom(self._zoom_mode)

        idx = self.current_page - 1
        scale = self._effective_scale(idx, self.zoom)
        key = (idx, round(scale, 4))

        img = self._preview_cache.get(key)
        if img is None:
            try:
                img = page_image(self.session.doc[idx], scale, max_pixels=0)
            except Exception as exc:
                self._log(f"渲染失败：{exc}")
                return
            self._preview_cache[key] = img
            while len(self._preview_cache) > PREVIEW_CACHE_MAX:
                _, old = self._preview_cache.popitem(last=False)
                try:
                    old.close()
                except Exception:
                    pass
        else:
            self._preview_cache.move_to_end(key)

        self.canvas.delete("all")
        vw, vh = self._viewport()
        iw, ih = img.size
        max_sx = max(0, iw - vw + 40)
        max_sy = max(0, ih - vh + 40)
        self._scroll_x = min(max(self._scroll_x, 0), max_sx)
        self._scroll_y = min(max(self._scroll_y, 0), max_sy)
        ox = (vw - iw) / 2 - self._scroll_x
        oy = (vh - ih) / 2 - self._scroll_y
        if ih > vh:
            oy = 20 - self._scroll_y
        self._view_origin = (ox, oy)
        self._view_scale = scale

        # 纸张阴影 + 白底
        self.canvas.create_rectangle(ox + 4, oy + 5, ox + iw + 4, oy + ih + 5,
                                     fill="#6E7A88", outline="")
        self.canvas.create_rectangle(ox, oy, ox + iw, oy + ih,
                                     fill="#FFFFFF", outline=BORDER)
        self._photo_ref = ImageTk.PhotoImage(img)
        self.canvas.create_image(ox, oy, image=self._photo_ref, anchor="nw")

        self._draw_find_highlights()
        self._draw_annot_overlay()
        self._status(f"第 {self.current_page} 页 / 共 {self._page_count} 页　缩放 {int(self.zoom * 100)}%")
        if self.zoom_var.get() != f"{int(self.zoom * 100)}%":
            self.zoom_var.set(f"{int(self.zoom * 100)}%")

    def _page_to_canvas(self, px: float, py: float) -> tuple[float, float]:
        ox, oy = self._view_origin
        rect = self.session.doc[self.current_page - 1].rect
        return (ox + (px - rect.x0) * self._view_scale,
                oy + (py - rect.y0) * self._view_scale)

    def _canvas_to_page(self, cx: float, cy: float) -> tuple[float, float]:
        ox, oy = self._view_origin
        rect = self.session.doc[self.current_page - 1].rect
        return ((cx - ox) / self._view_scale + rect.x0,
                (cy - oy) / self._view_scale + rect.y0)

    def _scroll_by(self, dy: float, dx: float = 0.0) -> None:
        if not self.session.is_open:
            return
        before = self._scroll_y
        self._scroll_y += dy
        self._scroll_x += dx
        vw, vh = self._viewport()
        idx = min(self.current_page - 1, len(self._dims) - 1)
        w, h = self._dims[idx]
        ih = h * self._view_scale
        max_sy = max(0, ih - vh + 40)
        if self._scroll_y < 0 and before <= 0 and dy < 0:
            self.goto_page(self.current_page - 1)
            self._scroll_y = 10 ** 9  # 触发下一页时保持在底部
            return
        if self._scroll_y > max_sy and dy > 0:
            self.goto_page(self.current_page + 1)
            self._scroll_y = 0
            return
        self._scroll_y = min(max(self._scroll_y, 0), max_sy)
        self._render_page()

    def _on_wheel(self, event) -> None:
        if not self.session.is_open:
            return
        if event.state & 0x0004:  # Ctrl + 滚轮 -> 缩放
            self.zoom_step(1.15 if event.delta > 0 else 1 / 1.15)
            return
        self._scroll_by(-event.delta / 3)

    def _on_hwheel(self, event) -> None:
        self._scroll_by(0, -event.delta / 3)

    def _on_pan_start(self, event) -> None:
        self._pan_start = (event.x, event.y, self._scroll_x, self._scroll_y)

    def _on_pan_move(self, event) -> None:
        if not self._pan_start:
            return
        sx, sy, ox, oy = self._pan_start
        self._scroll_x = ox - (event.x - sx)
        self._scroll_y = oy - (event.y - sy)
        self._render_page()

    # ------------------------------------------------------------ 标注交互
    def toggle_annot(self, tool: str) -> None:
        if not self.session.is_open:
            self._warn("请先打开一个 PDF 文件")
            return
        if self._annot_tool == tool:
            self.cancel_annot()
            return
        self._annot_tool = tool
        label = {"text": "便签", "freetext": "文本框", "ink": "手绘",
                 "redact": "涂黑脱敏"}.get(tool, ANNOT_KINDS.get(tool, tool))
        self.canvas.configure(cursor="crosshair")
        self._status(f"标注模式：{label} —— 在页面上拖拽即可添加（Esc 退出）")
        self._log(f"进入标注模式：{label}")

    def cancel_annot(self) -> None:
        if self._annot_tool:
            self._log("已退出标注模式")
        self._annot_tool = None
        self._drag_start = None
        if self._drag_id:
            try:
                self.canvas.delete(self._drag_id)
            except Exception:
                pass
            self._drag_id = None
        try:
            self.canvas.configure(cursor="")
        except Exception:
            pass
        self._status("就绪")

    def _on_press(self, event) -> None:
        if not self._annot_tool or not self.session.is_open:
            return
        self._drag_start = None
        self._ink_points = []
        if self._annot_tool == "ink":
            self._ink_points = [event.x, event.y]
            self._drag_start = (event.x, event.y)
            self._drag_id = None
            return
        self._drag_start = (event.x, event.y)

    def _on_drag(self, event) -> None:
        if not self._annot_tool or not self.session.is_open:
            return
        if self._annot_tool == "ink":
            if not self._ink_points:
                return
            self._ink_points += [event.x, event.y]
            self._render_page()
            self._draw_annot_overlay(ink_draft=self._ink_points)
            return
        if not self._drag_start:
            return
        self._render_page()
        x0, y0 = self._drag_start
        self._draw_annot_overlay(draft=(x0, y0, event.x, event.y))

    def _on_release(self, event) -> None:
        if not self._annot_tool or not self.session.is_open:
            return
        tool = self._annot_tool
        if tool == "ink":
            pts = self._ink_points or []
            self._ink_points = []
            self._drag_start = None
            if len(pts) < 6:
                self._render_page()
                return

            def op(d):
                page_pts = []
                stroke: list[float] = []
                for i in range(0, len(pts) - 1, 2):
                    px, py = self._canvas_to_page(pts[i], pts[i + 1])
                    stroke += [px, py]
                page_pts.append(stroke)
                add_annotation(d, self.current_page, "ink", (0, 0, 0, 0),
                               points=page_pts, stroke=(0.1, 0.25, 0.6), width=2)

            self._mutate(op, f"已添加手绘批注（第 {self.current_page} 页）")
            return

        if not self._drag_start:
            return
        x0, y0 = self._drag_start
        self._drag_start = None
        px0, py0 = self._canvas_to_page(x0, y0)
        px1, py1 = self._canvas_to_page(event.x, event.y)
        rect = (min(px0, px1), min(py0, py1), max(px0, px1), max(py0, py1))
        if tool in ("text", "freetext", "stamp"):
            if rect[2] - rect[0] < 6 or rect[3] - rect[1] < 6:
                rect = (rect[0], rect[1], rect[0] + 160, rect[1] + 44)
        elif tool == "redact":
            if rect[2] - rect[0] < 3 or rect[3] - rect[1] < 3:
                self._render_page()
                self._status("拖拽范围太小，已取消")
                return
        elif rect[2] - rect[0] < 3 or rect[3] - rect[1] < 3:
            self._render_page()
            self._status("拖拽范围太小，已取消")
            return
        simple = {"highlight", "underline", "strikeout", "squiggly",
                  "rect", "circle"}.intersection({tool})
        if simple:
            self._apply_annot(tool, rect)
        else:
            self._render_page()
            self._annot_interactive(tool, rect)

    def _annot_interactive(self, tool: str, rect) -> None:
        """需要补充信息的标注（便签/文本框/图章/涂黑/手绘）。"""
        page = self.current_page
        if tool == "text":
            txt = simpledialog.askstring("便签内容", "输入便签文字：", parent=self.root)
            if not txt:
                return
            self._mutate(lambda d: add_annotation(d, page, "text", rect, text=txt),
                         "已添加便签")
        elif tool == "freetext":
            txt = simpledialog.askstring("文本框内容", "输入文本（可多行）：", parent=self.root)
            if not txt:
                return
            self._mutate(lambda d: add_annotation(d, page, "freetext", rect, text=txt),
                         "已添加文本框")
        elif tool == "stamp":
            name = simpledialog.askstring(
                "图章", "图章文字（Draft / Approved / Confidential…）：",
                initialvalue="Draft", parent=self.root)
            if not name:
                return
            self._mutate(lambda d: add_annotation(d, page, "stamp", rect, stamp=name),
                         f"已添加图章「{name}」")
        elif tool == "redact":
            if not messagebox.askyesno(
                "确认脱敏",
                "涂黑会**永久移除**该区域内的文字与图像，且无法撤销到原始内容。\n\n继续吗？",
            ):
                return
            self._mutate(lambda d: apply_redaction(d, page, rect), "已完成脱敏涂黑")
        elif tool == "ink":
            pts = [[(rect[0], rect[1]), ((rect[0] + rect[2]) / 2, rect[3]), (rect[2], rect[1])]]
            self._mutate(lambda d: add_annotation(d, page, "ink", rect, points=pts),
                         "已添加手绘")

    def _apply_annot(self, tool: str, rect, *, keep_mode: bool = True) -> None:
        page = self.current_page
        kind, label, color = ANNOT_TOOLS.get(tool, (tool, tool, BLUE))
        rgb = tuple(int(color[i:i + 2], 16) / 255 for i in (1, 3, 5))

        def op(d):
            add_annotation(d, page, kind, rect, color=rgb, opacity=0.45 if kind in
                           ("highlight", "underline", "strikeout", "squiggly") else 0.9)

        self._mutate(op, f"已添加{label}（第 {page} 页）", keep_annot=keep_mode)

    def _draw_annot_overlay(self, items: list | None = None, *, draft=None,
                            ink_draft=None) -> None:
        """在预览上描出批注轮廓：已有批注 + 正在拖拽的草稿。"""
        if self.session.is_open:
            if items is None:
                try:
                    items = list_annotations(self.session.doc, self.current_page)
                except Exception:
                    items = []
            for a in items:
                try:
                    x0, y0, x1, y1 = a["rect"]
                    c0 = self._page_to_canvas(x0, y0)
                    c1 = self._page_to_canvas(x1, y1)
                    pad = 1
                    self.canvas.create_rectangle(
                        c0[0] - pad, c0[1] - pad, c1[0] + pad, c1[1] + pad,
                        outline="#F0A32B", dash=(3, 2), width=1)
                except Exception:
                    continue
        if draft is not None:
            self.canvas.create_rectangle(*draft, outline=BLUE, dash=(4, 3), width=2)
        if ink_draft:
            flat = [c for pair in zip(ink_draft[::2], ink_draft[1::2]) for c in pair]
            if len(flat) >= 4:
                self.canvas.create_line(*flat, fill=BLUE, width=2, smooth=True)

    # ---------------------------------------------------------- 查找高亮
    def toggle_find_bar(self, show: bool | None = None) -> None:
        target = (not self._find_visible) if show is None else show
        if target:
            self.find_bar.pack(fill=X, after=None, before=self.canvas)
            self._find_visible = True
            self.find_entry.focus_set()
            self.find_entry.select_range(0, "end")
        else:
            self.find_bar.pack_forget()
            self._find_visible = False
            self._find_hits = []
            self._find_index = -1
            self._render_page()

    def _refind(self) -> None:
        """查找条件（区分大小写）变化后重新定位。"""
        self._find_hits = []
        self._find_index = -1
        if self.find_var.get().strip():
            self._find_run(forward=True)
        else:
            self.find_info.configure(text="")
            self._render_page()

    def _do_find(self) -> list:
        """同步查找并返回命中列表（供导航使用）。"""
        needle = self.find_var.get().strip()
        if not needle or not self.session.is_open:
            return []
        try:
            self._find_hits = search_text(
                self.session.doc, needle,
                ignore_case=not self.find_case_var.get(),
            )
        except Exception as exc:
            self._log(f"查找失败：{exc}")
            self._find_hits = []
        return self._find_hits

    def find_next(self) -> None:
        self._find_run(forward=True)

    def find_prev(self) -> None:
        self._find_run(forward=False)

    def _find_run(self, *, forward: bool) -> None:
        needle = self.find_var.get().strip()
        if not needle:
            return
        if not self.session.is_open:
            self._warn("请先打开一个 PDF 文件")
            return

        # 同步查找：search_text 对常规文档足够快（万页级别仍在百毫秒内）
        try:
            self._find_hits = search_text(
                self.session.doc, needle,
                ignore_case=not self.find_case_var.get(),
            )
        except Exception as exc:
            self._error_dialog("查找失败", str(exc))
            return
        if not self._find_hits:
            self.find_info.configure(text="未找到")
            self._log(f"查找「{needle}」：无结果")
            self._render_page()
            return
        pages = [h.page for h in self._find_hits]
        total = sum(h.count for h in self._find_hits)
        if self._find_index < 0:
            # 从当前页开始找
            start = 0
            for i, p in enumerate(pages):
                if p >= self.current_page:
                    start = i
                    break
            self._find_index = start
        else:
            self._find_index = (self._find_index + (1 if forward else -1)) % len(pages)
        target = pages[self._find_index]
        self.find_info.configure(
            text=f"第 {self._find_index + 1} / {len(pages)} 处（本页 {self._find_hits[self._find_index].count} 处，共 {total} 处）")
        self.goto_page(target)
        self._log(f"查找「{needle}」：命中 {total} 处")

    def _draw_find_highlights(self) -> None:
        if not self._find_hits:
            return
        for hit in self._find_hits:
            if hit.page != self.current_page:
                continue
            first = True
            for x0, y0, x1, y1 in hit.rects:
                c0 = self._page_to_canvas(x0, y0)
                c1 = self._page_to_canvas(x1, y1)
                self.canvas.create_rectangle(
                    c0[0] - 1, c0[1] - 1, c1[0] + 1, c1[1] + 1,
                    outline="#E8A33D" if first else "", fill=FIND_HL, stipple="gray50",
                    width=2 if first else 0)
                first = False

    # ============================================================== 导航
    def goto_page(self, page: int) -> None:
        if not self.session.is_open or self._page_count == 0:
            return
        page = max(1, min(int(page), self._page_count))
        changed = page != self.current_page
        self.current_page = page
        if changed:
            self._scroll_x = self._scroll_y = 0
        self._render_page()
        self._schedule_thumb_sync()
        self._update_ui_state()
        # 注意：此处不刷新批注/目录面板——批注不随翻页变化，
        # 每翻一页重扫全部页面既拖慢翻页又会清空用户的选择。

    def _jump_entry(self) -> None:
        try:
            self.goto_page(int(self.jump_var.get()))
        except ValueError:
            self._status("页码格式不正确")

    def goto_dialog(self) -> None:
        if not self.session.is_open:
            self._warn("请先打开一个 PDF 文件")
            return
        s = simpledialog.askstring("跳转", f"输入页码（1-{self._page_count}）：",
                                   initialvalue=str(self.current_page), parent=self.root)
        if s:
            try:
                self.goto_page(int(s.strip()))
            except ValueError:
                self._warn("页码格式不正确")

    def zoom_step(self, factor: float) -> None:
        if not self.session.is_open:
            return
        self._zoom_mode = "custom"
        self.zoom = max(0.1, min(self.zoom * factor, 6.0))
        self._scroll_x = self._scroll_y = 0
        self._render_page()
        self._update_ui_state()

    def zoom_reset(self) -> None:
        if not self.session.is_open:
            return
        self._zoom_mode = "custom"
        self.zoom = 1.0
        self._scroll_x = self._scroll_y = 0
        self._render_page()
        self._update_ui_state()

    def fit_width(self) -> None:
        if not self.session.is_open:
            return
        self._zoom_mode = "fit_width"
        self._scroll_x = self._scroll_y = 0
        self._render_page()
        self._update_ui_state()

    def fit_page(self) -> None:
        if not self.session.is_open:
            return
        self._zoom_mode = "fit_page"
        self._scroll_x = self._scroll_y = 0
        self._render_page()
        self._update_ui_state()

    # ============================================================== 选择
    def select_all(self) -> None:
        if not self.session.is_open:
            return
        self.selection = set(range(1, self._page_count + 1))
        self._sel_anchor = 1
        self._schedule_thumb_sync()
        self._update_ui_state()
        self._status(f"已全选 {self._page_count} 页")

    def clear_selection(self) -> None:
        self.selection.clear()
        self._sel_anchor = None
        self._schedule_thumb_sync()
        self._update_ui_state()

    def _target_pages(self) -> list[int]:
        """当前操作目标页：有选择时用选择，否则用当前页。"""
        return sorted(self.selection) if self.selection else [self.current_page]

    # ========================================================== 修改封装
    def _mutate(self, op, msg: str, *, keep_annot: bool = False) -> bool:
        """执行一次文档修改：快照 → 修改 → 刷新界面。"""
        if not self.session.is_open:
            self._warn("请先打开一个 PDF 文件")
            return False
        undo_ok = self.session.push_undo()
        try:
            op(self.session.doc)
        except Exception as exc:
            self._error_dialog("操作失败", str(exc))
            return False
        if not undo_ok:
            self._log("提示：文档较大，本次操作未记录撤销点")
        self._page_count = self.session.page_count
        self._dims = _PageDims(self.session.doc, self._page_count)
        self.current_page = max(1, min(self.current_page, max(self._page_count, 1)))
        self.selection = {p for p in self.selection if p <= self._page_count}
        self._preview_cache.clear()
        release_render_cache()
        self._compute_thumb_cell()
        self._invalidate_thumbs()
        self._render_page()
        self._update_ui_state()
        self._refresh_panels()
        self._log("✓ " + msg)
        self._status(msg)
        self._start_thumb_pump()
        return True

    def _refresh_panels(self) -> None:
        self.refresh_catalog(quiet=True)
        self.refresh_annotations(quiet=True)

    # ============================================================ 撤销重做
    @guarded
    def undo(self) -> None:
        if not self.session.is_open:
            return
        if not self.session.can_undo:
            self._status("没有可撤销的操作")
            return
        self.session.undo()
        self._after_history("已撤销")

    @guarded
    def redo(self) -> None:
        if not self.session.is_open:
            return
        if not self.session.can_redo:
            self._status("没有可重做的操作")
            return
        self.session.redo()
        self._after_history("已重做")

    def _after_history(self, msg: str) -> None:
        self._page_count = self.session.page_count
        # 撤销/重做后页面结构已变，旧的尺寸缓存必须作废重建（仍用惰性表）
        self._dims = _PageDims(self.session.doc, self._page_count)
        self.current_page = max(1, min(self.current_page, max(self._page_count, 1)))
        self._preview_cache.clear()
        release_render_cache()
        self._compute_thumb_cell()
        self._invalidate_thumbs()
        self._render_page()
        self._update_ui_state()
        self._refresh_panels()
        self._log(msg)
        self._start_thumb_pump()

    # ============================================================ 页面操作
    @guarded
    def rotate(self, angle: int) -> None:
        pages = self._target_pages()
        self._mutate(lambda d: rotate_document(d, angle, pages),
                     f"已旋转 {len(pages)} 页（{angle:+d}°）")

    @guarded
    def delete_current(self) -> None:
        if not self.session.is_open:
            return
        if self._page_count <= 1:
            self._warn("至少需要保留一页")
            return
        if not messagebox.askyesno("确认", f"确定删除第 {self.current_page} 页？"):
            return
        p = self.current_page
        self._mutate(lambda d: delete_document_pages(d, [p]), f"已删除第 {p} 页")

    @guarded
    def delete_selected(self) -> None:
        pages = self._target_pages()
        if len(pages) >= self._page_count:
            self._warn("不能删除全部页面")
            return
        if not messagebox.askyesno("确认", f"确定删除选中的 {len(pages)} 页？"):
            return
        self.selection.clear()
        self._mutate(lambda d: delete_document_pages(d, pages),
                     f"已删除 {len(pages)} 页")

    @guarded
    def duplicate_page(self) -> None:
        if not self.session.is_open:
            return
        p = self.current_page

        def op(d):
            nd = extract_document_pages(d, [p])
            try:
                insert_document(d, nd, at=len(d))
            finally:
                nd.close()

        self._mutate(op, f"已复制第 {p} 页到末尾")

    @guarded
    def insert_blank(self) -> None:
        size = simpledialog.askstring(
            "插入空白页", "页面尺寸（a4 / a3 / letter / same=与当前页相同）：",
            initialvalue="a4", parent=self.root)
        if not size:
            return
        size = size.strip().lower()
        if size not in ("a4", "a3", "a5", "letter", "legal", "same"):
            self._warn("不支持的尺寸，请输入 a4 / a3 / a5 / letter / legal / same")
            return
        at = self.current_page
        self._mutate(lambda d: insert_blank_document_page(d, at=at, size=size),
                     f"已在第 {at} 页后插入空白页")

    @guarded
    def extract_selected(self) -> None:
        pages = self._target_pages()
        out = filedialog.asksaveasfilename(
            title="提取页面另存为", defaultextension=".pdf",
            initialfile=f"{self.doc_path.stem}_extract.pdf" if self.doc_path else "extract.pdf",
            filetypes=[("PDF 文件", "*.pdf")])
        if not out:
            return
        nd = extract_document_pages(self.session.doc, pages)
        try:
            nd.save(out, garbage=4, deflate=True)
        finally:
            nd.close()
        self._log(f"✓ 已提取 {len(pages)} 页 → {out}")
        self._status(f"已提取 {len(pages)} 页")
        if messagebox.askyesno("完成", "提取完成，是否立即打开该文件？"):
            self.open_path(Path(out))

    @guarded
    def reorder_dialog(self) -> None:
        if not self.session.is_open:
            return
        s = simpledialog.askstring(
            "重排页面",
            f"输入新的页序（1-{self._page_count}，逗号分隔）\n例如 3,1,2 表示新第 1 页是原第 3 页",
            initialvalue=",".join(str(i) for i in range(1, self._page_count + 1)),
            parent=self.root)
        if not s:
            return
        try:
            order = [int(x.strip()) for x in s.replace("，", ",").split(",") if x.strip()]
        except ValueError:
            self._warn("页序格式不正确，请用逗号分隔数字")
            return
        self.selection.clear()
        self._mutate(lambda d: reorder_document(d, order), "已完成页面重排")

    @guarded
    def move_rel(self, delta: int) -> None:
        if not self.session.is_open:
            return
        p = self.current_page
        t = p + delta
        if t < 1 or t > self._page_count:
            self._status("已经到头了")
            return
        self._mutate(lambda d: move_document_page(d, p, t),
                     f"已把第 {p} 页移动到第 {t} 位")
        self.goto_page(t)

    @guarded
    def move_abs(self, to: int) -> None:
        if not self.session.is_open:
            return
        p = self.current_page
        t = 1 if to <= 0 else to
        if p == t:
            return
        self._mutate(lambda d: move_document_page(d, p, t),
                     f"已把第 {p} 页移动到第 {t} 位")
        self.goto_page(t)

    @guarded
    def set_size(self, size: str) -> None:
        pages = self._target_pages()
        name = {"a4": "A4", "letter": "Letter"}.get(size, size)
        self._mutate(lambda d: set_document_page_size(d, size, pages),
                     f"已把 {len(pages)} 页统一为 {name}")

    @guarded
    def insert_pdf(self, at: int) -> None:
        if not self.session.is_open:
            return
        p = filedialog.askopenfilename(title="选择要插入的 PDF",
                                       filetypes=[("PDF 文件", "*.pdf")])
        if not p:
            return
        src_path = Path(p)

        def op(d):
            src = DocumentSession(src_path).doc
            try:
                insert_document(d, src, at=at)
            finally:
                src.close()

        self._mutate(op, f"已插入 {src_path.name}")

    @guarded
    def split_dialog(self) -> None:
        if not self.session.is_open:
            return
        mode = simpledialog.askstring(
            "拆分 PDF",
            f"总页数 {self._page_count}。请选择拆分方式：\n"
            "  each  —— 每页一个文件\n"
            "  N     —— 每 N 页一个文件（如 2）\n"
            "  1-3,4-6 —— 按范围拆分",
            initialvalue="each", parent=self.root)
        if not mode:
            return
        mode = mode.strip()
        kwargs: dict = {"mode": "each"}
        if mode.lower() == "each":
            kwargs = {"mode": "each"}
        elif mode.isdigit():
            kwargs = {"mode": "every", "every": int(mode)}
        else:
            try:
                ranges = []
                for part in mode.replace("，", ",").split(","):
                    a, b = part.split("-")
                    ranges.append((int(a), int(b)))
                kwargs = {"mode": "ranges", "ranges": ranges}
            except ValueError:
                self._warn("格式不正确，请输入 each 或 2 或 1-3,4-6")
                return

        out_dir = filedialog.askdirectory(title="选择输出目录")
        if not out_dir:
            return

        def job(progress):
            docs = split_document(self.session.doc, **kwargs)
            written = []
            stem = self.doc_path.stem if self.doc_path else "split"
            try:
                for i, nd in enumerate(docs, start=1):
                    f = Path(out_dir) / f"{stem}_part{i}.pdf"
                    nd.save(str(f), garbage=4, deflate=True)
                    written.append(f)
                    nd.close()
                    progress(i, len(docs), "拆分")
            finally:
                for nd in docs:
                    try:
                        nd.close()
                    except Exception:
                        pass
            return written

        def done(paths):
            self._log(f"✓ 拆分完成，共 {len(paths)} 个文件，输出到 {out_dir}")
            self._status(f"拆分完成，生成 {len(paths)} 个文件")
            for f in paths[:5]:
                self._log("   " + str(f))
            if len(paths) > 5:
                self._log(f"   …另有 {len(paths) - 5} 个文件")
            messagebox.showinfo("拆分完成", f"已生成 {len(paths)} 个文件：\n{out_dir}")

        self._tasks.submit("拆分", job, done, on_error=self._task_error)

    # ============================================================ 水印/页码
    @guarded
    def text_watermark_dialog(self) -> None:
        if not self.session.is_open:
            return
        dlg = _Dialog(self.root, "文字水印", "添加居中文字水印")
        dlg.text("文字", "机密")
        dlg.number("字号", 48, 6, 300)
        dlg.number("角度", 45, -180, 180)
        dlg.slider("不透明度", 0.3, 0.02, 1.0)
        dlg.check("仅当前页", False)
        dlg.color("#808080")
        if not dlg.show():
            return
        v = dlg.values
        pages = [self.current_page] if v["仅当前页"] else None
        rgb = _hex_to_rgb(v["颜色"])
        self._mutate(
            lambda d: text_watermark_document(
                d, v["文字"], opacity=v["不透明度"], angle=int(v["角度"]),
                font_size=int(v["字号"]), color=rgb, pages=pages),
            f"已添加文字水印「{v['文字']}」")

    @guarded
    def image_watermark_dialog(self) -> None:
        if not self.session.is_open:
            return
        p = filedialog.askopenfilename(
            title="选择水印图片",
            filetypes=[("图片", "*.png;*.jpg;*.jpeg;*.bmp"), ("所有文件", "*.*")])
        if not p:
            return
        dlg = _Dialog(self.root, "图片水印", "添加居中图片水印")
        dlg.slider("不透明度", 0.35, 0.02, 1.0)
        dlg.slider("大小比例", 0.4, 0.05, 1.0)
        dlg.number("旋转角度", 0, -180, 180)
        dlg.check("仅当前页", False)
        if not dlg.show():
            return
        v = dlg.values
        pages = [self.current_page] if v["仅当前页"] else None
        img = Path(p)
        self._mutate(
            lambda d: image_watermark_document(
                d, img, opacity=v["不透明度"], scale=v["大小比例"],
                angle=int(v["旋转角度"]), pages=pages),
            f"已添加图片水印（{img.name}）")

    @guarded
    def page_number_dialog(self) -> None:
        if not self.session.is_open:
            return
        dlg = _Dialog(self.root, "插入页码", "为每页添加页码")
        dlg.text("格式", "第 {page} 页 / 共 {total} 页")
        dlg.choice("位置", ["bottom-center", "bottom-right", "bottom-left",
                           "top-center", "top-right", "top-left"], "bottom-center")
        dlg.number("起始页码", 1, 0, 9999)
        dlg.number("字号", 10, 5, 72)
        dlg.check("首页不显示", False)
        if not dlg.show():
            return
        v = dlg.values
        self._mutate(
            lambda d: page_numbers_document(
                d, pattern=v["格式"], position=v["位置"], start=int(v["起始页码"]),
                font_size=int(v["字号"]), skip_first=v["首页不显示"]),
            "已插入页码")

    @guarded
    def header_footer_dialog(self) -> None:
        if not self.session.is_open:
            return
        dlg = _Dialog(self.root, "页眉 / 页脚",
                      "支持 {page} {total} {name} 占位符；"
                      "页脚建议选左/右对齐，以免与居中页码重叠")
        dlg.text("页眉", "")
        dlg.choice("页眉位置", ["top-center", "top-left", "top-right"], "top-center")
        dlg.text("页脚", "第 {page} 页")
        dlg.choice("页脚位置", ["bottom-left", "bottom-center", "bottom-right"],
                   "bottom-left")
        dlg.number("字号", 9, 5, 48)
        if not dlg.show():
            return
        v = dlg.values
        if not v["页眉"] and not v["页脚"]:
            self._warn("页眉与页脚至少填一项")
            return
        self._mutate(
            lambda d: header_footer_document(
                d, header=v["页眉"] or None, footer=v["页脚"] or None,
                font_size=int(v["字号"]),
                header_position=v["页眉位置"], footer_position=v["页脚位置"],
                name=self.doc_path.name if self.doc_path else ""),
            "已添加页眉/页脚")

    # ================================================================ 内容
    @guarded
    def extract_text_dialog(self) -> None:
        if not self.session.is_open:
            return
        pages = self._target_pages()
        text = extract_document_text(self.session.doc, pages)
        win = tk.Toplevel(self.root)
        win.title(f"提取的文字（{len(pages)} 页，{len(text)} 字符）")
        win.geometry("820x580")
        win.transient(self.root)
        holder = tk.Frame(win, bg=PANEL)
        holder.pack(fill=BOTH, expand=True)
        box = tk.Text(holder, wrap="word", font=font(10), relief="flat",
                      bg="#FFFFFF", fg=TEXT, padx=10, pady=8)
        sb = _ttk.Scrollbar(holder, orient=VERTICAL, command=box.yview)
        box.configure(yscrollcommand=sb.set)
        sb.pack(side=RIGHT, fill=Y)
        box.pack(fill=BOTH, expand=True)
        box.insert("1.0", text or "（未提取到文字，可能是扫描件）")
        bar = tk.Frame(win, bg=PANEL)
        bar.pack(fill=X)
        flat_button(bar, "复制全部",
                    lambda: (win.clipboard_clear(), win.clipboard_append(text),
                             self._status("已复制到剪贴板")), padx=10, pady=4).pack(side=LEFT, padx=8, pady=6)
        flat_button(bar, "保存为 txt…", lambda: self._save_text(text),
                    padx=10, pady=4).pack(side=LEFT, padx=2, pady=6)
        flat_button(bar, "关闭", win.destroy, padx=10, pady=4).pack(side=RIGHT, padx=8, pady=6)
        self._log(f"提取文字：{len(pages)} 页，{len(text)} 字符")

    def _save_text(self, text: str) -> None:
        p = filedialog.asksaveasfilename(title="保存文本", defaultextension=".txt",
                                         filetypes=[("文本文件", "*.txt")])
        if p:
            Path(p).write_text(text, encoding="utf-8")
            self._log(f"✓ 文本已保存：{p}")
            self._status("文本已保存")

    @guarded
    def export_text_dialog(self) -> None:
        if not self.session.is_open:
            return
        out_dir = filedialog.askdirectory(title="选择导出目录")
        if not out_dir:
            return
        src = self.session.source

        def job(progress):
            return extract_pages_to_files(src, Path(out_dir))

        def done(paths):
            self._log(f"✓ 已导出 {len(paths)} 个文本文件 → {out_dir}")
            messagebox.showinfo("导出完成", f"已导出 {len(paths)} 个 txt 文件。")

        self._tasks.submit("导出文本", job, done, on_error=self._task_error)

    @guarded
    def export_images_dialog(self) -> None:
        if not self.session.is_open:
            return
        fmt = simpledialog.askstring("导出图片", "图片格式（png / jpg）：",
                                     initialvalue="png", parent=self.root)
        if not fmt:
            return
        fmt = fmt.strip().lower()
        if fmt not in ("png", "jpg", "jpeg", "webp"):
            self._warn("仅支持 png / jpg / webp")
            return
        dpi_s = simpledialog.askstring("导出图片", "分辨率 DPI（如 150 / 300）：",
                                       initialvalue="150", parent=self.root)
        if not dpi_s:
            return
        try:
            dpi = max(30, min(int(dpi_s), 600))
        except ValueError:
            self._warn("DPI 必须是数字")
            return
        out_dir = filedialog.askdirectory(title="选择导出目录")
        if not out_dir:
            return
        src = self.session.source
        pages = self._target_pages()

        def job(progress):
            return export_pages_to_images(
                src, Path(out_dir), pages=pages, fmt=fmt, dpi=dpi,
                progress=lambda i, n: progress(i, n, "导出页面"))

        def done(paths):
            self._log(f"✓ 已导出 {len(paths)} 张图片（{fmt.upper()} {dpi}dpi）→ {out_dir}")
            messagebox.showinfo("导出完成", f"已导出 {len(paths)} 张图片。")

        self._tasks.submit("导出图片", job, done, on_error=self._task_error)

    @guarded
    def extract_images_dialog(self) -> None:
        if not self.session.is_open:
            return
        out_dir = filedialog.askdirectory(title="选择保存目录")
        if not out_dir:
            return
        src = self.session.source

        def job(progress):
            return extract_images(src, Path(out_dir))

        def done(paths):
            if not paths:
                self._log("未在该 PDF 中找到可提取的位图（可能是矢量内容）")
                messagebox.showinfo("提取完成", "未找到可提取的嵌入图片。")
                return
            self._log(f"✓ 已提取 {len(paths)} 张图片 → {out_dir}")
            messagebox.showinfo("提取完成", f"已提取 {len(paths)} 张图片。")

        self._tasks.submit("提取图片", job, done, on_error=self._task_error)

    @guarded
    def tables_dialog(self) -> None:
        if not self.session.is_open:
            return
        tables = find_tables(self.session.doc, self._target_pages())
        if not tables:
            self._log("未识别到表格结构")
            messagebox.showinfo("表格识别", "未在当前页面识别到表格。")
            return
        win = tk.Toplevel(self.root)
        win.title(f"表格识别结果（{len(tables)} 个）")
        win.geometry("760x520")
        box = tk.Text(win, wrap="none", font=mono(9), bg="#FFFFFF", fg=TEXT)
        box.pack(fill=BOTH, expand=True, padx=6, pady=6)
        out = []
        for i, t in enumerate(tables, 1):
            out.append(f"===== 表格 {i}（第 {t['page']} 页）=====")
            for row in t["rows"]:
                out.append(" | ".join((c or "").replace("\n", " ") for c in row))
            out.append("")
        box.insert("1.0", "\n".join(out))
        self._log(f"识别到 {len(tables)} 个表格")

    # ============================================================== 书签
    @guarded
    def add_bookmark_dialog(self) -> None:
        if not self.session.is_open:
            return
        pages = self._target_pages()
        title = simpledialog.askstring(
            "添加书签", f"书签标题（将指向第 {pages[0]} 页）：",
            initialvalue=f"第 {pages[0]} 页", parent=self.root)
        if not title:
            return
        page = pages[0]
        self._mutate(lambda d: add_bookmark(d, title, page), f"已添加书签「{title}」")
        self.show_catalog_tab()

    @guarded
    def delete_bookmark_selected(self) -> None:
        sel = self.catalog.selection()
        if not sel:
            self._status("请先在目录列表中选择书签")
            return
        idx = self.catalog.index(sel[0])
        self._mutate(lambda d: delete_bookmark(d, idx), "已删除书签")
        self.refresh_catalog()

    def refresh_catalog(self, quiet: bool = False) -> None:
        try:
            for item in self.catalog.get_children():
                self.catalog.delete(item)
            if not self.session.is_open:
                return
            rows = get_toc(self.session.doc)
            for lv, title, page in rows:
                self.catalog.insert("", "end", values=(lv, title, page))
            self._catalog_rows = len(rows)
        except Exception as exc:
            self._log(f"✗ 目录读取失败：{exc}")
            if not quiet:
                self._error_dialog("目录读取失败", str(exc))

    def _catalog_goto(self, event) -> None:
        sel = self.catalog.selection()
        if not sel:
            return
        vals = self.catalog.item(sel[0], "values")
        try:
            self.goto_page(int(vals[2]))
            self._status(f"已跳转到「{vals[1]}」")
        except (ValueError, IndexError):
            pass

    # ============================================================== 批注管理
    def refresh_annotations(self, quiet: bool = False) -> None:
        """重建批注列表；用 xref 作为 item iid，避免按内容匹配导致误删。"""
        try:
            keep = self.annots.selection()
            keep_iid = keep[0] if keep else None
            for item in self.annots.get_children():
                self.annots.delete(item)
            if not self.session.is_open:
                self._annot_rows = 0
                return
            total = 0
            for p in range(1, self._page_count + 1):
                for a in list_annotations(self.session.doc, p):
                    iid = str(a["xref"])
                    if self.annots.exists(iid):
                        iid = f"{a['xref']}-p{p}"
                    self.annots.insert(
                        "", "end", iid=iid,
                        values=(p, a["type"], (a["content"] or "")[:80],
                                ANNOT_KINDS.get(a["type"].lower(), a["type"])))
                    total += 1
                    if total >= 600:
                        break
                if total >= 600:
                    break
            if keep_iid and self.annots.exists(keep_iid):
                self.annots.selection_set(keep_iid)
            self._annot_rows = total
        except Exception as exc:
            self._log(f"✗ 批注读取失败：{exc}")
            if not quiet:
                self._error_dialog("批注读取失败", str(exc))

    def _annot_goto(self, event) -> None:
        sel = self.annots.selection()
        if not sel:
            return
        self.locate_annotation_selected()

    @guarded
    def delete_annotation_selected(self) -> None:
        sel = self.annots.selection()
        if not sel:
            self._status("请先在批注列表中选择一条")
            return
        iid = sel[0]
        page = int(self.annots.item(iid, "values")[0])
        if not self.session.is_open:
            return
        xref = None
        for a in list_annotations(self.session.doc, page):
            if str(a["xref"]) == iid.split("-p")[0]:
                xref = a["xref"]
                break
        if xref is None:
            self.refresh_annotations(quiet=True)
            self._warn("该批注已不存在，列表已刷新")
            return
        self._mutate(lambda d: delete_annotation(d, page, xref), "已删除批注")

    def locate_annotation_selected(self) -> None:
        """跳转到所选批注所在页并闪烁提示。"""
        sel = self.annots.selection()
        if not sel:
            self._status("请先在批注列表中选择一条")
            return
        page = int(self.annots.item(sel[0], "values")[0])
        self.goto_page(page)
        self._flash_annot(sel[0])

    def _flash_annot(self, iid: str) -> None:
        page = int(self.annots.item(iid, "values")[0])
        if page != self.current_page or not self.session.is_open:
            return
        try:
            target = None
            for a in list_annotations(self.session.doc, page):
                if str(a["xref"]) == iid.split("-p")[0]:
                    target = a
                    break
            if not target:
                return
            x0, y0, x1, y1 = target["rect"]
            c0 = self._page_to_canvas(x0, y0)
            c1 = self._page_to_canvas(x1, y1)
            item = self.canvas.create_rectangle(
                c0[0] - 3, c0[1] - 3, c1[0] + 3, c1[1] + 3,
                outline="#E8433B", width=3)
            self.root.after(1400, lambda: self.canvas.delete(item))
        except Exception:
            pass

    @guarded
    def clear_page_annots(self) -> None:
        if not self.session.is_open:
            return
        page = self.current_page
        n = len(list_annotations(self.session.doc, page))
        if n == 0:
            self._status(f"第 {page} 页没有批注")
            return
        if not messagebox.askyesno("确认", f"清除第 {page} 页的 {n} 条批注？"):
            return
        self._mutate(lambda d: clear_annotations(d, pages=[page]),
                     f"已清除第 {page} 页的 {n} 条批注")

    @guarded
    def clear_all_annots(self) -> None:
        if not self.session.is_open:
            return
        total = sum(len(list_annotations(self.session.doc, p))
                    for p in range(1, self._page_count + 1))
        if total == 0:
            self._status("文档中没有批注")
            return
        if not messagebox.askyesno("确认", f"清除全部 {total} 条批注？此操作可撤销。"):
            return
        self._mutate(lambda d: clear_annotations(d), f"已清除全部批注（{total} 条）")

    # ============================================================ 属性/安全
    @guarded
    def properties_dialog(self) -> None:
        if not self.session.is_open:
            return
        md = get_metadata(self.session.source)
        dlg = _Dialog(self.root, "文档属性", "编辑 PDF 元数据")
        dlg.text("标题", md.get("title", ""))
        dlg.text("作者", md.get("author", ""))
        dlg.text("主题", md.get("subject", ""))
        dlg.text("关键词", md.get("keywords", ""))
        dlg.readonly("页数", str(self._page_count))
        dlg.readonly("创建者", md.get("creator", "") or "—")
        dlg.readonly("格式", md.get("format", "") or "—")
        if not dlg.show():
            return
        v = dlg.values
        self._mutate(
            lambda d: set_document_metadata(d, {
                "title": v["标题"], "author": v["作者"],
                "subject": v["主题"], "keywords": v["关键词"]}),
            "已更新文档属性")

    @guarded
    def encrypt_dialog(self) -> None:
        if not self.session.is_open:
            return
        dlg = _Dialog(self.root, "添加密码", "为 PDF 设置打开口令")
        dlg.text("打开口令", "", secret=True)
        dlg.text("所有者口令（可选）", "", secret=True)
        dlg.check("允许打印", True)
        dlg.check("允许复制文字", True)
        dlg.check("允许批注", True)
        dlg.check("允许修改页面", False)
        if not dlg.show():
            return
        v = dlg.values
        if not v["打开口令"]:
            self._warn("请设置打开口令")
            return
        out = filedialog.asksaveasfilename(
            title="加密后另存为", defaultextension=".pdf",
            initialfile=f"{self.doc_path.stem}_encrypted.pdf",
            filetypes=[("PDF 文件", "*.pdf")])
        if not out:
            return
        src = self.session.source
        try:
            set_encryption(
                src, Path(out), user_password=v["打开口令"],
                owner_password=v["所有者口令（可选）"] or None,
                allow_print=v["允许打印"], allow_copy=v["允许复制文字"],
                allow_modify=v["允许修改页面"], allow_annotate=v["允许批注"])
        except Exception as exc:
            self._error_dialog("加密失败", str(exc))
            return
        self._log(f"✓ 已生成加密文件：{out}")
        messagebox.showinfo("完成", "加密文件已生成。\n请牢记口令，PDF 口令无法找回。")

    @guarded
    def decrypt_dialog(self) -> None:
        p = filedialog.askopenfilename(title="选择加密的 PDF",
                                       filetypes=[("PDF 文件", "*.pdf")])
        if not p:
            return
        pw = simpledialog.askstring("口令", "输入打开口令：", show="•", parent=self.root)
        if pw is None:
            return
        out = filedialog.asksaveasfilename(
            title="解除密码后另存为", defaultextension=".pdf",
            initialfile=f"{Path(p).stem}_decrypted.pdf",
            filetypes=[("PDF 文件", "*.pdf")])
        if not out:
            return
        try:
            remove_encryption(Path(p), Path(out), password=pw)
        except (PdfPasswordRequired, PdfPasswordError) as exc:
            self._error_dialog("口令错误", str(exc))
            return
        except Exception as exc:
            self._error_dialog("解密失败", str(exc))
            return
        self._log(f"✓ 已解除密码：{out}")
        if messagebox.askyesno("完成", "已生成无密码文件，是否打开？"):
            self.open_path(Path(out))

    @guarded
    def compress_dialog(self) -> None:
        p = filedialog.askopenfilename(title="选择要压缩的 PDF",
                                       filetypes=[("PDF 文件", "*.pdf")])
        if not p:
            return
        dlg = _Dialog(self.root, "压缩优化", "降低图像分辨率以减小体积")
        dlg.choice("图像质量", ["高质量（150dpi）", "均衡（120dpi）", "高压缩（96dpi）"],
                   "均衡（120dpi）")
        if not dlg.show():
            return
        dpi = {"高质量（150dpi）": 150, "均衡（120dpi）": 120, "高压缩（96dpi）": 96}[
            dlg.values["图像质量"]]
        out = filedialog.asksaveasfilename(
            title="压缩后另存为", defaultextension=".pdf",
            initialfile=f"{Path(p).stem}_compressed.pdf",
            filetypes=[("PDF 文件", "*.pdf")])
        if not out:
            return
        src = Path(p)

        def job(progress):
            progress(0, 0, "压缩")
            return compress_document(src, Path(out), dpi=dpi)

        def done(res):
            self._log(
                f"✓ 压缩完成：{res['before'] / 1024:.0f} KB → {res['after'] / 1024:.0f} KB"
                f"（省 {res['saved_percent']}%）")
            messagebox.showinfo(
                "压缩完成",
                f"原始大小：{res['before'] / 1024:.0f} KB\n"
                f"压缩后：{res['after'] / 1024:.0f} KB\n"
                f"节省：{res['saved_percent']}%")

        self._tasks.submit("压缩", job, done, on_error=self._task_error)

    # ============================================================== 保存
    @guarded
    def save(self) -> None:
        if not self.session.is_open:
            self._warn("请先打开一个 PDF 文件")
            return
        if self.doc_path is None:
            self.save_as()
            return
        try:
            self.session.save()
        except Exception as exc:
            self._error_dialog("保存失败", str(exc))
            return
        self._log(f"✓ 已保存：{self.doc_path}")
        self._status(f"已保存 {self.doc_path.name}")
        self._update_ui_state()

    @guarded
    def save_as(self) -> None:
        if not self.session.is_open:
            self._warn("请先打开一个 PDF 文件")
            return
        initial = f"{self.doc_path.stem}_副本.pdf" if self.doc_path else "output.pdf"
        out = filedialog.asksaveasfilename(
            title="另存为", defaultextension=".pdf", initialfile=initial,
            filetypes=[("PDF 文件", "*.pdf")])
        if not out:
            return
        try:
            self.session.save(Path(out))
        except Exception as exc:
            self._error_dialog("保存失败", str(exc))
            return
        self.doc_path = Path(out)
        self._remember(self.doc_path)
        self._log(f"✓ 已另存为：{out}")
        self._status(f"已另存为 {Path(out).name}")
        self._update_ui_state()

    @guarded
    def merge_dialog(self) -> None:
        paths = filedialog.askopenfilenames(
            title="选择要合并的 PDF（按选择顺序）",
            filetypes=[("PDF 文件", "*.pdf")])
        if not paths or len(paths) < 2:
            self._warn("合并至少需要选择 2 个文件")
            return
        out = filedialog.asksaveasfilename(
            title="合并输出", defaultextension=".pdf",
            initialfile="merged.pdf", filetypes=[("PDF 文件", "*.pdf")])
        if not out:
            return
        srcs = [Path(p) for p in paths]

        def job(progress):
            merge_pdfs(srcs, Path(out))
            return out

        def done(_):
            self._log(f"✓ 已合并 {len(srcs)} 个文件 → {out}")
            self._status("合并完成")
            if messagebox.askyesno("合并完成", f"已合并 {len(srcs)} 个文件。\n是否立即打开？"):
                self.open_path(Path(out))

        self._tasks.submit("合并", job, done, on_error=self._task_error)

    # ============================================================== 帮助
    def _shortcuts(self) -> None:
        rows = [
            ("Ctrl+O", "打开 PDF"), ("Ctrl+S", "保存"), ("Ctrl+Shift+S", "另存为"),
            ("Ctrl+Z / Ctrl+Y", "撤销 / 重做"), ("Ctrl+A", "全选页面"),
            ("Ctrl+F", "查找"), ("F3", "查找下一个"), ("Ctrl+G", "跳转到页"),
            ("Ctrl++ / Ctrl+-", "放大 / 缩小"), ("Ctrl+0", "实际大小"),
            ("Ctrl+滚轮", "缩放"), ("滚轮", "上下滚动（到边界自动翻页）"),
            ("PgUp / PgDn", "上一页 / 下一页"), ("Home / End", "首页 / 末页"),
            ("中键拖动", "平移页面"), ("Esc", "退出标注模式 / 关闭查找栏"),
            ("Ctrl+Q", "退出程序"), ("拖入文件", "直接打开 PDF"),
        ]
        win = tk.Toplevel(self.root)
        win.title("快捷键")
        win.geometry("520x460")
        win.transient(self.root)
        frame = tk.Frame(win, bg=PANEL)
        frame.pack(fill=BOTH, expand=True, padx=14, pady=12)
        tk.Label(frame, text="快捷键一览", bg=PANEL, fg=BLUE_DARK,
                 font=font(13, True)).pack(anchor="w", pady=(0, 10))
        for k, v in rows:
            line = tk.Frame(frame, bg=PANEL)
            line.pack(fill=X, pady=1)
            tk.Label(line, text=k, bg=PANEL, fg=BLUE_DARK, font=mono(9),
                     width=18, anchor="w").pack(side=LEFT)
            tk.Label(line, text=v, bg=PANEL, fg=TEXT, font=font(9),
                     anchor="w").pack(side=LEFT)
        flat_button(frame, "关闭", win.destroy, padx=12, pady=4).pack(pady=10)

    def _about(self) -> None:
        messagebox.showinfo(
            "关于",
            f"PDF 编辑器 v{APP_VERSION}\n\n"
            "界面参照 WPS PDF 设计：Ribbon 工具栏 + 缩略图导航 + 实时预览。\n\n"
            "功能：合并 · 拆分 · 旋转 · 重排 · 移动 · 空白页 · 提取 · 删除 · 复制\n"
            "　　　文字/图片水印 · 页码 · 页眉页脚 · 文字与形状批注 · 涂黑脱敏\n"
            "　　　提取文字 · 导出图片 · 提取图片 · 表格识别 · 书签目录\n"
            "　　　文档属性 · 压缩优化 · 加密 / 解密\n\n"
            "全部本地离线运行；编辑过程不修改原文件，保存时才原子写回。\n"
            "基于 Python + tkinter + PyMuPDF。")

    # ============================================================== 关闭
    def _on_close(self) -> None:
        try:
            if self.session.is_open and self.session.dirty:
                ans = messagebox.askyesnocancel(
                    "退出", "当前文档有未保存的修改。\n\n是：保存后退出　否：直接退出")
                if ans is None:
                    return
                if ans:
                    self.save()
                    if self.session.dirty:
                        return
            self._save_config()
            self.session.close()
            from . import icons as _ic

            _ic.clear_cache()
            release_render_cache()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass


# ================================================================= 通用对话框
class _Dialog:
    """轻量模态参数对话框（Toplevel + 主线程等待），返回字段字典。"""

    def __init__(self, parent: tk.Misc, title: str, subtitle: str = ""):
        self.parent = parent
        self.title = title
        self.subtitle = subtitle
        self._fields: list[tuple[str, str, dict]] = []
        self._vars: dict[str, tk.Variable] = {}
        self.values: dict = {}
        self._result = False

    # ---- 字段定义
    def text(self, label: str, default: str = "", *, secret: bool = False) -> None:
        self._fields.append(("text", label, {"default": default, "secret": secret}))

    def readonly(self, label: str, value: str) -> None:
        self._fields.append(("ro", label, {"default": value}))

    def number(self, label: str, default: float, lo: float, hi: float) -> None:
        self._fields.append(("num", label, {"default": default, "lo": lo, "hi": hi}))

    def slider(self, label: str, default: float, lo: float, hi: float) -> None:
        self._fields.append(("slider", label, {"default": default, "lo": lo, "hi": hi}))

    def check(self, label: str, default: bool) -> None:
        self._fields.append(("bool", label, {"default": default}))

    def choice(self, label: str, options: list[str], default: str) -> None:
        self._fields.append(("choice", label, {"options": options, "default": default}))

    def color(self, default: str) -> None:
        self._fields.append(("color", "颜色", {"default": default}))

    # ---- 显示
    def show(self) -> bool:
        win = tk.Toplevel(self.parent)
        win.title(self.title)
        win.configure(bg=PANEL)
        win.transient(self.parent)
        win.resizable(False, False)

        pad = tk.Frame(win, bg=PANEL)
        pad.pack(fill=BOTH, expand=True, padx=18, pady=14)
        tk.Label(pad, text=self.title, bg=PANEL, fg=BLUE_DARK,
                 font=font(12, True)).pack(anchor="w")
        if self.subtitle:
            tk.Label(pad, text=self.subtitle, bg=PANEL, fg=TEXT_MUTED,
                     font=font(9)).pack(anchor="w", pady=(2, 10))

        grid = tk.Frame(pad, bg=PANEL)
        grid.pack(fill=BOTH, expand=True)
        for i, (kind, label, meta) in enumerate(self._fields):
            tk.Label(grid, text=label, bg=PANEL, fg=TEXT, font=font(9),
                     anchor="w").grid(row=i, column=0, sticky="w", pady=5, padx=(0, 12))
            if kind == "text":
                var = tk.StringVar(value=str(meta["default"]))
                ent = _ttk.Entry(grid, textvariable=var, width=30,
                                 show="•" if meta.get("secret") else "")
                ent.grid(row=i, column=1, sticky="we", pady=5)
            elif kind == "ro":
                var = tk.StringVar(value=str(meta["default"]))
                tk.Label(grid, textvariable=var, bg=PANEL, fg=TEXT_MUTED,
                         font=font(9), anchor="w").grid(row=i, column=1, sticky="w", pady=5)
            elif kind == "num":
                var = tk.StringVar(value=_fmt_num(meta["default"]))
                _ttk.Spinbox(grid, from_=meta["lo"], to=meta["hi"], textvariable=var,
                             width=10).grid(row=i, column=1, sticky="w", pady=5)
            elif kind == "slider":
                var = tk.DoubleVar(value=float(meta["default"]))
                box = tk.Frame(grid, bg=PANEL)
                box.grid(row=i, column=1, sticky="we", pady=5)
                _ttk.Scale(box, from_=meta["lo"], to=meta["hi"], variable=var,
                           orient=HORIZONTAL, length=190).pack(side=LEFT)
                lbl = tk.Label(box, text=_fmt_num(meta["default"]), bg=PANEL,
                               fg=TEXT_MUTED, font=font(8), width=6)
                lbl.pack(side=LEFT, padx=6)
                var.trace_add("write", lambda *a, v=var, l=lbl: l.configure(
                    text=_fmt_num(v.get())))
            elif kind == "bool":
                var = tk.BooleanVar(value=bool(meta["default"]))
                _ttk.Checkbutton(grid, variable=var, bootstyle="primary-round-toggle"
                                 ).grid(row=i, column=1, sticky="w", pady=5)
            elif kind == "choice":
                var = tk.StringVar(value=meta["default"])
                _ttk.Combobox(grid, textvariable=var, values=meta["options"],
                              state="readonly", width=28).grid(row=i, column=1,
                                                               sticky="we", pady=5)
            else:  # color
                var = tk.StringVar(value=meta["default"])
                box = tk.Frame(grid, bg=PANEL)
                box.grid(row=i, column=1, sticky="w", pady=5)
                sw = tk.Label(box, text="　", bg=meta["default"], width=4,
                              relief="solid", bd=1)
                sw.pack(side=LEFT)

                def pick(v=var, s=sw):
                    c = colorchooser.askcolor(color=v.get(), parent=win)[1]
                    if c:
                        v.set(c)
                        s.configure(bg=c)

                flat_button(box, "选择…", pick, padx=8, pady=2).pack(side=LEFT, padx=6)
            self._vars[label] = var

        btns = tk.Frame(pad, bg=PANEL)
        btns.pack(fill=X, pady=(14, 0))

        def ok():
            self.values = {}
            for kind, label, meta in self._fields:
                var = self._vars[label]
                if kind == "num":
                    try:
                        self.values[label] = float(var.get())
                    except (ValueError, tk.TclError):
                        self.values[label] = meta["default"]
                elif kind == "slider":
                    self.values[label] = float(var.get())
                else:
                    self.values[label] = var.get()
            self._result = True
            win.destroy()

        flat_button(btns, "确定", ok, bg=BLUE, fg="white", hover=BLUE_DARK,
                    padx=18, pady=5).pack(side=RIGHT, padx=(6, 0))
        flat_button(btns, "取消", win.destroy, padx=18, pady=5).pack(side=RIGHT)
        win.bind("<Return>", lambda e: ok())
        win.bind("<Escape>", lambda e: win.destroy())

        win.update_idletasks()
        try:
            px = self.parent.winfo_rootx() + (self.parent.winfo_width() - win.winfo_width()) // 2
            py = self.parent.winfo_rooty() + (self.parent.winfo_height() - win.winfo_height()) // 3
            win.geometry(f"+{max(px, 0)}+{max(py, 0)}")
        except Exception:
            pass
        win.grab_set()
        self.parent.wait_window(win)
        return self._result


def _fmt_num(v) -> str:
    try:
        f = float(v)
        return str(int(f)) if abs(f - int(f)) < 1e-9 else f"{f:.2f}"
    except Exception:
        return str(v)


def _hex_to_rgb(h: str) -> tuple[float, float, float]:
    h = (h or "#808080").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]
    except Exception:
        return (0.5, 0.5, 0.5)


# ===================================================================== 入口
def _make_root() -> ttk.Window:
    """创建主窗口；若 tkinterdnd2 可用则启用文件拖放。"""
    try:
        from tkinterdnd2 import TkinterDnD

        class _Root(ttk.Window, TkinterDnD.DnDWrapper):
            def __init__(self, **kw):
                super().__init__(**kw)
                self.TkdndVersion = TkinterDnD._require(self)

        return _Root(themename="flatly")
    except Exception:
        return ttk.Window(themename="flatly")


def _enable_drop(root: ttk.Window, app: PDFEditorApp) -> None:
    try:
        from tkinterdnd2 import DND_FILES

        def on_drop(event):
            paths = root.tk.splitlist(event.data)
            for p in paths:
                if str(p).lower().endswith(".pdf"):
                    app.open_path(Path(p))
                    return
            app._warn("请拖入 PDF 文件")

        root.drop_target_register(DND_FILES)
        root.dnd_bind("<<Drop>>", on_drop)
    except Exception:
        pass


def main(initial_file: str | None = None) -> None:
    root = _make_root()
    app = PDFEditorApp(root)
    _enable_drop(root, app)
    if initial_file:
        def _open_initial() -> None:
            p = Path(initial_file)
            if p.exists():
                app.open_path(p)
            else:
                app._warn(f"文件不存在：{p}")

        root.after(80, _open_initial)
    root.mainloop()