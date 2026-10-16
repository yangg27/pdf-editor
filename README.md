# PDF 编辑器

本地桌面 PDF 编辑软件，界面参照 **WPS PDF** 设计，基于 Python + tkinter/ttkbootstrap + PyMuPDF。支持 Windows 10/11。

> 在线仓库：<https://github.com/yangg27/pdf-editor> · 下载：[Releases](https://github.com/yangg27/pdf-editor/releases)

> 当前版本 **v0.3.0** —— Ribbon 工具栏 + 三栏布局；40+ 项功能；原文件隔离与原子保存；撤销/重做；内存受控。

## 功能

### 页面管理
- **合并** 多个 PDF 为一个文件
- **拆分** 每页一个文件 / 每 N 页一个文件 / 按范围拆分
- **旋转** 左转 / 右转 / 180°（可多选批量）
- **重排** 自定义页面顺序（如 `3,1,2`）
- **移动** 上移 / 下移 / 移动到指定位置
- **删除 / 复制** 页面
- **提取** 指定页面另存为新文件
- **插入** 另一个 PDF 的页面（末尾 / 最前 / 当前页后）
- **插入空白页**（可选 A4 / A3 / A5 / Letter / Legal / 与当前页相同）
- **统一页面尺寸**（A4 / Letter）

### 批注与标注
- 高亮 / 下划线 / 删除线 / 矩形 / 椭圆
- 图章 / 手绘 / 便签 / 文本框
- **密文遮盖（脱敏涂黑）** —— 真正移除底层文字与图像，不可恢复
- 批注集中管理（列举 / 定位 / 删除 / 按页清空 / 全部清除）

### 水印与页码
- **文字水印**（支持中文、任意角度、透明度；空格与连字符保真，可搜索可复制）
- **图片水印**（印章 / Logo，可调透明度与缩放）
- **插入页码**（支持 `{page}` / `{total}` 占位符，首页可跳过）
- **页眉页脚**（支持 `{page}` / `{total}` / `{name}`，页眉与页脚位置可分别设置）

### 内容提取与导出
- **提取文字**（全文 / 指定页 / 保留版式）
- **导出页面为图片**（PNG / JPG，可选 DPI 与页码范围）
- **逐页导出文本**（每页一个 `.txt`）
- **提取内嵌图片**（原始位图，可选最小尺寸）
- **表格识别**（导出为表格数据）
- **全文查找**（跨页、支持区分大小写）

### 安全与属性
- **加密**（AES-256，可设置打开口令 / 权限口令与打印、复制、修改、批注权限）
- **解密**
- **文档属性**（标题 / 作者 / 主题 / 关键字）
- **书签目录**（添加 / 删除 / 跳转）
- **压缩优化**（清理冗余对象 + 字体子集化 + 图像降采样）

## 界面特性

- Ribbon 分组工具栏，六个页签：**开始 / 页面 / 批注 / 水印 / 工具 / 视图**
- 左侧页面缩略图：单击跳转、`Ctrl`/`Shift` 多选、右键批量操作
- 中间页面实时预览：滚轮翻页、`Ctrl`+滚轮缩放、拖拽平移
- 底部信息面板：**操作日志 / 目录书签 / 批注** 三个页签
- 状态栏：页码 / 缩放 / 翻页 / 页码跳转
- 支持**拖拽打开**、**最近打开记录**
- WPS 蓝主题

## 稳定性设计

| 机制 | 说明 |
|---|---|
| 原文件隔离 | 所有编辑在临时工作副本上进行，原文件全程只读、字节不变 |
| 原子保存 | 先写同目录临时文件再 `os.replace` 替换，避免写入中断损坏文件 |
| 撤销 / 重做 | 快照栈按内存上限自动裁剪（默认 20 步 / 96 MB） |
| 统一异常 | 底层错误统一包装为 `PdfError`，界面层不会因未捕获异常退出 |
| 后台任务 | 耗时操作在后台线程执行，界面保持响应并显示进度 |
| 崩溃兜底 | 未捕获异常写入 `~/.pdf_editor/error.log` 并弹窗提示，不静默退出 |

