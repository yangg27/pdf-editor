"""界面主题：配色与 ttk 样式（WPS 风格现代蓝）。"""

from __future__ import annotations

import tkinter as tk

import ttkbootstrap as ttk

# ------------------------------------------------------------------ 配色
BLUE = "#2B7BD6"          # 主色
BLUE_DARK = "#1F5FA8"
BLUE_LIGHT = "#EAF2FC"
BLUE_HOVER = "#D8E7FA"
BG = "#F1F3F7"            # 工作区背景
PANEL = "#FFFFFF"
CANVAS_BG = "#8E9AA8"     # 文档区背景（纸张之外）
BORDER = "#DCE1E8"
BORDER_SOFT = "#EAEEF4"
TEXT = "#1F2D3D"
TEXT_MUTED = "#78879A"
TEXT_FAINT = "#A6B2C0"
SEL = "#2B7BD6"
SEL_SOFT = "#DCE9F9"
WARN = "#E6A23C"
ERROR = "#D9534F"
OK = "#3C9D5B"
FIND_HL = "#FFE066"

FONT_UI = "Microsoft YaHei"
FONT_MONO = "Consolas"

# 每个功能组的强调色（Ribbon 图标用）
GROUP_ACCENT = {
    "文件": "#2B7BD6",
    "编辑": "#5B6B7F",
    "页面": "#2F9E7E",
    "旋转": "#C77A2B",
    "插入": "#7B5BC7",
    "水印": "#C74B6B",
    "批注": "#D08A2C",
    "工具": "#3B7D9E",
    "视图": "#4A6FA5",
    "安全": "#8A4B4B",
}


def font(size: int = 9, bold: bool = False) -> tuple:
    """界面字体。"""
    return (FONT_UI, size, "bold") if bold else (FONT_UI, size)


def mono(size: int = 9) -> tuple:
    return (FONT_MONO, size)


def apply_styles(root: tk.Misc) -> ttk.Style:
    """统一设置 ttk 控件样式，并返回 style 对象。"""
    style = ttk.Style()
    try:
        style.theme_use("flatly")
    except Exception:
        pass

    style.configure("TNotebook", background=PANEL, borderwidth=0)
    style.configure(
        "TNotebook.Tab", font=font(9), padding=(14, 6), background=PANEL,
        foreground=TEXT_MUTED, borderwidth=0,
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", BLUE_LIGHT)],
        foreground=[("selected", BLUE_DARK)],
    )
    style.configure(
        "Treeview", font=font(9), rowheight=24, background=PANEL,
        fieldbackground=PANEL, foreground=TEXT, borderwidth=0,
    )
    style.map("Treeview", background=[("selected", SEL_SOFT)],
              foreground=[("selected", TEXT)])
    style.configure("Treeview.Heading", font=font(9, True), background=BG,
                    foreground=TEXT_MUTED, relief="flat", padding=(6, 4))
    style.configure("TProgressbar", thickness=10, background=BLUE,
                    troughcolor=BORDER_SOFT, borderwidth=0)
    style.configure("TScrollbar", background=BORDER, troughcolor=BG,
                    borderwidth=0, arrowsize=12)
    style.configure("TCombobox", padding=4)
    style.configure("TEntry", padding=4)
    style.configure("TSpinbox", padding=4)
    return style


# ------------------------------------------------------------ 通用小控件
def flat_button(
    master: tk.Misc,
    text: str = "",
    command=None,
    *,
    width: int | None = None,
    icon: object = None,
    bg: str = PANEL,
    fg: str = TEXT,
    hover: str = BLUE_LIGHT,
    font_spec: tuple | None = None,
    padx: int = 8,
    pady: int = 5,
    compound: str = "left",
    anchor: str = "center",
) -> tk.Button:
    """扁平风格按钮（带悬停高亮）。"""
    b = tk.Button(
        master, text=text, command=command, image=icon, compound=compound,
        relief="flat", bd=0, bg=bg, fg=fg, activebackground=hover,
        activeforeground=BLUE_DARK, cursor="hand2", highlightthickness=0,
        font=font_spec or font(9), padx=padx, pady=pady, anchor=anchor,
    )
    if width:
        b.configure(width=width)
    b.bind("<Enter>", lambda e, w=b, c=hover: w.configure(bg=c))
    b.bind("<Leave>", lambda e, w=b, c=bg: w.configure(bg=c))
    return b


def separator(master: tk.Misc, *, vertical: bool = True, color: str = BORDER,
              pad: int = 6) -> tk.Frame:
    """细分隔线。"""
    if vertical:
        f = tk.Frame(master, bg=color, width=1)
        f.pack(side="left", fill="y", pady=pad, padx=2)
    else:
        f = tk.Frame(master, bg=color, height=1)
        f.pack(fill="x", pady=pad)
    return f


def section_title(master: tk.Misc, text: str, *, pad=(10, 6)) -> tk.Label:
    """面板分组标题。"""
    lbl = tk.Label(master, text=text, bg=PANEL, fg=TEXT_MUTED,
                   font=font(8, True), anchor="w")
    lbl.pack(fill="x", padx=pad[0], pady=pad)
    return lbl