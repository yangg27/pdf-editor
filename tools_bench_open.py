"""打开速度分段基准：定位「打开 PDF」链路的真实耗时分布。

对以下每一段单独计时（多次取中位数）：
  A. 源文件校验/探测（_open_raw + needs_pass）
  B. 复制为工作副本（shutil.copyfile）  [Open]
  C. 打开工作副本（_open_raw）
  D. 逐页读 rect（open_path 里的解析循环）
  E. 首页预览渲染（page_image）
  F. 缩略图渲染（若干张，THUMB 尺寸）

用法：
    <venv-sys>/python.exe tools_bench_open.py [pdf路径] [--json]
"""
from __future__ import annotations

import json
import shutil
import statistics
import sys
import tempfile
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import fitz  # noqa: E402

from pdf_editor.pdf_engine import (  # noqa: E402
    DocumentSession,
    page_image,
    release_render_cache,
)

THUMB_MAX_H = 132.0


def _ms(fn, repeat: int = 5) -> float:
    """跑 repeat 次取中位数（毫秒）。"""
    samples: list[float] = []
    for _ in range(repeat):
        t = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t) * 1000)
    return statistics.median(samples)


def bench(path: Path) -> dict:
    out: dict = {"file": path.name, "size_mb": round(path.stat().st_size / 1048576, 2)}
    tmpdir = Path(tempfile.mkdtemp(prefix="bench-open-"))
    work = tmpdir / path.name

    # A. 源文件探测
    def a_probe():
        d = fitz.open(path)
        _ = d.needs_pass
        d.close()

    out["A_probe_ms"] = round(_ms(a_probe), 2)

    # B. 复制工作副本
    def b_copy():
        if work.exists():
            work.unlink()
        shutil.copyfile(path, work)

    out["B_copy_ms"] = round(_ms(b_copy, 3), 2)
    if not work.exists():
        shutil.copyfile(path, work)

    # C. 打开工作副本
    def c_open():
        d = fitz.open(work)
        d.close()

    out["C_open_ms"] = round(_ms(c_open), 2)

    # D. 逐页读 rect
    doc = fitz.open(work)
    n = doc.page_count
    out["pages"] = n

    def d_rects():
        for i in range(n):
            _ = doc[i].rect

    out["D_rects_ms"] = round(_ms(d_rects, 5), 2)

    # E. 首页预览（fit_width 近似：约 800px 宽）
    p0 = doc[0]
    fit_zoom = 800.0 / max(1.0, p0.rect.width)
    out["E_preview_ms"] = round(_ms(lambda: page_image(p0, fit_zoom, max_pixels=0), 5), 2)

    # F. 单张缩略图
    tz = THUMB_MAX_H / max(1.0, p0.rect.height)
    out["F_thumb1_ms"] = round(_ms(lambda: page_image(p0, tz, max_pixels=0), 8), 2)

    # G. 首批 12 张缩略图
    def g_thumbs():
        for i in range(min(12, n)):
            page_image(doc[i], tz, max_pixels=0)

    out["G_thumb12_ms"] = round(_ms(g_thumbs, 3), 2)
    doc.close()

    # H. 完整 DocumentSession.open
    def h_session():
        s = DocumentSession(path)
        s.close()

    out["H_session_open_ms"] = round(_ms(h_session, 3), 2)

    shutil.rmtree(tmpdir, ignore_errors=True)
    release_render_cache()
    return out


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    as_json = "--json" in sys.argv
    if args:
        paths = [Path(args[0])]
    else:
        samples = sorted((PROJECT_ROOT / ".benchmark" / "samples").glob("*.pdf"),
                         key=lambda p: p.stat().st_size)
        paths = samples or []
    results = [bench(p) for p in paths if p.exists()]
    if as_json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0
    for r in results:
        print(f"\n=== {r['file']}  ({r['size_mb']} MB, {r['pages']} 页) ===")
        rows = [
            ("A 源文件探测", "A_probe_ms"),
            ("B 复制工作副本", "B_copy_ms"),
            ("C 打开工作副本", "C_open_ms"),
            ("D 逐页读 rect", "D_rects_ms"),
            ("E 首页预览渲染", "E_preview_ms"),
            ("F 单张缩略图", "F_thumb1_ms"),
            ("G 首批12张缩略图", "G_thumb12_ms"),
            ("H DocumentSession.open", "H_session_open_ms"),
        ]
        for label, k in rows:
            print(f"  {label:<24} {r[k]:>9.2f} ms")
        # 打开阶段合计（用户感知：点开到看到首页）
        total = r["H_session_open_ms"] + r["D_rects_ms"] + r["E_preview_ms"]
        print(f"  {'→ 打开至首页可见(估)':<22} {total:>9.2f} ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())