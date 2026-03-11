# literature-explainer 转换报告

## 1. 转换结论

- `status`: `succeeded`
- `classification`: `convertible_with_constraints`
- `execution_modes`: `["interactive"]`

## 2. 任务类型判断

结论：`产出文件型`

依据：

1. Skill 的可选最终产物是学习笔记文件，输出字段为 `note_path`。
2. 执行过程中会稳定生成 `source.md`、`source_meta.json` 和记忆文件，说明流程围绕文件产物组织。
3. 领域目标不是直接返回一次性文本，而是在需要时落盘学习笔记。

## 3. 双模式适配性评估

### 3.1 auto_suitability

- 结论：`unsuitable`

依据：

1. 原始 Skill 明确要求读完论文后等待用户指定当前意图。
2. Q&A 和笔记生成都依赖运行期的实时用户决策，无法从现有输入参数中唯一推出。
3. 笔记落盘前需要先展示内容并等待用户确认，这一关键步骤不适合无交互单轮执行。

### 3.2 interactive_suitability

- 结论：`suitable`

依据：

1. 原始状态机天然是多轮交互式设计。
2. 输入边界稳定，`source_path` 是唯一内容来源，`language` 是可选参数。
3. 核心脚本都能输出稳定 JSON，失败路径可验证，包括文件探测失败、证据验证失败、记忆不足和未确认笔记落盘。

## 4. 约束化决策

本次转换采用以下保守约束：

1. 不向 `SKILL.md` 直接插入 `__SKILL_DONE__`；interactive 完成依赖最终 stdout JSON 满足 output schema。
2. 最终输出合同只保留单字段 `note_path`。
3. `note_path` 为可选字段语义：不生成笔记时返回空字符串，不要求产出 note artifact。
4. 将 `pymupdf4llm` 视为必要运行时依赖，并在 runner 中显式声明。
5. 内部归一化文件与记忆文件降级为工作产物，不纳入最终输出 schema。

## 5. 变更文件

- `SKILL.md`
  - 补齐 Skill-Runner 执行说明、interactive-only 约束、最终输出收敛规则和 artifact 路径。
- `assets/input.schema.json`
  - 定义必需文件输入 `source_path`。
- `assets/parameter.schema.json`
  - 定义可选参数 `language`。
- `assets/output.schema.json`
  - 将最终输出收敛到可选 note artifact 路径 `note_path`。
- `assets/runner.json`
  - 声明版本、执行模式、schema 路径和 `pymupdf4llm` 依赖。
- `references/file_protocol.md`
  - 复制 Skill-Runner 文件协议参考。
- `references/conversion_report.md`
  - 记录本次转换依据与约束。

## 6. 风险与剩余事项

1. 当前 Skill 仍以交互为中心，若未来要支持 `auto`，必须新增参数来固定执行目标。
2. `dispatch_source.py` 仍保留标准库 PDF 兜底逻辑，但 runner 侧已将 `pymupdf4llm` 视为必需依赖。
3. `note_path` 在 schema 中是可选 artifact 字段，最终是否存在取决于用户是否明确要求并确认落盘。
