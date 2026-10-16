"""性能与内存基准（v0.3.0）。

测量项：
1. 引擎导入耗时
2. 单页渲染耗时（新架构：samples 直出 vs 旧架构：PNG 往返）
3. 打开 N 页文档耗时（句柄复用 vs 反复开关文件）
4. 预览渲染 + 缓存的内存占用（峰值与常驻）
5. 缩略图缓存上限是否生效

用法：
    .venv-sys/Scripts/python.exe bench_v3.py
"""

from __future__ import annotations

import ctypes
import gc
import io
import json
import collections
import statistics
import sys
import tempfile
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pymupdf as fitz  # noqa: E402
from PIL import Image  # noqa: E402

from pdf_editor import pdf_engine as E  # noqa: E402


# --------------------------------------------------------------- 内存工具
class _PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_ulong),
        ("PageFaultCount", ctypes.c_ulong),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def _mem() -> tuple[float, float]:
    """返回 (当前工作集 MB, 峰值工作集 MB)。

    坑点：必须显式声明 ``argtypes``。否则 ctypes 会把 Python 的 -1 当成
    32 位 int 传递，而 ``GetCurrentProcess()`` 返回的伪句柄是
    64 位 ``(HANDLE)-1``，被截断后调用静默失败并返回 0。
    """
    try:
        from ctypes import wintypes

        psapi = ctypes.windll.psapi
        k32 = ctypes.windll.kernel32
        counters = _PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(counters)
        handle = k32.GetCurrentProcess()
        for mod, name in ((psapi, "GetProcessMemoryInfo"),
                          (k32, "K32GetProcessMemoryInfo")):
            fn = getattr(mod, name, None)
            if fn is None:
                continue
            fn.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_ulong]
            fn.restype = wintypes.BOOL
            if fn(handle, ctypes.byref(counters), counters.cb):
                return (counters.WorkingSetSize / 1048576.0,
                        counters.PeakWorkingSetSize / 1048576.0)
        return 0.0, 0.0
    except Exception as exc:
        print(f"  （内存探针不可用：{exc}）")
        return 0.0, 0.0


def available_ram_mb() -> float:
    """系统当前可用物理内存（MB），用于说明测试环境。"""
    try:
        class MEMSTAT(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        m = MEMSTAT()
        m.dwLength = ctypes.sizeof(m)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
            return m.ullAvailPhys / 1048576.0
    except Exception:
        pass
    return 0.0


def rss_mb() -> float:
    """当前进程常驻内存（MB）。"""
    return _mem()[0]


def peak_rss_mb() -> float:
    """进程峰值内存（MB）。"""
    return _mem()[1]


def make_doc(path: Path, pages: int, text_lines: int = 20) -> Path:
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 80), f"性能测试 第 {i + 1} 页", fontname="china-s",
                         fontsize=18)
        for j in range(text_lines):
            page.insert_text((72, 120 + j * 18),
                             f"示例正文行 {j + 1}：hello benchmark content",
                             fontsize=9)
        page.draw_rect(fitz.Rect(60, 500, 530, 640),
                       color=(0.2, 0.4, 0.8), width=1)
    doc.save(path)
    doc.close()
    return path


def timeit(fn, repeat: int = 5):
    """返回 (中位数毫秒, 最小毫秒)。"""
    samples = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t0) * 1000)
    return statistics.median(samples), min(samples)


