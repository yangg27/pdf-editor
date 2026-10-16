"""v0.3.0 引擎全功能冒烟验证（真实调用，逐项打印结果）。

用法：
    .venv-sys/Scripts/python.exe tools_smoke_engine.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pymupdf as fitz
from PIL import Image

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pdf_editor import pdf_engine as E  # noqa: E402


def mk(d: Path, name: str, pages: int, label: str = "P") -> Path:
    p = d / name
    doc = fitz.open()
    for i in range(pages):
        pg = doc.new_page(width=595, height=842)
        pg.insert_text((72, 100), f"{label}{i + 1} hello world",
                       fontname="china-s", fontsize=14)
    doc.save(p)
    doc.close()
    return p


def norm(text: str) -> str:
    """PDF 文本抽取中空格可能是不断行空格，统一成普通空格便于断言。"""
    return text.replace("\xa0", " ")


def main() -> int:
    d = Path(tempfile.mkdtemp(prefix="pdf-smoke-"))
    src = mk(d, "s.pdf", 4, "页")
    a = mk(d, "a.pdf", 2, "A")

    print("1  page_count:", E.page_count(src))
    print("2  page_size:", E.page_size(src, 1))
    print("3  render png magic:", E.render_page_png(src, 1, zoom=0.5)[:4])
    im = E.render_page_image(src, 1, zoom=1.0)
    print("4  render image:", im.size, im.mode)
    imbig = E.render_page_image(src, 1, zoom=6.0, max_pixels=1_000_000)
    print("5  max_pixels cap:", imbig.size)

    s = E.DocumentSession(src)
    print("6  session open:", s.page_count, s.source.name, s.work_path.exists())
    print("7  source not copied over:", src.read_bytes()[:5] == b"%PDF-")
    s.push_undo()
    E.insert_blank_document_page(s.doc, at=1)
    print("8  insert blank -> pages:", s.page_count, "| can_undo:", s.can_undo, "| dirty:", s.dirty)
    s.undo()
    print("9  undo -> pages:", s.page_count)
    s.redo()
    print("10 redo -> pages:", s.page_count)
    out = d / "saved.pdf"
    s.save(out)
    print("11 session save:", out.exists(), E.page_count(out))
    tmpdir = s._tmpdir
    s.close()
    print("12 temp cleanup:", tmpdir is None or not tmpdir.exists())

    m = d / "m.pdf"
    E.merge_pdfs([a, mk(d, "b.pdf", 3, "B")], m)
    print("13 merge:", E.page_count(m))
    print("14 split:", [E.page_count(x) for x in E.split_pdf(m, d / "split", [(1, 2), (3, 5)])])

    r = d / "r.pdf"
    E.rotate_pdf(src, r, 90, [1])
    print("15 rotate:", fitz.open(r)[0].rotation)
    ro = d / "ro.pdf"
    E.reorder_pdf(src, ro, [4, 3, 2, 1])
    print("16 reorder head:", E.extract_text(ro).split("\n")[0].strip())
    de = d / "del.pdf"
    E.delete_pages(src, de, [2, 3])
    print("17 delete:", E.page_count(de))
    ex = d / "ex.pdf"
    E.extract_pages(src, ex, [4, 1])
    print("18 extract:", E.page_count(ex))
    ins = d / "ins.pdf"
    E.insert_pages(src, ins, a, at=2)
    print("19 insert at 2:", E.page_count(ins))
    mv = d / "mv.pdf"
    E.move_page(src, mv, 1, 4)
    print("20 move page 1->4:", E.extract_text(mv).split("\n")[0].strip())
    ib = d / "ib.pdf"
    E.insert_pages(src, ib, a, at=99)
    print("21 insert beyond end (old bug):", E.page_count(ib))
    bl = d / "bl.pdf"
    E.insert_blank_page(src, bl, at=-1, size="a4")
    print("22 blank page:", E.page_count(bl), E.page_size(bl, 5))
    sz = d / "sz.pdf"
    E.set_page_size(src, sz, "letter")
    print("23 set page size:", E.page_size(sz, 1))

    wm = d / "wm.pdf"
    E.add_text_watermark(src, wm, "机密 - 三一重工", angle=45)
    tw = E.extract_text(wm)
    print("24 cjk watermark:", "机密" in tw, "三一重工" in tw)
    wm2 = d / "wm2.pdf"
    E.add_text_watermark(src, wm2, "DRAFT", angle=30, opacity=0.4, color=(1, 0, 0))
    print("25 latin watermark:", "DRAFT" in E.extract_text(wm2))

    logo = d / "logo.png"
    Image.new("RGBA", (200, 200), (200, 30, 30, 255)).save(logo)
    iw = d / "iw.pdf"
    E.add_image_watermark(src, iw, logo, opacity=0.35, scale=0.5, angle=15)
    print("26 image watermark embedded:", len(fitz.open(iw)[0].get_images()) >= 1)

    pn = d / "pn.pdf"
    E.add_page_numbers(src, pn, pattern="- {page} -")
    print("27 page numbers:", "- 2 -" in norm(E.extract_text(pn)))
    hf = d / "hf.pdf"
    E.add_header_footer(src, hf, header="{name}", footer="第 {page} 页")
    hf_text = norm(E.extract_text(hf))
    print("28 header/footer:", "第 3 页" in hf_text and "hf.pdf" in hf_text)

    print("29 extract text:", len(E.extract_text(src)) > 0)
    print("30 layout text:", "第 1 页" in E.extract_text_with_layout(src))
    print("31 search:", [(h.page, h.count) for h in E.search_text(src, "hello")])
    print("32 txt export:", len(E.extract_pages_to_files(src, d / "txt")))
    pimgs = E.export_pages_to_images(src, d / "imgs", fmt="jpg", dpi=100)
    print("33 page->jpg:", len(pimgs), pimgs[0].stat().st_size > 500)
    print("34 find_tables:", E.find_tables(src))
    print("35 extract_images:", len(E.extract_images(iw, d / "extimg")))

    s2 = E.DocumentSession(src)
    E.add_annotation(s2.doc, 1, "highlight", (60, 80, 300, 120), text="重点")
    E.add_annotation(s2.doc, 1, "underline", (60, 80, 300, 120))
    E.add_annotation(s2.doc, 1, "strikeout", (60, 80, 300, 120))
    E.add_annotation(s2.doc, 1, "squiggly", (60, 80, 300, 120))
    E.add_annotation(s2.doc, 1, "text", (400, 80, 420, 100), text="便签")
    E.add_annotation(s2.doc, 1, "freetext", (60, 700, 300, 750), text="文本框注释")
    E.add_annotation(s2.doc, 1, "rect", (60, 600, 200, 660), stroke=(1, 0, 0))
    E.add_annotation(s2.doc, 1, "circle", (250, 600, 400, 660), stroke=(0, 0.5, 1))
    E.add_annotation(s2.doc, 1, "stamp", (400, 700, 520, 780), stamp="approved")
    E.add_annotation(s2.doc, 1, "ink", (0, 0, 0, 0),
                     points=[[[100, 500], [150, 520], [200, 510]]])
    lst = E.list_annotations(s2.doc, 1)
    print("36 annotations:", len(lst), [x["type"] for x in lst])
    print("37 delete annotation:", E.delete_annotation(s2.doc, 1, lst[0]["xref"]),
          "->", len(E.list_annotations(s2.doc, 1)))
    ao = d / "annot.pdf"
    s2.save(ao)
    t2 = E.DocumentSession(ao)
    saved_annots = E.list_annotations(t2.doc, 1)
    contents = [a["content"] for a in saved_annots]
    page_text = t2.doc[0].get_text()
    print("38 annot persisted:", len(saved_annots),
          "| comment kept:", "重点" in contents,
          "| freetext is real text:", "文本框注释" in page_text)
    t2.close()
    print("39 clear annotations:", E.clear_annotations(s2.doc))
    s2.close()

    s3 = E.DocumentSession(src)
    E.apply_redaction(s3.doc, 1, (60, 85, 250, 110))
    red = d / "redact.pdf"
    s3.save(red)
    t3 = E.DocumentSession(red)
    p1 = t3.doc[0].get_text()
    t3.close()
    print("40 redaction removed page-1 text:", "hello" not in p1)
    s3.close()

    print("41 metadata:", E.get_metadata(src)["format"])
    sm = d / "meta.pdf"
    E.set_metadata(src, sm, {"title": "测试标题", "author": "三一", "keywords": "a,b"})
    print("42 metadata written:", E.get_metadata(sm)["title"], "/", E.get_metadata(sm)["author"])

    s4 = E.DocumentSession(src)
    E.add_bookmark(s4.doc, "第一章", 1)
    E.add_bookmark(s4.doc, "第二章", 3)
    print("43 bookmarks:", len(s4.doc.get_toc()))
    tb = d / "toc.pdf"
    s4.save(tb)
    print("44 toc persisted:", E.get_toc(tb))
    print("45 delete bookmark ->", len(E.delete_bookmark(s4.doc, 0)))
    s4.close()
    pl = d / "labels.pdf"
    E.set_page_labels(src, pl, [{"startpage": 0, "prefix": "A-", "style": "D", "firstpagenum": 1}])
    print("46 page labels:", E.get_page_labels(pl))

    print("47 compress:", E.compress_document(src, d / "cmp.pdf", dpi=120))
    enc = d / "enc.pdf"
    E.set_encryption(src, enc, user_password="abc", owner_password="own")
    print("48 is_encrypted:", E.is_encrypted(enc))
    try:
        E.page_count(enc)
        print("   !! 未抛出口令异常")
    except E.PdfPasswordRequired:
        print("49 no password -> PdfPasswordRequired OK")
    try:
        E.page_count(enc, "wrong")
        print("   !! 错误口令未抛出")
    except E.PdfPasswordError:
        print("50 wrong password -> PdfPasswordError OK")
    print("51 open with password:", E.page_count(enc, "abc"))
    dec = d / "dec.pdf"
    E.remove_encryption(enc, dec, password="abc")
    print("52 decrypted:", not E.is_encrypted(dec))
    print("53 release cache:", E.release_render_cache() is None)

    s5 = E.DocumentSession(src)
    before = src.read_bytes()
    s5.push_undo()
    E.rotate_document(s5.doc, 90)
    print("54 source untouched during edit:", src.read_bytes() == before)
    s5.save()
    print("55 saved back to source:", E.page_count(src),
          "rot:", fitz.open(src)[0].rotation)
    s5.close()

    print("\nALL ENGINE SMOKE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())