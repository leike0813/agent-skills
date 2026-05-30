# Script-assisted Extension Template

## Use When

适用于 Tier 3 script-assisted skill，或任何包含正式 `scripts/` 入口的 skill。与 [minimal-skill-template.md](minimal-skill-template.md) 组合使用；如果脚本 payload 复杂，也应叠加 reference-backed 结构。

## Authoring Rules

- 只要有正式脚本，`SKILL.md` 必须给最小命令示例。
- 复杂 payload 必须给最小合法 payload，并列出枚举值或指向直接 reference。
- 语义判断必须归 LLM；确定性校验、渲染、写入才归脚本。
- 删除所有 `<<...>>` 占位符和 authoring 提示。

## Extension Sections

把以下章节合并进目标 `SKILL.md`：

````markdown
## Formal Entrypoints

Use these scripts only for their stated deterministic responsibilities.

### `scripts/<<script_name>>`

Purpose: <<脚本做什么确定性任务，不做什么语义任务>>

Minimal command:

```bash
<<command example>>
```

Minimal payload:

```json
{
  "<<field>>": "<<value>>"
}
```

On success: <<脚本成功后 agent 应读取什么、继续什么步骤>>.

On failure: <<停止、修复 payload、询问用户或进入 repair 的规则>>.

## LLM And Script Responsibilities

LLM must:

- <<语义理解、归纳、策略、判断、写作等职责>>

Scripts must:

- <<schema 校验、枚举检查、文件分发、稳定渲染等职责>>

Never:

- Use a temporary script to replace <<语义任务>>.
- Hand-assemble <<脚本或 renderer 的权威产物>> when a formal script is required.

## Payload Rules

- Required fields: `<<field>>`, `<<field>>`.
- Optional fields: `<<field>>`.
- Enum values:
  - `<<enum_value>>`: <<含义>>
  - `<<enum_value>>`: <<含义>>
- Invalid payloads must <<拒绝、修复、返回失败或询问用户>>.
````
