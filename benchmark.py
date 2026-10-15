"""性能基准测试。

测量维度：
1. 启动时间：子进程运行 main.py --version 的耗时
2. 处理耗时：合并、拆分、旋转、添加水印
3. 峰值内存：处理大文件时的最大 RSS
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import tracemalloc
from pathlib import Path

import pymupdf as fitz

from pdf_editor.pdf_engine import (
    merge_pdfs,
    split_pdf,
    rotate_pdf,
    add_text_watermark,
)


PROJECT_ROOT = Path(__file__).parent


def _make_pdf(path: Path, pages: int):
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=595, height=842)
        for j in range(20):
            page.insert_text((50, 50 + j * 30), f"Line {j} on page {i + 1}")
    doc.save(path)
    doc.close()


def _prepare_samples(tmp_dir: Path):
    sample_dir = tmp_dir / "samples"
    sample_dir.mkdir(exist_ok=True)
    files = []
    for i in range(5):
        p = sample_dir / f"sample{i}.pdf"
        _make_pdf(p, 20)
        files.append(p)
    big = sample_dir / "big.pdf"
    _make_pdf(big, 200)
    return files, big


def measure_startup() -> float:
    """测量 main.py 冷启动耗时（运行 --version）。"""
    script = PROJECT_ROOT / "main.py"
    cmd = [sys.executable, str(script), "--version"]
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    # 预热一次，减少文件缓存影响
    subprocess.run(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
    times = []
    for _ in range(3):
        start = time.perf_counter()
        proc = subprocess.run(
            cmd,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=60,
        )
        elapsed = time.perf_counter() - start
        if proc.returncode != 0:
            raise RuntimeError("main.py --version 启动失败")
        times.append(elapsed)
    return min(times)


def measure_import_time() -> float:
    """测量 import 核心引擎耗时。"""
    start = time.perf_counter()
    import pdf_editor.pdf_engine  # noqa: F401
    return time.perf_counter() - start


def _timed(func, *args, **kwargs):
    start = time.perf_counter()
    func(*args, **kwargs)
    return time.perf_counter() - start


def measure_processing(samples: list[Path], big: Path, tmp_dir: Path) -> dict:
    out_dir = tmp_dir / "out"
    out_dir.mkdir(exist_ok=True)

    merge_out = out_dir / "merged.pdf"
    merge_time = _timed(merge_pdfs, samples, merge_out)

    split_out_dir = out_dir / "split"
    split_time = _timed(split_pdf, big, split_out_dir, [(1, 50), (51, 100), (101, 150), (151, 200)])

    rotate_out = out_dir / "rotated.pdf"
    rotate_time = _timed(rotate_pdf, big, rotate_out, 90)

    wm_out = out_dir / "watermarked.pdf"
    wm_time = _timed(add_text_watermark, big, wm_out, "BENCHMARK")

    return {
        "merge": merge_time,
        "split": split_time,
        "rotate": rotate_time,
        "watermark": wm_time,
    }


def measure_memory(big: Path, tmp_dir: Path) -> float:
    """测量处理大文件时的峰值内存增量（MB）。"""
    out = tmp_dir / "out_memory.pdf"
    tracemalloc.start()
    add_text_watermark(big, out, "MEMORY TEST")
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return peak / 1024 / 1024


def run_benchmark() -> dict:
    tmp_dir = PROJECT_ROOT / ".benchmark"
    tmp_dir.mkdir(exist_ok=True)
    samples, big = _prepare_samples(tmp_dir)

    startup = measure_startup()
    processing = measure_processing(samples, big, tmp_dir)
    memory = measure_memory(big, tmp_dir)

    return {
        "version": "baseline",
        "startup_seconds": startup,
        "processing_seconds": processing,
        "memory_peak_mb": memory,
        "total_processing_seconds": sum(processing.values()),
    }


if __name__ == "__main__":
    result = run_benchmark()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    out_path = PROJECT_ROOT / "benchmark_result.json"
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
