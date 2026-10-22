---
name: transcript-shaker
description: Turn a local agent-session transcript into a readable log (markdown or YAML; default, full, or compact compression), optionally plus a digest or handoff document. Use when locating, reading, exporting, summarizing, or handing off past agent sessions.
---

# transcript-shaker

## 何时使用

把 Agent Harness 的本地会话记录（transcript）读成一份可读日志；需要摘要或交接时，在同一份日志之上再产出一份独立文档。日志本身完全由脚本确定性产出，你只负责定位会话、选模式、写附加文档。

出现下列任一信号就用本 skill：

- 用户给出或描述一段**已有**会话记录（transcript / rollout / chat history / 会话文件）。
- 用户提到「之前那次」「上次那个会话」「最近的 agent 会话」。
- 用户记得会话内容（说过的话、某个报错文本、某个关键词）但说不清是哪个文件 → `--search` 内容检索。
- 用户要求导出、整理、精炼、通读、审计一段会话过程。
- 用户要求基于某段会话写摘要、提要、交接文档。
- 用户要求把会话转成机器可解析格式。

不适用于：当前正在进行的会话本身（无需转写）、没有本地记录可读的对话。

## 输入输出契约

**输入**：自由文本，可以为空。

- 给出路径 → 直接转写。
- 只给 harness / 目录 / 时间 / 项目线索（没说内容）→ `--list` 定位。
- 只给内容线索（说过什么、什么报错）且 harness 已知 → `--search` 定位；harness 未知 → 先问用户是哪个 harness，不要跨 harness 试，也不要靠猜。
- 为空或只说「最近的会话」→ `--list` 列候选，然后取最符合的一条或问用户。

内容检索只用于定位，不产出交付物；命中后照常按「三个轴」转写。

**输出**：

- 必有一份 transcript 日志（Markdown 或 YAML）。
- 可选一份附加文档（digest 或 handoff），由你按模版撰写，脚本不产出。
- 交付说明包含：harness、压缩档位、格式、输出路径、事件条数（取自 `- events:` 行或 YAML `events` 的长度）。

## 三个轴

三个轴彼此正交，可自由组合。

### 轴一：压缩（`--profile`）

| 档位 | 产出 | 取舍 | 用在哪 |
|---|---|---|---|
| `default` | 消息全文；工具状态、命令与结果（结果与 system 消息截断到 `--max-chars`，默认 2000） | 体积与原文的折中；超长工具输出带 `[... truncated N chars ...]` | 缺省选择：要看清过程，但不关心超长输出原文 |
| `full` | 同结构，任何字段都不截断 | 体积最大、token 成本最高 | 要完整命令、完整结果或完整 system 提示词；审计工具输出 |
| `compact` | 消息按角色截断（system 300 字、user / assistant 1200 字）；工具只留名字与状态，shell 命令前 160 字；无结果块 | 体积最小（同一会话约为 `default` 的 1/6），细节不可恢复 | 只要过程骨架；也是 digest / handoff 的素材档 |

- `full` / `compact` 的会话头含 `- profile: <档位>`，`default` 不含。
- `compact` 的脚本产出仍逐事件编号、事件条数与 `default` 一致。你可以在它基础上删除与用户问题无关的条目、合并同类条目、去掉重复噪声；不得补写脚本已丢弃的内容，不得新增结论或评价。

### 轴二：附加输出

| 值 | 产出 | 用在哪 |
|---|---|---|
| 无（缺省） | 只有 transcript | 大多数情况 |
| `digest` | 另交一份 `# Digest ·` 文档（四节，≤40 行） | 用户要摘要、提要、「这段会话做了什么」 |
| `handoff` | 另交一份 `# Handoff ·` 文档（五节） | 用户要把工作交接给下一次会话或另一个人 |

两个附加值互斥。附加文档一律由你撰写，模版在 `assets/`，格式随轴三。

### 轴三：格式（`--format`）

