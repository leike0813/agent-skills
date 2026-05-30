# Minimal SKILL.md Template

## Use When

适用于所有 skill 的起草起点，尤其是 Tier 1 simple contract skill。先用本模板写出最小可执行主文件，再按复杂度叠加其它 extension 模板。

## Authoring Rules

- 保留真正的运行时指令，删除所有 `<<...>>` 占位符和 `Authoring hint`。
- 不要为了填满章节而编造内容；不适用的章节应删掉或合并。
- `description` 必须写英文触发说明，正文可以按用户项目语言撰写。
- 简单 skill 不要引入 gate、SQLite、resume、renderer 等重型机制。

## Template

````markdown
---
name: <<kebab-case skill name>>
description: <<What the skill does>>. Use when <<user request patterns, artifacts, workflows, and near-synonyms that should trigger this skill>>.
---

# <<Human-readable Skill Title>>

## Mission

<<用 1-3 句话说明这个 skill 要稳定完成什么任务。写给执行任务的 agent，不写市场化介绍。>>

## When To Use

Use this skill when:

- <<触发场景 1：用户会怎样说，或会提供什么工件>>
- <<触发场景 2>>

Do not use this skill when:

- <<相邻但不该触发的场景>>
- <<超出能力边界的场景>>

## Inputs

Required:

- `<<input_name>>`: <<语义、来源、格式、缺失时怎么处理>>

Optional:

- `<<input_name>>`: <<默认行为和约束>>

Ask the user only if <<列出必须询问的缺口；不要写泛泛的“如有需要就问”>>.

## Workflow

1. <<第一步：必须能让 agent 知道触发后先做什么>>
2. <<第二步：核心语义或操作步骤>>
3. <<第三步：检查、输出或收尾>>

Stop and report a blocker if <<列出不能继续的条件>>.

## Constraints

- Must: <<必须稳定遵守的规则>>
- Must not: <<真实容易犯错的禁止事项>>
- Prefer: <<有取舍空间时的默认偏好>>

## Output Contract

Return:

- <<输出形态：对话、Markdown、JSON、文件、目录等>>
- <<必须包含的字段/章节/要点>>
- <<不得混入的内容，例如解释文字、Markdown fence、未验证字段>>

## Examples

### Happy Path

Input:

```text
<<最小真实感输入>>
```

Expected output:

```text
<<最小合法输出或关键结构>>
```

### Near Miss / Failure

Input:

```text
<<看起来相关但不该处理，或非法输入>>
```

Expected behavior:

<<拒绝、询问、降级处理或返回失败 shape。>>

## Failure Handling

- If <<失败条件>>, then <<agent 应做什么>>.
- If <<信息不足>>, ask <<具体问题>> instead of <<禁止的猜测行为>>.
````
