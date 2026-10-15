"""自动化性能优化迭代器。

每轮：
1. 应用一个优化策略
2. 运行单元测试
3. 运行 benchmark
4. 帕累托验收：三项指标均不劣化，且至少一项提升 ≥5%
5. 通过则 commit；未通过则 git checkout 回滚
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

import benchmark


PROJECT_ROOT = Path(__file__).parent
RESULTS_FILE = PROJECT_ROOT / "optimization_results.json"
ENGINE_FILE = PROJECT_ROOT / "src" / "pdf_editor" / "pdf_engine.py"
MAIN_FILE = PROJECT_ROOT / "main.py"
BENCH_FILE = PROJECT_ROOT / "benchmark.py"


@dataclass
class Metrics:
    startup_seconds: float
    total_processing_seconds: float
    memory_peak_mb: float

    def to_dict(self):
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Metrics":
        return Metrics(
            startup_seconds=d["startup_seconds"],
            total_processing_seconds=d["total_processing_seconds"],
            memory_peak_mb=d["memory_peak_mb"],
        )


@dataclass
class RoundResult:
    round: int
    strategy: str
    before: Metrics
    after: Metrics
    tests_passed: bool
    accepted: bool

    def to_dict(self):
        return {
            "round": self.round,
            "strategy": self.strategy,
            "before": self.before.to_dict(),
            "after": self.after.to_dict(),
            "tests_passed": self.tests_passed,
            "accepted": self.accepted,
        }


def run_git(args: list[str], check: bool = True):
    return subprocess.run(
        ["git", *args],
        cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=check,
    )


def run_tests() -> bool:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(PROJECT_ROOT / "tests"), "-q"],
        cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.returncode == 0


def run_benchmark() -> Metrics:
    result = benchmark.run_benchmark()
    return Metrics.from_dict(result)


def is_pareto_better(before: Metrics, after: Metrics) -> bool:
    """验收：三项均不劣化（允许 0.5% 噪声），且至少一项提升 ≥5%。"""
    eps = 1e-9
    not_worse = (
        after.startup_seconds <= before.startup_seconds * 1.005 + eps
        and after.total_processing_seconds <= before.total_processing_seconds * 1.005 + eps
        and after.memory_peak_mb <= before.memory_peak_mb * 1.005 + eps
    )
    improved = (
        after.startup_seconds <= before.startup_seconds * 0.95
        or after.total_processing_seconds <= before.total_processing_seconds * 0.95
        or after.memory_peak_mb <= before.memory_peak_mb * 0.95
    )
    return not_worse and improved


# ===== 优化策略 =====

def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write(path: Path, content: str):
    path.write_text(content, encoding="utf-8")


def apply_pymupdf_alias() -> bool:
    """将 fitz 导入改为 pymupdf 别名，消除弃用警告。"""
    changed = False
    for path in [ENGINE_FILE, BENCH_FILE]:
        content = _read(path)
        if "import fitz" in content and "import pymupdf as fitz" not in content:
            new_content = content.replace("import fitz", "import pymupdf as fitz")
            _write(path, new_content)
            changed = True
    return changed


def apply_lazy_ui() -> bool:
    """main.py 延迟导入 UI，降低 --version / 启动耗时。"""
    content = _read(MAIN_FILE)
    marker = "# LAZY_UI"
    if marker in content:
        return False
    new_content = """#!/usr/bin/env python3
\"\"\"PDF 编辑器入口。\"\"\"

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("--version", "-v"):
        print("pdf-editor 0.1.0")
        sys.exit(0)
    from pdf_editor.ui import main  # LAZY_UI
    main()
