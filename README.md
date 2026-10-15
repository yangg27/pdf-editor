# PDF 编辑器

本地桌面 PDF 编辑软件，界面参照 **WPS PDF** 设计，基于 Python + tkinter/ttkbootstrap + PyMuPDF。支持 Windows 10/11。

> 当前版本 **v0.2.0** —— 采用 WPS 风格三栏布局（工具栏 + 缩略图导航 + 页面预览）。

## 功能

- **合并** 多个 PDF 为一个文件
- **拆分** 按页码范围拆成多个文件
- **旋转** 当前页 90° / 180°（校正扫描件）
- **重排** 页面顺序
- **删除** 当前页
- **提取** 指定页面另存
- **插入** 另一个 PDF 的页面
- **文字水印**（支持中文，45° 斜向居中）
- **图片水印**（印章 / Logo）
- **提取文字**

## 界面特性

- WPS 风格 Ribbon 分组工具栏（文件 / 页面 / 旋转 / 插入 / 水印 / 工具）
- 左侧页面缩略图导航，点击即跳转
- 中间页面实时预览，支持滚轮翻页、缩放、适应宽度
- 底部操作日志与状态栏（页码 / 缩放 / 翻页按钮）
- WPS 蓝主题

## Windows 下载即用

下载 `dist/pdf-editor-win10.zip`，解压后双击 `PDF编辑器.exe` 即可运行（绿色免安装）。

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
# 单元测试（15 项）
python -m pytest tests/test_pdf_engine.py -v

# 完整功能测试（12 项，含 exe 启动验证与页面渲染）
python integration_test.py
```

## 打包

```powershell
python build.py
```

将在 `dist/` 目录生成：

- `PDF编辑器.exe`：单文件可执行程序
- `pdf-editor-win10.zip`：绿色版压缩包

## 操作手册

- `docs/PDF编辑器操作手册.docx`：图文并茂操作手册（Word）
- `docs/manual.html`：手册源文件（图片 base64 内嵌）
- `docs/images/`：手册配图（软件实测截图 + 效果图）

## 项目结构

```
pdf-editor/
├── src/pdf_editor/
│   ├── pdf_engine.py   # PDF 引擎：合并/拆分/旋转/重排/增删页/水印/提取/渲染
│   └── ui.py           # WPS 风格界面
├── tests/              # 单元测试
├── docs/               # 设计文档、操作手册与配图
├── build.py            # 打包脚本
├── build_manual.py     # 手册生成脚本
├── tools_capture_ui.py # 手册配图截图脚本
├── integration_test.py # 完整功能测试
├── main.py             # 入口
└── requirements.txt
```

## 优化迭代

本项目经过 10 轮性能优化迭代，覆盖启动速度、处理速度和内存占用。详见 [OPTIMIZATION.md](./OPTIMIZATION.md)。