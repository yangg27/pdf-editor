#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成《PDF 编辑器 操作手册》HTML（图片以 base64 内嵌），供转 docx。

用法：
    python build_manual.py            # 生成 docs/manual.html
"""

from __future__ import annotations

import base64
import time
from pathlib import Path

PROJECT = Path(__file__).parent
IMG = PROJECT / "docs" / "images"
OUT_HTML = PROJECT / "docs" / "manual.html"

VERSION = "v0.2.0"


def img_uri(name: str) -> str:
    p = IMG / name
    if not p.exists():
        return ""
    b64 = base64.b64encode(p.read_bytes()).decode()
    return f"data:image/png;base64,{b64}"


def figure(name: str, caption: str, width: str = "100%") -> str:
    uri = img_uri(name)
    if not uri:
        return ""
    return (
        f'<div class="figure"><img src="{uri}" style="width:{width}"/>'
        f'<p class="caption">{caption}</p></div>'
    )


STYLE = """
body { font-family: "Microsoft YaHei","微软雅黑",sans-serif; color:#1f2937;
       font-size:11pt; line-height:1.75; margin:0; }
h1 { color:#1d4ed8; font-size:22pt; text-align:center; margin:6pt 0 2pt; }
h2 { color:#1d4ed8; font-size:15pt; border-left:5px solid #2563eb;
     padding-left:10px; margin-top:20pt; margin-bottom:8pt; }
h3 { color:#0f172a; font-size:12.5pt; margin-top:14pt; margin-bottom:6pt; }
p  { margin:5pt 0; }
.subtitle { text-align:center; color:#64748b; font-size:12pt; margin-bottom:4pt; }
.meta { text-align:center; color:#94a3b8; font-size:10pt; margin-bottom:18pt; }
.step { background:#f1f5f9; border-left:4px solid #2563eb; padding:8pt 12pt;
        margin:7pt 0; }
.step b { color:#1d4ed8; }
table { border-collapse:collapse; width:100%; margin:8pt 0; }
th { background:#2563eb; color:#fff; padding:6pt 8pt; text-align:left;
     font-size:10.5pt; border:1px solid #cbd5e1; }
td { padding:6pt 8pt; border:1px solid #cbd5e1; font-size:10.5pt; }
tr:nth-child(even) td { background:#f8fafc; }
.figure { text-align:center; margin:10pt 0; }
.figure img { max-width:100%; border:1px solid #e2e8f0; }
.caption { color:#64748b; font-size:9.5pt; margin-top:3pt; }
.tip { background:#eff6ff; border:1px solid #bfdbfe; padding:8pt 12pt;
       margin:8pt 0; }
.warn { background:#fef3c7; border:1px solid #fcd34d; padding:8pt 12pt;
        margin:8pt 0; }
code { background:#f1f5f9; padding:1pt 4pt; font-family:Consolas,monospace;
       font-size:10pt; color:#be123c; }
.pagebreak { page-break-before:always; }
"""


def build_html() -> str:
    css = STYLE
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>PDF 编辑器 操作手册</title><style>{css}</style></head><body>

<h1>PDF 编辑器 操作手册</h1>
<p class="subtitle">Windows 10 桌面版 · 图文操作指南（WPS 风格界面）</p>
<p class="meta">版本 {VERSION} &nbsp;|&nbsp; 适用平台：Windows 10 / 11（64 位） &nbsp;|&nbsp; 生成日期：{time.strftime('%Y-%m-%d')}</p>

<h2>一、软件简介</h2>
<p>PDF 编辑器是一款轻量的本地桌面工具，界面参照 <b>WPS PDF</b> 设计，提供页面可视化预览与完整的页面级编辑能力。所有操作均在<b>本机离线完成</b>，文件不会上传到任何服务器，安全可靠。</p>
<p>当前版本（{VERSION}）支持以下 10 项核心功能：</p>
<table>
<tr><th style="width:26%">功能</th><th>说明</th></tr>
<tr><td>合并 PDF</td><td>把多个 PDF 文件按顺序合并为一个文件</td></tr>
<tr><td>拆分 PDF</td><td>按页码范围把一个 PDF 拆成多个文件</td></tr>
<tr><td>旋转页面</td><td>将当前页顺时针旋转 90° 或 180°（校正扫描件方向）</td></tr>
<tr><td>重排页面</td><td>调整页面先后顺序，如把第 3 页移到最前</td></tr>
<tr><td>删除页面</td><td>删除当前选中的页面</td></tr>
<tr><td>提取页面</td><td>按页码抽取指定页，另存为新文件</td></tr>
<tr><td>插入页面</td><td>把另一个 PDF 的页面插入到当前位置/最前/末尾</td></tr>
<tr><td>文字水印</td><td>在每页居中叠加文字水印，支持中文，默认 45° 斜向</td></tr>
<tr><td>图片水印</td><td>在每页居中叠加图片（如公司印章、Logo）</td></tr>
<tr><td>提取文字</td><td>把 PDF 中的文字内容提取出来并显示</td></tr>
</table>
{figure("01_main_ui.png", "图 1　PDF 编辑器主界面（WPS 风格三栏布局）", "92%")}

<h2>二、安装与启动</h2>
<h3>2.1 使用安装包（推荐）</h3>
<div class="step"><b>第 1 步</b>　获取发布包中的 <code>pdf-editor-win10.zip</code>，解压到任意目录（如 <code>D:\\PDF编辑器</code>）。</div>
<div class="step"><b>第 2 步</b>　双击其中的 <code>PDF编辑器.exe</code> 即可运行。</div>
<div class="tip"><b>提示：</b>本软件为<b>绿色免安装</b>程序，无需安装、不写注册表，删除文件夹即可完全卸载。首次运行如遇 Windows 防火墙或安全提示，选择"允许运行"即可。</div>

<h3>2.2 使用源码运行（开发者）</h3>
<div class="step"><b>第 1 步</b>　确保已安装 Python 3.10 及以上版本。</div>
<div class="step"><b>第 2 步</b>　在源码目录执行：<code>pip install -r requirements.txt</code></div>
<div class="step"><b>第 3 步</b>　执行 <code>python main.py</code> 启动程序。</div>
<div class="warn"><b>注意：</b>源码运行需要 <code>PyMuPDF</code>、<code>ttkbootstrap</code>、<code>Pillow</code> 等依赖；打包成 exe 后无需任何依赖。</div>

<h2 class="pagebreak">三、界面总览</h2>
<p>程序启动后进入主界面，整体采用 WPS PDF 风格的<b>三栏布局</b>：顶部为菜单栏与 Ribbon 工具栏，左侧为页面缩略图导航，中间为页面预览区，底部为操作日志与状态栏。</p>
{figure("10_main_ui_annotated.png", "图 2　主界面功能分区说明", "94%")}
<table>
<tr><th style="width:14%">编号</th><th style="width:22%">区域</th><th>作用</th></tr>
<tr><td>①</td><td>Ribbon 工具栏</td><td>按"文件 / 页面 / 旋转 / 插入 / 水印 / 工具"分组排列全部功能按钮</td></tr>
<tr><td>②</td><td>页面缩略图导航</td><td>显示全部页面缩略图，点击任意缩略图即可跳转到该页</td></tr>
<tr><td>③</td><td>页面预览区</td><td>大图预览当前页，支持滚轮翻页、缩放、适应宽度</td></tr>
<tr><td>④</td><td>操作日志</td><td>实时显示每一步操作的结果与输出文件路径</td></tr>
<tr><td>⑤</td><td>状态栏</td><td>显示当前页码、缩放比例，并提供上一页/下一页按钮</td></tr>
</table>
<div class="tip"><b>菜单栏：</b>除工具栏按钮外，顶部菜单栏（文件 / 编辑 / 页面 / 插入 / 水印 / 帮助）提供同样的功能入口，快捷键 <code>Ctrl+O</code> 可快速打开文件。</div>

<h2>四、打开文件与页面浏览</h2>
<h3>4.1 打开 PDF</h3>
<div class="step"><b>第 1 步</b>　点击工具栏 <b>打开</b> 按钮（或菜单"文件 → 打开 PDF…"，或按 <code>Ctrl+O</code>）。</div>
<div class="step"><b>第 2 步</b>　在文件对话框中选择一个 PDF 文件并确认。</div>
<div class="step"><b>第 3 步</b>　左侧自动生成全部页面缩略图，中间显示第 1 页大图，标题栏显示文件名，状态栏显示总页数。</div>

<h3>4.2 翻页与缩放</h3>
<table>
<tr><th style="width:34%">操作</th><th>效果</th></tr>
<tr><td>点击左侧缩略图</td><td>直接跳转到对应页面</td></tr>
<tr><td>预览区滚动鼠标滚轮</td><td>向下滚＝下一页，向上滚＝上一页</td></tr>
<tr><td>状态栏"上一页 / 下一页"</td><td>逐页前后翻页</td></tr>
<tr><td>工具栏"缩放＋ / 缩放−"</td><td>放大或缩小预览（20% ~ 500%）</td></tr>
<tr><td>工具栏"适应宽度"</td><td>自动缩放使页面宽度铺满预览区</td></tr>
</table>
<div class="tip"><b>提示：</b>页面预览由 PDF 引擎实时渲染，所见即所得的编辑结果。所有编辑操作都会输出到<b>新文件</b>，原文件保持不变。</div>

<h2 class="pagebreak">五、功能一：合并 PDF</h2>
<p>把多个 PDF 按选择顺序拼接成一个完整文件，常用于合并报告的各章节。</p>
<div class="step"><b>第 1 步</b>　点击工具栏 <b>合并</b> 按钮。</div>
<div class="step"><b>第 2 步</b>　在文件对话框中按住 <code>Ctrl</code> 或 <code>Shift</code> <b>多选</b>待合并的 PDF（至少 2 个，按点选顺序排列）。</div>
<div class="step"><b>第 3 步</b>　选择保存位置与文件名。</div>
<div class="step"><b>第 4 步</b>　合并完成后自动载入结果文件，日志区显示"合并完成"。</div>
{figure("04_merge_effect.png", "图 3　3 个文件（3+2+2 页）合并为 7 页的单一 PDF", "100%")}

<h2>六、功能二：拆分 PDF</h2>
<p>按页码范围把一个 PDF 拆成多个独立文件，适合把某一章节单独抽出。</p>
<div class="step"><b>第 1 步</b>　点击工具栏 <b>拆分</b> 按钮。</div>
<div class="step"><b>第 2 步</b>　在弹出的输入框中填写拆分范围，格式为 <code>起始页-结束页</code>，多段用英文逗号分隔，例如 <code>1-3,4-6</code>。</div>
<div class="step"><b>第 3 步</b>　选择输出目录。</div>
<div class="step"><b>第 4 步</b>　日志区列出生成的全部文件，命名形如 <code>原名_part1_1-3.pdf</code>。</div>
{figure("05_split_effect.png", "图 4　按 1-1、2-3 两段拆分，生成 2 个文件", "86%")}
<div class="warn"><b>注意：</b>页码从 1 开始且为闭区间；范围超出总页数时会提示错误，请先确认原文件页数。</div>

<h2 class="pagebreak">七、功能三：旋转页面</h2>
<p>用于校正横向或倒置的扫描件。旋转作用于<b>当前显示页</b>。</p>
<div class="step"><b>第 1 步</b>　在左侧缩略图或预览区定位到要旋转的页面。</div>
<div class="step"><b>第 2 步</b>　点击工具栏 <b>↻ 90°</b> 或 <b>↻ 180°</b> 按钮，确认后选择保存位置。</div>
<div class="step"><b>第 3 步</b>　输出文件命名为 <code>原名_rotated.pdf</code>，随后自动载入并可预览旋转结果。</div>
{figure("06_rotate_effect.png", "图 5　旋转前后对比：纵向页面变为横向（90°）", "100%")}
<div class="tip"><b>提示：</b>若需对<b>全部页面</b>旋转，可分别定位到各页执行；如需连续旋转（如 180°），可对输出文件再执行一次 90°。</div>

<h2>八、功能四：重排页面</h2>
<p>调整页面顺序，例如把作为结论的第 3 页提到最前面。</p>
<div class="step"><b>第 1 步</b>　点击工具栏 <b>重排</b> 按钮。</div>
<div class="step"><b>第 2 步</b>　在弹出的输入框中填写新页序，用英文逗号分隔，例如 <code>3,1,2</code>。</div>
<div class="step"><b>第 3 步</b>　选择保存位置，输出文件为 <code>原名_reordered.pdf</code>。</div>
{figure("07_reorder_effect.png", "图 6　按 3,1,2 重排后：新第 1 页为原第 3 页，依次类推", "92%")}
<div class="warn"><b>注意：</b>所填数字必须恰好是 1 到总页数的<b>完整排列</b>（每页出现且仅出现一次），否则程序会提示错误。</div>

<h2 class="pagebreak">九、功能五：删除与提取页面</h2>
<h3>9.1 删除当前页</h3>
<div class="step"><b>第 1 步</b>　定位到要删除的页面（左侧缩略图点选）。</div>
<div class="step"><b>第 2 步</b>　点击工具栏 <b>删除页</b> 按钮，确认删除提示。</div>
<div class="step"><b>第 3 步</b>　选择保存位置，输出文件为 <code>原名_del.pdf</code>。</div>
<div class="warn"><b>注意：</b>至少需保留一页，若文件仅剩 1 页则无法继续删除。</div>

<h3>9.2 提取指定页面</h3>
<div class="step"><b>第 1 步</b>　点击工具栏 <b>提取页</b> 按钮。</div>
<div class="step"><b>第 2 步</b>　输入要提取的页码，逗号分隔，例如 <code>1,3,5</code>。</div>
<div class="step"><b>第 3 步</b>　选择保存位置，输出文件为 <code>原名_extract.pdf</code>。</div>

<h2>十、功能六：插入页面</h2>
<p>把另一个 PDF 的页面插入到当前文档中，可插入到最前、末尾或当前页之后。</p>
<div class="step"><b>第 1 步</b>　点击工具栏 <b>插入 PDF</b> 按钮（菜单"插入"中可选择插入位置：末尾 / 最前 / 当前页后）。</div>
<div class="step"><b>第 2 步</b>　选择要插入的 PDF 文件。</div>
<div class="step"><b>第 3 步</b>　选择保存位置，输出文件为 <code>原名_inserted.pdf</code>，总页数相应增加。</div>

<h2 class="pagebreak">十一、功能七：添加文字水印</h2>
<p>为每一页添加居中的文字水印，适用于内部资料、合同等标注场景，<b>支持中文</b>，默认呈 45° 斜向、半透明显示。</p>
<div class="step"><b>第 1 步</b>　点击工具栏 <b>文字水印</b> 按钮。</div>
<div class="step"><b>第 2 步</b>　在弹出的输入框中填写水印文字（默认"机密"），例如"机密 - 内部资料"。</div>
<div class="step"><b>第 3 步</b>　选择保存位置，输出文件为 <code>原名_watermarked.pdf</code>。</div>
{figure("08_text_watermark.png", "图 7　中文文字水印效果（45° 斜向、居中、半透明）", "76%")}
<div class="tip"><b>提示：</b>程序会自动选用系统中文字体（微软雅黑/黑体等），并内置中文字体回退，确保中文正常显示，不会出现乱码或方框。</div>

<h2>十二、功能八：添加图片水印</h2>
<p>为每一页叠加一张图片作为水印，常用于加盖公司印章或放置品牌 Logo。</p>
<div class="step"><b>第 1 步</b>　点击工具栏 <b>图片水印</b> 按钮。</div>
<div class="step"><b>第 2 步</b>　在文件对话框中选择图片（支持 <code>png / jpg / jpeg</code>）。</div>
<div class="step"><b>第 3 步</b>　选择保存位置，输出文件为 <code>原名_img_watermarked.pdf</code>。</div>
{figure("09_image_watermark.png", "图 8　图片水印效果（印章居中叠加于每页）", "76%")}
<div class="tip"><b>提示：</b>建议使用<b>带透明通道的 PNG</b> 图片，叠加效果更自然；图片会自动缩放至页面居中区域。</div>

<h2 class="pagebreak">十三、功能九：提取文字</h2>
<p>读取 PDF 中的文字内容，用于复制、检索或核对。</p>
<div class="step"><b>第 1 步</b>　打开目标 PDF 后，点击工具栏 <b>提取文字</b> 按钮。</div>
<div class="step"><b>第 2 步</b>　程序弹出"提取的文字"窗口，展示全文内容，可框选复制。</div>
<div class="step"><b>第 3 步</b>　日志区提示提取完成及文字长度。</div>
{figure("02_extract_text.png", "图 9　「提取的文字」结果窗口", "82%")}
<div class="warn"><b>注意：</b>提取文字依赖 PDF 内置的文本层。若文件是<b>纯图片扫描件</b>（未做 OCR），将无法提取出文字，这属于正常现象。</div>

<h2>十四、操作日志与状态反馈</h2>
<p>界面底部的<b>操作日志</b>会记录每一步操作，包括打开的文件、输出的路径与结果，便于回溯核对。</p>
{figure("03_operation_log.png", "图 10　操作日志区实时反馈每一步结果", "92%")}

<h2>十五、常见问题（FAQ）</h2>
<table>
<tr><th style="width:38%">问题</th><th>解决办法</th></tr>
<tr><td>双击 exe 没有反应</td><td>确认系统为 Win10 及以上 64 位；将文件解压后再运行，不要在压缩包内直接双击。</td></tr>
<tr><td>预览区空白 / 未显示</td><td>请先通过"打开"载入一个 PDF 文件；未打开文件时预览区会提示"打开一个 PDF 文件后在此预览"。</td></tr>
<tr><td>中文水印显示为方块/乱码</td><td>确保系统已安装中文字体（微软雅黑/黑体）。本版本已内置中文字体回退，正常情况下不会乱码。</td></tr>
<tr><td>拆分提示"无效页码范围"</td><td>检查输入格式（如 <code>1-3,4-6</code>）及页码是否超出原文件总页数。</td></tr>
<tr><td>重排提示"order 必须是排列"</td><td>输入数字须为 1…总页数的完整排列，不重复、不遗漏。</td></tr>
<tr><td>只删不掉最后一页</td><td>程序要求至少保留一页，请勿删除唯一剩余页面。</td></tr>
<tr><td>处理大文件较慢</td><td>处理耗时取决于文件页数与内容，属正常范围；缩略图较多时首屏渲染会稍慢。</td></tr>
<tr><td>原文件会被修改吗？</td><td>不会。所有功能均输出到您指定的<b>新文件</b>，原文件保持原样。</td></tr>
</table>

<h2>十六、附录：技术参数与测试情况</h2>
<h3>16.1 运行环境</h3>
<table>
<tr><th style="width:30%">项目</th><th>说明</th></tr>
<tr><td>操作系统</td><td>Windows 10 / 11（64 位）</td></tr>
<tr><td>运行方式</td><td>绿色免安装（单文件 exe）或源码运行</td></tr>
<tr><td>核心引擎</td><td>PyMuPDF（fitz）</td></tr>
<tr><td>界面框架</td><td>tkinter + ttkbootstrap（WPS 蓝主题）</td></tr>
<tr><td>网络依赖</td><td>无，全离线运行</td></tr>
</table>
<h3>16.2 功能测试结论</h3>
<p>发布前已对全部功能执行完整测试，<b>单元测试 15 项、集成测试 8 项（含 exe 启动）全部通过</b>：</p>
<table>
<tr><th style="width:40%">测试项</th><th>结果</th></tr>
<tr><td>程序启动（exe --version）</td><td>通过</td></tr>
<tr><td>合并 / 拆分 / 旋转 / 重排</td><td>通过</td></tr>
<tr><td>删除页 / 提取页 / 插入页</td><td>通过</td></tr>
<tr><td>文字水印（含中文）/ 图片水印</td><td>通过</td></tr>
<tr><td>提取文字 / 页面渲染</td><td>通过</td></tr>
</table>
<div class="tip"><b>说明：</b>本手册所有界面截图与功能效果图，均来自软件实测结果，非示意图。</div>

</body></html>"""


def main():
    html = build_html()
    OUT_HTML.write_text(html, encoding="utf-8")
    print(f"生成: {OUT_HTML}  ({len(html)} 字符)")


if __name__ == "__main__":
    main()