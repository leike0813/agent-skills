# OpenAI Skill Creator Lessons

## Purpose

本文件提炼 `references/meta-skills/openai-skill-creator` 中可迁移的设计经验。读它的时机：需要决定 skill 的资源目录、上下文预算、自由度约束、OpenAI/Codex UI 元数据或产品特定配置。

不要把 OpenAI 原始包作为普通运行时必读材料。本文件只吸收设计原则，不复制 `init_skill.py`、`quick_validate.py`、`generate_openai_yaml.py` 等脚手架命令作为 `skill-smith` 的必需流程。

## Context Economy

上下文窗口是公共资源。写 skill 时默认假设 Codex 已经很强，只加入它不会自然知道、但对任务稳定性有实际帮助的信息。

应该加入：

- 专用 workflow、顺序、门禁和失败恢复。
- 用户组织、领域或工具的特殊约束。
- 机器契约、schema、目录协议和枚举值。
- 容易被 agent 重复写错的确定性步骤。
- 能显著减少重复探索的脚本、reference 或 asset。

不应该加入：

- 通用常识。
- 冗长背景介绍。
- README、安装指南、变更日志、quick reference 等非运行时文档。
- 与当前 skill 执行无关的开发过程记录。

## Degree Of Freedom Calibration

根据任务脆弱性设置自由度：

| Freedom | Use when | Design shape |
| --- | --- | --- |
| High | 多种方案都合理，结果依赖语义判断 | 文字指令、原则、少量示例 |
| Medium | 有推荐流程，但允许上下文调整 | 分步 workflow、payload 约定、辅助脚本 |
| Low | 操作易错、脆弱、需稳定复现 | 正式脚本、schema、gate、少参数入口 |

不要用低自由度工具压制开放式任务。也不要让脆弱任务只靠自由文本提示。

## Resource Responsibilities

### `SKILL.md`

运行时主控。放触发后必须立即知道的目标、流程、约束、职责边界和 reference 路由。

### `references/`

给 agent 按需读取的知识和细节。适合放：

- 长字段说明。
- API 或数据库 schema。
- 领域规则。
- stage playbook。
- 大量正例/反例。

如果 reference 很长，应加目录或检索提示。不要让 reference 互相深层跳转。

### `scripts/`

确定性、重复性、易错任务的正式执行入口。适合放：

- 文件转换。
- schema 校验。
- 稳定渲染。
- gate 判定。
- 数据库写入。

有脚本就必须在 `SKILL.md` 给调用示例。

### `assets/`

输出资源，不是给 agent 通读的文档。适合放：

- 模板文件。
- 图片、图标、字体。
- boilerplate 项目。
- JSON schema 或其它被脚本/runner 使用的静态资源。

### `agents/openai.yaml`

可选的产品特定 UI 元数据，不替代 `SKILL.md`。只有当目标环境需要 Codex UI skill chip、默认 prompt 或 MCP dependency metadata 时才建议设计。

推荐字段：

- `interface.display_name`：人类可读名称。
- `interface.short_description`：25-64 字符的 UI 简述。
- `interface.default_prompt`：短句，且显式提到 `$skill-name`。
- `dependencies.tools`：只有需要声明 MCP 等工具依赖时才写。

不要把 `agents/openai.yaml` 当作所有 skill 的必备结构。更新已有 skill 时，如果存在该文件，应检查它是否仍与 `SKILL.md` 能力一致。

## No Surprise Principle

skill 的内容不应让用户对它的真实意图、权限、依赖或副作用感到意外。

必须显式暴露：

- 外部服务、MCP、API 或网络依赖。
- 会修改全局配置、系统文件或外部账户的行为。
- 需要私密凭据、客户数据或内部路径的流程。
- 安装、执行、上传、删除、覆盖等高影响动作。

不要创建会误导用户、伪装能力边界、隐藏副作用或促进未授权访问的 skill。

## Initialization And Validation Awareness

如果目标环境已经提供 skill 初始化或校验工具，可以建议使用它们来减少结构错误。但不要把某个生态的脚手架命令写成 `skill-smith` 的通用硬约束。

通用校验应关注：

- frontmatter 是否只有目标平台支持的字段。
- `name` 是否与目录一致。
- `description` 是否覆盖触发场景。
- 所有正式脚本是否有调用示例并经过代表性运行。
- 资源目录是否都有实际运行价值。
- 占位符、示例垃圾文件和无用目录是否清理。

## Do Not Copy

- 不复制 OpenAI 原始脚手架命令作为必跑步骤。
- 不默认生成 `agents/openai.yaml`。
- 不把 README、安装指南、变更日志作为 skill 包标配。
- 不要求普通设计任务读取原始 OpenAI skill-creator 包。

## Reusable Design Rules

- 先问“这段内容值不值得占用上下文”。
- 先判断自由度，再决定用提示词、reference、脚本还是 gate。
- `references/` 是给 agent 读的，`assets/` 是给输出或脚本用的，`agents/` 是产品配置。
- 简单 skill 应保持单文件优先。
- 产品特定元数据必须是可选层，不能替代运行时指令。
