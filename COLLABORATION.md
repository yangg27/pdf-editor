# WorkBuddy 多角色协同开发指南

本项目使用 WorkBuddy 的多 Agent 协作能力完成。下面是你自己继续扩展时的标准操作流程。

## 一、角色定义

| 角色 | 名称建议 | 职责 |
|---|---|---|
| 项目经理 | `pm` | 维护 TaskList，拆分任务，协调阻塞 |
| 架构师 | `architect` | 写/更新 `docs/design.md`，定义接口契约 |
| PDF 引擎开发 | `engine-dev` | 维护 `src/pdf_editor/pdf_engine.py` |
| UI 开发 | `ui-dev` | 维护 `src/pdf_editor/ui.py` |
| 测试/QA | `qa` | 维护 `tests/`，运行测试，输出报告 |

## 二、在 WorkBuddy 中创建团队

在对话中使用：

```text
TeamCreate -> 创建团队，例如 pdf-editor-team
```

然后为每个角色创建一个 Agent：

```text
Agent(name="pm", subagent_type="general-purpose", prompt="你是 pdf-editor 的项目经理...")
Agent(name="architect", subagent_type="Plan", prompt="你是架构师，只读，负责 review 设计...")
Agent(name="engine-dev", subagent_type="general-purpose", prompt="你负责实现 pdf_engine.py...")
Agent(name="ui-dev", subagent_type="general-purpose", prompt="你负责实现 ui.py...")
Agent(name="qa", subagent_type="general-purpose", prompt="你负责测试...")
```

## 三、协作流程

1. **项目经理** 创建 TaskList 并分配任务。
2. **架构师** 先输出/确认 `docs/design.md`。
3. **engine-dev** 和 **ui-dev** 并行开发，严格按接口契约。
4. **qa** 编写测试，发现问题后给对应角色提 bug。
5. 所有角色通过 `TaskUpdate` 更新进度。

## 四、关键规则

- **先定设计再写代码**：任何接口变更必须先改 `docs/design.md`。
- **一个功能一个任务**：不要在一个任务里同时改引擎和 UI。
- **测试驱动**：engine-dev 提交功能后，qa 必须补充对应测试并通过。
- **统一入口**：最终运行都是 `python main.py`。

## 五、扩展建议

下一阶段可以新增：

- 页面可视化缩略图
- 加密/解密 PDF
- 压缩 PDF
- 导出为图片

每新增一个功能，按“设计 → 引擎 → UI → 测试”四步走。