## 内存控制

| 参数 | 值 | 说明 |
|---|---|---|
| 预览缓存 | 6 张 | 超出即淘汰（LRU） |
| 缩略图缓存 | 200 张 | 虚拟化：只创建可见单元格 |
| 单页渲染像素上限 | 600 万 | 防止高倍缩放或超大页面撑爆内存 |
| 撤销内存上限 | 96 MB | 超出自动降级而非卡死 |

## Windows 下载即用

前往 [Releases](https://github.com/yangg27/pdf-editor/releases) 下载：

| 文件 | 说明 |
|---|---|
| `PDFEditor-win10.exe` | 单文件绿色版，双击即用 |
| `pdf-editor-win10.zip` | 绿色包（含操作手册） |
| `PDFEditor-Manual.docx` | 图文操作手册（12 章 20 图） |

解压后双击 `PDF编辑器.exe` 即可运行（绿色免安装）。

命令行参数：

```powershell
PDF编辑器.exe --version        # 打印版本
PDF编辑器.exe --help           # 打印帮助
PDF编辑器.exe 报告.pdf         # 启动并直接打开文件
```

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
# 引擎单元测试（129 项）
python -m pytest tests/ -q

# 引擎冒烟测试（55 项检查）
python tools_smoke_engine.py

# 界面冒烟测试（41 个步骤）
python tools_smoke_ui.py

# 端到端集成测试（26 个用例，含 exe 启动与 CLI 自检）
python integration_test.py

# 性能与内存基准
python bench_v3.py
```

发布前实测结果：单元测试 129 项通过、引擎冒烟 55 项通过、界面冒烟 41 步通过、集成测试 26/26 通过。

## 打包

```powershell
python build.py
```

将在 `dist/` 目录生成：

- `PDF编辑器.exe`：单文件可执行程序（约 37.5 MB）
- `pdf-editor-win10.zip`：绿色版压缩包

打包脚本会自动：收集 `tkinterdnd2` 拖拽运行时、声明隐藏导入、嵌入应用图标，并在打包后自检 `--version` 与源码版本号是否一致。

## 操作手册

```powershell
# 1. 生成手册配图（界面截图 + 功能效果图，共 20 张）
python tools_capture_ui.py

# 2. 生成手册 HTML（图片 base64 内嵌）
python build_manual.py

# 3. 转换为 Word
python tools_make_docx.py
```

产物：

- `docs/PDF编辑器操作手册.docx`：图文并茂操作手册（Word）
- `docs/manual.html`：手册源文件（图片 base64 内嵌）
- `docs/images/`：手册配图（软件实测截图 + 效果图）

## 项目结构

```
pdf-editor/
├── src/pdf_editor/
│   ├── pdf_engine.py   # PDF 引擎（60+ 函数）：页面操作/水印/批注/加密/压缩/查找/导出
│   ├── ui.py           # Ribbon 界面与交互逻辑
│   ├── theme.py        # WPS 蓝色调与样式
│   ├── icons.py        # 45 个程序化矢量图标
│   └── tasks.py        # 后台任务调度
├── tests/              # 单元测试（129 项）
├── docs/               # 设计文档、操作手册与配图
├── assets/             # 应用图标
├── build.py            # 打包脚本
├── build_manual.py     # 手册生成脚本
├── tools_capture_ui.py # 手册配图截图脚本
├── tools_make_docx.py  # 手册转 Word
├── tools_smoke_engine.py # 引擎冒烟测试
├── tools_smoke_ui.py   # 界面冒烟测试
├── integration_test.py # 端到端集成测试
├── bench_v3.py         # 性能与内存基准
├── main.py             # 入口
└── requirements.txt
```

## 优化迭代

本项目经过 10 轮性能优化迭代，覆盖启动速度、处理速度和内存占用。详见 [OPTIMIZATION.md](./OPTIMIZATION.md)。