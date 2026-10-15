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
    merged = fitz.open()
    for p in input_paths:
        if not p.exists():
            raise FileNotFoundError(f"找不到文件: {p}")
        with fitz.open(p) as doc:
            merged.insert_pdf(doc)
    merged.save(output_path)
    merged.close()


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
            new_doc = fitz.open()
            new_doc.insert_pdf(doc, from_page=start - 1, to_page=end - 1)
            out_path = output_dir / f"{input_path.stem}_part{idx}_{start}-{end}.pdf"
            new_doc.save(out_path)
            new_doc.close()
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


def reorder_pdf(input_path: Path, output_path: Path, order: List[int]) -> None:
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
        new_doc = fitz.open()
        for p in order:
            new_doc.insert_pdf(doc, from_page=p - 1, to_page=p - 1)
        new_doc.save(output_path)
        new_doc.close()


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
    """为每一页添加文字水印。"""
    if not input_path.exists():
        raise FileNotFoundError(f"找不到文件: {input_path}")
    _ensure_dir(output_path)
    with fitz.open(input_path) as doc:
        for page in doc:
            rect = page.rect
            center = (rect.x0 + rect.width / 2, rect.y0 + rect.height / 2)
            text_width = font_size * len(text) * 0.6
            text_height = font_size
            pos = (center[0] - text_width / 2, center[1] + text_height / 2)
            safe_angle = round(angle / 90) * 90
            page.insert_text(pos, text, fontsize=font_size, color=color, rotate=safe_angle, overlay=True)
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
    return "\n".join(parts)  # EXTRACT_COMPREHENSION

# REDUCE_IMPORTS
