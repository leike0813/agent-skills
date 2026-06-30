# Git Command Cheatsheet

Reference for common Git commands with parameter breakdowns, effects, and mnemonics.

## Branch

### `git branch <name>`

- 参数: `<name>` — 新分支名
- 效果: 在当前 HEAD 指向的 commit 上创建新分支指针，不切换过去
- 助记: branch = 树枝分叉

### `git checkout -b <name>`

- 参数: `-b` = 创建新分支并切换到该分支
- 效果: 创建新分支并立即切换到该分支
- 助记: `-b` = **b**irth a branch and jump on it

### `git branch -d <name>`

- 参数: `-d` = `--delete`
- 效果: 删除已合并的分支
- 助记: `-d` = **d**elete (safe, only merged)

### `git branch -D <name>`

- 参数: `-D` = `--delete --force`
- 效果: 强制删除分支（即使未合并）
- ⚠️ 警告: 未合并的 commits 会丢失

### `git switch <name>` / `git checkout <name>`

- 效果: 切换到已有分支，更新工作区和 HEAD
- 助记: switch = 换轨道

### `git switch -c <name>`

- 参数: `-c` = `--create`
- 效果: 创建新分支并切换（同 `git checkout -b`）
- 助记: `-c` = **c**reate and switch

## Commit

### `git add <file>`

- 参数: `<file>` — 文件路径，`.` 表示当前目录所有改动
- 效果: 将文件改动加入暂存区（staging area）
- 助记: add = 把改动"装进购物车"

### `git commit -m "<message>"`

- 参数: `-m` = `--message`
- 效果: 将暂存区的内容创建为一个 commit
- 助记: `-m` = **m**essage

### `git commit -am "<message>"`

- 参数: `-a` = `--all` (暂存所有已跟踪文件的改动)，`-m` = `--message`
- 效果: 跳过 `git add`，直接暂存+提交所有已跟踪文件的改动
- ⚠️ 注意: 对新文件（untracked）无效
- 助记: `-am` = **a**ll **m**essage (一气呵成)

## Remote & Push/Pull

### `git push`

- 效果: 将本地 commits 推送到已绑定的远程分支
- 前提: 当前分支已设置 upstream
- 助记: push = 推向远端

### `git push -u origin <branch>`

- 参数: `-u` = `--set-upstream`，`origin` = 远程名，`<branch>` = 分支名
- 效果: 首次推送并建立跟踪关系，之后只需 `git push`
- 助记: `-u` = **u**pstream (绑定长期关系)

### `git push --force-with-lease`

- 参数: `--force-with-lease` = 只有远端仍是本地所知状态时才允许强推
- 效果: 改写远端分支历史，但比 `--force` 多一层协作保护
- 警告: 仍然会改写远端历史，执行前必须确认目标分支和协作者影响
- 助记: lease = 租约；租约没变才允许改门锁

### `git push --force` / `git push -f`

- 参数: `--force` / `-f` = 强制更新远端分支
- 效果: 用本地历史覆盖远端历史
- 警告: 可能覆盖他人提交；优先建议 `--force-with-lease`
- 助记: force = 强推；看到 force 先停

### `git push origin --delete <branch>`

- 参数: `--delete` = 删除远端分支
- 效果: 从远端仓库删除指定分支
- 警告: 会改变远端共享状态，执行前确认分支名
- 助记: remote delete = 删除别人也能看到的分支

### `git pull`

- 效果: 拉取远程 commits 并合并到当前分支 (= `git fetch` + `git merge`)
- 助记: pull = 拉下来合上

### `git fetch`

- 效果: 只拉取远程更新，不合并
- 助记: fetch = 只拿来看，不动手

## Merge & Rebase

### `git merge <branch>`

- 效果: 将 `<branch>` 的 commits 合并到当前分支
- 策略: fast-forward（直线）或 three-way（分叉后合并，产生 merge commit）
- 助记: merge = 两条河汇成一条

### `git rebase <branch>`

- 效果: 将当前分支的 commits "搬到" `<branch>` 最新 commit 后面，改写历史为一条直线
- 警告: rebase 会改写当前分支提交历史；如果这些 commits 已经推送并被他人基于其开发，必须先确认协作影响
- 助记: rebase = 换一个"底盘"

### `git rebase --continue` / `git rebase --abort`

- 效果: 解决冲突后继续 / 放弃 rebase
- 助记: continue = 继续前进，abort = 回到原点

## Undo

### `git reset --soft HEAD~1`

- 参数: `--soft` = 保留工作区和暂存区，`HEAD~1` = 回退一个 commit
- 效果: 撤销最近一次 commit，改动回到暂存区
- 助记: soft reset = 温柔的撤销，只撤销 commit 不丢改动

### `git reset --hard HEAD~1`

- 参数: `--hard` = 丢弃工作区和暂存区
- 效果: 彻底删除最近一次 commit 及其改动
- ⚠️ 警告: 改动不可恢复

### `git revert <commit>`

- 参数: `<commit>` = 要撤销效果的提交
- 效果: 新建一个反向提交，用公开历史中更安全的方式撤销改动
- 助记: revert = 写一张反向发票，不撕掉旧发票

### `git clean -n` / `git clean -fd`

- 参数: `-n` = 预览会删除什么，`-f` = force，`-d` = 包含目录
- 效果: 删除未跟踪文件；`-n` 只预览，`-fd` 真删除
- 警告: 执行 `git clean -fd` 前应先运行 `git clean -n`
- 助记: clean = 清扫；先预览垃圾袋里有什么

### `git stash`

- 效果: 暂存当前未提交的改动，恢复干净工作区
- 助记: stash = 暂时藏起来

### `git stash pop`

- 效果: 恢复最近一次 stash 的改动并删除 stash 记录
- 助记: pop = 拿出来

## Inspect

### `git status`

- 效果: 查看工作区和暂存区状态
- 助记: status = "现在什么情况？"

### `git log --oneline -n <N>`

- 参数: `--oneline` = 单行模式，`-n <N>` = 显示最近 N 条
- 效果: 查看 commit 历史
- 助记: log = 翻日志

### `git diff`

- 效果: 查看未暂存的改动差异
- 助记: diff = difference, "改了什么？"

### `git diff --staged`

- 效果: 查看暂存区中待提交的改动
- 助记: staged diff = "购物车里有什么？"