`markdown`（缺省）或 `yaml`。同时作用于 transcript 与附加文档：选 `yaml` 时 transcript 用 YAML，附加文档也用 YAML 模版。

### 组合与脚本调用次数

| 压缩 + 附加 | 脚本调用 | 交付物 |
|---|---|---|
| 任一 + 无 | 1 次：`--profile <压缩档位>` | 1 份 transcript |
| `compact` + digest/handoff | 1 次：`--profile compact` | transcript + 附加文档（同一份产出） |
| `default` / `full` + digest/handoff | 2 次：交付档位一次、`--profile compact` 一次 | transcript + 附加文档（附加文档只读 compact 那次） |

非 compact 且要附加输出时多跑一次 compact，是因为写附加文档只需要骨架，不该把 `default` / `full` 的全文塞进上下文。

## 执行流程

1. **定输入**：见「输入输出契约」。只有内容线索时走 `--search`；harness 不明先问用户。
2. **定三个轴**：压缩档位按用户意图对照轴一表格；附加输出看用户要不要摘要 / 交接；格式看是给人读（markdown）还是给程序解析（yaml）。用户没说就 `default` + 无 + `markdown`。
3. **跑脚本**：见「脚本调用」。
4. **写附加文档**（若轴二不为「无」）：见「附加输出流程」。
5. **交付**：说明 harness、档位、格式、路径、事件条数。脚本退出码非 0 时把 stderr 原文转述给用户，不要自行修复或改写 transcript。

## 脚本调用

```bash
python3 <skill_dir>/scripts/transcript_shaker/__main__.py <transcript> --profile default|full|compact --format markdown|yaml [--max-chars N] [--out PATH]
python3 <skill_dir>/scripts/transcript_shaker/__main__.py --list [--harness NAME] [--match TEXT] [--since YYYY-MM-DD] [--limit N]
python3 <skill_dir>/scripts/transcript_shaker/__main__.py --search "<内容关键词>" --harness NAME [--since YYYY-MM-DD] [--match TEXT] [--limit N]
```

| 参数 | 含义 |
|---|---|
| `transcript` | 要转写的文件路径（绝对、相对或 `~` 开头） |
| `--list` | 不解析内容，按各 harness 固定目录列出候选 |
| `--search` | 内容检索：按空白切词后匹配原始字节；必须配 `--harness`；`kilo-code` 不支持 |
| `--harness` | 配合 `--list` / `--search` 过滤；检索时用户没给 harness 必须先问用户，给了会话目录即视为已给 |
| `--match` / `--since` / `--limit` | 配合 `--list` / `--search` 过滤；不能用于转写 |
| `--profile` | 压缩档位，取值见轴一 |
| `--format` | `markdown`（缺省）或 `yaml` |
| `--max-chars` | 仅 `default` 可用：工具结果与 system 消息的截断上限，缺省 2000 |
| `--out` | 输出文件路径；缺省写 stdout，父目录自动创建 |

完整参数约束、退出码、输出契约、依赖与边界情况见 `references/script-usage.md`。

## 内容检索

用户只记得会话里说过什么、不知道是哪个文件时用它。

1. **先定 harness**。用户说了 harness、给了会话文件路径或会话目录 → 直接用；只给内容 → **先问用户是哪个 harness**（列出「支持范围」里的 harness 名，去掉不支持检索的 kilo-code），不要跨 harness 逐个试，也不要猜。
2. **跑检索**：`--search "<词>" --harness <name>`，可加 `--since` / `--match`（项目目录片段）缩小范围。词用有区分度的 2–3 个关键词，全词命中优于单个常见词；中文查询没有空格时先自己拆成 2–3 个词项（整句会被当成一个词项）。
3. **看歧义标记**：
   - `# ambiguous: no` → 首行就是目标，直接转写它。
   - `# ambiguous: yes` → **不要自己挑**：把候选行（修改时间、score、路径）连同各路径含义列给用户，问处理哪一个；用户选定后再转写。
   - `# matches: 0` → 先确认 harness 对不对、词是否换过（去掉最泛的词），或改用 `--since` / `--match` 再试一次；仍无结果就如实报告没找到。
