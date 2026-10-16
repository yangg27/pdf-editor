"""矢量图标：用 Pillow 程序化绘制，避免依赖外部图标文件。

每个图标是一个在 ``S x S``（默认 32）画布上作画的函数，接收 ``ImageDraw``
与描边宽度。渲染结果按 ``(名称, 尺寸, 颜色)`` 缓存为 ``PhotoImage``。

这样做的收益：
- 打包体积不增加（无图片资源），任何 DPI 下清晰；
- 图标颜色跟随主题，深浅色都能保证可读；
- 与 tkinter 的 PhotoImage 生命周期问题解耦（统一持有引用）。
"""

from __future__ import annotations

import math
from typing import Callable

from PIL import Image, ImageDraw, ImageTk

S = 32
_W = 2  # 默认线宽


# --------------------------------------------------------------- 绘制工具
def _new(size: int):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def _rr(d: ImageDraw.ImageDraw, box, r=2, **kw):
    """圆角矩形。"""
    try:
        d.rounded_rectangle(box, radius=r, **kw)
    except Exception:
        d.rectangle(box, **kw)


def _poly(d, pts, **kw):
    d.polygon(pts, **kw)


def _line(d, pts, **kw):
    d.line(pts, **kw)


def _arc(d, box, start, end, **kw):
    d.arc(box, start, end, **kw)


def _arrow_head(d, tip, angle_deg, size=5, **kw):
    a = math.radians(angle_deg)
    for off in (150, -150):
        b = a + math.radians(off)
        d.line([tip, (tip[0] + size * math.cos(b), tip[1] + size * math.sin(b))], **kw)


# ------------------------------------------------------------------- 图标
def _open(d, w, col):
    _rr(d, (3, 10, 29, 26), r=2, outline=col, width=w)
    _line(d, [(3, 13), (13, 13), (15, 10), (24, 10)], fill=col, width=w)
    d.polygon([(9, 17), (12.5, 17), (12.5, 20.5)], fill=col)
    _line(d, [(12.5, 17), (12.5, 24.5)], fill=col, width=w)
    _line(d, [(9, 24.5), (16, 24.5)], fill=col, width=w)


def _save(d, w, col):
    _rr(d, (4, 5, 28, 27), r=2, outline=col, width=w)
    _rr(d, (10, 5, 22, 13), r=1, outline=col, width=w)
    _rr(d, (9, 17, 23, 27), r=1, outline=col, width=w)
    _line(d, [(14, 17), (14, 23)], fill=col, width=max(1, w - 1))
    _line(d, [(11, 20), (14, 23), (17, 20)], fill=col, width=max(1, w - 1))


def _saveas(d, w, col):
    _rr(d, (3, 5, 21, 27), r=2, outline=col, width=w)
    _line(d, [(7, 10), (17, 10)], fill=col, width=w)
    _line(d, [(7, 14), (14, 14)], fill=col, width=w)
    _line(d, [(7, 18), (12, 18)], fill=col, width=w)
    _line(d, [(19, 22), (29, 22)], fill=col, width=w)
    _arrow_head(d, (29, 22), 0, 4, fill=col, width=w)


def _merge(d, w, col):
    _rr(d, (3, 6, 14, 15), r=1, outline=col, width=w)
    _rr(d, (3, 18, 14, 27), r=1, outline=col, width=w)
    _line(d, [(15, 10.5), (20, 10.5), (20, 16), (24, 16)], fill=col, width=w)
    _line(d, [(15, 22.5), (20, 22.5), (20, 16)], fill=col, width=w)
    _rr(d, (24, 11, 30, 21), r=1, outline=col, width=w)


def _split(d, w, col):
    _rr(d, (3, 8, 17, 25), r=1, outline=col, width=w)
    for y in (12, 16, 20):
        for x in range(5, 15, 4):
            d.point((x, y), fill=col)
    _line(d, [(20, 9), (20, 24)], fill=col, width=1)
    _rr(d, (23, 12, 30, 20), r=1, outline=col, width=w)


def _delete(d, w, col):
    _line(d, [(6, 9), (26, 9)], fill=col, width=w)
    _line(d, [(12, 9), (12, 6), (20, 6), (20, 9)], fill=col, width=w)
    _rr(d, (8, 11, 24, 27), r=2, outline=col, width=w)
    for x in (13, 16, 19):
        _line(d, [(x, 15), (x, 23)], fill=col, width=max(1, w - 1))


