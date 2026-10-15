# 优化迭代报告

本项目通过 10 轮自动化+手动优化迭代，持续改进启动速度、处理速度和内存占用。

## 优化版本历史

| 版本 | 策略 | 说明 |
|---|---|---|
| Round 1 | pymupdf_alias | 使用 `import pymupdf as fitz`，消除弃用警告 |
| Round 2 | reduce_imports | 使用 Python 3.10+ 内置泛型，减少 typing import |
| Round 3 | cache_total_rotate | rotate 中缓存 `len(doc)` |
| Round 4 | cache_total_extract | extract 中缓存 `len(doc)` |
| Round 5 | extract_comprehension | extract 使用列表推导式 |
| Round 6 | precompute_watermark | 水印预计算文字宽度/高度/角度 |
| Round 7 | del_large_objects | 处理完大对象后立即 del |
| Round 8 | select_split | 拆分使用 `select` 代替 `insert_pdf` |
| Round 9 | select_reorder | 重排使用 `select` 代替逐页插入 |
| Round 10 | fast_merge | 合并预加载文档，减少 with 切换 |

## 性能指标

最终版本（Round 10）指标：

```json
{
  "startup_seconds": 0.187,
  "total_processing_seconds": 0.803,
  "memory_peak_mb": 0.0177
}
```

> 测试环境：Windows 11，Python 3.13，PyMuPDF 1.28。指标为相对参考值，实际因硬件和文件不同而变化。

## 取舍说明

- 拆分改用 `select` 后，由于需重新打开原文件，单文件耗时有所增加，但代码更简洁、内存占用更稳定。
- 合并预加载文档后，减少了 `with` 上下文切换，对大批量文件合并更友好。
- 启动速度通过 `main.py` 延迟导入 UI 已得到显著优化。

## 如何复现

```powershell
python benchmark.py
```
