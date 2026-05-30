# LLM And Script Boundary

## Principle

LLM 负责语义，脚本负责确定性。skill 设计必须把这条边界写清楚，否则 agent 往往会出现两类错误：

- 用临时脚本逃避本应由 LLM 完成的理解、归纳、判断。
- 由 LLM 手工拼接本应由脚本校验或渲染的权威产物。

## Must Be Done By LLM

这些任务需要意义理解或价值判断，不应交给脚本：

- 摘要、解释、归纳、分类、命名。
- 判断用户真实意图。
- 从失败记录中提取通用经验。
- 判断证据是否支持主张。
- 学术、业务、写作、策略取舍。
- 与用户协商、请求确认、处理歧义。
- 生成 response、draft、strategy、analysis 等语义内容。

可接受模式：

1. LLM 产出结构化 payload。
2. 脚本校验 payload schema。
3. 脚本写库或渲染只读视图。

不可接受模式：

- 写一个临时 Python 脚本自动“总结论文”。
- 写脚本按关键词替代 reviewer comment 的语义合并。
- 让脚本按字符串规则决定复杂学术策略。

## Must Be Done By Scripts

这些任务应交给脚本：

- payload/schema 校验。
- 枚举值、字段类型、必填项检查。
- SQLite schema 初始化与写入。
- gate 状态判断与 `next_action` 计算。
- 目录创建、文件分发、哈希计算。
- 确定性提取，如文件头检测、固定格式解析、稳定排序。
- 从 DB 或结构化数据渲染最终 JSON/Markdown/LaTeX。
- 输出合法性检查。

不可接受模式：

- LLM 手写最终 stdout JSON，但该 JSON 已规定必须由 renderer 生成。
- LLM 直接编辑只读视图并把它当作真源。
- LLM 绕过 schema 手工补字段。

## Script Call Requirements

只要 skill 包含 `scripts/`，`SKILL.md` 必须至少写清：

- 脚本路径。
- 调用时机。
- 最小命令示例。
- 输入来自哪里。
- stdout 或副作用是什么。
- 失败时如何处理。
- 脚本是否属于正式主路径，还是可选辅助工具。
- 脚本是否允许被跳过；若允许，回退协议是什么。

复杂 payload 还必须在 `SKILL.md` 或 reference 中给出：

- 最小合法 payload。
- 典型非法 payload。
- 字段语义。
- 枚举值列表。
- payload 太长时是否使用 `--payload-file`。

## Minimal Script Entry Format

在 `SKILL.md` 中描述正式脚本时，使用这种最小格式：

```markdown
### `<script-name>`

Path: `scripts/<script>.py`

Use when: <exact trigger>

Command:
\```bash
python -u scripts/<script>.py --arg "<value>"
\```

Input:
- `<field>`: <meaning>

Output:
- stdout JSON with `<field>`
- writes `<path>` if applicable

On failure:
- stop / ask user / rerun gate / return schema-compatible error
```

如果脚本 payload 复杂，命令示例必须使用 `--payload-file`，不要鼓励 agent 在 shell 中拼接超长 JSON。

## Boundary Section Template

```markdown
## Responsibilities

### Must Be Done By LLM

- <semantic task>
- <judgment task>

### Must Be Done By Scripts

- <deterministic task>
- <validation task>

### Forbidden

- Do not use temporary scripts for <semantic task>.
- Do not hand-write <authoritative artifact>; render it through <script>.
```

## Review Checklist

- 是否有脚本承担了语义判断？
- 是否有 LLM 手工拼接机器消费产物？
- 是否所有脚本都有调用示例？
- 是否复杂 payload 有正例、反例和枚举值？
- 是否写清脚本失败后的恢复路径？