def main() -> int:
    results: dict = {}
    tmp = Path(tempfile.mkdtemp(prefix="pdf-bench-"))
    small = make_doc(tmp / "small.pdf", 20)
    big = make_doc(tmp / "big.pdf", 300)

    print("=" * 62)
    print(" PDF 编辑器 v0.3.0 性能与内存基准")
    print("=" * 62)
    print(f" 系统可用物理内存: {available_ram_mb():.0f} MB")

    # ---- 1. 渲染：samples 直出 vs PNG 往返 ----
    with E.open_document(small) as doc:
        page = doc[0]

        def render_new():
            img = E.page_image(page, 1.5)
            img.close()

        def render_old():
            pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            img.load()
            img.close()

        new_med, _ = timeit(render_new, 8)
        old_med, _ = timeit(render_old, 8)

    results["render_ms"] = {"new": round(new_med, 2), "old": round(old_med, 2),
                            "speedup": round(old_med / max(new_med, 0.01), 1)}
    print(f"\n[1] 单页渲染（zoom=1.5）")
    print(f"    v0.3.0 直出 samples : {new_med:7.2f} ms")
    print(f"    v0.2.0 PNG 往返     : {old_med:7.2f} ms")
    print(f"    → 提速 {old_med / max(new_med, 0.01):.1f}x")

    # ---- 2. 打开文档：单句柄 vs 反复开关 ----
    def open_session():
        s = E.DocumentSession(small)
        _ = s.page_count
        s.close()

    def open_repeated():
        for _ in range(20):
            with E.open_document(small) as d:
                _ = len(d)

    sess_med, _ = timeit(open_session, 5)
    rep_med, _ = timeit(open_repeated, 5)
    results["open_20pages_ms"] = {"session": round(sess_med, 2),
                                  "reopen20": round(rep_med, 2)}
    print(f"\n[2] 打开 20 页文档")
    print(f"    单句柄会话          : {sess_med:7.2f} ms")
    print(f"    反复开关 20 次      : {rep_med:7.2f} ms")
    print(f"    → 旧方式每次预览都重开文件，新架构全程复用同一句柄")

    # ---- 3. 大文档打开与渲染 ----
    t0 = time.perf_counter()
    s = E.DocumentSession(big)
    open_big = (time.perf_counter() - t0) * 1000
    t0 = time.perf_counter()
    dims = [(s.doc[i].rect.width, s.doc[i].rect.height) for i in range(s.page_count)]
    dims_ms = (time.perf_counter() - t0) * 1000
    t0 = time.perf_counter()
    imgs = [E.page_image(s.doc[i], 0.22) for i in (0, 5, 10, 20, 40)]
    thumb_ms = (time.perf_counter() - t0) * 1000
    for im in imgs:
        im.close()
    results["big_doc"] = {"pages": s.page_count, "open_ms": round(open_big, 1),
                          "dims_ms": round(dims_ms, 1),
                          "5_thumb_ms": round(thumb_ms, 1)}
    print(f"\n[3] 300 页文档")
    print(f"    打开（建工作副本）  : {open_big:7.1f} ms")
    print(f"    读取全部页面尺寸    : {dims_ms:7.1f} ms")
    print(f"    渲染 5 张缩略图     : {thumb_ms:7.1f} ms（{thumb_ms / 5:.1f} ms/张）")

    # ---- 4. 内存：渲染与缓存 ----
    gc.collect()
    base = rss_mb()
    peak_before = peak_rss_mb()

    # 连续渲染 40 页（模拟浏览），并限制缓存条数
    cache: collections.OrderedDict = collections.OrderedDict()
    for i in range(40):
        img = E.page_image(s.doc[i % s.page_count], 1.2)
        cache[(i, 1.2)] = img
        while len(cache) > 6:
            _, old = cache.popitem(last=False)
            old.close()
    after_render = rss_mb()
    E.release_render_cache()
    gc.collect()
    after_release = rss_mb()

    results["memory_mb"] = {"baseline": round(base, 1),
                            "after_40_render_cache6": round(after_render, 1),
                            "after_release": round(after_release, 1),
                            "peak": round(peak_rss_mb(), 1)}
    print(f"\n[4] 内存（浏览 40 页，预览缓存上限 6 张）")
    print(f"    基线                : {base:7.1f} MB")
    print(f"    渲染 40 页后        : {after_render:7.1f} MB  (+{after_render - base:.1f})")
    print(f"    释放缓存后          : {after_release:7.1f} MB  (-{after_render - after_release:.1f})")
    print(f"    进程峰值            : {peak_rss_mb():7.1f} MB")

    # ---- 5. 像素上限是否生效 ----
    huge = E.page_image(s.doc[0], 8.0, max_pixels=6_000_000)
    px = huge.width * huge.height
    huge.close()
    results["max_pixels"] = {"limit": 6_000_000, "actual": px}
    print(f"\n[5] 预览像素上限")
    print(f"    zoom=8.0 时实际像素 : {px:,}（上限 6,000,000）")
    print(f"    → 上限{'生效' if px <= 6_000_000 else '未生效'}")

    # ---- 6. 撤销栈内存控制 ----
    s2 = E.DocumentSession(small, max_undo_steps=3)
    for _ in range(10):
        s2.push_undo()
        E.insert_blank_document_page(s2.doc)
    n_undo = len(s2._undo)
    undo_bytes = s2._undo_bytes / 1024 / 1024
    s2.close()
    results["undo"] = {"max_steps": 3, "kept": n_undo,
                       "bytes_mb": round(undo_bytes, 2)}
    print(f"\n[6] 撤销栈上限")
    print(f"    上限 3 步，实际保留 : {n_undo} 步，占用 {undo_bytes:.2f} MB")

    s.close()

    out = PROJECT_ROOT / "benchmark_v3.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"\n结果已保存: {out.name}")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())