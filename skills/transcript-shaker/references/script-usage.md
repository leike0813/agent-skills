# transcript_shaker 脚本用法

本文是 `scripts/transcript_shaker/__main__.py` 的完整说明；`SKILL.md` 只保留参数摘要与一个调用示例。

## 调用形态

三种形态互斥：列候选、按内容检索，或转写一个文件。

```bash
python3 <skill_dir>/scripts/transcript_shaker/__main__.py --list [--harness NAME] [--match TEXT] [--since YYYY-MM-DD] [--limit N]
python3 <skill_dir>/scripts/transcript_shaker/__main__.py --search "<内容关键词>" --harness NAME [--since YYYY-MM-DD] [--match TEXT] [--limit N]
python3 <skill_dir>/scripts/transcript_shaker/__main__.py <transcript> [--profile default|full|compact] [--format markdown|yaml] [--max-chars N] [--out PATH]
```

`<skill_dir>` 是 skill 包根目录；脚本可在任意 cwd 运行，不依赖工作目录。

## 参数

| 参数 | 含义 | 约束 |
|---|---|---|
| `transcript` | 要转写的文件路径（绝对、相对或 `~` 开头） | 与 `--list` / `--search` 互斥 |
| `--list` | 按各 harness 固定目录列出候选，不解析内容 | 不能与 `transcript` / `--search` / `--max-chars` / `--out` / `--format` / `--profile` 同用（退出码 2） |
| `--search` | 按内容定位 transcript：查询按空白切词、小写去重后匹配文件原始字节（`.zst` / `.zstd` 为解压后字节） | 必须配 `--harness`（内容检索不跨 harness）；不能与 `transcript` / `--list` / `--max-chars` / `--out` / `--format` / `--profile` 同用；`kilo-code` 不支持；去空白后为空退出码 2 |
| `--harness` | 只列 / 只搜某个 harness 的候选 | 配 `--list` 或 `--search`；取值见 `SKILL.md` 的「支持范围」 |
| `--match` | 只看路径包含该子串的候选，不区分大小写 | 配 `--list` 或 `--search` |
| `--since` | 只看修改时间不早于该本地日期的候选 | 配 `--list` 或 `--search`；格式 `YYYY-MM-DD`，非法日期退出码 2 |
| `--limit` | 最多输出条数 | 配 `--list` 或 `--search`；正整数；`--list` 缺省 20，`--search` 缺省 10 |
| `--profile` | 压缩档位 | 取值只有 `default` / `full` / `compact`；`digest` / `handoff` 不是脚本档位（传入即退出码 2） |
| `--format` | 输出格式 | `markdown`（缺省）或 `yaml` |
| `--max-chars` | 工具结果与 system 消息的截断上限，缺省 2000 | 只能配 `--profile default`；正整数 |
| `--out` | 输出文件路径 | 缺省写 stdout；父目录自动创建 |

## 退出码

| 码 | 含义 |
|---|---|
| `0` | 成功 |
| `1` | 文件不存在 / 不是文件 / 不可读 / 格式无法识别 / 解压失败 / 写文件失败 |
| `2` | 参数错误：上表全部约束冲突、非法日期、未知 harness / 档位 / 格式、缺少输入 |

## 输出契约

### Markdown

首行 `# Transcript · <harness> · <开始时间>`（无开始时间时为 `# Transcript · <harness>`）。

会话头字段按此顺序，空值字段整行省略：

1. `- harness:`
2. `- profile:`（仅 `full` / `compact`）
3. `- session:`
4. `- source:`（恒有）
5. `- cwd:`
6. `- origin:`（originator 与 version 以空格连接）
7. `- history:`
8. `- events: <N> (<角色 计数>)`（有事件时带括号计数，顺序 user / assistant / system / tool）

其后一行 `---`，然后每个事件一个小节：`## <序号> · <种类>[ · <工具名>][ · <时间戳>]`。

- 消息事件：正文直接写出。
- 工具事件：`- status:`（仅非空时）、调用块（shell 类工具标 `bash`，其余标 `text`）、结果块（标 `text`）。
- `compact` 档位没有结果块；非 shell 工具也没有调用块；状态为 `completed` 时不写 `- status:`。

### YAML

顶层键固定为 `harness`、`profile`、`session`、`source`、`cwd`、`started`、`origin`、`history`、`events`；空值字段整键省略，`profile` 三档都写。

事件键固定为 `kind`、`role`、`tool`、`ts`、`status`、`text`、`call`、`result`；空值字段整键省略。多行文本用 `|` / `|-` 字面块；时间戳、路径与含 `: ` 或空格的字符串加双引号，解析后仍是字符串。

`compact` 档位省略 `result` 与非 shell 工具的 `call`，并省略状态为 `completed` 的 `status`。

### --list

首行 `# candidates: <N>`，`N` 等于其后实际行数；每行 `<修改时间 YYYY-MM-DDTHH:MM:SS>\t<harness>\t<绝对路径>`，按修改时间倒序。无候选时只输出首行。

### --search

