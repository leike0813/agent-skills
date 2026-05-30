# Reference-backed Extension Template

## Use When

适用于 Tier 2 reference-backed skill，或任何需要把细节拆到 `references/` 的 skill。与 [minimal-skill-template.md](minimal-skill-template.md) 组合使用。

## Authoring Rules

- 每个 reference 必须从 `SKILL.md` 直接链接，并说明读取时机。
- `SKILL.md` 仍要包含完整主流程；不能只做目录索引。
- 不要要求 agent 启动时通读所有 references。
- 删除所有 `<<...>>` 占位符和 authoring 提示。

## Extension Sections

把以下章节合并进目标 `SKILL.md`：

````markdown
## Operating Modes

先判断当前请求属于哪一种模式：

| Mode | Use when | Goal |
| --- | --- | --- |
| `<<mode_name>>` | <<触发信号>> | <<本模式的交付目标>> |
| `<<mode_name>>` | <<触发信号>> | <<本模式的交付目标>> |

If the mode is unclear, infer from <<上下文来源>>. Ask the user only when <<模式差异会改变交付物的关键条件>>.

## Reference Loading Guide

Default to this `SKILL.md`. Load references only when the current task needs them.

| Need | Read |
| --- | --- |
| <<设计问题或执行问题>> | [<<reference-name.md>>](references/<<reference-name.md>>) |
| <<设计问题或执行问题>> | [<<reference-name.md>>](references/<<reference-name.md>>) |

## Main File / Reference Boundary

Keep in `SKILL.md`:

- <<触发后必须立即知道的运行时规则>>
- <<模式分流、主流程、硬约束>>

Move to references:

- <<长字段语义、长示例、领域术语、stage playbook>>
- <<只在少数任务需要的细则>>

Do not duplicate the same rule in both places unless <<必须重复的原因，例如安全硬约束>>.
````
