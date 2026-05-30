# I/O Schema Contracts

## When Required

只要 skill 具有上/下游自动化需求，就必须设计输入输出契约：

- skill 由 runner、MCP、另一个 agent 或脚本调用。
- stdout 被机器读取。
- 输出 artifact 被后续流程消费。
- 错误输出也需要被程序处理。
- 字段遗漏或顺序漂移会导致下游失败。

## Contract Locations

推荐布局：

```text
skill-name/
├── SKILL.md
├── assets/
│   ├── input.schema.json
│   ├── output.schema.json
│   ├── parameter.schema.json
│   └── runner.json
├── references/
│   └── io-contract.md
└── scripts/
    └── validate_output.py
```

`SKILL.md` 写硬约束和最小示例，reference 写字段语义、枚举值、正例和反例。

## SKILL.md Must State

- 输入字段。
- 输出字段。
- 成功输出 shape。
- 失败输出 shape。
- stdout 是否只能输出 JSON。
- artifact 输出目录和文件名。
- 缺失输入的默认行为。
- 可恢复错误与不可恢复错误。
- 哪些字段必须回显原输入。

## Enumerations

枚举值必须显式列出，不能让 agent 自行探索。

示例：

```markdown
`valid_tags_format` supports exactly:
- `yaml`
- `json`
- `auto`

Unsupported values such as `markdown`, `txt`, or free-form text are invalid.
```

## Payload Examples

至少提供：

- 最小合法输入。
- 典型完整输入。
- 缺字段但可恢复输入。
- 非法输入。
- 成功输出。
- 失败输出。

复杂 payload 优先通过文件传递：

```bash
python scripts/stage_runtime.py persist_step --payload-file payload.json
```

不要要求 agent 在 shell 命令中拼接超长 JSON。

## Output Stability Rules

机器消费输出必须稳定：

- 固定 required keys。
- 空值也保留字段。
- 数组稳定排序。
- 时间使用 UTC ISO-8601。
- 错误对象有固定 `type` 或 `code`。
- warning 是数组，不用自由段落替代。
- JSON stdout 不夹杂日志、Markdown code fence 或解释文字。

## Stdout JSON Templates

成功输出最小模板：

```json
{
  "result_path": "/abs/path/result.json",
  "provenance": {
    "generated_at": "2026-05-31T00:00:00Z",
    "input_hash": "sha256:<hex>",
    "model": "<model>"
  },
  "warnings": [],
  "error": null
}
```

失败输出最小模板：

```json
{
  "result_path": "",
  "provenance": {
    "generated_at": "",
    "input_hash": "",
    "model": ""
  },
  "warnings": [],
  "error": {
    "type": "invalid_input",
    "message": "<human-readable but stable enough>"
  }
}
```

字段名可按 skill 调整，但成功和失败必须共享同一顶层结构。

## Directory Protocol

文件式输入输出必须写清：

- 当前工作目录如何确定。
- 临时目录命名。
- artifact root 命名。
- 最终输出目录。
- 哪些文件是只读视图。
- 哪些文件是正式 artifact。
- 哪些文件可删除重跑。

## Validation

推荐提供验证脚本：

```bash
python scripts/validate_output.py --output result.json
```

验证脚本应检查：

- JSON 可解析。
- required keys 存在。
- 字段类型正确。
- 枚举值合法。
- 文件路径存在。
- 成功/失败 shape 都合法。

## Asset Schema Guidance

当 schema 放入 `assets/`：

- `input.schema.json` 描述 prompt payload 或 runner input。
- `parameter.schema.json` 描述可选参数和默认值。
- `output.schema.json` 描述 stdout 或最终 result JSON。
- `runner.json` 只描述 runner 需要的入口、参数和能力，不替代 `SKILL.md`。

`SKILL.md` 必须链接这些 schema，并说明 agent 何时需要读取或调用验证脚本。

## Anti-patterns

- 只在正文里描述“输出一个 JSON”，但不给完整 schema 示例。
- 枚举值写成“例如”，导致 agent 自行发明。
- 成功输出稳定，失败输出自由发挥。
- stdout 同时输出日志和 JSON。
- 文件名不固定，下游无法定位。
