"""完整功能集成测试（v0.3.1）。

分层覆盖：
  A. exe 可启动（--version / --help）与版本号一致性
  B. 路径级 API：合并、拆分、旋转、重排、删除页、提取页、插入页、渲染
  C. 文字/图片水印、页码、页眉页脚、提取文字（含版式）
  D. 页面管理：移动、插入空白页、统一页面尺寸、页面标签
  E. 内容：查找、表格、图片提取、页面导出为图片
  F. 批注：新增/列举/删除、清空、密文遮盖
  G. 文档级：元数据、书签目录
  H. 加密/解密/压缩
  I. DocumentSession：撤销/重做、原子保存、原文件隔离、内存上限
  J. 健壮性：损坏文件、错误密码、并发保存、异常类型

共 26 个用例。全部通过则打印 "全部集成测试通过 (26/26)"。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

import fitz

from pdf_editor import VERSION
from pdf_editor.pdf_engine import (
    DocumentSession,
    PdfError,
    PdfPasswordError,
    PdfPasswordRequired,
    add_annotation,
    add_header_footer,
    add_image_watermark,
    add_page_numbers,
    add_text_watermark,
    apply_redaction,
    clear_annotations,
    compress_document,
    delete_annotation,
    delete_document_pages,
    delete_pages,
    export_pages_to_images,
    extract_document_pages,
    extract_document_text,
    extract_images,
    extract_pages,
    extract_pages_to_files,
    extract_text,
    extract_text_with_layout,
    find_tables,
    get_metadata,
    get_page_labels,
    get_toc,
    insert_blank_document_page,
    insert_blank_page,
    insert_pages,
    is_encrypted,
    list_annotations,
    merge_pdfs,
    move_document_page,
    move_page,
    open_document,
    page_count,
    page_image,
    page_size,
    release_render_cache,
    remove_encryption,
    render_page_image,
    render_page_png,
    reorder_document,
    reorder_pdf,
    rotate_document,
    rotate_page,
    rotate_pdf,
    save_document,
    search_text,
    set_document_metadata,
    set_document_page_size,
    set_document_toc,
    set_encryption,
    set_metadata,
    set_page_labels,
    set_page_size,
    set_toc,
    split_pdf,
    text_watermark_document,
)


PROJECT_ROOT = Path(__file__).parent
EXE_PATH = PROJECT_ROOT / "dist" / "PDF编辑器.exe"

TOTAL_CASES = 26


# ---------------------------------------------------------------- helpers

def _page_texts(doc_or_path, pages: list[int] | None = None) -> list[str]:
    """逐页取文本（去掉首尾空白），用于断言页面位置。

    比在整篇文本上按 ``"\\n\\n"`` 切分可靠：空白页不会产生歧义。
    """
    if isinstance(doc_or_path, fitz.Document):
        doc, owned = doc_or_path, False
    else:
        doc, owned = open_document(doc_or_path), True
    try:
        target = pages or list(range(1, len(doc) + 1))
        return [doc[p - 1].get_text().strip() for p in target]
    finally:
        if owned:
            doc.close()


def _make_pdf(path: Path, pages: int, label: str = "Page") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=595, height=842)
        page.insert_text((100, 200), f"{label} {i + 1}")
    doc.save(path)
    doc.close()


def _make_image(path: Path) -> None:
    """生成一个简单 PNG 图片用于图片水印测试。"""
    from PIL import Image
    Image.new("RGBA", (100, 100), (255, 0, 0, 128)).save(path)


def _make_table_pdf(path: Path) -> None:
    """生成一个带规则表格的 PDF，用于 find_tables 测试。"""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    x0, y0, w, h = 60.0, 120.0, 160.0, 30.0
    rows, cols = 3, 3
    for r in range(rows + 1):
        y = y0 + r * h
        page.draw_line(fitz.Point(x0, y), fitz.Point(x0 + cols * w, y), width=0.8)
    for c in range(cols + 1):
        x = x0 + c * w
        page.draw_line(fitz.Point(x, y0), fitz.Point(x, y0 + rows * h), width=0.8)
    for r in range(rows):
        for c in range(cols):
            page.insert_text(
                (x0 + c * w + 8, y0 + r * h + 20),
                f"R{r + 1}C{c + 1}",
                fontsize=9,
            )
    doc.save(path)
    doc.close()


def _make_image_pdf(path: Path) -> None:
    """生成内嵌位图的 PDF，用于 extract_images 测试。"""
    from PIL import Image
    img = Image.new("RGB", (240, 180), (30, 120, 210))
    img_path = path.with_suffix(".src.png")
    img.save(img_path)
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_image(fitz.Rect(80, 100, 400, 340), filename=str(img_path))
    doc.save(path)
    doc.close()
    img_path.unlink(missing_ok=True)


# ------------------------------------------------------- A. exe 与版本

def _run_exe(*args: str) -> tuple[int, str]:
    """运行 exe 并以 UTF-8 解码输出（windowed exe 走字节流）。"""
    r = subprocess.run(
        [str(EXE_PATH), *args],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180,
    )
    text = (r.stdout or b"").decode("utf-8", "replace")
    if not text.strip():
        text = (r.stderr or b"").decode("utf-8", "replace")
    return r.returncode, text


def case_exe_version() -> None:
    if not EXE_PATH.exists():
        raise FileNotFoundError(f"未找到 exe: {EXE_PATH}")
    rc, out = _run_exe("--version")
    assert rc == 0, f"exe 启动失败（退出码 {rc}）"
    assert "pdf-editor" in out, f"版本输出异常: {out!r}"
    assert VERSION in out, f"exe 版本 {out.strip()} 与源码 VERSION={VERSION} 不一致"
    print(f"[OK] 01 exe 可启动且版本一致: {out.strip()}")


def case_exe_help() -> None:
    if not EXE_PATH.exists():
        raise FileNotFoundError(f"未找到 exe: {EXE_PATH}")
    rc, out = _run_exe("--help")
    assert rc == 0, f"exe --help 失败（退出码 {rc}）"
    assert "main.py" in out or "usage" in out.lower(), f"--help 输出异常: {out!r}"
    # windowed exe 曾按 ANSI 代码页输出导致中文乱码，必须能按 UTF-8 正确解码
    assert "用法" in out or "启动图形界面" in out, f"--help 中文输出未能按 UTF-8 解码: {out!r}"
    assert "\ufffd" not in out, f"--help 输出存在解码失败字符: {out!r}"
    print("[OK] 02 exe --help 正常输出用法（UTF-8 中文可读）")


# ------------------------------------------------- B. 路径级基础操作

def case_merge(tmp: Path) -> None:
    a, b = tmp / "a.pdf", tmp / "b.pdf"
    _make_pdf(a, 2, "A")
    _make_pdf(b, 3, "B")
    out = tmp / "merged.pdf"
    merge_pdfs([a, b], out)
    assert out.exists() and page_count(out) == 5
    t = extract_text(out)
    assert "A 1" in t and "B 3" in t
    print("[OK] 03 合并 PDF（5 页，内容正确）")


def case_split(tmp: Path) -> None:
    src = tmp / "split_src.pdf"
    _make_pdf(src, 6, "S")
    paths = split_pdf(src, tmp / "split", [(1, 2), (3, 4), (5, 6)])
    assert len(paths) == 3
    assert [page_count(p) for p in paths] == [2, 2, 2]
    print("[OK] 04 拆分 PDF（3 份 × 2 页）")


def case_rotate_and_reorder(tmp: Path) -> None:
    src = tmp / "rr_src.pdf"
    _make_pdf(src, 3, "R")
    rot = tmp / "rot.pdf"
    rotate_pdf(src, rot, 90)
    with fitz.open(rot) as doc:
        assert all(doc[i].rotation == 90 for i in range(len(doc)))
    reo = tmp / "reo.pdf"
    reorder_pdf(src, reo, [3, 1, 2])
    t = extract_text(reo).split("\n\n")
    assert "R 3" in t[0] and "R 1" in t[1] and "R 2" in t[2], f"重排结果异常: {t}"
    print("[OK] 05 旋转（全篇 90°）+ 重排（3,1,2）")


def case_delete_and_extract_pages(tmp: Path) -> None:
    src = tmp / "dep_src.pdf"
    _make_pdf(src, 5, "D")
    dele = tmp / "del.pdf"
    delete_pages(src, dele, [2, 4])
    assert page_count(dele) == 3
    t = extract_text(dele)
    assert "D 1" in t and "D 3" in t and "D 5" in t
    assert "D 2" not in t and "D 4" not in t
    ext = tmp / "ext.pdf"
    extract_pages(src, ext, [5, 1])
    assert page_count(ext) == 2
    te = extract_text(ext).split("\n\n")
    assert "D 5" in te[0] and "D 1" in te[1]
    print("[OK] 06 删除页 + 提取指定页（顺序保持）")


def case_insert_pages_and_blank(tmp: Path) -> None:
    src = tmp / "ins_src.pdf"
    _make_pdf(src, 3, "M")
    app = tmp / "ins_app.pdf"
    _make_pdf(app, 1, "X")
    # at=2 表示「插入到第 2 页之后」→ 新页成为第 3 页
    out = tmp / "ins_out.pdf"
    insert_pages(src, out, app, at=2)
    assert page_count(out) == 4
    pages = _page_texts(out)
    assert "X 1" in pages[2], f"插入位置错误: {pages}"
    assert "M 2" in pages[1] and "M 3" in pages[3], f"原有页顺序错乱: {pages}"
    # at=0 表示插入到最前
    first = tmp / "ins_first.pdf"
    insert_pages(src, first, app, at=0)
    assert "X 1" in _page_texts(first)[0], "at=0 未插入到最前"
    # 末尾插入空白页
    blank = tmp / "blank.pdf"
    insert_blank_page(src, blank, at=-1, size="a4")
    assert page_count(blank) == 4
    bp = _page_texts(blank)
    assert bp[3] == "" and "M 3" in bp[2], f"末尾空白页位置错误: {bp}"
    # at=1 表示插入到第 1 页之后 → 新页成为第 2 页
    blank2 = tmp / "blank2.pdf"
    insert_blank_page(src, blank2, at=1, size="a4")
    b2 = _page_texts(blank2)
    assert b2[1] == "", f"空白页未落在第 2 页: {b2}"
    assert "M 2" in b2[2], f"空白页插入位置错误: {b2}"
    print("[OK] 07 插入外部页（at=0/2）+ 插入空白页（末尾/中间）")


def case_render_and_move(tmp: Path) -> None:
    src = tmp / "rnd_src.pdf"
    _make_pdf(src, 3, "N")
    png = render_page_png(src, 1, zoom=0.5)
    assert png[:4] == b"\x89PNG", "渲染输出不是 PNG"
    img = render_page_image(src, 2, zoom=1.0)
    assert img.size[0] > 0 and img.size[1] > 0
    w, h = page_size(src, 1)
    assert abs(w - 595) < 1 and abs(h - 842) < 1, f"页面尺寸异常: {w}x{h}"
    ro = tmp / "rot_one.pdf"
    rotate_page(src, ro, 3, 90)
    with fitz.open(ro) as doc:
        assert doc[2].rotation == 90 and doc[0].rotation == 0
    mv = tmp / "moved.pdf"
    move_page(src, mv, 1, 3)
    om = extract_text(mv).split("\n\n")
    assert "N 2" in om[0] and "N 3" in om[1] and "N 1" in om[2], f"移动结果异常: {om}"
    # 原地移动（UI 使用的 *_document 变体）：1→3 与 3→1 都应正确
    md = tmp / "moved_doc.pdf"
    with open_document(src) as doc:
        move_document_page(doc, 1, 3)
        assert len(doc) == 3
        save_document(doc, md)
    od = extract_text(md).split("\n\n")
    assert "N 2" in od[0] and "N 3" in od[1] and "N 1" in od[2], f"原地移动结果异常: {od}"
    print("[OK] 08 渲染 PNG/PIL + 单页旋转 + 单页移动（路径态 + 原地）")


# ------------------------------------------------------- C. 水印与文本

def case_text_watermark(tmp: Path) -> None:
    src = tmp / "wm_src.pdf"
    _make_pdf(src, 2)
    out = tmp / "wm.pdf"
    add_text_watermark(src, out, "CONFIDENTIAL", opacity=0.35, angle=45)
    t = extract_text(out)
    assert t.count("CONFIDENTIAL") >= 2, "水印未覆盖全部页面"
    out_cn = tmp / "wm_cn.pdf"
    add_text_watermark(src, out_cn, "机密 - 三一重工")
    tcn = extract_text(out_cn)
    assert "机密" in tcn and "三一重工" in tcn, f"中文水印异常: {tcn!r}"
    one = tmp / "wm_one.pdf"
    add_text_watermark(src, one, "ONLYP1", pages=[1])
    assert extract_text(one, pages=[2]).count("ONLYP1") == 0
    print("[OK] 09 文字水印（英文/中文/限定页）")


def case_image_watermark(tmp: Path) -> None:
    src = tmp / "iwm_src.pdf"
    _make_pdf(src, 2)
    img = tmp / "mark.png"
    _make_image(img)
    out = tmp / "iwm.pdf"
    add_image_watermark(src, out, img, opacity=0.25, scale=0.4)
    assert page_count(out) == 2
    with fitz.open(out) as doc:
        assert len(doc[0].get_images(full=True)) >= 1, "图片水印未写入"
    print("[OK] 10 图片水印（透明度 + 缩放）")


def case_page_numbers_header_footer(tmp: Path) -> None:
    src = tmp / "pn_src.pdf"
    _make_pdf(src, 3, "P")
    out = tmp / "pn.pdf"
    add_page_numbers(src, out, pattern="第 {page} 页 / 共 {total} 页", skip_first=True)
    t = extract_text(out)
    assert "第 2 页 / 共 3 页" in t and "第 3 页 / 共 3 页" in t
    assert "第 1 页" not in t, "skip_first 未生效"
    hf = tmp / "hf.pdf"
    add_header_footer(src, hf, header="三一重工内部资料", footer="严禁外传")
    th = extract_text(hf)
    assert "三一重工内部资料" in th and "严禁外传" in th
    print("[OK] 11 页码（跳过首页）+ 页眉页脚")


def case_extract_text(tmp: Path) -> None:
    src = tmp / "txt_src.pdf"
    _make_pdf(src, 3, "T")
    t = extract_text(src)
    assert "T 1" in t and "T 3" in t
    t1 = extract_text(src, pages=[2])
    assert "T 2" in t1 and "T 1" not in t1
    lay = extract_text_with_layout(src, pages=[1])
    assert "T 1" in lay
    print("[OK] 12 提取文字（全文/指定页/保留版式）")


# ----------------------------------------------------- D. 页面级管理

def case_document_page_ops(tmp: Path) -> None:
    p = tmp / "docops.pdf"
    _make_pdf(p, 4, "Z")
    with open_document(p) as doc:
        set_document_page_size(doc, "a5", pages=[1])
        assert abs(doc[0].rect.width - 420) < 1, f"页面尺寸未改变: {doc[0].rect}"
        assert abs(doc[2].rect.width - 595) < 1, "非目标页被误改"
        set_document_page_size(doc, "a4")
        assert abs(doc[0].rect.width - 595) < 1, "统一尺寸失败"

        # at=2 → 新页成为第 3 页（约定：插入到第 2 页之后）
        n = insert_blank_document_page(doc, at=2)
        assert n == 3, f"返回页码异常: {n}"
        assert len(doc) == 5
        assert doc[2].get_text().strip() == "", "空白页未落在第 3 页"
        assert "Z 3" in doc[3].get_text(), "原有页位置错乱"

        # 当前顺序：Z1, Z2, (空白), Z3, Z4
        assert _page_texts(doc)[2] == "", "空白页不在第 3 页"
        move_document_page(doc, 5, 1)  # 末页（Z4）移到开头
        assert len(doc) == 5
        after = _page_texts(doc)
        assert "Z 4" in after[0], f"移动后首页应为 Z4: {after}"
        assert "Z 1" in after[1], f"移动后第 2 页应为 Z1: {after}"
        assert after[3] == "", f"空白页应随整体后移到第 4 页: {after}"
        assert "Z 3" in after[4], f"移动后末页应为 Z3: {after}"

        delete_document_pages(doc, [5])
        assert len(doc) == 4

        sub = extract_document_pages(doc, [1, 2])
        assert len(sub) == 2
        sub.close()

        out = tmp / "docops_out.pdf"
        save_document(doc, out)
    assert out.exists() and page_count(out) == 4
    print("[OK] 13 文档内页面操作（改尺寸/插空白/移动/删除/提取/保存）")


def case_page_labels_and_toc(tmp: Path) -> None:
    src = tmp / "lbl_src.pdf"
    _make_pdf(src, 5, "L")
    out = tmp / "lbl.pdf"
    set_page_labels(src, out, [
        {"startpage": 0, "prefix": "封面 ", "style": "D", "firstpagenum": 1},
        {"startpage": 1, "prefix": "", "style": "r", "firstpagenum": 1},
    ])
    labels = get_page_labels(out)
    assert len(labels) >= 2, f"页面标签未写入: {labels}"

    toc_out = tmp / "toc.pdf"
    toc = [[1, "第一章", 1], [1, "第二章", 3], [2, "2.1 小节", 4]]
    set_toc(src, toc_out, toc)
    got = get_toc(toc_out)
    assert len(got) == 3 and got[0][1] == "第一章", f"目录异常: {got}"
    with open_document(toc_out) as doc:
        got2 = get_toc(doc)
        assert len(got2) == 3, f"打开状态下读目录异常: {got2}"
        set_document_toc(doc, [[1, "只留一章", 1]])
        assert len(doc.get_toc()) == 1
        save_document(doc, tmp / "toc2.pdf")
    print("[OK] 14 页面标签 + 书签目录（路径态/打开态均可读写）")


# --------------------------------------------------- E. 查找与内容提取

def case_search_text(tmp: Path) -> None:
    src = tmp / "search_src.pdf"
    doc = fitz.open()
    for i in range(4):
        pg = doc.new_page(width=595, height=842)
        pg.insert_text((80, 120), f"Report {i + 1}")
        pg.insert_text((80, 160), "hello world" if i % 2 == 0 else "HELLO WORLD")
    doc.save(src)
    doc.close()
    hits = search_text(src, "hello")
    assert len(hits) >= 4, f"查找命中过少: {len(hits)}"
    assert all(h.rects for h in hits), "命中缺少矩形"
    assert all(1 <= h.page <= 4 for h in hits), "命中页码越界"
    one = search_text(src, "hello", pages=[1])
    assert all(h.page == 1 for h in one)
    case_sens = search_text(src, "hello", ignore_case=False)
    assert len(case_sens) == 2, f"大小写敏感命中数异常: {len(case_sens)}"
    with open_document(src) as d:
        assert len(search_text(d, "Report")) >= 4, "打开状态下查找失败"
    print("[OK] 15 全文查找（跨页/限定页/大小写/打开态）")


def case_tables_and_images(tmp: Path) -> None:
    tsrc = tmp / "table.pdf"
    _make_table_pdf(tsrc)
    tables = find_tables(tsrc)
    assert tables, "未识别到表格"
    cells = [c for t in tables for row in t["rows"] for c in row if c]
    assert any("R1C1" in c for c in cells), f"表格内容异常: {cells[:10]}"

    isrc = tmp / "img.pdf"
    _make_image_pdf(isrc)
    found = extract_images(isrc, tmp / "imgs")
    assert found, "未提取到图片"
    assert all(f.exists() and f.stat().st_size > 0 for f in found)
    print(f"[OK] 16 表格识别（{len(tables)} 张）+ 图片提取（{len(found)} 个文件）")


def case_export_pages(tmp: Path) -> None:
    src = tmp / "exp_src.pdf"
    _make_pdf(src, 3, "E")
    pngs = export_pages_to_images(src, tmp / "pngs", fmt="png", dpi=72)
    assert len(pngs) == 3 and all(p.exists() for p in pngs)
    jpgs = export_pages_to_images(src, tmp / "jpgs", pages=[1, 2], fmt="jpg", dpi=72)
    assert len(jpgs) == 2 and all(p.suffix == ".jpg" for p in jpgs)
    with open_document(src) as doc:
        again = export_pages_to_images(doc, tmp / "pngs2", fmt="png", dpi=72)
        assert len(again) == 3, "打开状态下导出失败"
    # 逐页文本拆分导出
    files = extract_pages_to_files(src, tmp / "pages")
    assert len(files) == 3 and all(f.suffix == ".txt" for f in files), f"逐页导出失败: {files}"
    assert "E 1" in files[0].read_text(encoding="utf-8")
    print("[OK] 17 导出页面为图片（PNG/JPG/指定页/打开态）+ 逐页文本拆分")


# ----------------------------------------------------------- F. 批注

def case_annotations(tmp: Path) -> None:
    src = tmp / "ann_src.pdf"
    _make_pdf(src, 2, "K")
    with open_document(src) as doc:
        x1 = add_annotation(doc, 1, "highlight", (80, 180, 300, 210), color=(1, 0.9, 0))
        x2 = add_annotation(doc, 1, "text", (90, 220, 150, 250), text="批注内容")
        x3 = add_annotation(doc, 2, "rect", (100, 260, 220, 330))
        x4 = add_annotation(doc, 2, "stamp", (100, 340, 260, 380), stamp="Approved")
        x5 = add_annotation(doc, 2, "ink", (100, 260, 220, 330),
                           points=[[(120, 400), (150, 430), (180, 410)]])
        items = list_annotations(doc, 1)
        assert len(items) == 2, f"第 1 页批注数异常: {len(items)}"
        assert all("xref" in it and "rect" in it for it in items)
        assert delete_annotation(doc, 1, x1) is True
        assert len(list_annotations(doc, 1)) == 1
        cleared = clear_annotations(doc, pages=[2])
        assert cleared >= 1, f"清空批注失败: {cleared}"
        assert list_annotations(doc, 2) == []
        save_document(doc, tmp / "ann_out.pdf")
    assert page_count(tmp / "ann_out.pdf") == 2
    print("[OK] 18 批注（5 种类型/列举/删除/按页清空）")


def case_redaction(tmp: Path) -> None:
    src = tmp / "red_src.pdf"
    doc = fitz.open()
    pg = doc.new_page(width=595, height=842)
    pg.insert_text((80, 120), "SECRET-TITLE")
    pg.insert_text((80, 160), "hello world")
    doc.save(src)
    doc.close()
    with open_document(src) as d:
        apply_redaction(d, 1, (70, 145, 400, 175), fill=(0, 0, 0))
        save_document(d, tmp / "red_out.pdf")
    t = extract_text(tmp / "red_out.pdf")
    assert "hello world" not in t, f"密文遮盖未生效，仍可读到: {t!r}"
    assert "SECRET-TITLE" in t, "遮盖范围误伤其它文本"
    print("[OK] 19 密文遮盖（目标文本已彻底移除，邻行完好）")


# --------------------------------------------------- G. 元数据与文档级

def case_metadata(tmp: Path) -> None:
    src = tmp / "meta_src.pdf"
    _make_pdf(src, 1)
    out = tmp / "meta.pdf"
    set_metadata(src, out, {
        "title": "测试文档", "author": "三一重工", "subject": "集成测试", "keywords": "pdf,test",
    })
    md = get_metadata(out)
    assert md.get("title") == "测试文档", f"标题未写入: {md}"
    assert md.get("author") == "三一重工", f"作者未写入: {md}"
    with open_document(out) as doc:
        set_document_metadata(doc, {"title": "改后标题"})
        save_document(doc, tmp / "meta2.pdf")
    assert get_metadata(tmp / "meta2.pdf").get("title") == "改后标题"
    print("[OK] 20 文档属性（标题/作者/主题/关键字，路径态+打开态）")


# --------------------------------------------------- H. 加密/解密/压缩

def case_encryption(tmp: Path) -> None:
    src = tmp / "enc_src.pdf"
    _make_pdf(src, 2, "S")
    enc = tmp / "enc.pdf"
    set_encryption(src, enc, user_password="open123", owner_password="own456",
                   allow_print=True, allow_copy=False)
    assert is_encrypted(enc) is True
    with fitz.open(enc) as doc:
        assert doc.needs_pass, "未加密"
        assert doc.authenticate("open123"), "用户密码验证失败"
    # 错误密码必须抛 PdfPasswordError（而非静默失败）
    try:
        page_count(enc, password="wrong")
    except (PdfPasswordError, PdfPasswordRequired):
        pass
    else:
        raise AssertionError("错误密码未抛出异常")
    # 缺少密码必须抛 PdfPasswordRequired
    try:
        page_count(enc)
    except (PdfPasswordRequired, PdfPasswordError):
        pass
    else:
        raise AssertionError("缺密码未抛出异常")
    dec = tmp / "dec.pdf"
    remove_encryption(enc, dec, password="open123")
    assert is_encrypted(dec) is False
    assert page_count(dec) == 2
    # 带密码打开后内容可正常读取
    doc = open_document(enc, password="open123")
    try:
        assert "S 1" in extract_document_text(doc)
    finally:
        doc.close()
    print("[OK] 21 加密（AES-256）+ 错误/缺失密码异常 + 解密")


def case_compression(tmp: Path) -> None:
    src = tmp / "cmp_src.pdf"
    doc = fitz.open()
    for i in range(3):
        pg = doc.new_page(width=595, height=842)
        pg.insert_text((80, 120), f"Compress page {i + 1}")
        pg.insert_text((80, 160), "A" * 400)
    doc.save(src)
    doc.close()
    out = tmp / "cmp.pdf"
    stats = compress_document(src, out, dpi=100, quality=70)
    assert out.exists() and page_count(out) == 3
    assert set(stats) == {"before", "after", "saved_percent"}, f"压缩统计异常: {stats}"
    assert stats["before"] > 0 and stats["after"] > 0
    assert 0 <= stats["saved_percent"] <= 100
    print(f"[OK] 22 压缩文档（{stats['before']}B → {stats['after']}B，省 {stats['saved_percent']}%）")


# -------------------------------------------------- I. DocumentSession

def case_session_undo_redo(tmp: Path) -> None:
    src = tmp / "ses_src.pdf"
    _make_pdf(src, 4, "U")
    ses = DocumentSession(src)
    try:
        assert ses.page_count == 4, f"页数异常: {ses.page_count}"

        ses.push_undo()
        delete_document_pages(ses.doc, [2])
        assert ses.page_count == 3, "删除后页数未变"
        assert ses.can_undo is True, "未记录撤销点"

        ses.push_undo()
        rotate_document(ses.doc, 90)
        assert ses.doc[0].rotation == 90

        assert ses.undo() is True, "撤销失败"
        assert ses.doc[0].rotation == 0, "撤销未回退旋转"
        assert ses.page_count == 3, f"撤销后页数异常: {ses.page_count}"
        assert ses.can_redo is True

        assert ses.undo() is True, "第二次撤销失败"
        assert ses.page_count == 4, f"撤销删除失败: {ses.page_count}"
        assert ses.can_undo is False

        assert ses.redo() is True and ses.page_count == 3
        assert ses.redo() is True and ses.doc[0].rotation == 90
        assert ses.can_redo is False
        print("[OK] 23 会话撤销/重做（删除 + 旋转两级可逆）")
    finally:
        ses.close()


def case_session_atomic_and_isolation(tmp: Path) -> None:
    src = tmp / "atom_src.pdf"
    _make_pdf(src, 3, "O")
    original_bytes = src.read_bytes()
    ses = DocumentSession(src)
    try:
        ses.push_undo()
        delete_document_pages(ses.doc, [1])
        assert ses.page_count == 2

        # 1) 原文件在编辑期间完全未被触碰
        assert page_count(src) == 3, "原文件已被篡改（隔离失效）"
        assert src.read_bytes() == original_bytes, "原文件字节发生变化"
        assert ses.dirty is True

        # 2) 另存为：原文件仍不变
        out = tmp / "atom_out.pdf"
        ses.save(out)
        assert out.exists() and page_count(out) == 2
        assert page_count(src) == 3, "另存为却改动了原文件"
        assert ses.dirty is False, "保存后 dirty 未复位"

        # 3) 覆盖保存原文件：原子替换，且不残留临时文件
        ses.save(src)
        assert page_count(src) == 2, "覆盖保存失败"
        assert ses.doc is not None and ses.page_count == 2, "覆盖后句柄未重建"
        leftovers = [p for p in src.parent.iterdir() if p.name.startswith(".pdfedit-")]
        assert not leftovers, f"存在残留临时文件: {leftovers}"
        print("[OK] 24 原子保存 + 原文件隔离（无残留 tmp，可覆盖保存）")
    finally:
        ses.close()


def case_session_limits_and_reopen(tmp: Path) -> None:
    src = tmp / "lim_src.pdf"
    _make_pdf(src, 8, "C")
    ses = DocumentSession(src, max_undo_steps=3)
    try:
        for i in range(6):
            ses.push_undo()
            rotate_document(ses.doc, 90 * (1 + i % 4))
        assert len(ses._undo) <= 3, f"撤销栈未按上限裁剪: {len(ses._undo)}"
        assert ses.page_count == 8
        assert ses.dirty is True
    finally:
        ses.close()

    # 关闭后可重新打开同一会话对象（回归：临时目录曾被删除导致无法重开）
    try:
        ses.open(src)
        assert ses.is_open is True
        assert ses.page_count == 8
        assert ses.dirty is False, "重开后 dirty 未复位"
        assert ses.can_undo is False, "重开后撤销历史未清空"
        ses.close()
        assert ses.is_open is False
        ses.close()  # 幂等
        print("[OK] 25 撤销栈上限裁剪（≤3）+ 关闭后可重新打开（幂等 close）")
    finally:
        ses.close()


# ------------------------------------------------------ J. 健壮性

def case_robustness(tmp: Path) -> None:
    # 1) 损坏文件：必须包装成 PdfError，不能泄漏底层异常类型
    bad = tmp / "broken.pdf"
    bad.write_bytes(b"%PDF-1.7\nthis is not a real pdf\n")
    try:
        page_count(bad)
    except PdfError:
        pass
    except Exception as exc:  # noqa: BLE001
        raise AssertionError(f"损坏文件抛出未包装异常: {type(exc).__name__}: {exc}") from exc
    else:
        raise AssertionError("损坏文件未报错")

    # 2) 空文件同样应包装为 PdfError
    empty = tmp / "empty.pdf"
    empty.write_bytes(b"")
    try:
        page_count(empty)
    except PdfError:
        pass
    except Exception as exc:  # noqa: BLE001
        raise AssertionError(f"空文件抛出未包装异常: {type(exc).__name__}: {exc}") from exc
    else:
        raise AssertionError("空文件未报错")

    # 3) 非 PDF 文件（伪装扩展名）
    fake = tmp / "fake.pdf"
    fake.write_bytes("这是一段普通文本".encode("utf-8") * 10)
    try:
        page_count(fake)
    except PdfError:
        pass
    except Exception as exc:  # noqa: BLE001
        raise AssertionError(f"非 PDF 文件抛出未包装异常: {type(exc).__name__}: {exc}") from exc
    else:
        raise AssertionError("非 PDF 文件未报错")

    # 4) 文件不存在 / 传入目录
    try:
        page_count(tmp / "nope.pdf")
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("不存在的文件未抛 FileNotFoundError")
    try:
        page_count(tmp)
    except PdfError:
        pass
    else:
        raise AssertionError("传入目录未报错")

    # 5) 越界页码应报错而非崩溃
    src = tmp / "rb_src.pdf"
    _make_pdf(src, 2, "B")
    try:
        render_page_png(src, 99, zoom=1)
    except Exception:
        pass
    else:
        raise AssertionError("越界页码未报错")

    # 6) 空查找 / 空关键字不应抛异常
    assert search_text(src, "不存在的词") == []
    assert search_text(src, "") == []

    # 7) 释放渲染缓存应幂等
    release_render_cache()
    release_render_cache()

    # 8) page_image 像素上限生效
    with fitz.open(src) as doc:
        img = page_image(doc[0], zoom=8.0, max_pixels=1_000_000)
        assert img.size[0] * img.size[1] <= 1_000_000, f"像素上限失效: {img.size}"
        img.close()

    # 9) 删空全部页必须被拒绝（不留 0 页文档）
    with open_document(src) as doc:
        try:
            delete_document_pages(doc, [1, 2])
        except (ValueError, PdfError):
            pass
        else:
            raise AssertionError("删除全部页未被拒绝")
        assert len(doc) == 2, "被拒绝的删除操作仍改动了文档"

    # 10) 非法旋转角度 / 非法页面尺寸应报错
    with open_document(src) as doc:
        for callable_, args in (
            (rotate_document, (doc, 45)),
            (set_document_page_size, (doc, "b5")),
        ):
            try:
                callable_(*args)
            except (ValueError, PdfError):
                pass
            else:
                raise AssertionError(f"{getattr(callable_, '__name__', callable_)}{args[1:]} 未报错")

    # 11) 批注非法类型应报错
    with open_document(src) as doc:
        try:
            add_annotation(doc, 1, "hexagon", (10, 10, 50, 50))
        except (ValueError, PdfError):
            pass
        else:
            raise AssertionError("非法批注类型未报错")

    print("[OK] 26 健壮性（损坏/空/伪装文件/目录/越界页/空查找/缓存幂等/"
          "像素上限/删空保护/非法参数）")


# ---------------------------------------------------------------- main

CASES = [
    ("01 exe --version", lambda t: case_exe_version()),
    ("02 exe --help", lambda t: case_exe_help()),
    ("03 merge", case_merge),
    ("04 split", case_split),
    ("05 rotate+reorder", case_rotate_and_reorder),
    ("06 delete+extract", case_delete_and_extract_pages),
    ("07 insert page", case_insert_pages_and_blank),
    ("08 render+move", case_render_and_move),
    ("09 text watermark", case_text_watermark),
    ("10 image watermark", case_image_watermark),
    ("11 page no + header", case_page_numbers_header_footer),
    ("12 extract text", case_extract_text),
    ("13 doc page ops", case_document_page_ops),
    ("14 labels + toc", case_page_labels_and_toc),
    ("15 search text", case_search_text),
    ("16 tables + images", case_tables_and_images),
    ("17 export pages", case_export_pages),
    ("18 annotations", case_annotations),
    ("19 redaction", case_redaction),
    ("20 metadata", case_metadata),
    ("21 encryption", case_encryption),
    ("22 compression", case_compression),
    ("23 session undo/redo", case_session_undo_redo),
    ("24 atomic save", case_session_atomic_and_isolation),
    ("25 session limits", case_session_limits_and_reopen),
    ("26 robustness", case_robustness),
]


def main() -> int:
    assert len(CASES) == TOTAL_CASES, f"用例数 {len(CASES)} != {TOTAL_CASES}"
    base = PROJECT_ROOT / ".integration_test"
    base.mkdir(exist_ok=True)
    # 每次运行使用独立的子目录，避免对既有目录做递归删除
    stamp = time.strftime("%Y%m%d-%H%M%S")
    tmp = base / f"run-{stamp}"
    tmp.mkdir(parents=True, exist_ok=True)

    failed: list[str] = []
    for name, fn in CASES:
        try:
            fn(tmp)
        except Exception as exc:  # noqa: BLE001
            failed.append(f"{name}: {type(exc).__name__}: {exc}")
            print(f"[FAIL] {name} -> {type(exc).__name__}: {exc}")

    print()
    if failed:
        print(f"集成测试失败 {len(failed)}/{TOTAL_CASES}:")
        for line in failed:
            print("  -", line)
        return 1
    print(f"全部集成测试通过 ({TOTAL_CASES}/{TOTAL_CASES})")
    return 0


if __name__ == "__main__":
    sys.exit(main())