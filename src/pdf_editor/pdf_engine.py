"""PDF 编辑核心引擎。

使用 PyMuPDF (fitz) 作为主引擎，所有函数接收 pathlib.Path，输出也写入 Path。
"""

from __future__ import annotations

import pymupdf as fitz
from pathlib import Path


def _ensure_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def merge_pdfs(input_paths: list[Path], output_path: Path) -> None:
    """合并多个 PDF 文件为一个。"""
    if not input_paths:
        raise ValueError("至少需要一个输入文件")
    _ensure_dir(output_path)
    docs = [fitz.open(p) for p in input_paths]
    merged = fitz.open()
    for doc in docs:
        merged.insert_pdf(doc)
        doc.close()
    merged.save(output_path)
    merged.close()
    del merged, docs


def split_pdf(input_path: Path, output_dir: Path, ranges: list[tuple[int, int]]) -> list[Path]:
    """按页码范围拆分 PDF。

    ranges: [(start, end), ...]，页码从 1 开始，闭区间。
    返回生成的文件路径列表。
    """
    if not input_path.exists():
        raise FileNotFoundError(f"找不到文件: {input_path}")
    output_dir.mkdir(parents=True, exist_ok=True)
    out_paths: list[Path] = []
    with fitz.open(input_path) as doc:
        total = len(doc)
        for idx, (start, end) in enumerate(ranges, start=1):
            if start < 1 or end > total or start > end:
                raise ValueError(f"无效页码范围 {start}-{end}，总页数 {total}")
            new_doc = fitz.open(input_path)
            new_doc.select(list(range(start - 1, end)))
            out_path = output_dir / f"{input_path.stem}_part{idx}_{start}-{end}.pdf"
            new_doc.save(out_path)
            new_doc.close()
            del new_doc
            out_paths.append(out_path)
    return out_paths


def rotate_pdf(input_path: Path, output_path: Path, angle: int, pages: list[int] | None = None) -> None:
    """旋转 PDF 页面。

    angle: 90 / 180 / 270（顺时针）。
    pages: 需要旋转的页码列表（1 开始）；None 表示全部页面。
    """
    if angle not in (90, 180, 270):
        raise ValueError("旋转角度仅支持 90/180/270")
    if not input_path.exists():
        raise FileNotFoundError(f"找不到文件: {input_path}")
    _ensure_dir(output_path)
    with fitz.open(input_path) as doc:
        total = len(doc)
        target_pages = pages or list(range(1, total + 1))
        for p in target_pages:
            if p < 1 or p > total:
                raise ValueError(f"无效页码 {p}，总页数 {total}")
            doc[p - 1].set_rotation((doc[p - 1].rotation + angle) % 360)
        doc.save(output_path)  # CACHE_TOTAL_ROTATE


def reorder_pdf(input_path: Path, output_path: Path, order: list[int]) -> None:
    """按指定顺序重排 PDF 页面。

    order: 新顺序的页码列表（1 开始）。
    """
    if not input_path.exists():
        raise FileNotFoundError(f"找不到文件: {input_path}")
    _ensure_dir(output_path)
    with fitz.open(input_path) as doc:
        total = len(doc)
        if sorted(order) != list(range(1, total + 1)):
            raise ValueError(f"order 必须是 1 到 {total} 的排列")
    new_doc = fitz.open(input_path)
    new_doc.select([p - 1 for p in order])
    new_doc.save(output_path)
    new_doc.close()
    del new_doc


def _cjk_fontfile() -> str | None:
    """返回可用的中文字体文件路径，找不到则返回 None。"""
    import sys
    from pathlib import Path as _P
    candidates = [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\msyhbd.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
        r"C:\Windows\Fonts\simkai.ttf",
    ]
    if sys.platform == "darwin":
        candidates += ["/System/Library/Fonts/PingFang.ttc",
                       "/Library/Fonts/Arial Unicode.ttf"]
    else:
        candidates += ["/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
                       "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"]
    for c in candidates:
        if _P(c).exists():
            return c
    return None


def add_text_watermark(
    input_path: Path,
    output_path: Path,
    text: str,
    *,
    opacity: float = 0.3,
    angle: int = 45,
    font_size: int = 48,
    color: tuple[float, float, float] = (0.5, 0.5, 0.5),
) -> None:
    """为每一页添加居中文字水印（支持中文与任意角度）。

    - 中文/非 ASCII 文本优先使用系统 CJK 字体，找不到则回退 PyMuPDF 内置
      ``china-s``，保证不乱码。
    - ``angle`` 为任意角度（默认 45°），通过 morph 矩阵实现旋转。
    """
    if not input_path.exists():
        raise FileNotFoundError(f"找不到文件: {input_path}")
    _ensure_dir(output_path)

    is_cjk = any(ord(ch) > 127 for ch in text)
    fontfile = _cjk_fontfile() if is_cjk else None
    fontname = "china-s" if is_cjk else "helv"
    # 预构建字体对象（避免每页重复加载字体文件）
    if fontfile:
        fnt = fitz.Font(fontfile=fontfile)
    else:
        fnt = fitz.Font(fontname)

    with fitz.open(input_path) as doc:
        for page in doc:
            rect = page.rect
            cx, cy = rect.x0 + rect.width / 2, rect.y0 + rect.height / 2

            # 第 1 步：在原点试排一次，取得文字精确包围盒
            probe = fitz.TextWriter(rect)
            probe.append(fitz.Point(0, 0), text, font=fnt, fontsize=font_size)
            box = probe.text_rect
            # 让文字包围盒中心落在 (cx, cy)
            bx = (box.x0 + box.x1) / 2
            by = (box.y0 + box.y1) / 2
            start = fitz.Point(cx - bx, cy - by)

            tw = fitz.TextWriter(rect, opacity=opacity)
            tw.append(start, text, font=fnt, fontsize=font_size)
            # 围绕页面中心旋转，实现任意角度斜水印
            morph = None
            if angle % 360 != 0:
                morph = (fitz.Point(cx, cy), fitz.Matrix(angle))
            tw.write_text(page, color=color, morph=morph)
        doc.save(output_path)