4. **检索结果不是交付物**。交付物永远是转写出来的 transcript（以及按需的 digest / handoff）。

## 附加输出流程

1. **取素材**：压缩轴已是 `compact` 时直接用第 3 步的 transcript；否则再跑一次 `--profile compact`（同一 `--format`）。素材超过约 300 行时用 `--out` 落盘再分段读。
2. **套模版**：`assets/digest.md` / `assets/digest.yaml` / `assets/handoff.md` / `assets/handoff.yaml`。`<...>` 是占位符，填充后不得残留。
3. **落盘**：用户给了路径就用它；否则写到当前工作目录，命名 `<transcript 主名>-digest.<ext>` / `<transcript 主名>-handoff.<ext>`，`<ext>` 与格式轴一致（`md` / `yaml`）。
4. **只写素材里有的内容**：compact 丢弃的工具参数与结果不得凭猜测补写；用户需要细节就说改用 `default` / `full` 重跑。
5. **handoff 脱敏**：API key、密码、token、个人身份信息一律替换为 `<redacted>`；引用按路径 / 命令 / commit 写，不复制原文。

## 禁止事项

- 不得手工解析 transcript，或用其它工具重新拼接输出；识别、解析、裁剪、渲染一律由脚本完成。
- 不得修改、移动、删除原 transcript。
- 不得输出 thinking / reasoning 内容。
- 不得对支持范围以外的 harness 伪造解析结果；直接说明尚未支持。
- 不得把 `--list` 的候选列表当作转写结果交付。
- 不得跳过 `assets/` 模版自创 digest / handoff 结构，也不得把脚本输出当成交付的附加文档。

## 支持范围

下表同时是 `--list` 的扫描范围；用户直接给路径时按“备注”判断。脚本一次只解析传入的那一个文件。

| harness | 传入文件 | 备注 |
|---|---|---|
| codex | `$CODEX_HOME/sessions/*/*/*/rollout-*`（或 `.jsonl.zst`）；归档在 `$CODEX_HOME/archived_sessions/` | 旧版本 rollout 也支持；`CODEX_HOME` 未设置时用 `~/.codex` |
| claude-code | `~/.claude/projects/*/<session-uuid>.jsonl` | `subagents/agent-*.jsonl` 是子代理会话，需单独传入 |
| qwen-code | `~/.qwen/projects/*/chats/<uuid>.jsonl` | 同目录 `<uuid>.runtime.json`、`meta.json` 不是正文 |
| command-code | `~/.commandcode/projects/*/*.jsonl` | `*.checkpoints.jsonl` 是检查点元数据（prompt + 文件快照），`--list` 跳过；`~/.commandcode/sessions/hooks-audit-*.jsonl` 是审计日志，不支持 |
| codebuddy | `~/.codebuddy/projects/*/*.jsonl` | 0 字节文件很常见，跳过 |
| gemini-cli | `~/.gemini/tmp/*/chats/session-*.json` | 同一会话可能有两份副本，按 `sessionId` 取一份 |
| pi | `~/.pi/agent/sessions/*/*.jsonl` | 一个文件一个会话 |
| omp | `~/.omp/agent/sessions/*/*.jsonl` | `<会话>/<Agent>.jsonl` 是子代理会话，需单独传入 |
| minimax-code | `~/.minimax/v2/sessions/*/*/*/*/messages.jsonl` | 会话 id 与开始时间取自同目录 `manifest.json` |
| kilo-code | `~/.local/share/kilo/kilo.db` | 整个库，只取最新的一个会话 |
| cline | `~/.cline/data/sessions/*/*.messages.json` | 同目录 `<id>.json` 提供 cwd 与真实开始时间 |
| multicoder | `~/.multicoder/content/ses_*.json` | 无逐条时间戳 |
| grok | `~/.grok/sessions/*/*/chat_history.jsonl` | 只读这一份；同目录 `updates.jsonl`、`events.jsonl` 是重复流；模型未回复的会话也识别，输出 `events: 0` |
| kimi-code | `~/.kimi-code/sessions/*/session_*/agents/main/wire.jsonl` | `agents/agent-*/wire.jsonl` 是子代理会话，需单独传入；只有会话头与配置事件的空会话输出 `events: 0` |
| deepseek-harness | `~/.dsh/sessions/*/*/session*.jsonl.zstd` | 子会话是独立目录，需单独传入 |

