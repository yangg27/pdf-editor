"""完整功能集成测试。

覆盖：
1. exe 可启动（--version）
2. PDF 引擎所有功能：合并、拆分、旋转、重排、文字水印、图片水印、提取文字
3. 输出文件存在且内容正确
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import fitz

from pdf_editor.pdf_engine import (
    merge_pdfs,
    split_pdf,
    rotate_pdf,
    reorder_pdf,
    add_text_watermark,
    add_image_watermark,
    extract_text,
)


PROJECT_ROOT = Path(__file__).parent
EXE_PATH = PROJECT_ROOT / "dist" / "PDF编辑器.exe"


def _make_pdf(path: Path, pages: int, label: str = "Page"):
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=595, height=842)
        page.insert_text((100, 200), f"{label} {i + 1}")
    doc.save(path)
    doc.close()


def _make_image(path: Path):
    """生成一个简单 PNG 图片用于图片水印测试。"""
    from PIL import Image
    img = Image.new("RGBA", (100, 100), (255, 0, 0, 128))
    img.save(path)


def test_exe_version():
    if not EXE_PATH.exists():
        raise FileNotFoundError(f"未找到 exe: {EXE_PATH}")
    result = subprocess.run(
        [str(EXE_PATH), "--version"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, f"exe 启动失败: {result.stderr}"
    assert "pdf-editor" in result.stdout, f"版本输出异常: {result.stdout}"
    print(f"[OK] exe 可启动: {result.stdout.strip()}")


def test_merge(tmp_dir: Path):
    a = tmp_dir / "a.pdf"
    b = tmp_dir / "b.pdf"
    _make_pdf(a, 2, "A")
    _make_pdf(b, 3, "B")
    out = tmp_dir / "merged.pdf"
    merge_pdfs([a, b], out)
    assert out.exists()
    with fitz.open(out) as doc:
        assert len(doc) == 5
    print("[OK] 合并功能")


def test_split(tmp_dir: Path):
    src = tmp_dir / "src.pdf"
    _make_pdf(src, 6, "S")
    out_dir = tmp_dir / "split"
    paths = split_pdf(src, out_dir, [(1, 2), (3, 4), (5, 6)])
    assert len(paths) == 3
    with fitz.open(paths[0]) as doc:
        assert len(doc) == 2
    print("[OK] 拆分功能")


def test_rotate(tmp_dir: Path):
    src = tmp_dir / "src.pdf"
    _make_pdf(src, 1)
    out = tmp_dir / "rotated.pdf"
    rotate_pdf(src, out, 90)
    with fitz.open(out) as doc:
        assert doc[0].rotation == 90
    print("[OK] 旋转功能")


def test_reorder(tmp_dir: Path):
    src = tmp_dir / "src.pdf"
    _make_pdf(src, 3)
    out = tmp_dir / "reordered.pdf"
    reorder_pdf(src, out, [3, 1, 2])
    with fitz.open(out) as doc:
        assert "Page 3" in doc[0].get_text()
        assert "Page 1" in doc[1].get_text()
    print("[OK] 重排功能")


def test_text_watermark(tmp_dir: Path):
    src = tmp_dir / "src.pdf"
    _make_pdf(src, 1)
    out = tmp_dir / "wm.pdf"
    add_text_watermark(src, out, "CONFIDENTIAL")
    text = extract_text(out)
    assert "CONFIDENTIAL" in text
    print("[OK] 文字水印")


def test_image_watermark(tmp_dir: Path):
    src = tmp_dir / "src.pdf"
    _make_pdf(src, 1)
    img = tmp_dir / "mark.png"
    _make_image(img)
    out = tmp_dir / "img_wm.pdf"
    add_image_watermark(src, out, img)
    assert out.exists()
    with fitz.open(out) as doc:
        assert len(doc) == 1
    print("[OK] 图片水印")


def test_extract_text(tmp_dir: Path):
    src = tmp_dir / "src.pdf"
    _make_pdf(src, 2)
    text = extract_text(src)
    assert "Page 1" in text
    assert "Page 2" in text
    print("[OK] 提取文字")


def main():
    tmp_dir = PROJECT_ROOT / ".integration_test"
    if tmp_dir.exists():
        import shutil
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir()

    try:
        test_exe_version()
        test_merge(tmp_dir)
        test_split(tmp_dir)
        test_rotate(tmp_dir)
        test_reorder(tmp_dir)
        test_text_watermark(tmp_dir)
        test_image_watermark(tmp_dir)
        test_extract_text(tmp_dir)
        print("\n全部功能测试通过")
        return 0
    except Exception as e:
        print(f"\n测试失败: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
