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

VERSION = "v0.3.1"


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
.kbd { background:#1e293b; color:#f8fafc; padding:1pt 5pt; border-radius:3pt;
       font-family:Consolas,monospace; font-size:9.5pt; }
.pagebreak { page-break-before:always; }
"""


def build_html() -> str:
    css = STYLE
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>PDF 编辑器 操作手册</title><style>{css}</style></head><body>

<h1>PDF 编辑器 操作手册</h1>
<p class="subtitle">Windows 桌面版 · 图文操作指南</p>
<p class="meta">版本 {VERSION} &nbsp;|&nbsp; 适用平台：Windows 10 / 11（64 位） &nbsp;|&nbsp; 生成日期：{time.strftime('%Y-%m-%d')}</p>

<h2>一、软件简介</h2>
<p>PDF 编辑器是一款<b>轻量、完全离线</b>的本地桌面 PDF 工具，界面参照 WPS PDF 设计，采用 Ribbon 工具栏 + 三栏布局，提供页面可视化预览与完整的页面级编辑能力。所有操作均在<b>本机完成</b>，文件不会上传到任何服务器。</p>

<h3>1.1 核心特性</h3>
<table>
<tr><th style="width:26%">特性</th><th>说明</th></tr>
<tr><td>功能齐全</td><td>覆盖 40+ 项操作：页面管理、批注、水印、加密、压缩、内容提取与导出</td></tr>
<tr><td>安全可靠</td><td>原文件全程只读不修改；编辑在临时副本上进行，保存时才原子替换目标文件</td></tr>
<tr><td>可撤销</td><td>内置撤销 / 重做栈，误操作可一键回退（默认保留最近 20 步）</td></tr>
<tr><td>加密兼容</td><td>支持打开带口令的 PDF，也可为文档设置 AES-256 加密与权限限制</td></tr>
<tr><td>内存友好</td><td>预览与缩略图采用缓存上限 + 像素上限策略，长时间浏览大文件不涨内存</td></tr>
</table>

<h3>1.2 功能一览</h3>
<table>
<tr><th style="width:22%">分类</th><th>功能</th></tr>
<tr><td>文件</td><td>打开、保存、另存为、合并、压缩、最近打开记录、拖拽打开</td></tr>
<tr><td>页面</td><td>旋转（左/右/180°）、删除、复制、移动（上移/下移/绝对定位）、重排、提取、拆分、插入 PDF、插入空白页、统一页面尺寸</td></tr>
<tr><td>批注</td><td>高亮、下划线、删除线、矩形、椭圆、图章、手绘、便签、文本框、密文遮盖（脱敏涂黑）</td></tr>
<tr><td>水印 / 页眉</td><td>文字水印、图片水印、页码、页眉页脚</td></tr>
<tr><td>内容</td><td>提取文字、导出页面为图片、逐页导出文本、提取内嵌图片、表格识别、全文查找</td></tr>
<tr><td>安全与属性</td><td>加密码、解除密码、文档属性、书签目录管理、页面标签</td></tr>
</table>
{figure("01_main_ui.png", "图 1　PDF 编辑器主界面", "94%")}

<h2>二、安装与启动</h2>
<h3>2.1 使用发布包（推荐）</h3>
<div class="step"><b>第 1 步</b>　获取发布包中的 <code>pdf-editor-win10.zip</code>，解压到任意目录（如 <code>D:\\PDF编辑器</code>）。</div>
<div class="step"><b>第 2 步</b>　双击其中的 <code>PDF编辑器.exe</code> 即可运行。</div>
<div class="tip"><b>提示：</b>本软件为<b>绿色免安装</b>程序，无需安装、不写注册表，删除文件夹即可完全卸载。首次运行如遇 Windows 防火墙或安全提示，选择"允许运行"即可。</div>

<h3>2.2 命令行参数</h3>
<table>
<tr><th style="width:42%">命令</th><th>作用</th></tr>
<tr><td><code>PDF编辑器.exe</code></td><td>启动图形界面</td></tr>
<tr><td><code>PDF编辑器.exe --version</code></td><td>打印版本号</td></tr>
<tr><td><code>PDF编辑器.exe --help</code></td><td>打印帮助信息</td></tr>
<tr><td><code>PDF编辑器.exe 报告.pdf</code></td><td>启动并直接打开指定文件</td></tr>
</table>

<h3>2.3 使用源码运行（开发者）</h3>
<div class="step"><b>第 1 步</b>　确保已安装 Python 3.10 及以上版本。</div>
<div class="step"><b>第 2 步</b>　在源码目录执行：<code>pip install -r requirements.txt</code></div>
<div class="step"><b>第 3 步</b>　执行 <code>python main.py</code> 启动程序。</div>

<h2 class="pagebreak">三、界面总览</h2>
<p>程序启动后进入主界面，自上而下依次为：<b>菜单栏</b>、<b>Ribbon 工具栏</b>、<b>主工作区</b>（左缩略图 + 中预览）、<b>底部信息面板</b>、<b>状态栏</b>。</p>
{figure("10_main_ui_annotated.png", "图 2　主界面功能分区说明", "96%")}
<table>
<tr><th style="width:12%">编号</th><th style="width:24%">区域</th><th>作用</th></tr>
<tr><td>①</td><td>菜单栏 + Ribbon 工具栏</td><td>Ribbon 按「开始 / 页面 / 批注 / 水印 / 工具 / 视图」六个页签分组，每个页签内再按功能块划分，图标按钮一目了然</td></tr>
<tr><td>②</td><td>页面缩略图</td><td>显示全部页面缩略图；单击跳转、<code>Ctrl</code>/<code>Shift</code> 多选、右键弹出批量操作菜单</td></tr>
<tr><td>③</td><td>页面预览区</td><td>大图预览当前页；支持滚轮翻页、<code>Ctrl</code>+滚轮缩放、拖拽平移</td></tr>
<tr><td>④</td><td>信息面板</td><td>三个页签：<b>操作日志</b> / <b>目录书签</b> / <b>批注</b></td></tr>
<tr><td>⑤</td><td>状态栏</td><td>页码、缩放比例、上一页/下一页按钮、页码跳转框</td></tr>
</table>

<h3>3.1 Ribbon 六个页签</h3>
{figure("12_ribbon_pages.png", "图 3　Ribbon 工具栏（页签下方按功能分组）", "100%")}
<table>
<tr><th style="width:14%">页签</th><th>包含操作</th></tr>
<tr><td>开始</td><td>文件（打开 / 保存 / 合并 / 压缩）、编辑（撤销 / 重做 / 复制页 / 删除页）、旋转（左转 / 右转 / 180°）、视图（缩小 / 放大 / 适宽 / 整页）、查找</td></tr>
<tr><td>页面</td><td>空白页、提取页、拆分、重排、上移、下移、统一为 A4 / Letter</td></tr>
<tr><td>批注</td><td>高亮、下划线、删除线、矩形、椭圆、图章、手绘、便签、文本框、清除本页、涂黑脱敏、加书签</td></tr>
<tr><td>水印</td><td>文字水印、图片水印、插入页码、页眉页脚</td></tr>
<tr><td>工具</td><td>提取文字、导出图片、导出文本、提取图片、加密码、解除密码、压缩优化、文档属性、书签目录、表格识别</td></tr>
<tr><td>视图</td><td>放大、缩小、适应宽度、适应页面、缩略图开关、信息面板开关</td></tr>
</table>
<div class="tip"><b>菜单栏：</b>顶部菜单（文件 / 编辑 / 视图 / 页面 / 插入 / 水印 / 批注 / 工具 / 帮助）提供同样的功能入口，便于键盘操作。</div>

<h3>3.2 快捷键</h3>
<table>
<tr><th style="width:34%">快捷键</th><th>作用</th></tr>
<tr><td><span class="kbd">Ctrl</span> + <span class="kbd">O</span></td><td>打开 PDF</td></tr>
<tr><td><span class="kbd">Ctrl</span> + <span class="kbd">S</span></td><td>保存</td></tr>
<tr><td><span class="kbd">Ctrl</span> + <span class="kbd">Shift</span> + <span class="kbd">S</span></td><td>另存为</td></tr>
<tr><td><span class="kbd">Ctrl</span> + <span class="kbd">Z</span> / <span class="kbd">Ctrl</span> + <span class="kbd">Y</span></td><td>撤销 / 重做</td></tr>
<tr><td><span class="kbd">Ctrl</span> + <span class="kbd">F</span></td><td>打开查找栏</td></tr>
<tr><td><span class="kbd">Ctrl</span> + <span class="kbd">滚轮</span></td><td>缩放预览</td></tr>
<tr><td><span class="kbd">PgUp</span> / <span class="kbd">PgDn</span></td><td>上一页 / 下一页</td></tr>
<tr><td><span class="kbd">Esc</span></td><td>取消当前标注 / 关闭查找栏</td></tr>
</table>

<h2 class="pagebreak">四、打开文件与页面浏览</h2>
<h3>4.1 打开 PDF</h3>
<div class="step"><b>方式一</b>　点击 Ribbon「开始 → 打开」按钮，或按 <span class="kbd">Ctrl</span>+<span class="kbd">O</span>，在对话框中选择文件。</div>
<div class="step"><b>方式二</b>　直接把 PDF 文件<b>拖拽</b>到程序窗口中释放。</div>
<div class="step"><b>方式三</b>　双击 exe 时带上文件路径参数：<code>PDF编辑器.exe 报告.pdf</code>。</div>
<div class="step"><b>方式四</b>　从「文件 → 最近打开」中快速选择最近用过的文件。</div>
<p>打开后左侧自动生成全部页面缩略图，中间显示第 1 页大图，标题栏显示文件名，状态栏显示总页数。</p>
<div class="warn"><b>加密文档：</b>若 PDF 设有打开口令，程序会弹窗要求输入口令；口令错误或取消输入则不会打开该文件。</div>

<h3>4.2 页面缩略图导航</h3>
{figure("11_thumbnail_panel.png", "图 4　缩略图面板：支持单击跳转、多选与右键菜单", "30%")}
<table>
<tr><th style="width:36%">操作</th><th>效果</th></tr>
<tr><td>单击缩略图</td><td>跳转到该页并在预览区显示</td></tr>
<tr><td><span class="kbd">Ctrl</span> + 单击</td><td>加选 / 减选（多选不连续页）</td></tr>
<tr><td><span class="kbd">Shift</span> + 单击</td><td>区间选择（选中两页之间的所有页）</td></tr>
<tr><td>右键缩略图</td><td>弹出菜单：删除 / 提取 / 旋转 / 上移 / 下移 / 复制 / 设尺寸 / 全选 / 清除选择</td></tr>
</table>
<div class="tip"><b>目标页规则：</b>当缩略图中选中了多页时，工具栏上的页面类操作（旋转、删除、提取、加水印等）<b>只作用于选中的页面</b>；未选中任何页时作用于当前页。</div>

<h3>4.3 翻页与缩放</h3>
<table>
<tr><th style="width:36%">操作</th><th>效果</th></tr>
<tr><td>预览区滚动鼠标滚轮</td><td>向下滚 = 下一页，向上滚 = 上一页</td></tr>
<tr><td><span class="kbd">Ctrl</span> + 滚轮</td><td>以鼠标位置为中心缩放预览</td></tr>
<tr><td>状态栏「上一页 / 下一页」</td><td>逐页前后翻页</td></tr>
<tr><td>状态栏「跳至」输入框</td><td>输入页码后回车，直接跳转</td></tr>
<tr><td>Ribbon「开始 → 放大 / 缩小」</td><td>按步长调整缩放（20% ~ 500%）</td></tr>
<tr><td>Ribbon「开始 → 适宽 / 整页」</td><td>自动适应预览区宽度 / 整页显示</td></tr>
<tr><td>在预览区拖拽</td><td>手动平移视图</td></tr>
</table>

<h2 class="pagebreak">五、页面管理</h2>
<h3>5.1 旋转页面</h3>
<p>用于校正横向或倒置的扫描件。</p>
<div class="step"><b>第 1 步</b>　定位到目标页（可多选）。</div>
<div class="step"><b>第 2 步</b>　点击 Ribbon「开始 → 左转 / 右转 / 180°」。</div>
<div class="step"><b>第 3 步</b>　预览区立即显示旋转结果；如有误可按 <span class="kbd">Ctrl</span>+<span class="kbd">Z</span> 撤销。</div>
{figure("06_rotate_effect.png", "图 5　旋转前后对比：纵向页面变为横向（90°）", "100%")}

<h3>5.2 删除与复制页面</h3>
<div class="step"><b>删除</b>　选中页面后点击 Ribbon「开始 → 删除页」，或右键缩略图选择"删除所选页"。</div>
<div class="step"><b>复制</b>　点击「开始 → 复制页」，将当前页复制并追加到文档末尾。</div>
<div class="warn"><b>注意：</b>程序要求文档至少保留一页。若试图删除全部页面，操作会被拒绝并提示。</div>

<h3>5.3 移动与重排页面</h3>
<div class="step"><b>逐页移动</b>　选中页后点击 Ribbon「页面 → 上移 / 下移」，每次移动一位。</div>
<div class="step"><b>自由重排</b>　点击 Ribbon「页面 → 重排」，在对话框中输入新页序，用英文逗号分隔，例如 <code>3,1,2</code>。</div>
{figure("07_reorder_effect.png", "图 6　按 3,1,2 重排后：新第 1 页为原第 3 页，依次类推", "92%")}
<div class="warn"><b>注意：</b>所填数字必须恰好是 1 到总页数的<b>完整排列</b>（每页出现且仅出现一次），否则程序会提示错误。</div>

<h3>5.4 提取、拆分与插入</h3>
<table>
<tr><th style="width:20%">操作</th><th>步骤</th></tr>
<tr><td>提取指定页</td><td>点「页面 → 提取页」，输入页码（如 <code>1,3,5</code>），选择保存位置</td></tr>
<tr><td>拆分文件</td><td>点「页面 → 拆分」，输入拆分方式：<code>each</code> 每页一个文件 / 数字 N 每 N 页一个文件 / 范围 <code>1-3,4-6</code>，再选择输出目录</td></tr>
<tr><td>插入 PDF</td><td>点「页面 → 插入PDF」，选择文件，从子菜单指定插入位置（末尾 / 最前 / 当前页后）</td></tr>
<tr><td>插入空白页</td><td>点「页面 → 空白页」，输入尺寸（<code>a4</code>/<code>a3</code>/<code>a5</code>/<code>letter</code>/<code>legal</code>/<code>same</code>），插入到当前页之后</td></tr>
<tr><td>统一页面尺寸</td><td>点「页面 → A4」或「Letter」，把目标页统一为标准尺寸</td></tr>
</table>
{figure("04_merge_effect.png", "图 7　合并：3 个文件（3+2+2 页）合并为 7 页的单一 PDF", "100%")}
{figure("05_split_effect.png", "图 8　拆分：按 1-1、2-3 两段拆分，生成 2 个独立文件", "86%")}

<h2 class="pagebreak">六、批注与标注</h2>
<p>Ribbon「批注」页签提供 9 种批注工具。用法统一：<b>先点工具按钮，再在预览区拖拽出区域</b>（便签与图章为单击落点）。</p>
<table>
<tr><th style="width:18%">工具</th><th>说明</th></tr>
<tr><td>高亮 / 下划线 / 删除线</td><td>在文字上拖拽，生成对应标记</td></tr>
<tr><td>矩形 / 椭圆</td><td>拖拽出矩形或椭圆框，用于圈注</td></tr>
<tr><td>图章</td><td>单击落点，加盖预设图章（如 Approved）</td></tr>
<tr><td>手绘</td><td>按住鼠标自由绘制曲线</td></tr>
<tr><td>便签</td><td>单击落点生成便签图标，可填写文字内容</td></tr>
<tr><td>文本框</td><td>拖拽出区域后输入文字，直接写在页面上</td></tr>
</table>
{figure("18_annotation.png", "图 9　批注效果：高亮 / 下划线 / 矩形 / 便签 / 图章", "88%")}

<h3>6.1 管理已有批注</h3>
<div class="step"><b>查看</b>　切换到信息面板的<b>批注</b>页签，列出全文档所有批注（页码 / 类型 / 内容 / 说明）。</div>
<div class="step"><b>定位</b>　双击批注行即可跳转到该批注所在页面。</div>
<div class="step"><b>删除</b>　选中批注行后点「删除所选」；或点「全部清除」移除整篇文档的批注。</div>
{figure("13_annot_panel.png", "图 10　批注面板：集中管理全文档批注", "100%")}

<h3>6.2 密文遮盖（脱敏涂黑）</h3>
<p>用于对外发布前<b>彻底移除</b>敏感信息。与普通黑色矩形不同，密文遮盖会把区域内的文字与图像<b>真正从文件中删除</b>，无法通过复制文本或提取图像还原。</p>
<div class="step"><b>第 1 步</b>　点击 Ribbon「批注 → 涂黑脱敏」。</div>
<div class="step"><b>第 2 步</b>　在预览区拖拽框选要遮盖的区域。</div>
<div class="step"><b>第 3 步</b>　区域被涂黑，同时底层内容已被移除。</div>
{figure("19_redaction.png", "图 11　密文遮盖前后：左侧原文可读，右侧内容已被彻底移除", "100%")}
<div class="warn"><b>重要：</b>密文遮盖是<b>不可恢复</b>操作。建议先「另存为」一份副本再执行脱敏。</div>

<h2 class="pagebreak">七、水印、页码与页眉页脚</h2>
<h3>7.1 文字水印</h3>
<div class="step"><b>第 1 步</b>　点击 Ribbon「水印 → 文字水印」。</div>
<div class="step"><b>第 2 步</b>　在对话框中填写水印文字、不透明度、旋转角度、字号与颜色。</div>
<div class="step"><b>第 3 步</b>　确认后水印应用到目标页。</div>
{figure("08_text_watermark.png", "图 12　中文文字水印（45° 斜向、居中、半透明）", "76%")}
<div class="tip"><b>提示：</b>程序会自动选用系统中文字体，并做<b>空格与连字符保真校验</b>——确保水印文字能用"查找"搜到、能正常复制，不会因字体映射问题变成不可搜索的字符。</div>

<h3>7.2 图片水印</h3>
<div class="step"><b>第 1 步</b>　点击 Ribbon「水印 → 图片水印」。</div>
<div class="step"><b>第 2 步</b>　选择图片（支持 <code>png / jpg / jpeg</code>／<code>bmp</code>）。</div>
<div class="step"><b>第 3 步</b>　设置不透明度、缩放比例与旋转角度后确认。</div>
{figure("09_image_watermark.png", "图 13　图片水印（示例印章居中叠加于每页）", "76%")}
<div class="tip"><b>提示：</b>建议使用<b>带透明通道的 PNG</b> 图片，叠加效果更自然。</div>

<h3>7.3 页码与页眉页脚</h3>
<div class="step"><b>页码</b>　点「水印 → 插入页码」，可设置格式（支持 <code>{{page}}</code> / <code>{{total}}</code> 占位符）、位置、起始页码、字号，以及"首页不显示"。</div>
<div class="step"><b>页眉页脚</b>　点「水印 → 页眉页脚」，分别填写页眉与页脚文本（支持 <code>{{page}}</code> / <code>{{total}}</code> / <code>{{name}}</code> 占位符），并各自选择对齐位置。</div>
{figure("17_page_number.png", "图 14　页码居中、页眉居中、页脚左对齐，三者互不遮挡", "88%")}
<div class="tip"><b>避免重叠：</b>页脚默认靠左、页码默认居中，因此同时使用时不会叠在一起。若需调整，可在对话框中修改各自的位置选项。</div>

<h2 class="pagebreak">八、内容提取与导出</h2>
<h3>8.1 提取文字</h3>
<div class="step"><b>第 1 步</b>　点击 Ribbon「工具 → 提取文字」。</div>
<div class="step"><b>第 2 步</b>　弹出"提取的文字"窗口展示全文，可框选复制。</div>
{figure("02_extract_text.png", "图 15　「提取的文字」结果窗口", "82%")}
<div class="warn"><b>注意：</b>提取文字依赖 PDF 内置的文本层。若文件是<b>纯图片扫描件</b>（未做 OCR），将无法提取出文字。</div>

<h3>8.2 导出与提取</h3>
<table>
<tr><th style="width:24%">操作</th><th>说明</th></tr>
<tr><td>导出图片</td><td>把页面渲染为图片文件。可选输出目录、页码范围、格式（PNG / JPG）与 DPI</td></tr>
<tr><td>导出文本</td><td>把每页文字导出为独立的 <code>.txt</code> 文件</td></tr>
<tr><td>提取图片</td><td>抽取文档中内嵌的原始位图（不经重采样），可选最小尺寸过滤</td></tr>
<tr><td>表格识别</td><td>自动识别页面中的表格结构，导出为可编辑的表格数据</td></tr>
</table>

<h3>8.3 全文查找</h3>
<div class="step"><b>第 1 步</b>　按 <span class="kbd">Ctrl</span>+<span class="kbd">F</span> 打开查找栏，输入关键字后回车。</div>
<div class="step"><b>第 2 步</b>　命中结果会在页面高亮显示，右侧提示"第 N / M 处"。</div>
<div class="step"><b>第 3 步</b>　点「上一个 / 下一个」在命中之间跳转；点「区分大小写」可切换精确匹配。</div>
{figure("14_find_bar.png", "图 16　查找栏：支持上一处/下一处跳转与区分大小写", "100%")}

<h2>九、安全与文档属性</h2>
<h3>9.1 加密与解密</h3>
<div class="step"><b>加密</b>　点「工具 → 加密码」，分别设置"打开口令"与"权限口令"，并勾选允许的操作（打印 / 复制 / 修改 / 批注）。输出文件使用 <b>AES-256</b> 加密。</div>
<div class="step"><b>解密</b>　点「工具 → 解密码」，输入正确口令后即可移除限制。</div>
{figure("16_encrypt.png", "图 17　加密保护对话框", "62%")}
<div class="warn"><b>请务必牢记口令：</b>PDF 加密后无法通过本软件找回口令。口令遗失则该文件将无法打开。</div>

<h3>9.2 文档属性</h3>
<p>点「工具 → 文档属性」可编辑标题、作者、主题、关键字等元数据。填写规范的属性有助于文件检索与归档。</p>
{figure("15_properties.png", "图 18　文档属性编辑对话框", "62%")}

<h3>9.3 书签与目录</h3>
<div class="step"><b>添加</b>　定位到页面后点「批注 → 加书签」，输入书签标题。</div>
<div class="step"><b>查看 / 跳转</b>　切换到信息面板的<b>目录书签</b>页签，双击条目即可跳转。</div>
<div class="step"><b>删除</b>　选中条目后删除。</div>

<h3>9.4 压缩优化</h3>
<p>点「工具 → 压缩优化」，程序会清理冗余对象、做字体子集化并对图像降采样。可选 DPI 与图片质量。</p>
{figure("20_compress.png", "图 19　压缩效果：清理冗余对象 + 字体子集化 + 图像降采样", "86%")}

<h2 class="pagebreak">十、操作日志与状态反馈</h2>
<p>界面底部的<b>操作日志</b>会记录每一步操作，包括打开的文件、输出的路径与结果，便于回溯核对。发生错误时，日志会以红色标记显示具体原因。</p>
{figure("03_operation_log.png", "图 20　操作日志区实时反馈每一步结果", "100%")}
<div class="tip"><b>进度提示：</b>处理大文件（如打开、导出、压缩）时，状态栏右侧会显示进度动画与说明文字，界面保持可响应，不会卡死。</div>

<h2>十一、常见问题（FAQ）</h2>
<table>
<tr><th style="width:36%">问题</th><th>解决办法</th></tr>
<tr><td>双击 exe 没有反应</td><td>确认系统为 Win10 及以上 64 位；将文件解压后再运行，不要在压缩包内直接双击。</td></tr>
<tr><td>预览区空白 / 未显示</td><td>请先打开一个 PDF 文件；未打开文件时预览区会提示"打开一个 PDF 文件后在此预览"。</td></tr>
<tr><td>打开时提示"文件可能损坏"</td><td>该文件不是有效的 PDF，或下载/传输过程中损坏。可用其他阅读器交叉验证。</td></tr>
<tr><td>中文水印显示为方块/乱码</td><td>确保系统已安装中文字体（微软雅黑/黑体/宋体）。本版本已内置中文字体回退，正常情况下不会乱码。</td></tr>
<tr><td>水印文字搜索不到</td><td>本版本已修复字体映射问题，水印与页码中的空格均可被搜索。若仍异常，请反馈具体字体环境。</td></tr>
<tr><td>拆分提示"无效页码范围"</td><td>检查输入格式（如 <code>1-3,4-6</code>）及页码是否超出原文件总页数。</td></tr>
<tr><td>重排提示"必须是完整排列"</td><td>输入数字须为 1…总页数的完整排列，不重复、不遗漏。</td></tr>
<tr><td>删除时报"不能删除全部页面"</td><td>程序要求至少保留一页，请勿删除唯一剩余页面。</td></tr>
<tr><td>误操作了怎么办</td><td>按 <span class="kbd">Ctrl</span>+<span class="kbd">Z</span> 撤销（可连续撤销最近 20 步），<span class="kbd">Ctrl</span>+<span class="kbd">Y</span> 重做。</td></tr>
<tr><td>忘记加密口令</td><td>无法找回。加密 PDF 的口令不可逆，请务必妥善保管。</td></tr>
<tr><td>处理大文件较慢</td><td>耗时取决于文件页数与内容；缩略图较多时首屏渲染会稍慢，之后浏览流畅。</td></tr>
<tr><td>原文件会被修改吗？</td><td>不会。编辑在临时副本上进行，只有您主动点"保存"时才会写入；不保存则原文件完全不变。</td></tr>
</table>

<h2>十二、附录</h2>
<h3>12.1 运行环境</h3>
<table>
<tr><th style="width:30%">项目</th><th>说明</th></tr>
<tr><td>操作系统</td><td>Windows 10 / 11（64 位）</td></tr>
<tr><td>运行方式</td><td>绿色免安装（单文件 exe）或源码运行</td></tr>
<tr><td>核心引擎</td><td>PyMuPDF（pymupdf / fitz）</td></tr>
<tr><td>界面框架</td><td>tkinter + ttkbootstrap（WPS 蓝主题）</td></tr>
<tr><td>网络依赖</td><td>无，全离线运行</td></tr>
<tr><td>程序体积</td><td>单文件 exe 约 37.5 MB</td></tr>
</table>

<h3>12.2 稳定性与内存设计</h3>
<table>
<tr><th style="width:30%">机制</th><th>说明</th></tr>
<tr><td>原文件隔离</td><td>所有编辑在临时工作副本上进行，原文件全程只读</td></tr>
<tr><td>原子保存</td><td>先写入同目录临时文件，再 <code>os.replace</code> 原子替换，避免写入中断损坏文件</td></tr>
<tr><td>撤销快照</td><td>按内存上限自动裁剪（默认 20 步 / 96 MB），大文档自动降级而非卡死</td></tr>
<tr><td>预览缓存</td><td>预览缓存上限 6 张、缩略图缓存上限 200 张，超出即淘汰</td></tr>
<tr><td>像素上限</td><td>单页渲染像素上限 600 万，防止超大页面（或高倍缩放）撑爆内存</td></tr>
<tr><td>异常兜底</td><td>底层错误统一包装为可读提示；界面异常与后台任务异常均被捕获，不会导致程序退出</td></tr>
</table>

<h3>12.3 发布前测试情况</h3>
<p>发布前已对全部功能执行完整自动化测试，全部通过：</p>
<table>
<tr><th style="width:44%">测试类型</th><th>规模</th><th>结果</th></tr>
<tr><td>引擎单元测试</td><td>129 项</td><td>全部通过</td></tr>
<tr><td>引擎冒烟测试</td><td>55 项检查</td><td>全部通过</td></tr>
<tr><td>界面冒烟测试</td><td>41 个步骤</td><td>全部通过</td></tr>
<tr><td>端到端集成测试</td><td>26 个用例（含 exe 启动与 CLI 自检）</td><td>全部通过</td></tr>
<tr><td>性能与内存基准</td><td>渲染 / 打开 / 浏览 / 峰值内存</td><td>达标</td></tr>
</table>
<div class="tip"><b>说明：</b>本手册所有界面截图与功能效果图，均来自软件实测结果，非示意图。所有图中文字均可在 PDF 中正常搜索与复制。</div>

</body></html>"""


def main():
    html = build_html()
    OUT_HTML.write_text(html, encoding="utf-8")
    print(f"生成: {OUT_HTML}  ({len(html)} 字符)")


if __name__ == "__main__":
    main()