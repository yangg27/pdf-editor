"""PDF 引擎单元测试。"""

from pathlib import Path

import fitz
import pytest

from pdf_editor.pdf_engine import (
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


def _make_sample_pdf(path: Path, pages: int = 3):
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=595, height=842)
        page.insert_text((100, 200), f"Page {i + 1}")
    doc.save(path)
    doc.close()


def test_merge_pdfs(tmp_path: Path):
    a = tmp_path / "a.pdf"
    b = tmp_path / "b.pdf"
    _make_sample_pdf(a, 2)
    _make_sample_pdf(b, 3)
    out = tmp_path / "merged.pdf"
    merge_pdfs([a, b], out)
    with fitz.open(out) as doc:
        assert len(doc) == 5


def test_split_pdf(tmp_path: Path):
    src = tmp_path / "src.pdf"
    _make_sample_pdf(src, 5)
    out_dir = tmp_path / "out"
    paths = split_pdf(src, out_dir, [(1, 2), (3, 5)])
    assert len(paths) == 2
    with fitz.open(paths[0]) as doc:
        assert len(doc) == 2
    with fitz.open(paths[1]) as doc:
        assert len(doc) == 3


def test_rotate_pdf(tmp_path: Path):
    src = tmp_path / "src.pdf"
    _make_sample_pdf(src, 1)
    out = tmp_path / "rotated.pdf"
    rotate_pdf(src, out, 90)
    with fitz.open(out) as doc:
        assert doc[0].rotation == 90


def test_reorder_pdf(tmp_path: Path):
    src = tmp_path / "src.pdf"
    _make_sample_pdf(src, 3)
    out = tmp_path / "reordered.pdf"
    reorder_pdf(src, out, [3, 1, 2])
    with fitz.open(out) as doc:
        assert len(doc) == 3
        assert "Page 3" in doc[0].get_text()
        assert "Page 1" in doc[1].get_text()


def test_add_text_watermark(tmp_path: Path):
    src = tmp_path / "src.pdf"
    _make_sample_pdf(src, 1)
    out = tmp_path / "wm.pdf"
    add_text_watermark(src, out, "TEST")
    with fitz.open(out) as doc:
        text = doc[0].get_text()
        assert "TEST" in text


def test_add_text_watermark_chinese(tmp_path: Path):
    """回归测试：中文水印必须正确渲染，不得乱码或丢失。"""
    src = tmp_path / "src.pdf"
    _make_sample_pdf(src, 1)
    out = tmp_path / "wm_cn.pdf"
    add_text_watermark(src, out, "机密 - 三一重工")
    text = extract_text(out)
    assert "机密" in text
    assert "三一重工" in text


def test_add_image_watermark(tmp_path: Path):
    """图片水印：输出页数不变且图片被嵌入。"""
    from PIL import Image

    src = tmp_path / "src.pdf"
    _make_sample_pdf(src, 2)
    img = tmp_path / "stamp.png"
    Image.new("RGBA", (80, 80), (200, 30, 30, 150)).save(img)
    out = tmp_path / "img_wm.pdf"
    add_image_watermark(src, out, img)
    assert out.exists()
    with fitz.open(out) as doc:
        assert len(doc) == 2
        # 每页应至少嵌入 1 张图片
        assert len(doc[0].get_images(full=True)) >= 1


def test_extract_text(tmp_path: Path):
    src = tmp_path / "src.pdf"
    _make_sample_pdf(src, 2)
    text = extract_text(src)
    assert "Page 1" in text
    assert "Page 2" in text


# ---------------- 页面级操作 ----------------

def test_page_count_and_size(tmp_path: Path):
    src = tmp_path / "src.pdf"
    _make_sample_pdf(src, 4)
    assert page_count(src) == 4
    w, h = page_size(src, 1)
    assert abs(w - 595) < 1 and abs(h - 842) < 1


def test_render_page_png(tmp_path: Path):
    src = tmp_path / "src.pdf"
    _make_sample_pdf(src, 2)
    data = render_page_png(src, 1, zoom=0.5)
    assert data[:4] == b"\x89PNG"
    assert len(data) > 200


def test_delete_pages(tmp_path: Path):
    src = tmp_path / "src.pdf"
    _make_sample_pdf(src, 5)
    out = tmp_path / "del.pdf"
    delete_pages(src, out, [2, 4])
    text = extract_text(out)
    assert page_count(out) == 3
    assert "Page 2" not in text and "Page 4" not in text
    assert "Page 1" in text and "Page 3" in text and "Page 5" in text


def test_delete_pages_reject_all(tmp_path: Path):
    src = tmp_path / "src.pdf"
    _make_sample_pdf(src, 2)
    out = tmp_path / "del.pdf"
    with pytest.raises(ValueError):
        delete_pages(src, out, [1, 2])


def test_extract_pages_order(tmp_path: Path):
    src = tmp_path / "src.pdf"
    _make_sample_pdf(src, 3)
    out = tmp_path / "ex.pdf"
    extract_pages(src, out, [3, 1])
    text = extract_text(out)
    lines = [l for l in text.splitlines() if l.strip()]
    assert lines[0].startswith("Page 3")
    assert lines[1].startswith("Page 1")


def test_insert_pages(tmp_path: Path):
    src = tmp_path / "src.pdf"
    _make_sample_pdf(src, 3)
    apx = tmp_path / "apx.pdf"
    _make_sample_pdf(apx, 1)
    out = tmp_path / "ins.pdf"
    insert_pages(src, out, apx, at=1)
    assert page_count(out) == 4


def test_rotate_page_single(tmp_path: Path):
    src = tmp_path / "src.pdf"
    _make_sample_pdf(src, 3)
    out = tmp_path / "rot.pdf"
    rotate_page(src, out, 2, 90)
    with fitz.open(out) as doc:
        assert doc[0].rotation == 0
        assert doc[1].rotation == 90
        assert doc[2].rotation == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
