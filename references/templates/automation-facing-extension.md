# Automation-facing Extension Template

## Use When

适用于 Tier 7 automation-facing skill，或任何输出会被 runner、脚本、另一个 agent、MCP、外部系统消费的 skill。可叠加在 simple、script-assisted、gate 或 SQLite 架构上。

## Authoring Rules

- 成功和失败输出都必须有稳定 shape。
- stdout 和 artifact 要有唯一权威路径；不要混日志、解释或 Markdown fence。
- 枚举值必须显式列出或直接链接 schema。
- 删除所有 `<<...>>` 占位符和 authoring 提示。

## Extension Sections

把以下章节合并进目标 `SKILL.md`：

````markdown
## Automation Contract

This skill may be called by automation. Keep outputs stable and machine-parseable.

Input source:

- <<prompt payload、file、directory、stdin、runner config 等>>

Authoritative output:

- stdout: <<yes/no；如果 yes，写唯一 JSON shape>>
- artifacts: <<路径约定；如果有>>

Do not write logs, commentary, or Markdown fences to stdout when stdout is the machine contract.

## Input Schema

Required fields:

- `<<field>>`: <<类型、含义、允许值>>

Optional fields:

- `<<field>>`: <<默认值、缺省行为>>

Enum values:

- `<<enum>>`: <<含义>>
- `<<enum>>`: <<含义>>

## Success Output

```json
{
  "ok": true,
  "result": {
    "<<field>>": "<<value>>"
  },
  "artifacts": []
}
```

## Failure Output

```json
{
  "ok": false,
  "error": {
    "code": "<<stable_error_code>>",
    "message": "<<human-readable but stable enough>>",
    "details": {}
  },
  "artifacts": []
}
```

## Directory Protocol

- Inputs: `<<path convention>>`
- Temporary files: `<<path convention>>`
- Final artifacts: `<<path convention>>`
- Validation assets: `assets/<<schema file>>`

## Validation

Before returning machine-facing output:

1. Validate required keys.
2. Validate enum values.
3. Validate success or failure shape.
4. Ensure stdout contains only the contract object when stdout is authoritative.
````
