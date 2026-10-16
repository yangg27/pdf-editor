"""生成真实量级的大 PDF 样本（含嵌入图片），用于打开速度基准。

输出到 .benchmark/samples/：
  real_5mb.pdf / real_20mb.pdf / real_50mb.pdf  （页数约 100 / 200 / 300）
"""
from __future__ import annotations

import io
import random
import sys
from pathlib import Path

import fitz
from PIL import Image

OUT = Path(__file__).resolve().parent / ".benchmark" / "samples"
OUT.mkdir(parents=True, exist_ok=True)


def noise_image(w: int, h: int, seed: int) -> bytes:
    """生成不可压缩的随机噪声 PNG（模拟真实扫描件/照片页）。"""
    rnd = random.Random(seed)
    im = Image.new("RGB", (w, h))
    px = im.load()
    for y in range(h):
        for x in range(0, w, 4):
            px[x, y] = (rnd.randrange(256), rnd.randrange(256), rnd.randrange(256))
            if x + 1 < w:
                px[x + 1, y] = px[x, y]
            if x + 2 < w:
                px[x + 2, y] = px[x, y]
            if x + 3 < w:
                px[x + 3, y] = px[x, y]
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def build(path: Path, pages: int, img_w: int, img_h: int) -> None:
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=595, height=842)  # A4
        png = noise_image(img_w, img_h, seed=i)
        page.insert_image(fitz.Rect(0, 0, 595, 742), stream=png)
        page.insert_text((40, 800), f"Page {i + 1}", fontsize=12,
                         fontname="china-s")
    doc.save(str(path), deflate=True, garbage=3)
    doc.close()
    print(f"  {path.name:<18} {path.stat().st_size / 1048576:>6.2f} MB  {pages} 页")


def main() -> int:
    print("生成真实量级样本...")
    build(OUT / "real_5mb.pdf", 100, 420, 520)
    build(OUT / "real_20mb.pdf", 200, 620, 760)
    build(OUT / "real_50mb.pdf", 300, 820, 1000)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())