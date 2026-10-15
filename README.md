# PDF 编辑器

本地桌面 PDF 编辑软件 MVP，基于 Python + tkinter/ttkbootstrap + PyMuPDF。

## 功能

- 合并多个 PDF
- 按页码范围拆分 PDF
- 旋转页面（90°）
- 重排页面顺序
- 添加文字水印
- 添加图片水印
- 提取文字

## 运行方式

```powershell
# 1. 进入项目目录
cd pdf-editor

# 2. 创建并激活虚拟环境
C:/Users/Administrator/.workbuddy/binaries/python/versions/3.13.12/python.exe -m venv .venv
.\.venv\Scripts\activate

# 3. 安装依赖
pip install -r requirements.txt
pip install -e .

# 4. 运行
python main.py
```

## 测试

```powershell
python -m pytest tests/test_pdf_engine.py -v
```

## 项目结构

```
pdf-editor/
├── src/pdf_editor/   # 核心引擎与 UI
├── tests/            # 单元测试
├── docs/design.md    # 架构设计
├── OPTIMIZATION.md   # 10 轮优化迭代报告
├── main.py           # 入口
└── requirements.txt
```

## 优化迭代

本项目经过 10 轮性能优化迭代，覆盖启动速度、处理速度和内存占用。详见 [OPTIMIZATION.md](./OPTIMIZATION.md)。