def _extract(d, w, col):
    _rr(d, (5, 4, 20, 24), r=2, outline=col, width=w)
    _line(d, [(9, 9), (16, 9)], fill=col, width=w)
    _line(d, [(9, 13), (14, 13)], fill=col, width=w)
    _line(d, [(16, 22), (28, 22)], fill=col, width=w)
    _arrow_head(d, (28, 22), 0, 4, fill=col, width=w)


def _rotate_cw(d, w, col):
    _arc(d, (6, 6, 26, 26), 40, 330, fill=col, width=w)
    _poly(d, [(23, 4), (28, 12), (19, 11)], fill=col)


def _rotate_ccw(d, w, col):
    _arc(d, (6, 6, 26, 26), 210, 140, fill=col, width=w)
    _poly(d, [(9, 4), (4, 12), (13, 11)], fill=col)


def _rotate180(d, w, col):
    _arc(d, (5, 7, 27, 25), 20, 160, fill=col, width=w)
    _arc(d, (5, 7, 27, 25), 200, 340, fill=col, width=w)
    _poly(d, [(25, 6), (30, 12), (21, 12)], fill=col)
    _poly(d, [(7, 26), (2, 20), (11, 20)], fill=col)


def _insert(d, w, col):
    _rr(d, (5, 4, 20, 27), r=2, outline=col, width=w)
    _line(d, [(9, 10), (16, 10)], fill=col, width=w)
    _line(d, [(9, 14), (14, 14)], fill=col, width=w)
    _line(d, [(23, 10), (23, 22)], fill=col, width=w)
    _line(d, [(17, 16), (29, 16)], fill=col, width=w)


def _blank(d, w, col):
    d.rectangle((6, 4, 26, 28), outline=col, width=1)
    for y in range(7, 27, 3):
        for x in range(8, 25, 3):
            d.point((x, y), fill=col)


def _arrow_up(d, w, col):
    _line(d, [(16, 26), (16, 8)], fill=col, width=w)
    _arrow_head(d, (16, 7), -90, 6, fill=col, width=w)
    _line(d, [(8, 26), (24, 26)], fill=col, width=w)


def _arrow_down(d, w, col):
    _line(d, [(16, 6), (16, 24)], fill=col, width=w)
    _arrow_head(d, (16, 25), 90, 6, fill=col, width=w)
    _line(d, [(8, 6), (24, 6)], fill=col, width=w)


def _copy(d, w, col):
    _rr(d, (4, 4, 20, 20), r=2, outline=col, width=w)
    _rr(d, (12, 12, 28, 28), r=2, outline=col, width=w)


def _wm_text(d, w, col):
    _line(d, [(6, 8), (18, 8)], fill=col, width=w)
    _line(d, [(12, 8), (12, 24)], fill=col, width=w)
    _line(d, [(7, 24), (17, 24)], fill=col, width=w)
    _line(d, [(21, 22), (28, 12)], fill=col, width=w)
    _line(d, [(20, 10), (24, 14)], fill=col, width=w)


def _wm_image(d, w, col):
    _rr(d, (4, 7, 28, 25), r=2, outline=col, width=w)
    d.ellipse((8, 11, 12, 15), outline=col, width=max(1, w - 1))
    d.polygon([(7, 23), (14, 15), (19, 21), (23, 17), (27, 23)], outline=col,
              width=max(1, w - 1))


def _page_num(d, w, col):
    _rr(d, (7, 4, 25, 28), r=2, outline=col, width=w)
    _line(d, [(16, 10), (16, 22)], fill=col, width=w)
    _line(d, [(12, 13), (16, 9), (20, 13)], fill=col, width=w)


def _header(d, w, col):
    _rr(d, (6, 4, 26, 28), r=2, outline=col, width=w)
    _line(d, [(9, 10), (23, 10)], fill=col, width=w + 1)
    for y in (15, 19, 23):
        _line(d, [(9, y), (20, y)], fill=col, width=1)


def _text(d, w, col):
    _rr(d, (6, 4, 26, 28), r=2, outline=col, width=w)
    for i, y in enumerate((10, 14, 18, 22)):
        _line(d, [(9, y), (23 - i * 3, y)], fill=col, width=1)


def _export_img(d, w, col):
    _rr(d, (4, 5, 22, 23), r=2, outline=col, width=w)
    d.polygon([(8, 20), (13, 13), (17, 18), (21, 14)], outline=col,
              width=max(1, w - 1))
    _line(d, [(20, 27), (30, 27)], fill=col, width=w)
    _arrow_head(d, (30, 27), 0, 4, fill=col, width=w)


def _find(d, w, col):
    _arc(d, (4, 4, 22, 22), 0, 360, fill=col, width=w)
    _line(d, [(20, 20), (28, 28)], fill=col, width=w + 1)