"""
    _write(MAIN_FILE, new_content)
    return True


def apply_reduce_imports() -> bool:
    """使用 Python 3.10+ 内置泛型，减少 typing import。"""
    content = _read(ENGINE_FILE)
    marker = "# REDUCE_IMPORTS"
    if marker in content:
        return False
    new_content = content.replace(
        "from typing import List, Tuple, Optional\n",
        "",
    )
    new_content = new_content.replace("List[Path]", "list[Path]")
    new_content = new_content.replace("List[Tuple[int, int]]", "list[tuple[int, int]]")
    new_content = new_content.replace("Optional[List[int]]", "list[int] | None")
    new_content = new_content.replace("Tuple[float, float, float]", "tuple[float, float, float]")
    new_content = new_content.replace("List[str]", "list[str]")
    new_content = new_content.replace("-> List[Path]", "-> list[Path]")
    new_content = new_content.replace("-> str", "-> str")
    new_content += f"\n{marker}\n"
    _write(ENGINE_FILE, new_content)
    return True


def apply_cache_total_rotate() -> bool:
    """rotate_pdf 中缓存 len(doc)。"""
    content = _read(ENGINE_FILE)
    marker = "# CACHE_TOTAL_ROTATE"
    if marker in content:
        return False
    old = """    with fitz.open(input_path) as doc:
        target_pages = pages or list(range(1, len(doc) + 1))
        for p in target_pages:
            if p < 1 or p > len(doc):
                raise ValueError(f\"无效页码 {p}，总页数 {len(doc)}\")
            doc[p - 1].set_rotation((doc[p - 1].rotation + angle) % 360)
        doc.save(output_path)"""
    new = """    with fitz.open(input_path) as doc:
        total = len(doc)
        target_pages = pages or list(range(1, total + 1))
        for p in target_pages:
            if p < 1 or p > total:
                raise ValueError(f\"无效页码 {p}，总页数 {total}\")
            doc[p - 1].set_rotation((doc[p - 1].rotation + angle) % 360)
        doc.save(output_path)  # CACHE_TOTAL_ROTATE"""
    if old not in content:
        return False
    _write(ENGINE_FILE, content.replace(old, new))
    return True


def apply_cache_total_extract() -> bool:
    """extract_text 中缓存 len(doc)。"""
    content = _read(ENGINE_FILE)
    marker = "# CACHE_TOTAL_EXTRACT"
    if marker in content:
        return False
    old = """    parts: list[str] = []
    with fitz.open(input_path) as doc:
        target_pages = pages or list(range(1, len(doc) + 1))
        for p in target_pages:
            if p < 1 or p > len(doc):
                raise ValueError(f\"无效页码 {p}，总页数 {len(doc)}\")
            parts.append(doc[p - 1].get_text())
    return "\\n".join(parts)"""
    new = """    parts: list[str] = []
    with fitz.open(input_path) as doc:
        total = len(doc)
        target_pages = pages or list(range(1, total + 1))
        for p in target_pages:
            if p < 1 or p > total:
                raise ValueError(f\"无效页码 {p}，总页数 {total}\")
            parts.append(doc[p - 1].get_text())
    return "\\n".join(parts)  # CACHE_TOTAL_EXTRACT"""
    if old not in content:
        return False
    _write(ENGINE_FILE, content.replace(old, new))
    return True


def apply_precompute_watermark() -> bool:
    """文字水印预计算常量。"""
    content = _read(ENGINE_FILE)
    marker = "# PRECOMPUTE_WM"
    if marker in content:
        return False
    old = """    _ensure_dir(output_path)
    with fitz.open(input_path) as doc:
        for page in doc:
            rect = page.rect
            center = (rect.x0 + rect.width / 2, rect.y0 + rect.height / 2)
            text_width = font_size * len(text) * 0.6
            text_height = font_size
            pos = (center[0] - text_width / 2, center[1] + text_height / 2)
            safe_angle = round(angle / 90) * 90
            page.insert_text(pos, text, fontsize=font_size, color=color, rotate=safe_angle, overlay=True)
        doc.save(output_path)"""
    new = """    _ensure_dir(output_path)
    text_width = font_size * len(text) * 0.6
    text_height = font_size
    safe_angle = round(angle / 90) * 90
    with fitz.open(input_path) as doc:
        for page in doc:
            rect = page.rect
            center = (rect.x0 + rect.width / 2, rect.y0 + rect.height / 2)
            pos = (center[0] - text_width / 2, center[1] + text_height / 2)
            page.insert_text(pos, text, fontsize=font_size, color=color, rotate=safe_angle, overlay=True)
        doc.save(output_path)  # PRECOMPUTE_WM"""
    if old not in content:
        return False
    _write(ENGINE_FILE, content.replace(old, new))
    return True


def apply_del_objects() -> bool:
    """处理完大对象后立即 del，帮助内存回收。"""
    content = _read(ENGINE_FILE)
    marker = "# DEL_OBJECTS"
    if marker in content:
        return False
    changes = [
        ("    merged.save(output_path)\n    merged.close()\n",
         "    merged.save(output_path)\n    merged.close()\n    del merged\n"),
        ("            new_doc.save(out_path)\n            new_doc.close()\n            out_paths.append(out_path)\n",
         "            new_doc.save(out_path)\n            new_doc.close()\n            del new_doc\n            out_paths.append(out_path)\n"),
        ("        new_doc.save(output_path)\n        new_doc.close()\n",
         "        new_doc.save(output_path)\n        new_doc.close()\n        del new_doc\n"),
    ]
    new_content = content
    for old, new in changes:
        if old in new_content:
            new_content = new_content.replace(old, new)
    if new_content == content:
        return False
    new_content += f"\n{marker}\n"
    _write(ENGINE_FILE, new_content)
    return True


def apply_select_split() -> bool:
    """拆分使用 select 代替 insert_pdf，减少内存拷贝。"""
    content = _read(ENGINE_FILE)
    marker = "# SELECT_SPLIT"
    if marker in content:
        return False
    old = """    out_paths: list[Path] = []
    with fitz.open(input_path) as doc:
        total = len(doc)
        for idx, (start, end) in enumerate(ranges, start=1):
            if start < 1 or end > total or start > end:
                raise ValueError(f\"无效页码范围 {start}-{end}，总页数 {total}\")
            new_doc = fitz.open()
            new_doc.insert_pdf(doc, from_page=start - 1, to_page=end - 1)
            out_path = output_dir / f\"{input_path.stem}_part{idx}_{start}-{end}.pdf\"
            new_doc.save(out_path)
            new_doc.close()
            out_paths.append(out_path)
    return out_paths"""
    new = """    out_paths: list[Path] = []
    with fitz.open(input_path) as doc:
        total = len(doc)
        for idx, (start, end) in enumerate(ranges, start=1):
            if start < 1 or end > total or start > end:
                raise ValueError(f\"无效页码范围 {start}-{end}，总页数 {total}\")
            new_doc = fitz.open(input_path)
            new_doc.select(list(range(start - 1, end)))
            out_path = output_dir / f\"{input_path.stem}_part{idx}_{start}-{end}.pdf\"
            new_doc.save(out_path)
            new_doc.close()
            del new_doc
            out_paths.append(out_path)
    return out_paths  # SELECT_SPLIT"""
    if old not in content:
        return False
    _write(ENGINE_FILE, content.replace(old, new))
    return True


def apply_select_reorder() -> bool:
    """重排使用 select 代替逐页 insert_pdf。"""
    content = _read(ENGINE_FILE)
    marker = "# SELECT_REORDER"
    if marker in content:
        return False
    old = """    with fitz.open(input_path) as doc:
        total = len(doc)
        if sorted(order) != list(range(1, total + 1)):
            raise ValueError(f\"order 必须是 1 到 {total} 的排列\")
        new_doc = fitz.open()
        for p in order:
            new_doc.insert_pdf(doc, from_page=p - 1, to_page=p - 1)
        new_doc.save(output_path)
        new_doc.close()"""
    new = """    with fitz.open(input_path) as doc:
        total = len(doc)
        if sorted(order) != list(range(1, total + 1)):
            raise ValueError(f\"order 必须是 1 到 {total} 的排列\")
        new_doc = fitz.open(input_path)
        new_doc.select([p - 1 for p in order])
        new_doc.save(output_path)
        new_doc.close()
        del new_doc  # SELECT_REORDER"""
    if old not in content:
        return False
    _write(ENGINE_FILE, content.replace(old, new))
    return True


def apply_fast_merge() -> bool:
    """合并时预加载所有文档再插入，减少 with 切换开销。"""
    content = _read(ENGINE_FILE)
    marker = "# FAST_MERGE"
    if marker in content:
        return False
    old = """    merged = fitz.open()
    for p in input_paths:
        if not p.exists():
            raise FileNotFoundError(f\"找不到文件: {p}\")
        with fitz.open(p) as doc:
            merged.insert_pdf(doc)
    merged.save(output_path)
    merged.close()"""
    new = """    docs = []
    for p in input_paths:
        if not p.exists():
            raise FileNotFoundError(f\"找不到文件: {p}\")
        docs.append(fitz.open(p))
    merged = fitz.open()
    for doc in docs:
        merged.insert_pdf(doc)
        doc.close()
    merged.save(output_path)
    merged.close()
    del merged, docs  # FAST_MERGE"""
    if old not in content:
        return False
    _write(ENGINE_FILE, content.replace(old, new))
    return True


STRATEGIES: list[tuple[str, Callable[[], bool]]] = [
    ("pymupdf_alias", apply_pymupdf_alias),
    ("lazy_ui_import", apply_lazy_ui),
    ("reduce_imports", apply_reduce_imports),
    ("cache_total_rotate", apply_cache_total_rotate),
    ("cache_total_extract", apply_cache_total_extract),
    ("precompute_watermark", apply_precompute_watermark),
    ("del_large_objects", apply_del_objects),
    ("select_split", apply_select_split),
    ("select_reorder", apply_select_reorder),
    ("fast_merge", apply_fast_merge),
]


def load_results() -> list[dict]:
    if RESULTS_FILE.exists():
        return json.loads(RESULTS_FILE.read_text(encoding="utf-8"))
    return []


def save_results(results: list[dict]):
    RESULTS_FILE.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")


def run_optimization(max_rounds: int = 10):
    results = load_results()
    current_metrics = run_benchmark()
    print(f"初始指标: {current_metrics.to_dict()}")

    # 保存基线 commit
    run_git(["add", "-A"])
    run_git(["commit", "-m", "Baseline before optimization rounds"], check=False)

    for r in range(1, max_rounds + 1):
        print(f"\n===== 第 {r} 轮 =====")
        strategy_name, strategy_fn = STRATEGIES[(r - 1) % len(STRATEGIES)]
        print(f"策略: {strategy_name}")

        before = current_metrics
        applied = strategy_fn()
        if not applied:
            print("策略未产生变化，跳过")
            results.append({
                "round": r,
                "strategy": strategy_name,
                "skipped": True,
            })
            save_results(results)
            continue

        tests_ok = run_tests()
        print(f"测试: {'通过' if tests_ok else '失败'}")
        if not tests_ok:
            print("测试失败，回滚")
            run_git(["checkout", "--", "."], check=False)
            results.append({
                "round": r,
                "strategy": strategy_name,
                "tests_passed": False,
                "accepted": False,
            })
            save_results(results)
            continue

        after = run_benchmark()
        print(f"优化后指标: {after.to_dict()}")

        accepted = is_pareto_better(before, after)
        print(f"验收: {'通过' if accepted else '未通过'}")

        if accepted:
            current_metrics = after
            run_git(["add", "-A"])
            run_git(["commit", "-m", f"Round {r}: {strategy_name}"], check=False)
        else:
            run_git(["checkout", "--", "."], check=False)

        round_result = RoundResult(
            round=r,
            strategy=strategy_name,
            before=before,
            after=after,
            tests_passed=tests_ok,
            accepted=accepted,
        )
        results.append(round_result.to_dict())
        save_results(results)

    print("\n最终指标:", current_metrics.to_dict())
    return results


if __name__ == "__main__":
    run_optimization(10)