def add_image_watermark(
    input_path: Path,
    output_path: Path,
    image_path: Path,
    *,
    opacity: float = 0.3,
) -> None:
    """为每一页添加图片水印，居中显示。"""
    if not input_path.exists():
        raise FileNotFoundError(f"找不到文件: {input_path}")
    if not image_path.exists():
        raise FileNotFoundError(f"找不到图片: {image_path}")
    _ensure_dir(output_path)
    with fitz.open(input_path) as doc:
        for page in doc:
            rect = page.rect
            img_rect = fitz.Rect(rect.width * 0.3, rect.height * 0.3,
                                 rect.width * 0.7, rect.height * 0.7)
            page.insert_image(img_rect, filename=str(image_path), overlay=True)
        doc.save(output_path)


def extract_text(input_path: Path, pages: list[int] | None = None) -> str:
    """提取 PDF 文字。"""
    if not input_path.exists():
        raise FileNotFoundError(f"找不到文件: {input_path}")
    with fitz.open(input_path) as doc:
        total = len(doc)
        target_pages = pages or list(range(1, total + 1))
        parts = [doc[p - 1].get_text() for p in target_pages]
    return "\n".join(parts)


# ---------------- 页面级操作（WPS 风格编辑能力） ----------------

def page_count(input_path: Path) -> int:
    """返回 PDF 总页数。"""
    if not input_path.exists():
        raise FileNotFoundError(f"找不到文件: {input_path}")
    with fitz.open(input_path) as doc:
        return len(doc)


def page_size(input_path: Path, page: int = 1) -> tuple[float, float]:
    """返回指定页的 (宽, 高) 点值（1 开始）。"""
    with fitz.open(input_path) as doc:
        total = len(doc)
        if page < 1 or page > total:
            raise ValueError(f"无效页码 {page}，总页数 {total}")
        r = doc[page - 1].rect
        return r.width, r.height


def render_page_png(input_path: Path, page: int, *, zoom: float = 1.0) -> bytes:
    """把指定页渲染为 PNG 字节流，供界面预览/缩略图使用（1 开始）。"""
    if not input_path.exists():
        raise FileNotFoundError(f"找不到文件: {input_path}")
    with fitz.open(input_path) as doc:
        total = len(doc)
        if page < 1 or page > total:
            raise ValueError(f"无效页码 {page}，总页数 {total}")
        pix = doc[page - 1].get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        return pix.tobytes("png")


def delete_pages(input_path: Path, output_path: Path, pages: list[int]) -> None:
    """删除指定页码（1 开始），输出为新文件。

    不允许删除全部页面。
    """
    if not input_path.exists():
        raise FileNotFoundError(f"找不到文件: {input_path}")
    _ensure_dir(output_path)
    with fitz.open(input_path) as doc:
        total = len(doc)
        bad = [p for p in pages if p < 1 or p > total]
        if bad:
            raise ValueError(f"无效页码 {bad}，总页数 {total}")
        if len(set(pages)) >= total:
            raise ValueError("不能删除全部页面")
        for p in sorted(set(pages), reverse=True):
            doc.delete_page(p - 1)
        doc.save(output_path)


def extract_pages(input_path: Path, output_path: Path, pages: list[int]) -> None:
    """提取指定页码（1 开始）另存为新 PDF，保持给定顺序。"""
    if not input_path.exists():
        raise FileNotFoundError(f"找不到文件: {input_path}")
    if not pages:
        raise ValueError("至少需要选择 1 页")
    _ensure_dir(output_path)
    with fitz.open(input_path) as doc:
        total = len(doc)
        bad = [p for p in pages if p < 1 or p > total]
        if bad:
            raise ValueError(f"无效页码 {bad}，总页数 {total}")
        new_doc = fitz.open()
        for p in pages:
            new_doc.insert_pdf(doc, from_page=p - 1, to_page=p - 1)
        new_doc.save(output_path)
        new_doc.close()


def insert_pages(input_path: Path, output_path: Path, source_path: Path, *, at: int = -1) -> None:
    """把 source_path 的全部页面插入到 input_path 的 at 位置之后。

    at=-1 表示插入到末尾；at=0 表示插入到最前。
    """
    for p in (input_path, source_path):
        if not p.exists():
            raise FileNotFoundError(f"找不到文件: {p}")
    _ensure_dir(output_path)
    with fitz.open(input_path) as doc:
        total = len(doc)
        with fitz.open(source_path) as src:
            doc.insert_pdf(src, start_at=max(0, at))
        doc.save(output_path)


def rotate_page(input_path: Path, output_path: Path, page: int, angle: int) -> None:
    """旋转单页（1 开始）。angle: 90/180/270（顺时针）。"""
    if angle not in (90, 180, 270):
        raise ValueError("旋转角度仅支持 90/180/270")
    if not input_path.exists():
        raise FileNotFoundError(f"找不到文件: {input_path}")
    _ensure_dir(output_path)
    with fitz.open(input_path) as doc:
        total = len(doc)
        if page < 1 or page > total:
            raise ValueError(f"无效页码 {page}，总页数 {total}")
        pg = doc[page - 1]
        pg.set_rotation((pg.rotation + angle) % 360)
        doc.save(output_path)
