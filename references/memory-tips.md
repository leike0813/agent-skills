# Memory Techniques

Techniques for crafting memorable mnemonics and analogies for Git/GH commands.

## Techniques

### 1. English Mnemonic (首字母/词根联想法)

Git 的 flag 参数通常是有语义的英文缩写。利用这一点帮助记忆：

- `git checkout -b` → `-b` = **b**irth (创建一个新分支)
- `git commit -m` → `-m` = **m**essage (附上提交信息)
- `git push -u` → `-u` = **u**pstream (建立长期跟踪)
- `git push -f` → `-f` = **f**orce... and **f**ear (强制推送有风险)
- `git pull --rebase` → rebase = **re**-base (换个底盘)

Pattern: **"flag letter → English word → effect"**

### 2. Action Analogy (动作类比法)

把 Git 操作类比成日常动作：

- `git add` → 把改动"装进购物车" (staging area = cart)
- `git commit` → "结账买单" (cart → receipt/commit)
- `git push` → "快递发出" (local → remote)
- `git pull` → "收快递并拆箱" (fetch + merge)
- `git stash` → "暂时藏进抽屉" (pop = 从抽屉拿出来)
- `git branch` → 树枝分叉 (branch = tree branch)
- `git merge` → 两条河水汇合
- `git rebase` → 换一个底盘 (就像换鞋底)

### 3. Contrast Pairs (对比记忆法)

把容易混淆的成对命令放在一起，突出差异：

- **`git fetch`** vs **`git pull`**: fetch = 只下载远端信息、不合并到当前分支；pull = 下载后立刻整合进当前分支
- **`git merge`** vs **`git rebase`**: merge = 保留分叉历史 (有 merge commit), rebase = 拉直线 (改写历史)
- **`git reset --soft`** vs **`git reset --hard`**: soft = 温柔的撤销 (保留改动), hard = 硬核的撤销 (全删)
- **`git stash`** vs **`git stash pop`**: stash = 存起来, pop = 取出来 (并存档消失)
- **`git branch -d`** vs **`git branch -D`**: `-d` = 安全删除 (已合并才行), `-D` = 强行删除 (不管合没合并)

### 4. Story Chain (故事链法)

把多步骤操作串成一个小故事：

**功能分支开发流程**: "分叉 → 修改 → 装车 → 结账 → 发出"
```
git checkout -b feature-x  # 分叉：从主干长出新枝条
...edit files...           # 修改：写代码
git add .                  # 装车：把改好的文件放进购物车
git commit -m "..."        # 结账：购物车结算，留下一张发票
git push -u origin feat..  # 发出：快递送到 GitHub
```

### 5. Danger Sign (危险信号标记法)

给危险命令标记明显的警告信号，形成条件反射：

- `--force` / `-f` → ⚠️ 看到 force 先停一停
- `--hard` → ⚠️ 看到 hard 三思而行 (hard reset, hard clean)
- `-D` (大写) → ⚠️ 大写 D = 危险的删除
- `git push --delete` → ⚠️ 远程删除不可逆

## When to Use Each Technique

| User type | Best technique |
| --- | --- |
| 程序员 (英语好) | English Mnemonic (flag letter → word) |
| 新手 (对细节不熟) | Action Analogy (日常类比) |
| 容易混淆的人 | Contrast Pairs (对比记忆) |
| 需要记住流程 | Story Chain (故事链) |
| 所有人 | Danger Sign (危险信号) — 每次都该提醒 |

## Crafting A Good Memory Tip

1. **Short**: One line, one idea.
2. **Concrete**: Use everyday objects or actions, not abstract concepts.
3. **Emotional**: A bit of humor or a warning tone sticks better.
4. **Visual**: Paint a mental picture.

Bad: "Git branch creates a new branch pointer at the current HEAD."
Good: "`git checkout -b` = **b**irth a new branch and jump on it"

Bad: "The push command transmits local commits to the remote repository."
Good: "`git push` = 把本地代码快递到 GitHub"
