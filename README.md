# PDF 编辑器

本地桌面 PDF 编辑软件 MVP，基于 Python + tkinter/ttkbootstrap + PyMuPDF。支持 Windows 10/11。

## 功能

- 合并多个 PDF
- 按页码范围拆分 PDF
- 旋转页面（90°）
- 重排页面顺序
- 添加文字水印
- 添加图片水印
- 提取文字

## Windows 下载即用

下载 `dist/pdf-editor-win10.zip`，解压后双击 `PDF编辑器.exe` 即可运行。

## 源码运行

```powershell
# 1. 进入项目目录
cd pdf-editor

# 2. 创建并激活虚拟环境
python -m venv .venv
.\.venv\Scripts\activate

# 3. 安装依赖
pip install -r requirements.txt
pip install -e .

# 4. 运行
python main.py
```

## 测试

```powershell
# 单元测试
python -m pytest tests/test_pdf_engine.py -v

# 完整功能测试（含 exe 启动验证）
python integration_test.py
```

## 打包

```powershell
python build.py
```

将在 `dist/` 目录生成：
- `PDF编辑器.exe`：单文件可执行程序
- `pdf-editor-win10.zip`：绿色版压缩包

## 项目结构

```
pdf-editor/
├── src/pdf_editor/     # 核心引擎与 UI
├── tests/              # 单元测试
├── docs/design.md      # 架构设计
├── OPTIMIZATION.md     # 10 轮优化迭代报告
├── build.py            # 打包脚本
├── integration_test.py # 完整功能测试
├── main.py             # 入口
└── requirements.txt
```

## 优化迭代

本项目经过 10 轮性能优化迭代，覆盖启动速度、处理速度和内存占用。详见 [OPTIMIZATION.md](./OPTIMIZATION.md)。