def _highlight(d, w, col):
    _line(d, [(7, 9), (25, 9)], fill=col, width=w)
    _line(d, [(7, 14), (25, 14)], fill=col, width=w)
    _line(d, [(7, 19), (18, 19)], fill=col, width=w)
    d.rectangle((5, 22, 27, 27), fill=col)


def _underline(d, w, col):
    _line(d, [(9, 6), (9, 17)], fill=col, width=w)
    _line(d, [(23, 6), (23, 17)], fill=col, width=w)
    _arc(d, (9, 8, 23, 24), 0, 180, fill=col, width=w)
    _line(d, [(6, 27), (26, 27)], fill=col, width=w + 1)


def _strikeout(d, w, col):
    _line(d, [(8, 7), (24, 7)], fill=col, width=w)
    _line(d, [(10, 7), (7, 25)], fill=col, width=w)
    _line(d, [(22, 7), (25, 25)], fill=col, width=w)
    _line(d, [(7, 25), (25, 25)], fill=col, width=w)
    _line(d, [(4, 16), (28, 16)], fill=col, width=w + 1)


def _note(d, w, col):
    d.polygon([(6, 5), (26, 5), (26, 21), (19, 27), (6, 27)], outline=col,
              width=w)
    d.polygon([(19, 27), (19, 21), (26, 21)], outline=col, width=max(1, w - 1))
    _line(d, [(10, 11), (22, 11)], fill=col, width=1)
    _line(d, [(10, 16), (19, 16)], fill=col, width=1)


def _rect_annot(d, w, col):
    _rr(d, (5, 8, 27, 24), r=2, outline=col, width=w)
    d.rectangle((5, 20, 27, 24), fill=col)


def _circle_annot(d, w, col):
    d.ellipse((5, 7, 27, 25), outline=col, width=w)


def _stamp(d, w, col):
    d.ellipse((5, 5, 27, 27), outline=col, width=w)
    d.polygon([(16, 10), (18.6, 15.4), (24.5, 16.2), (20.2, 20.3),
               (21.3, 26), (16, 23.2), (10.7, 26), (11.8, 20.3),
               (7.5, 16.2), (13.4, 15.4)], fill=col)


def _ink(d, w, col):
    d.polygon([(5, 27), (8, 18), (21, 5), (27, 11), (14, 24)], outline=col,
              width=w)
    _line(d, [(21, 5), (27, 11)], fill=col, width=w)


def _bookmark(d, w, col):
    d.polygon([(8, 4), (24, 4), (24, 28), (16, 21), (8, 28)], outline=col,
              width=w)


def _info(d, w, col):
    d.ellipse((4, 4, 28, 28), outline=col, width=w)
    d.ellipse((14.5, 9, 17.5, 12), fill=col)
    _line(d, [(16, 15), (16, 23)], fill=col, width=w + 1)


def _lock(d, w, col):
    _rr(d, (7, 14, 25, 28), r=2, outline=col, width=w)
    _arc(d, (10, 5, 22, 20), 180, 360, fill=col, width=w)
    d.ellipse((14.5, 19, 17.5, 22), fill=col)


def _unlock(d, w, col):
    _rr(d, (7, 14, 25, 28), r=2, outline=col, width=w)
    _arc(d, (10, 5, 22, 20), 180, 300, fill=col, width=w)
    d.ellipse((14.5, 19, 17.5, 22), fill=col)


def _compress(d, w, col):
    _rr(d, (5, 5, 27, 27), r=2, outline=col, width=1)
    _line(d, [(5, 9), (27, 9)], fill=col, width=1)
    _line(d, [(16, 12), (16, 19)], fill=col, width=w)
    _arrow_head(d, (16, 20), 90, 4, fill=col, width=w)
    _line(d, [(16, 28), (16, 21)], fill=col, width=w)
    _arrow_head(d, (16, 20), -90, 4, fill=col, width=w)


def _zoom_in(d, w, col):
    _arc(d, (4, 4, 22, 22), 0, 360, fill=col, width=w)
    _line(d, [(20, 20), (28, 28)], fill=col, width=w + 1)
    _line(d, [(13, 8), (13, 18)], fill=col, width=w)
    _line(d, [(8, 13), (18, 13)], fill=col, width=w)


def _zoom_out(d, w, col):
    _arc(d, (4, 4, 22, 22), 0, 360, fill=col, width=w)
    _line(d, [(20, 20), (28, 28)], fill=col, width=w + 1)
    _line(d, [(8, 13), (18, 13)], fill=col, width=w)


