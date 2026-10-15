# PDF 编辑器 - 架构设计

## 项目目标

使用 WorkBuddy 多角色协同，开发一款本地桌面 PDF 编辑软件 MVP。

## 默认决策

- **形态**：本地桌面端（Windows 11 优先）
- **UI 框架**：Python tkinter + ttkbootstrap（轻量、无需端口）
- **PDF 引擎**：PyMuPDF (fitz) + pypdf（功能强、许可友好）
- **MVP 功能**：
  1. 合并多个 PDF
  2. 拆分 PDF（按页码/范围）
  3. 旋转页面（90/180/270 度）
  4. 页码重排（拖拽/输入顺序）
  5. 添加文字水印
  6. 添加图片水印
  7. 提取文字
- **非目标**：可视化页面拖拽编辑、OCR、表单编辑、数字签名

## 目录结构

```
pdf-editor/
├── src/
│   └── pdf_editor/
│       ├── __init__.py
│       ├── pdf_engine.py   # PDF 操作核心
│       └── ui.py           # 桌面 UI
├── tests/
│   ├── __init__.py
│   └── test_pdf_engine.py
├── examples/               # 示例 PDF
├── docs/
│   └── design.md           # 本文档
├── README.md
├── COLLABORATION.md        # 协同开发教程
├── requirements.txt
└── main.py                 # 入口
```

## 模块接口契约

### pdf_engine.py

```python
from pathlib import Path
from typing import List, Tuple, Optional

def merge_pdfs(input_paths: List[Path], output_path: Path) -> None: ...
def split_pdf(input_path: Path, output_dir: Path, ranges: List[Tuple[int, int]]) -> List[Path]: ...
def rotate_pdf(input_path: Path, output_path: Path, angle: int, pages: Optional[List[int]] = None) -> None: ...
def reorder_pdf(input_path: Path, output_path: Path, order: List[int]) -> None: ...
def add_text_watermark(input_path: Path, output_path: Path, text: str, *, opacity: float = 0.3, angle: int = 45) -> None: ...
def add_image_watermark(input_path: Path, output_path: Path, image_path: Path, *, opacity: float = 0.3) -> None: ...
def extract_text(input_path: Path, pages: Optional[List[int]] = None) -> str: ...
```

### ui.py

- 主窗口：`PDFEditorApp`
- 职责：文件列表管理、参数输入、调用 pdf_engine、显示日志

## 角色分工

| 角色 | 职责 | 产出 |
|---|---|---|
| 项目经理 (pm) | 拆任务、跟踪进度、协调阻塞 | TaskList 维护 |
| 架构师 (architect) | 设计规范、接口契约、模块划分 | design.md |
| 后端/PDF 引擎 (engine-dev) | 实现 pdf_engine.py | 核心功能函数 |
| 前端/UI (ui-dev) | 实现 ui.py | 可运行桌面界面 |
| 测试/QA (qa) | 编写测试、验证功能 | tests/、报告 |

## WorkBuddy 协同模式

1. 使用 `TeamCreate` 创建团队，分配上述角色。
2. 每个角色由一个 Agent 承担，通过 `TaskList` 领取任务。
3. 关键决策写入 `docs/design.md`，避免角色间口径不一致。
4. 完成后统一由项目经理汇总，输出 README + 测试报告。
