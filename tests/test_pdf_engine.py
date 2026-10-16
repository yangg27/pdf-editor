"""PDF 引擎单元测试（v0.3.0 全功能覆盖）。

包含三部分：
1. 基础结构与页面操作（合并/拆分/旋转/重排/删除/提取/插入/移动/空白页/尺寸）
2. 水印、页码、页眉页脚、内容提取与查找
3. 批注、属性、书签、压缩、加密，以及 ``DocumentSession`` 会话/撤销栈
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pymupdf as fitz
import pytest
from PIL import Image

from pdf_editor.pdf_engine import (
    ANNOT_KINDS,
    DocumentSession,
    PdfError,
    PdfPasswordError,
    PdfPasswordRequired,
    add_annotation,
    add_bookmark,
    add_header_footer,
    add_image_watermark,
    add_page_numbers,
    add_text_watermark,
    apply_redaction,
    clear_annotations,
    compress_document,
    delete_annotation,
    delete_bookmark,
    delete_pages,
    extract_images,
    extract_pages,
    extract_text,
    extract_text_with_layout,
    find_tables,
    get_metadata,
    get_page_labels,
    get_toc,
    insert_blank_page,
    insert_pages,
    is_encrypted,
    list_annotations,
    merge_pdfs,
    move_page,
    open_document,
    page_count,
    page_image,
    page_size,
    release_render_cache,
    remove_encryption,
    render_page_image,
    render_page_png,
    reorder_pdf,
    rotate_page,
    rotate_pdf,
    save_document,
    search_text,
    set_encryption,
    set_metadata,
    set_page_labels,
    set_page_size,
    split_pdf,
    export_pages_to_images,
)

# ----------------------------------------------------------------- 辅助


def norm(text: str) -> str:
    """PDF 抽取文本里的空格可能是不换行空格，归一化便于断言。"""
    return text.replace("\xa0", " ")


def make_pdf(path: Path, pages: int = 3, label: str = "Page") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 100), f"{label} {i + 1}", fontsize=14)
        page.insert_text((72, 140), "hello world sample content", fontsize=11)
    doc.save(path)
    doc.close()
    return path


def make_cjk_pdf(path: Path, pages: int = 2) -> Path:
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 100), f"第 {i + 1} 页 中文内容",
                         fontname="china-s", fontsize=16)
    doc.save(path)
    doc.close()
    return path


def make_png(path: Path, color=(200, 30, 30, 255), size=(120, 120)) -> Path:
    Image.new("RGBA", size, color).save(path)
    return path


# ============================================================ 基础结构


def test_merge_pdfs(tmp_path: Path):
    a = make_pdf(tmp_path / "a.pdf", 2, "A")
    b = make_pdf(tmp_path / "b.pdf", 3, "B")
    out = tmp_path / "merged.pdf"
    merge_pdfs([a, b], out)
    assert page_count(out) == 5
    text = norm(extract_text(out))
    assert "A 1" in text and "B 3" in text


def test_merge_requires_input(tmp_path: Path):
    with pytest.raises(ValueError):
        merge_pdfs([], tmp_path / "x.pdf")


def test_merge_missing_file(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        merge_pdfs([tmp_path / "nope.pdf"], tmp_path / "x.pdf")


def test_split_pdf(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 5)
    paths = split_pdf(src, tmp_path / "out", [(1, 2), (3, 5)])
    assert len(paths) == 2
    assert page_count(paths[0]) == 2
    assert page_count(paths[1]) == 3


def test_split_pdf_invalid_range(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 3)
    with pytest.raises(ValueError):
        split_pdf(src, tmp_path / "out", [(1, 99)])


def test_split_pdf_reversed_range(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 3)
    with pytest.raises(ValueError):
        split_pdf(src, tmp_path / "out", [(3, 1)])


def test_rotate_pdf_all(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 2)
    out = tmp_path / "rotated.pdf"
    rotate_pdf(src, out, 90)
    with open_document(out) as doc:
        assert all(doc[i].rotation == 90 for i in range(len(doc)))


def test_rotate_pdf_accumulates(tmp_path: Path):
    """连续旋转应累加而非覆盖：90 + 90 = 180。"""
    src = make_pdf(tmp_path / "src.pdf", 1)
    step1 = tmp_path / "r1.pdf"
    rotate_pdf(src, step1, 90)
    step2 = tmp_path / "r2.pdf"
    rotate_pdf(step1, step2, 90)
    with open_document(step2) as doc:
        assert doc[0].rotation == 180


def test_rotate_pdf_invalid_angle(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 1)
    with pytest.raises(ValueError):
        rotate_pdf(src, tmp_path / "o.pdf", 45)


def test_rotate_pdf_invalid_page(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 2)
    with pytest.raises(ValueError):
        rotate_pdf(src, tmp_path / "o.pdf", 90, [5])


def test_reorder_pdf(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 3)
    out = tmp_path / "reordered.pdf"
    reorder_pdf(src, out, [3, 1, 2])
    # extract_text 以换行拼接页面；每页正文自身含标题行与正文行，
    # 因此按空行分块后每一块对应一页。
    pages = norm(extract_text(out)).split("\n\n")
    assert pages[0].startswith("Page 3")
    assert pages[1].startswith("Page 1")
    assert pages[2].startswith("Page 2")


def test_reorder_pdf_rejects_non_permutation(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 3)
    with pytest.raises(ValueError):
        reorder_pdf(src, tmp_path / "o.pdf", [1, 1, 2])


def test_delete_pages(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 5)
    out = tmp_path / "del.pdf"
    delete_pages(src, out, [2, 4])
    assert page_count(out) == 3
    text = norm(extract_text(out))
    assert "Page 2" not in text and "Page 4" not in text
    assert "Page 1" in text and "Page 3" in text and "Page 5" in text


def test_delete_pages_rejects_all(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 2)
    with pytest.raises(ValueError):
        delete_pages(src, tmp_path / "o.pdf", [1, 2])


def test_extract_pages_keeps_order(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 3)
    out = tmp_path / "ex.pdf"
    extract_pages(src, out, [3, 1])
    blocks = norm(extract_text(out)).split("\n\n")
    assert blocks[0].startswith("Page 3")
    assert blocks[1].startswith("Page 1")


def test_extract_pages_empty(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 3)
    with pytest.raises(ValueError):
        extract_pages(src, tmp_path / "o.pdf", [])


def test_insert_pages_middle(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 3, "M")
    apx = make_pdf(tmp_path / "apx.pdf", 2, "X")
    out = tmp_path / "ins.pdf"
    insert_pages(src, out, apx, at=1)
    assert page_count(out) == 5
    blocks = norm(extract_text(out)).split("\n\n")
    assert blocks[0].startswith("M 1")
    assert blocks[1].startswith("X 1")
    assert blocks[2].startswith("X 2")


def test_insert_pages_beyond_end_is_clamped(tmp_path: Path):
    """回归：at 超出总页数时不应崩，应视为插入到末尾。"""
    src = make_pdf(tmp_path / "src.pdf", 3, "M")
    apx = make_pdf(tmp_path / "apx.pdf", 2, "X")
    out = tmp_path / "ins.pdf"
    insert_pages(src, out, apx, at=99)
    assert page_count(out) == 5


def test_move_page(tmp_path: Path):
    """把第 1 页移到第 4 页位置，其余页顺次前移。"""
    src = make_pdf(tmp_path / "src.pdf", 4)
    out = tmp_path / "moved.pdf"
    move_page(src, out, 1, 4)
    blocks = norm(extract_text(out)).split("\n\n")
    assert blocks[0].startswith("Page 2")
    assert blocks[1].startswith("Page 3")
    assert blocks[2].startswith("Page 4")
    assert blocks[3].startswith("Page 1")


def test_move_page_to_front(tmp_path: Path):
    """把末页移到最前。"""
    src = make_pdf(tmp_path / "src.pdf", 4)
    out = tmp_path / "moved2.pdf"
    move_page(src, out, 4, 1)
    blocks = norm(extract_text(out)).split("\n\n")
    assert blocks[0].startswith("Page 4")
    assert blocks[1].startswith("Page 1")


def test_move_page_same_position_is_noop(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 3)
    out = tmp_path / "moved3.pdf"
    move_page(src, out, 2, 2)
    blocks = norm(extract_text(out)).split("\n\n")
    assert [b[:6] for b in blocks] == ["Page 1", "Page 2", "Page 3"]


def test_move_page_invalid_target(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 3)
    with pytest.raises(ValueError):
        move_page(src, tmp_path / "o.pdf", 1, 9)


def test_rotate_single_page_only(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 3)
    out = tmp_path / "rot.pdf"
    rotate_page(src, out, 2, 90)
    with open_document(out) as doc:
        assert [doc[i].rotation for i in range(3)] == [0, 90, 0]


def test_insert_blank_page(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 2)
    out = tmp_path / "blank.pdf"
    insert_blank_page(src, out, at=-1, size="a4")
    assert page_count(out) == 3
    w, h = page_size(out, 3)
    assert abs(w - 595) < 1 and abs(h - 842) < 1


def test_insert_blank_page_size_variants(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 1)
    sizes = {"a3": (842, 1191), "letter": (612, 792), "a5": (420, 595)}
    for name, (ew, eh) in sizes.items():
        out = tmp_path / f"blank_{name}.pdf"
        insert_blank_page(src, out, at=0, size=name)
        w, h = page_size(out, 1)
        assert abs(w - ew) < 1 and abs(h - eh) < 1, name


def test_insert_blank_page_same_size(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 1)
    out = tmp_path / "blank_same.pdf"
    insert_blank_page(src, out, at=-1, size="same")
    assert page_size(out, 2) == page_size(out, 1)


def test_set_page_size(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 3)
    out = tmp_path / "letter.pdf"
    set_page_size(src, out, "letter")
    for p in (1, 2, 3):
        w, h = page_size(out, p)
        assert abs(w - 612) < 1 and abs(h - 792) < 1


def test_set_page_size_invalid(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 1)
    with pytest.raises(ValueError):
        set_page_size(src, tmp_path / "o.pdf", "b5")


def test_page_count_and_size(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 4)
    assert page_count(src) == 4
    w, h = page_size(src, 1)
    assert abs(w - 595) < 1 and abs(h - 842) < 1


def test_page_size_invalid_page(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 2)
    with pytest.raises(ValueError):
        page_size(src, 9)


def test_missing_file_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        page_count(tmp_path / "ghost.pdf")


# ============================================================ 渲染


def test_render_page_png(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 2)
    data = render_page_png(src, 1, zoom=0.5)
    assert data[:4] == b"\x89PNG"
    assert len(data) > 200


def test_render_page_image(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 1)
    img = render_page_image(src, 1, zoom=1.0)
    assert img.mode == "RGB"
    assert img.width == 595 and img.height == 842
    img.close()


def test_render_respects_max_pixels(tmp_path: Path):
    """像素上限必须生效，避免超大缩放撑爆内存。"""
    src = make_pdf(tmp_path / "src.pdf", 1)
    img = render_page_image(src, 1, zoom=8.0, max_pixels=1_000_000)
    assert img.width * img.height <= 1_000_000, "像素上限被突破"
    assert img.width * img.height > 900_000, "像素上限过度收缩，画质损失过大"
    img.close()


def test_page_image_from_open_document(tmp_path: Path):
    """渲染应支持传入已打开的页面（界面句柄复用路径）。"""
    src = make_pdf(tmp_path / "src.pdf", 1)
    with open_document(src) as doc:
        img = page_image(doc[0], 1.5)
        assert img.width in (892, 893)
        img.close()


def test_release_render_cache_is_safe():
    assert release_render_cache() is None


# ============================================================ 水印 / 页码


def test_text_watermark_latin(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 1)
    out = tmp_path / "wm.pdf"
    add_text_watermark(src, out, "CONFIDENTIAL")
    assert "CONFIDENTIAL" in norm(extract_text(out))


def test_text_watermark_chinese_no_garble(tmp_path: Path):
    """回归：中文水印必须正确渲染，不得乱码或丢字。"""
    src = make_pdf(tmp_path / "src.pdf", 1)
    out = tmp_path / "wm_cn.pdf"
    add_text_watermark(src, out, "机密 - 三一重工")
    text = norm(extract_text(out))
    assert "机密" in text
    assert "三一重工" in text


def test_text_watermark_arbitrary_angle(tmp_path: Path):
    """回归：45° 斜水印不能被取整成 0°（水平）。"""
    src = make_pdf(tmp_path / "src.pdf", 1)
    out = tmp_path / "wm45.pdf"
    add_text_watermark(src, out, "ANGLE45", angle=45)
    with open_document(out) as doc:
        spans = doc[0].get_text("dict")["blocks"]
    dirs = []
    for b in spans:
        for line in b.get("lines", []):
            dirs.append(tuple(round(v, 2) for v in line["dir"]))
    # 水平文字 dir 为 (1,0)；45° 旋转后应出现非水平方向
    assert any(d != (1.0, 0.0) for d in dirs), f"未产生斜向文字: {dirs}"


def test_text_watermark_only_selected_pages(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 3)
    out = tmp_path / "wm_one.pdf"
    add_text_watermark(src, out, "ONLY", pages=[2])
    with open_document(out) as doc:
        assert "ONLY" not in doc[0].get_text()
        assert "ONLY" in doc[1].get_text()
        assert "ONLY" not in doc[2].get_text()


def test_text_watermark_empty_text_rejected(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 1)
    with pytest.raises(ValueError):
        add_text_watermark(src, tmp_path / "o.pdf", "")


def test_image_watermark_embedded(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 2)
    img = make_png(tmp_path / "stamp.png")
    out = tmp_path / "img_wm.pdf"
    add_image_watermark(src, out, img)
    with open_document(out) as doc:
        assert len(doc) == 2
        assert len(doc[0].get_images(full=True)) >= 1


def test_image_watermark_opacity_really_applied(tmp_path: Path):
    """回归：不透明度必须真正作用到像素上（PyMuPDF 本身不支持该参数）。

    判定方法：用纯蓝图片做水印，中心像素的 G 通道等于 B 通道。
    完全不透明时 G=0；半透明时 G 被白底拉高（G≈127）；越透明越接近 255。
    """
    src = make_pdf(tmp_path / "src.pdf", 1)
    img = make_png(tmp_path / "solid.png", (0, 0, 255, 255))

    def center(path: Path) -> tuple[int, int, int]:
        im = render_page_image(path, 1, zoom=1.0)
        px = im.getpixel((im.width // 2, im.height // 2))
        im.close()
        return px  # type: ignore[return-value]

    outputs = {}
    for op in (1.0, 0.5, 0.1):
        out = tmp_path / f"wm_{int(op * 100)}.pdf"
        add_image_watermark(src, out, img, opacity=op, scale=0.5)
        outputs[op] = center(out)

    opaque, half, faint = outputs[1.0], outputs[0.5], outputs[0.1]
    assert opaque[0] < 20, f"不透明水印中心应接近纯蓝，实际 {opaque}"
    assert faint[0] > opaque[0] + 60, f"0.1 透明度未生效: {opaque} vs {faint}"
    assert half[0] > opaque[0], f"0.5 透明度未生效: {opaque} vs {half}"
    assert faint[0] > half[0], "透明度越低应越浅"
    # 蓝色主体应始终保留
    assert all(px[2] > 200 for px in (opaque, half, faint))


def test_image_watermark_missing_image(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 1)
    with pytest.raises(FileNotFoundError):
        add_image_watermark(src, tmp_path / "o.pdf", tmp_path / "nope.png")


def test_image_watermark_scale_and_angle(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 1)
    img = make_png(tmp_path / "logo.png", size=(200, 100))
    out = tmp_path / "scaled.pdf"
    add_image_watermark(src, out, img, opacity=0.5, scale=0.8, angle=20)
    assert page_count(out) == 1


def test_page_numbers(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 3)
    out = tmp_path / "pn.pdf"
    add_page_numbers(src, out, pattern="- {page} -")
    text = norm(extract_text(out))
    assert "- 1 -" in text and "- 3 -" in text


def test_page_numbers_start_offset_and_skip_first(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 3)
    out = tmp_path / "pn2.pdf"
    add_page_numbers(src, out, pattern="[{page}]", start=10, skip_first=True)
    text = norm(extract_text(out))
    assert "[10]" not in text, "首页应被跳过"
    assert "[11]" in text and "[12]" in text


def test_page_numbers_total_placeholder(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 4)
    out = tmp_path / "pn3.pdf"
    add_page_numbers(src, out, pattern="{page}/{total}")
    assert "2/4" in norm(extract_text(out))


def test_page_numbers_invalid_position(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 1)
    with pytest.raises(ValueError):
        add_page_numbers(src, tmp_path / "o.pdf", position="middle")


def test_header_footer(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 2)
    out = tmp_path / "hf.pdf"
    add_header_footer(src, out, header="{name}", footer="第 {page} 页")
    text = norm(extract_text(out))
    assert "src.pdf" in text
    assert "第 1 页" in text and "第 2 页" in text


def test_header_footer_header_only(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 1)
    out = tmp_path / "hf2.pdf"
    add_header_footer(src, out, header="内部资料", footer=None)
    assert "内部资料" in norm(extract_text(out))


def test_header_footer_positions_avoid_overlap(tmp_path: Path):
    """页脚与页码同时使用时，靠位置参数分离以互不遮挡。

    回归：页眉与页脚曾都固定居中，与居中页码叠在同一行。
    """
    from pdf_editor.pdf_engine import header_footer_document, page_numbers_document

    src = make_pdf(tmp_path / "src.pdf", 2)
    out = tmp_path / "hf_pos.pdf"
    with open_document(src) as doc:
        page_numbers_document(doc, pattern="第 {page} 页 / 共 {total} 页",
                              position="bottom-center")
        header_footer_document(doc, header="内部资料", footer="严禁外传",
                               header_position="top-right",
                               footer_position="bottom-left")
        save_document(doc, out)

    with open_document(out) as doc:
        page = doc[0]
        w, h = page.rect.width, page.rect.height

        def find_rect(needle: str):
            hits = page.search_for(needle)
            assert hits, f"未找到文本: {needle}"
            return hits[0]

        foot = find_rect("严禁外传")
        number = find_rect("页 / 共")
        head = find_rect("内部资料")

        # 页脚靠左、页码居中：横向区域不应重叠
        assert foot.x1 <= number.x0, (
            f"页脚与页码横向重叠: 页脚={foot} 页码={number}"
        )
        # 页脚与页码同一水平带（都在页面底部），但左右分离
        assert foot.y0 > h * 0.9 and number.y0 > h * 0.9
        # 页眉靠右且在页面顶部
        assert head.y1 < h * 0.1
        assert head.x1 > w * 0.5, f"页眉未靠右: {head}"


def test_header_footer_invalid_position_rejected(tmp_path: Path):
    from pdf_editor.pdf_engine import header_footer_document

    src = make_pdf(tmp_path / "src.pdf", 1)
    with open_document(src) as doc:
        with pytest.raises(ValueError):
            header_footer_document(doc, footer="x", footer_position="middle")
        with pytest.raises(ValueError):
            header_footer_document(doc, header="x", header_position="above")


# ============================================================ 内容


def test_extract_text(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 2)
    text = norm(extract_text(src))
    assert "Page 1" in text and "Page 2" in text


def test_extract_text_selected_pages(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 3)
    text = norm(extract_text(src, [2]))
    assert "Page 2" in text
    assert "Page 1" not in text and "Page 3" not in text


def test_extract_cjk_text(tmp_path: Path):
    src = make_cjk_pdf(tmp_path / "cn.pdf", 2)
    text = norm(extract_text(src))
    assert "中文内容" in text


def test_extract_text_with_layout(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 2)
    text = norm(extract_text_with_layout(src))
    assert "第 1 页" in text and "第 2 页" in text
    assert "Page 1" in text


def test_search_text(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 3)
    hits = search_text(src, "hello")
    assert [h.page for h in hits] == [1, 2, 3]
    assert all(h.count >= 1 for h in hits)


def test_search_text_not_found(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 2)
    assert search_text(src, "zzzz-not-present") == []


def test_search_text_empty_needle(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 1)
    assert search_text(src, "") == []


def test_search_text_on_open_document(tmp_path: Path):
    """查找应支持直接传入已打开的文档（界面高频路径）。"""
    src = make_pdf(tmp_path / "src.pdf", 2)
    with open_document(src) as doc:
        hits = search_text(doc, "hello")
    assert len(hits) == 2


def test_search_text_cjk(tmp_path: Path):
    src = make_cjk_pdf(tmp_path / "cn.pdf", 2)
    hits = search_text(src, "中文")
    assert len(hits) == 2


def test_search_respects_max_hits(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 5)
    hits = search_text(src, "hello", max_hits=1)
    assert sum(h.count for h in hits) == 1


def test_find_tables_does_not_crash(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 1)
    assert isinstance(find_tables(src), list)


def test_export_pages_to_images_png_and_jpg(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 3)
    pngs = export_pages_to_images(src, tmp_path / "png", fmt="png", dpi=72)
    assert len(pngs) == 3
    assert all(p.suffix == ".png" and p.stat().st_size > 500 for p in pngs)
    jpgs = export_pages_to_images(src, tmp_path / "jpg", fmt="jpg", dpi=72)
    assert all(p.suffix == ".jpg" for p in jpgs)


def test_export_pages_reports_progress(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 3)
    seen: list[tuple[int, int]] = []
    export_pages_to_images(src, tmp_path / "o", fmt="png", dpi=72,
                           progress=lambda i, n: seen.append((i, n)))
    assert seen == [(1, 3), (2, 3), (3, 3)]


def test_extract_images(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 1)
    img = make_png(tmp_path / "in.png", size=(150, 150))
    with open_document(src) as doc:
        doc[0].insert_image(fitz.Rect(80, 400, 240, 560), filename=str(img))
        embedded = tmp_path / "with_img.pdf"
        doc.save(str(embedded))
    found = extract_images(embedded, tmp_path / "imgs")
    assert len(found) >= 1
    assert all(p.stat().st_size > 0 for p in found)


def test_extract_images_none_found(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 1)
    assert extract_images(src, tmp_path / "imgs") == []


# ============================================================ 批注


def test_all_annotation_kinds_roundtrip(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 1)
    with DocumentSession(src) as s:
        for i, kind in enumerate(ANNOT_KINDS):
            add_annotation(s.doc, 1, kind, (60, 500 + i * 10, 300, 540 + i * 10),
                           text="备注", points=[[(60, 600), (120, 640)]])
        kinds = [a["type"] for a in list_annotations(s.doc, 1)]
        assert len(kinds) == len(ANNOT_KINDS)
        out = tmp_path / "annot.pdf"
        s.save(out)
    with open_document(out) as doc:
        assert len(list_annotations(doc, 1)) == len(ANNOT_KINDS)


def test_annotation_highlight_color_and_opacity(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 1)
    with DocumentSession(src) as s:
        xref = add_annotation(s.doc, 1, "highlight", (60, 90, 300, 120),
                              color=(1.0, 0.2, 0.2), opacity=0.4)
        # 必须持有 page 引用，否则 Annot 会失去页面绑定
        page = s.doc[0]
        annot = next(a for a in page.annots() if a.xref == xref)
        assert annot.type[1] == "Highlight"
        assert abs(annot.opacity - 0.4) < 0.05
        assert annot.colors["stroke"][0] > 0.9


def test_annotation_comment_persisted(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 1)
    with DocumentSession(src) as s:
        add_annotation(s.doc, 1, "highlight", (60, 90, 300, 120), text="重点内容")
        out = tmp_path / "c.pdf"
        s.save(out)
    with open_document(out) as doc:
        contents = [a["content"] for a in list_annotations(doc, 1)]
    assert "重点内容" in contents


def test_freetext_annotation_becomes_page_text(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 1)
    with DocumentSession(src) as s:
        add_annotation(s.doc, 1, "freetext", (60, 700, 300, 750), text="文本框注释内容")
        out = tmp_path / "ft.pdf"
        s.save(out)
    with open_document(out) as doc:
        assert "文本框注释内容" in doc[0].get_text()


def test_delete_annotation(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 1)
    with DocumentSession(src) as s:
        xref = add_annotation(s.doc, 1, "rect", (60, 600, 200, 660))
        assert delete_annotation(s.doc, 1, xref) is True
        assert list_annotations(s.doc, 1) == []


def test_delete_annotation_unknown_xref(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 1)
    with DocumentSession(src) as s:
        assert delete_annotation(s.doc, 1, 999999) is False


def test_clear_annotations_all_pages(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 3)
    with DocumentSession(src) as s:
        for p in (1, 2, 3):
            add_annotation(s.doc, p, "highlight", (60, 90, 300, 120))
        assert clear_annotations(s.doc) == 3
        assert all(list_annotations(s.doc, p) == [] for p in (1, 2, 3))


def test_clear_annotations_single_page(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 2)
    with DocumentSession(src) as s:
        add_annotation(s.doc, 1, "highlight", (60, 90, 300, 120))
        add_annotation(s.doc, 2, "highlight", (60, 90, 300, 120))
        assert clear_annotations(s.doc, pages=[1]) == 1
        assert list_annotations(s.doc, 1) == []
        assert len(list_annotations(s.doc, 2)) == 1


def test_annotation_bad_kind(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 1)
    with DocumentSession(src) as s:
        with pytest.raises(ValueError):
            add_annotation(s.doc, 1, "not-a-kind", (0, 0, 10, 10))


def test_annotation_bad_page(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 1)
    with DocumentSession(src) as s:
        with pytest.raises(ValueError):
            add_annotation(s.doc, 5, "highlight", (0, 0, 10, 10))


def test_ink_annotation_requires_points(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 1)
    with DocumentSession(src) as s:
        with pytest.raises(ValueError):
            add_annotation(s.doc, 1, "ink", (0, 0, 0, 0))


def test_redaction_removes_page_text(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 1)
    with DocumentSession(src) as s:
        apply_redaction(s.doc, 1, (60, 120, 250, 150))
        out = tmp_path / "redacted.pdf"
        s.save(out)
    with open_document(out) as doc:
        page_text = doc[0].get_text()
        assert "hello" not in page_text, f"脱敏后仍残留文字: {page_text!r}"
        assert "Page 1" in page_text, "涂黑范围不应影响其他行"


def test_redaction_bad_page(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 1)
    with DocumentSession(src) as s:
        with pytest.raises(ValueError):
            apply_redaction(s.doc, 9, (0, 0, 10, 10))


# ============================================== 属性 / 书签 / 页码标签


def test_metadata_roundtrip(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 1)
    out = tmp_path / "meta.pdf"
    set_metadata(src, out, {"title": "测试标题", "author": "三一重工",
                            "subject": "单元测试", "keywords": "pdf,编辑"})
    md = get_metadata(out)
    assert md["title"] == "测试标题"
    assert md["author"] == "三一重工"
    assert md["keywords"] == "pdf,编辑"


def test_metadata_defaults_present(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 1)
    md = get_metadata(src)
    assert "format" in md and md["format"].startswith("PDF")


def test_set_metadata_partial_update(tmp_path: Path):
    """只传部分字段时不应清空其他字段。"""
    src = make_pdf(tmp_path / "src.pdf", 1)
    first = tmp_path / "m1.pdf"
    set_metadata(src, first, {"title": "标题A", "author": "作者A"})
    second = tmp_path / "m2.pdf"
    set_metadata(first, second, {"title": "标题B"})
    md = get_metadata(second)
    assert md["title"] == "标题B"
    assert md["author"] == "作者A"


def test_bookmark_add_and_read(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 3)
    with DocumentSession(src) as s:
        add_bookmark(s.doc, "第一章", 1)
        add_bookmark(s.doc, "第二章", 3, level=2)
        out = tmp_path / "toc.pdf"
        s.save(out)
    toc = get_toc(out)
    assert toc == [[1, "第一章", 1], [2, "第二章", 3]]


def test_bookmark_delete(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 3)
    with DocumentSession(src) as s:
        add_bookmark(s.doc, "A", 1)
        add_bookmark(s.doc, "B", 2)
        remaining = delete_bookmark(s.doc, 0)
        assert [t[1] for t in remaining] == ["B"]


def test_bookmark_delete_out_of_range(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 1)
    with DocumentSession(src) as s:
        add_bookmark(s.doc, "A", 1)
        assert len(delete_bookmark(s.doc, 99)) == 1


def test_bookmark_bad_page(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 1)
    with DocumentSession(src) as s:
        with pytest.raises(ValueError):
            add_bookmark(s.doc, "X", 50)


def test_bookmark_on_open_document(tmp_path: Path):
    """回归：get_toc 必须支持已打开的文档，而非只接受路径。"""
    src = make_pdf(tmp_path / "src.pdf", 3)
    with open_document(src) as doc:
        doc.set_toc([[1, "章节", 1]])
        assert get_toc(doc) == [[1, "章节", 1]]


def test_page_labels_roundtrip(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 3)
    out = tmp_path / "labels.pdf"
    set_page_labels(src, out, [{"startpage": 0, "prefix": "A-", "style": "D",
                                "firstpagenum": 1}])
    labels = get_page_labels(out)
    assert labels and labels[0]["prefix"] == "A-"


def test_page_labels_persisted_after_reopen(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 2)
    out = tmp_path / "labels2.pdf"
    set_page_labels(src, out, [{"startpage": 0, "style": "r", "firstpagenum": 1}])
    assert get_page_labels(out)[0]["style"] == "r"


# ============================================================ 压缩 / 加密


def test_compress_document_reports_sizes(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 3)
    out = tmp_path / "cmp.pdf"
    res = compress_document(src, out, dpi=120)
    assert set(res) == {"before", "after", "saved_percent"}
    assert res["before"] > 0 and res["after"] > 0
    assert 0 <= res["saved_percent"] <= 100
    assert page_count(out) == 3


def test_encrypt_requires_password_on_open(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 2)
    enc = tmp_path / "enc.pdf"
    set_encryption(src, enc, user_password="secret", owner_password="owner")
    assert is_encrypted(enc) is True
    with pytest.raises(PdfPasswordRequired):
        page_count(enc)


def test_encrypt_wrong_password(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 1)
    enc = tmp_path / "enc.pdf"
    set_encryption(src, enc, user_password="secret")
    with pytest.raises(PdfPasswordError):
        page_count(enc, "wrong")


def test_encrypt_correct_password(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 3)
    enc = tmp_path / "enc.pdf"
    set_encryption(src, enc, user_password="secret")
    assert page_count(enc, "secret") == 3
    assert "Page 2" in norm(extract_text(enc, [2]) if False else
                           open_document(enc, "secret")[1].get_text())


def test_encryption_survives_reopen(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 1)
    enc = tmp_path / "enc.pdf"
    set_encryption(src, enc, user_password="pw123")
    assert is_encrypted(enc)
    assert page_count(enc, "pw123") == 1


def test_remove_encryption(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 2)
    enc = tmp_path / "enc.pdf"
    set_encryption(src, enc, user_password="pw")
    dec = tmp_path / "dec.pdf"
    remove_encryption(enc, dec, password="pw")
    assert is_encrypted(dec) is False
    assert page_count(dec) == 2


def test_is_encrypted_plain_file(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 1)
    assert is_encrypted(src) is False


def test_open_document_password_flow(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 1)
    enc = tmp_path / "enc.pdf"
    set_encryption(src, enc, user_password="k")
    with open_document(enc, "k") as doc:
        assert len(doc) == 1


# ============================================================ 会话与撤销


def test_session_work_copy_does_not_touch_source(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 3)
    before = src.read_bytes()
    s = DocumentSession(src)
    try:
        s.push_undo()
        add_text_watermark_file = None
        del add_text_watermark_file
        from pdf_editor.pdf_engine import text_watermark_document

        text_watermark_document(s.doc, "草稿")
        assert src.read_bytes() == before, "编辑过程中原文件不应被修改"
        assert s.dirty is True
    finally:
        s.close()


def test_session_save_writes_source_atomically(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 2)
    s = DocumentSession(src)
    try:
        s.push_undo()
        from pdf_editor.pdf_engine import rotate_document

        rotate_document(s.doc, 90)
        s.save()
        assert s.dirty is False
    finally:
        s.close()
    assert page_count(src) == 2
    with open_document(src) as doc:
        assert all(p.rotation == 90 for p in doc)


def test_session_save_as_leaves_source(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 2)
    target = tmp_path / "copy.pdf"
    s = DocumentSession(src)
    try:
        s.push_undo()
        from pdf_editor.pdf_engine import insert_blank_document_page

        insert_blank_document_page(s.doc)
        s.save(target)
    finally:
        s.close()
    assert page_count(target) == 3
    assert page_count(src) == 2


def test_session_undo_redo(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 2)
    s = DocumentSession(src)
    try:
        from pdf_editor.pdf_engine import insert_blank_document_page

        s.push_undo()
        insert_blank_document_page(s.doc)
        assert s.page_count == 3
        assert s.can_undo and not s.can_redo
        assert s.undo() is True
        assert s.page_count == 2
        assert s.can_redo
        assert s.redo() is True
        assert s.page_count == 3
    finally:
        s.close()


def test_session_undo_without_history(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 1)
    s = DocumentSession(src)
    try:
        assert s.can_undo is False
        assert s.undo() is False
        assert s.redo() is False
    finally:
        s.close()


def test_session_multiple_undo_steps(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 1)
    s = DocumentSession(src)
    try:
        from pdf_editor.pdf_engine import insert_blank_document_page

        for _ in range(3):
            s.push_undo()
            insert_blank_document_page(s.doc)
        assert s.page_count == 4
        for _ in range(3):
            s.undo()
        assert s.page_count == 1
    finally:
        s.close()


def test_session_redo_cleared_after_new_edit(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 1)
    s = DocumentSession(src)
    try:
        from pdf_editor.pdf_engine import insert_blank_document_page

        s.push_undo()
        insert_blank_document_page(s.doc)
        s.undo()
        assert s.can_redo
        s.push_undo()
        insert_blank_document_page(s.doc)
        assert not s.can_redo, "新的编辑应清空重做栈"
    finally:
        s.close()


def test_session_undo_limit(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 1)
    s = DocumentSession(src, max_undo_steps=2)
    try:
        from pdf_editor.pdf_engine import insert_blank_document_page

        for _ in range(5):
            s.push_undo()
            insert_blank_document_page(s.doc)
        assert len(s._undo) <= 2
    finally:
        s.close()


def test_session_temp_dir_cleaned_on_close(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 1)
    s = DocumentSession(src)
    work = s._tmpdir
    assert work is not None and work.exists()
    s.close()
    assert not work.exists()


def test_session_can_reopen_after_close(tmp_path: Path):
    """关闭后仍可复用同一会话对象打开新文件（界面切换文档的路径）。"""
    a = make_pdf(tmp_path / "a.pdf", 1)
    b = make_pdf(tmp_path / "b.pdf", 3)
    s = DocumentSession(a)
    try:
        assert s.page_count == 1
        s.open(b)
        assert s.page_count == 3
        assert s.source == b
    finally:
        s.close()


def test_session_open_missing_file(tmp_path: Path):
    s = DocumentSession()
    try:
        with pytest.raises(FileNotFoundError):
            s.open(tmp_path / "nope.pdf")
    finally:
        s.close()


def test_session_open_encrypted(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 2)
    enc = tmp_path / "enc.pdf"
    set_encryption(src, enc, user_password="pw")
    with pytest.raises(PdfPasswordRequired):
        DocumentSession(enc)
    s = DocumentSession(enc, "pw")
    try:
        assert s.page_count == 2
    finally:
        s.close()


def test_session_sync_work(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 2)
    s = DocumentSession(src)
    try:
        from pdf_editor.pdf_engine import rotate_document

        s.push_undo()
        rotate_document(s.doc, 90)
        s.sync_work()
        assert s.work_path is not None
        with open_document(s.work_path) as doc:
            assert doc[0].rotation == 90
    finally:
        s.close()


def test_session_new_file_without_path(tmp_path: Path):
    """未指定路径时构造会话不应报错（界面启动即用该方式）。"""
    s = DocumentSession()
    try:
        assert s.is_open is False
        assert s.page_count == 0
        with pytest.raises(PdfError):
            s.save(tmp_path / "x.pdf")
    finally:
        s.close()


def test_atomic_save_no_leftover_temp_files(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 3)
    out_dir = tmp_path / "outdir"
    out = out_dir / "result.pdf"
    merge_pdfs([src, src], out)
    leftovers = [p.name for p in out_dir.iterdir() if p.name != "result.pdf"]
    assert leftovers == [], f"残留临时文件: {leftovers}"


def test_save_overwrites_existing_file(tmp_path: Path):
    src = make_pdf(tmp_path / "src.pdf", 1)
    target = tmp_path / "existing.pdf"
    make_pdf(target, 5, "OLD")
    rotate_page(src, target, 1, 90)
    assert page_count(target) == 1
    assert "OLD" not in norm(extract_text(target))


def test_concurrent_sessions_are_isolated(tmp_path: Path):
    a = make_pdf(tmp_path / "a.pdf", 1)
    b = make_pdf(tmp_path / "b.pdf", 1)
    sa, sb = DocumentSession(a), DocumentSession(b)
    try:
        from pdf_editor.pdf_engine import insert_blank_document_page

        sa.push_undo()
        insert_blank_document_page(sa.doc)
        assert sa.page_count == 2
        assert sb.page_count == 1
    finally:
        sa.close()
        sb.close()


# ============================================ 健壮性与编码保真（回归）


def test_open_broken_file_raises_pdf_error(tmp_path: Path):
    """损坏文件必须抛出 PdfError，而不是泄漏底层 FileDataError。

    回归：``fitz.open`` 的原始异常曾直接冒泡到界面层导致未捕获崩溃。
    """
    bad = tmp_path / "broken.pdf"
    bad.write_bytes(b"%PDF-1.7\nnope nope nope\n")
    with pytest.raises(PdfError):
        page_count(bad)
    with pytest.raises(PdfError):
        open_document(bad)


def test_open_empty_file_raises_pdf_error(tmp_path: Path):
    empty = tmp_path / "empty.pdf"
    empty.write_bytes(b"")
    with pytest.raises(PdfError):
        page_count(empty)


def test_open_non_pdf_masquerading_as_pdf(tmp_path: Path):
    fake = tmp_path / "fake.pdf"
    fake.write_bytes("纯文本不是 PDF".encode("utf-8") * 20)
    with pytest.raises(PdfError):
        page_count(fake)


def test_open_missing_file_and_directory(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        page_count(tmp_path / "nope.pdf")
    with pytest.raises(PdfError):
        page_count(tmp_path)


def test_is_encrypted_wraps_errors(tmp_path: Path):
    bad = tmp_path / "broken.pdf"
    bad.write_bytes(b"not a pdf at all")
    with pytest.raises(PdfError):
        is_encrypted(bad)


def test_session_open_broken_file_raises_pdf_error(tmp_path: Path):
    bad = tmp_path / "broken.pdf"
    bad.write_bytes(b"%PDF-1.7\ngarbage\n")
    s = DocumentSession()
    try:
        with pytest.raises(PdfError):
            s.open(bad)
    finally:
        s.close()


def test_page_number_spaces_are_searchable(tmp_path: Path):
    """页码中的空格必须能被搜索到（回归：微软雅黑会把空格写成 U+00A0）。"""
    src = make_pdf(tmp_path / "pn.pdf", 3, "P")
    out = tmp_path / "pn_out.pdf"
    add_page_numbers(src, out, pattern="第 {page} 页 / 共 {total} 页", skip_first=True)
    text = extract_text(out)
    assert "\xa0" not in text, f"页码中存在不换行空格: {text!r}"
    assert "第 2 页 / 共 3 页" in text
    hits = search_text(out, "共 3 页")
    assert hits, "页码中的空格无法被搜索到"


def test_watermark_spaces_and_hyphen_are_searchable(tmp_path: Path):
    src = make_pdf(tmp_path / "wm.pdf", 1)
    out = tmp_path / "wm_out.pdf"
    add_text_watermark(src, out, "机密 - 三一重工")
    text = extract_text(out)
    assert "\xa0" not in text, f"水印中存在不换行空格: {text!r}"
    assert "机密 - 三一重工" in text
    assert search_text(out, "机密 - 三一重工"), "水印文本无法被搜索到"


def test_header_footer_spaces_are_searchable(tmp_path: Path):
    src = make_pdf(tmp_path / "hf.pdf", 2)
    out = tmp_path / "hf_out.pdf"
    add_header_footer(src, out, header="三一重工 内部资料", footer="严禁外传 - 2024")
    text = extract_text(out)
    assert "\xa0" not in text, f"页眉页脚中存在不换行空格: {text!r}"
    assert "三一重工 内部资料" in text
    assert "严禁外传 - 2024" in text


def test_font_ascii_roundtrip_guard():
    """当前选用的 CJK 字体必须通过 ASCII 保真校验。"""
    from pdf_editor.pdf_engine import _font_ascii_safe, _font_for

    fnt, name = _font_for("第 1 页")
    assert fnt is not None
    if name == "cjk":
        from pdf_editor.pdf_engine import _cjk_fontfile

        path = _cjk_fontfile()
        assert path is not None
        assert _font_ascii_safe(path) is True


def test_search_case_sensitive_actually_differs(tmp_path: Path):
    """``ignore_case=False`` 必须真正区分大小写（回归：flags 曾静默失效）。"""
    doc = fitz.open()
    for i in range(4):
        page = doc.new_page(width=595, height=842)
        page.insert_text((80, 120), f"Report {i + 1}")
        page.insert_text((80, 160), "hello world" if i % 2 == 0 else "HELLO WORLD")
    src = tmp_path / "case.pdf"
    doc.save(src)
    doc.close()

    loose = sum(h.count for h in search_text(src, "hello"))
    strict = sum(h.count for h in search_text(src, "hello", ignore_case=False))
    assert loose == 4, f"不区分大小写命中数异常: {loose}"
    assert strict == 2, f"区分大小写命中数异常: {strict}"
    upper = sum(h.count for h in search_text(src, "HELLO", ignore_case=False))
    assert upper == 2
    assert sum(h.count for h in search_text(src, "Report", ignore_case=False)) == 4


def test_search_case_sensitive_rects_are_accurate(tmp_path: Path):
    src = make_pdf(tmp_path / "rect.pdf", 1)
    hits = search_text(src, "hello", ignore_case=False)
    assert hits and hits[0].rects
    x0, y0, x1, y1 = hits[0].rects[0]
    assert x1 > x0 and y1 > y0, "命中矩形无效"
    with open_document(src) as doc:
        page_rect = doc[0].rect
        assert 0 <= x0 < x1 <= page_rect.x1 + 1
        assert 0 <= y0 < y1 <= page_rect.y1 + 1


def test_empty_needle_returns_no_hits(tmp_path: Path):
    src = make_pdf(tmp_path / "e.pdf", 1)
    assert search_text(src, "") == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])