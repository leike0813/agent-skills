# Community Meta-skill Lessons

## Purpose

本文件提炼其它 meta-skill 中具有共性的可迁移经验。读它的时机：目标 skill 依赖外部资料、已有 skill、失败记录、第三方工具经验，或准备公开/共享/迁移到他人环境。

本文件不是 meta-skill 综述，不要求读取原始 meta-skill 包，也不引入 validator、scanner、初始化器或多 reviewer 流程。

## Source-backed Design

写 skill 前先判断设计材料是否足够，而不是直接套模板。

需要记录的来源：

- 用户经验：成功路径、失败路径、偏好、稳定输出、不要再试。
- 现有 skill：可复用的架构、触发描述、reference 路由、脚本边界。
- 上游文档：官方 API、CLI 帮助、schema、错误码、运行限制。
- 第三方工具经验：安装、认证、调用方式、常见错误、环境约束。
- 失败记录：重复出错的步骤、临时补丁、不可复现或不稳定的假设。

输出设计前先给出：

```markdown
## 来源覆盖判断
- 已覆盖来源:
- 关键缺口:
- 可直接沉淀的规则:
- 仍需用户确认的决策:
- 不确定性对架构的影响:
```

不要把来源覆盖变成重型研究流程。简单、单一、低风险 skill 可以只用 1-2 句说明“来源足够，按轻量设计继续”。

## Portable Core vs Product-specific Extensions

优先设计可移植核心，再决定是否需要产品特定扩展。

可移植核心通常包括：

- `SKILL.md` frontmatter 中的 `name` 和 `description`。
- 运行时 workflow、约束、输入输出、失败处理。
- references/scripts/assets 的职责和读取/调用时机。
- LLM 与脚本职责边界。

产品特定扩展包括：

- `agents/openai.yaml` 之类的 UI metadata。
- `allowed-tools`、hooks、model/context、agent invocation 等平台字段。
- MCP dependency metadata、默认 prompt、界面 chip、快捷入口。

规则：

- 产品字段不能替代 `SKILL.md` 中的能力描述和运行时指令。
- 只有目标环境明确需要时才设计产品字段。
- 产品字段必须和 `SKILL.md` 能力一致，不能暗藏权限、依赖或额外行为。
- 如果希望 skill 跨平台复用，把产品字段写成 optional extension，而不是通用要求。

## Release Safety And Sanitization

公开、共享或迁移 skill 前，必须做语义脱敏和副作用检查。

检查内容：

- 是否包含真实人名、机构名、项目名、客户名、会议内容。
- 是否包含内部路径、私有 URL、仓库名、服务名、数据库名。
- 是否包含 token、cookie、key、账号、个人配置。
- 示例字段、错误信息、业务规则是否泄露内部流程。
- 脚本是否有网络上传、删除、覆盖、修改全局配置、安装依赖、hook 等副作用。
- 依赖来源、许可证、远程下载或执行是否会让用户意外。

不要只靠关键词 grep。脱敏必须读懂文本语义，因为敏感信息经常表现为缩写、项目代号、目录结构、领域专有名词或“看似普通”的示例。

公开版 skill 应该让用户不意外：能力、权限、依赖、外部服务和副作用都应在 `description` 或运行时说明中可见。

## Wrapper Skill Decision

当用户想把第三方 CLI、API、MCP、插件或本地工具调试经验沉淀成 skill 时，先做 adopt / extend / build 判断。

| Decision | 适用场景 | Skill 设计方式 |
| --- | --- | --- |
| Adopt | 现有工具已经稳定，agent 只需要知道何时调用 | 轻量 wrapper，写清入口、参数、失败处理 |
| Extend | 现有 skill 或工具接近可用，但缺少场景规则 | 更新现有 skill，补 reference、脚本示例或边界 |
| Build | 工具链组合复杂、失败经验多、输出契约特殊 | 新建 wrapper skill，沉淀安装/认证/调用/恢复规则 |

Wrapper skill 不是默认模式。只有当工具操作本身是稳定能力的一部分时才采用。不要为了“看起来工程化”把普通语义任务包装成工具 skill。

## What Not To Import

不要把其它 meta-skill 的以下内容变成 `skill-smith` 的默认要求：

- 初始化脚本、validator、scanner 或平台专用命令。
- 精确行数阈值、完整字段百科或产品特定 schema 全表。
- 多 reviewer / counter-review 重流程。
- 完整安全扫描报告模板。
- 要求普通 agent 读取原始 meta-skill 包。

吸收原则：只保留能改变 skill 设计判断的共性经验；其它内容最多作为目标环境已有工具时的可选参考。