## 易错点

- `--list` 只看路径与修改时间，不读内容：0 字节文件与 command-code 的 `*.checkpoints.jsonl` 已被跳过，其余文件仍可能解析失败，以实际运行结果为准；空会话输出 `- events: 0` 或 `events: []`。
- `compact` 丢弃工具结果与非 shell 工具的调用内容；要原文用 `default` / `full`。
- 非 compact 压缩 + 附加输出要跑两次脚本，不要把 `default` / `full` 的输出读进上下文。
- codex 超过 7 天的会话被压成 `.jsonl.zst`，修改时间是压缩时间；按会话发生时间挑选时看文件名里的时间戳（本地时间）。
- gemini-cli 同一会话可能有两份副本，任选其一；要按 `sessionId` 判断时读文件内容，不要靠文件名。
- kilo-code 传整个 `kilo.db`，只转写库中最新的会话。
- claude-code、omp、kimi-code 的子代理文件是独立会话，需要逐个运行、分别交付。
- 部分会话含孤立代理项（如 `\ud83e`），脚本已替换，不要为此改动原文件。
- 附加文档默认写到当前工作目录，命名 `<transcript 主名>-digest.<ext>`；用户给了路径则以其为准。
- `--search` 匹配原始字节，不解析事件：system 提示、工具 schema 与思考文本都会参与匹配，命中数不等于命中质量；用有区分度的多词项，别用单个常见词。
- `--search` 只在指定 harness 内检索，且不支持 kilo-code（一个库含多个会话）。
- codex 全库含 4000+ 个 `.zst` 压缩会话，检索要解压，耗时可达几十秒；先用 `--since` / `--match` 缩小。

## 成功标准

- transcript 首行为 `# Transcript · <harness> · <开始时间>`，harness 与用户描述或 `--list` 结果一致；`full` / `compact` 会话头含 `- profile:`。
- 输出不含任何 thinking / reasoning 文本；`default` 下超限的工具结果带 `[... truncated N chars ...]`。
- 选了 digest / handoff 时，附加文档存在、标题正确（`# Digest ·` / `# Handoff ·`）、无残留 `<...>` 占位符、结构与 `assets/` 对应模版一致；handoff 已脱敏。
- 交付说明包含 harness、压缩档位、格式、路径、事件条数。
- 用户只给模糊描述时，最终转写的是真实存在的文件，且交付说明给出该路径。
- 用户只给内容线索时，harness 不明先问用户、不擅自跨 harness 检索；最终定位并转写的是真实存在的文件。
- `# ambiguous: yes` 时先让用户选，不擅自挑第一个。

## 参考资料

- `references/script-usage.md`：脚本完整用法（参数约束、退出码、输出契约、内容检索、依赖、边界情况、常见错误）。改脚本或排查调用问题时读。
- `assets/digest.md` / `assets/digest.yaml`：摘要模版（Markdown / YAML）。写 digest 时必读。
- `assets/handoff.md` / `assets/handoff.yaml`：交接模版（Markdown / YAML）。写 handoff 时必读。
- `scripts/transcript_shaker/`：实现；只在需要判断某个字段是否会被输出时读。