def _fit_width(d, w, col):
    _rr(d, (10, 6, 22, 26), r=1, outline=col, width=1)
    _line(d, [(6, 16), (1, 16)], fill=col, width=w)
    _arrow_head(d, (1, 16), 180, 4, fill=col, width=w)
    _line(d, [(26, 16), (31, 16)], fill=col, width=w)
    _arrow_head(d, (31, 16), 0, 4, fill=col, width=w)


def _fit_page(d, w, col):
    _rr(d, (7, 5, 25, 27), r=1, outline=col, width=w)
    _line(d, [(3, 3), (3, 7)], fill=col, width=w)
    _line(d, [(3, 3), (7, 3)], fill=col, width=w)
    _line(d, [(29, 25), (29, 29)], fill=col, width=w)
    _line(d, [(29, 29), (25, 29)], fill=col, width=w)


def _undo(d, w, col):
    _arc(d, (7, 9, 27, 27), 160, 20, fill=col, width=w)
    _poly(d, [(6, 8), (13, 4), (13, 13)], fill=col)


def _redo(d, w, col):
    _arc(d, (5, 9, 25, 27), 20, 200, fill=col, width=w)
    _poly(d, [(26, 8), (19, 4), (19, 13)], fill=col)


def _properties(d, w, col):
    _rr(d, (5, 4, 27, 28), r=2, outline=col, width=w)
    _line(d, [(10, 11), (22, 11)], fill=col, width=1)
    _line(d, [(10, 16), (22, 16)], fill=col, width=1)
    _line(d, [(10, 21), (17, 21)], fill=col, width=1)
    d.ellipse((19, 19, 26, 26), outline=col, width=max(1, w - 1))


def _recent(d, w, col):
    d.ellipse((4, 4, 28, 28), outline=col, width=w)
    _line(d, [(16, 9), (16, 17)], fill=col, width=w)
    _line(d, [(16, 17), (22, 20)], fill=col, width=w)


def _pdf_file(d, w, col):
    d.polygon([(7, 4), (20, 4), (27, 11), (27, 28), (7, 28)], outline=col,
              width=w)
    _line(d, [(20, 4), (20, 11), (27, 11)], fill=col, width=max(1, w - 1))
    for i, y in enumerate((16, 20, 24)):
        _line(d, [(11, y), (23 - i * 2, y)], fill=col, width=1)


ICON_DRAWERS: dict[str, Callable] = {
    "open": _open,
    "save": _save,
    "saveas": _saveas,
    "merge": _merge,
    "split": _split,
    "delete": _delete,
    "extract": _extract,
    "rotate_cw": _rotate_cw,
    "rotate_ccw": _rotate_ccw,
    "rotate180": _rotate180,
    "insert": _insert,
    "blank": _blank,
    "up": _arrow_up,
    "down": _arrow_down,
    "copy": _copy,
    "wm_text": _wm_text,
    "wm_image": _wm_image,
    "page_num": _page_num,
    "header": _header,
    "text": _text,
    "export_img": _export_img,
    "find": _find,
    "highlight": _highlight,
    "underline": _underline,
    "strikeout": _strikeout,
    "note": _note,
    "rect": _rect_annot,
    "circle": _circle_annot,
    "stamp": _stamp,
    "ink": _ink,
    "bookmark": _bookmark,
    "info": _info,
    "lock": _lock,
    "unlock": _unlock,
    "compress": _compress,
    "zoom_in": _zoom_in,
    "zoom_out": _zoom_out,
    "fit_width": _fit_width,
    "fit_page": _fit_page,
    "undo": _undo,
    "redo": _redo,
    "properties": _properties,
    "recent": _recent,
    "pdf": _pdf_file,
}

_cache: dict[tuple[str, int, str, int], ImageTk.PhotoImage] = {}


def icon(name: str, color: str = "#1F2D3D", size: int = 22,
         width: int = 2) -> ImageTk.PhotoImage | None:
    """取图标 PhotoImage（带缓存）。未知名称返回 ``None``。"""
    key = (name, size, color, width)
    hit = _cache.get(key)
    if hit is not None:
        return hit
    drawer = ICON_DRAWERS.get(name)
    if drawer is None:
        return None
    # 先在标准画布作画，再等比缩放到目标尺寸，保证各尺寸观感一致
    big, bd = _new(S)
    drawer(bd, width, color)
    img = big.resize((size, size), Image.LANCZOS)
    photo = ImageTk.PhotoImage(img)
    _cache[key] = photo
    return photo


def clear_cache() -> None:
    _cache.clear()