首行 `# matches: <N>` 是全部命中数（不受 `--limit` 影响）；次行 `# ambiguous: yes|no`。其后每个命中一行，制表符分隔：

<修改时间 YYYY-MM-DDTHH:MM:SS>\t<harness>\tscore=<最弱词项出现次数>\tterms=<命中词项数>/<词项总数>\t<绝对路径>

- 排序：命中词项数降序 → `score` 降序 → 修改时间降序 → 路径升序。
- `score` 取所有词项里最弱的那项出现次数；不要改用出现次数之和排序（常见词会把真正密集的会话顶掉）。
- 查询按空白切词、小写去重；存在全部词项都命中的文件时只输出这些（全命中），否则输出至少命中一个词项的文件（部分命中）。
- `ambiguous` 为 `yes` 当且仅当：首位是部分命中，或首位 `score` 小于第二位 `score` 的两倍。
- 大小写不敏感只对 ASCII 成立（实现用字节小写）。

### 三档差异

| 档位 | 消息 | 工具 | 体积 |
|---|---|---|---|
| `default` | 全文；system 截断到 `--max-chars` | 名字、状态、命令原文、结果（结果与非 shell 工具参数截断到 `--max-chars`） | 中等 |
| `full` | 全文，不截断 | 全部原文，不截断 | 最大 |
| `compact` | system 300 字符、user / assistant 1200 字符 | 只留名字与状态，shell 命令前 160 字符，无结果 | 最小 |

`default` 与 `full` 的截断处附 `[... truncated N chars ...]`。

### 附加文档

脚本不产出 digest / handoff。它们是 Agent 读 `compact` 素材后按 `assets/` 模版撰写的文档；其结构由模版与 `SKILL.md` 定义，本文不重复。

## 依赖

仅标准库，Python ≥3.9。

- `.jsonl.zst` / `.jsonl.zstd` 解压三选一：Python 3.14 `compression.zstd`、`zstandard` 包、`zstd` 命令行；都不可用时退出码 1。
- `kilo.db` 用标准库 `sqlite3` 只读打开。

## 示例

```bash
# 列候选
python3 transcript-shaker/scripts/transcript_shaker/__main__.py --list --harness omp --limit 5
```

```bash
# 按内容检索（有区分度的多词项）
python3 transcript-shaker/scripts/transcript_shaker/__main__.py --search "unify-skill-axes" --harness omp
```

```bash
# 压缩会话较多时先缩小语料
python3 transcript-shaker/scripts/transcript_shaker/__main__.py --search "transcript_shaker" --harness codex --since 2026-10-01 --limit 3
```

```bash
# default 档位写文件
python3 transcript-shaker/scripts/transcript_shaker/__main__.py ~/.omp/agent/sessions/x.jsonl --out session.md
```

```bash
# 全文 YAML
python3 transcript-shaker/scripts/transcript_shaker/__main__.py ~/.codex/sessions/x/rollout-2026-10-20.jsonl --profile full --format yaml
```

```bash
# compact 素材
python3 transcript-shaker/scripts/transcript_shaker/__main__.py ~/.claude/projects/p/s.jsonl --profile compact --out session.compact.md
```

## 边界情况

- 空事件流：Markdown 输出 `- events: 0`，YAML 输出 `events: []`，退出码 0。
- `--list` 跳过 0 字节文件与 command-code 的 `*.checkpoints.jsonl`；直接把这些路径传给转写会报格式错误。
- 含孤立代理项（如 `\ud83e`）的字段在输出时替换为 U+FFFD，源文件不动。
- 单次只解析传入的那一个文件；子代理 / 子会话 transcript 是独立会话，需分别传入。
- kilo-code 传整个 `kilo.db`，只转写库中最新的会话。
- gemini-cli 同一会话可能有两份副本，按内容里的 `sessionId` 取一份。
- `--search` 不支持 `kilo-code`（整个 `kilo.db` 含多个会话，定位语义不成立），传入即退出码 2。
- `--search` 中单文件读失败（权限、解压不可用）被跳过，不中断检索；该文件不出现在输出里。
- `--search` 的 `.zst` / `.zstd` 走三选一解压（`compression.zstd` / `zstandard` / `zstd` 命令）；三者都不可用时该候选被跳过。

## 常见错误

| stderr 片段 | 原因 | 处理 |
|---|---|---|
| `file not found` | 路径不存在 | 核对路径，或用 `--list` 找 |
| `unsupported transcript format` | 内容不属于任何已注册 harness | 报告支持范围，不要手写解析 |
| `--max-chars 只能用于 --profile default` | 档位与截断上限冲突 | 去掉 `--max-chars` |
| `--search 必须指定 --harness（内容检索暂不跨 harness）` | 内容检索不跨 harness | 先确定 harness 再检索 |
| `--search 不支持 kilo-code：kilo.db 含多个会话` | 该 harness 一个库文件含多个会话 | 改用别的 harness，或直接用 `--list` 定位 |

## 支持范围

harness × 文件路径 × 备注矩阵见 `SKILL.md` 的「支持范围」小节，此处不重复。
