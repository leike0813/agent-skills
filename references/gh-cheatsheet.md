# GitHub CLI Cheatsheet

Reference for common `gh` commands with parameter breakdowns, effects, and mnemonics.

## Prerequisites

### `gh auth login`

- 效果: 交互式登录 GitHub 账号（浏览器或 token）
- 助记: auth login = 刷卡进门

### `gh auth status`

- 效果: 检查当前登录状态
- 助记: auth status = "我还登录着吗？"

## Pull Requests

### `gh pr create`

- 效果: 交互式创建 PR（会提示填写 title、body、base branch 等）
- 助记: pr create = 提交"代码审查申请"

### `gh pr create --title "<t>" --body "<b>" --base <branch>`

- 参数: `--title` = PR 标题，`--body` = PR 描述，`--base` = 目标分支，`--head` = 源分支（默认当前分支）
- 效果: 非交互式创建 PR
- 助记: 带上参数 = 跳过问答，直接提交

### `gh pr list`

- 效果: 列出当前仓库的 PR
- 常用参数: `--state open|closed|merged`, `--author <user>`, `--label <label>`
- 助记: pr list = "有哪些在审查？"

### `gh pr view [<number>]`

- 效果: 在终端查看 PR 详情
- 参数: 可选 PR 编号，默认当前分支关联的 PR
- 助记: pr view = "看看这个 PR 什么情况"

### `gh pr checkout <number>`

- 效果: 将指定 PR 的代码拉到本地新分支
- 助记: pr checkout = 把别人的 PR 搬到本地

### `gh pr merge <number>`

- 效果: 合并指定 PR
- 参数: `--squash` (压缩合并), `--rebase` (rebase 合并), `--merge` (创建 merge commit)
- 助记: pr merge = "审查通过，合入！"

### `gh pr close <number>`

- 效果: 关闭 PR（不合并）
- 助记: pr close = "这个 PR 不要了"

## Issues

### `gh issue create`

- 效果: 交互式创建 Issue
- 助记: issue create = 提交"任务卡片"

### `gh issue list`

- 效果: 列出 Issues
- 常用参数: `--state open|closed`, `--label <label>`, `--assignee <user>`
- 助记: issue list = "有哪些待办？"

### `gh issue view <number>`

- 效果: 查看 Issue 详情
- 助记: issue view = 点开任务卡片

### `gh issue close <number>`

- 效果: 关闭 Issue
- 助记: issue close = "这个任务完成了/不需要了"

## Repos

### `gh repo clone <owner>/<repo>`

- 效果: 克隆仓库到本地
- 助记: repo clone = 下载别人代码

### `gh repo view [<owner>/<repo>]`

- 效果: 在终端查看仓库信息（README、描述、统计等）
- 助记: repo view = "这个仓库长什么样？"

## Workflows / Actions

### `gh run list`

- 效果: 列出最近的 Action 运行记录
- 助记: run list = "CI 跑完了吗？"

### `gh run view <run-id>`

- 效果: 查看 Action 运行详情和日志
- 助记: run view = 查看 CI 流水线
