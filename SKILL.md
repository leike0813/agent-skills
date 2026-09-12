---
name: codex-salvager
description: Salvage Codex session history from local rollout files and distill it into structured Markdown. Use when the user asks to recover, salvage, or summarize past Codex sessions — either one session found by a keyword or quoted passage, or every session of a workspace when given a path or nothing.
argument-hint: "[<工作区路径> | <关键词或一段精确文本>]"
disable-model-invocation: true
---

# codex-salvager

从本机 Codex 的 rollout 文件中打捞历史会话，产出结构化 markdown。两种模式：

- **精确文本模式**：按一段原文精确匹配，打捞**一个**会话。
- **工作区模式**：枚举关联到某个工作区的**全部**历史会话，汇总成一份报告。

## 触发与前置

用户发起时提供**一段精确文本**、**一个工作区路径**、或什么都不提供。

## 目录

会话文件位于 `$CODEX_HOME/sessions`；未设置该环境变量时回退 `~/.codex/sessions`。

## 解释器与路径

```bash
SKILL_DIR="<本 SKILL.md 所在目录的绝对路径>"
if [ -f "$HOME/.ar/pyproject.toml" ]; then
  PY=(uv run --project="$HOME/.ar" --locked -- python)
else
  PY=(python3)
fi
```

三个脚本的 stdout 都只输出**一个 JSON 对象**；失败、无命中、参数错误一律通过该 JSON 的 `error` 字段表达，进程退出码恒为 0。

## Step 0 · 模式判别

按下列顺序判定，命中即止，**不得**自行改变顺序或扩展条件：

1. 参数为空 → **工作区模式**，目标＝当前工作目录。
2. 参数非空，且「形如路径」（以 `/` 开头、以 `~/` 开头、含 `/`、或等于 `.` / `..`）**且** `test -d "<参数>"` 成功 → **工作区模式**，目标＝该参数。
3. 其余（含形如路径但目录不存在、以及任何不含 `/` 的普通词）→ **精确文本模式**。

判定 3 的取舍：形如路径但目录不存在时**不**进工作区模式，因为该参数可能只是含斜杠的关键词（如 `manuscript/v3.qmd`）。此时按精确文本模式搜索；若用户确认那是已被删除的工作区，请其改用绝对路径重试。

模式确定后按对应章节执行；两个模式的脚本调用与产物互不共用。

---

## 精确文本模式

### Step 1 · 搜索

```bash
"${PY[@]}" "$SKILL_DIR/scripts/search.py" --query "<用户提供的文本>"
```

输出字段：`candidates[]`（每个含 `path/thread_id/thread_name/role/phase/match_count/match_count_by_role/line/ordinal/timestamp/snippet/cwd/git/cli_version/originator/start/end/human_messages/noise_matches/forked_from_id`）、`scanned_files`、`elapsed_s`、`truncated_candidates`、`excluded{subagent_files,noise_only_files}`、`error`。

`role` 表示命中位置的语义，可信度由高到低：`user` > `assistant_final` > `plan` > `assistant_commentary` > `reasoning` > `tool_input` > `tool_output` > `noise`。

### Step 2 · 分派（硬规则，不得自由发挥）

1. `error` 非空 → 报告 `error.code` 与 `error.message`，停止。
2. `candidates` 为空 → 报告「未命中」，并给出 `excluded` 统计；若 `excluded.subagent_files > 0`，说明命中只落在子代理线程，可提示用户加 `--include-subagents` 查看文件名（但本流程不支持打捞子代理会话）；否则提示用户改用更短或更独特的片段。**不要**自动做模糊搜索、**不要**自动加 `--include-subagents`，停止。
3. `candidates` 恰好 1 个 → 进入 Step 3。
4. `candidates` ≥ 2 个 → 逐个预解析：

   ```bash
   "${PY[@]}" "$SKILL_DIR/scripts/parse.py" --rollout "<候选 path>" --preview --query "<用户提供的文本>"
   ```

   预解析不写任何文件。把每个候选汇总成一张表（`thread_name` | `cwd` | 时间跨度 | `role` | 片段），然后用 `ask` 单选让用户选定，推荐项＝`role` 优先级最高者（并列时取 `match_count` 更大者）。用户未选 → 停止，不写产物。

### Step 3 · 解析整个会话

```bash
"${PY[@]}" "$SKILL_DIR/scripts/parse.py" --rollout "<选定的 path>"
```

读取 stdout JSON：`timeline_path`、`stats_path`、`turns`、`chars`、`truncated`、`dropped_commentary`、`omitted_turns`、`budget_exceeded`、`error`。

`timeline.md` 是喂给总结的中间产物，包含：头部元信息、逐轮的 `### User` / `### Assistant (commentary)` / `### Assistant (final)` / `### Plan` / `### Turn actions`。它已剔除系统注入、压缩回放和工具输出正文。

**禁止**直接读 rollout `.jsonl` 原文。

### Step 4 · 读时间线并总结

用 `read` 分段读 `timeline.md`（每次 ≤400 行，按需续读；`stats.json` 只在需要时读）。然后写产物。

若 `omitted_turns > 0`，时间线中间省略了部分轮次——在产物的「Current State」里明确写出省略的轮次数。

### 产物（精确文本模式）

- 路径：`<当前工作目录>/codex-salvage-<thread_id 前8位>-<YYYYMMDD>.md`
- 已存在同名文件 → 追加 `-2`、`-3`…，**绝不覆盖**。写入前先 `read` 一次目标路径确认。
- 模板（标题文本固定，不得改写）：

```markdown
# Codex 会话打捞：<一句话主题>

- 会话线程：`<thread_id>`
- 项目目录：`<cwd>`
- Git：`<branch> @ <commit 前8位>`（无则省略本行）
- 客户端：`<originator>` / cli `<cli_version>`
- 时间跨度：`<start> → <end>`
- 命中文本：`<query>`
- 原始 rollout：`<path>`
- 打捞时间：`<YYYY-MM-DD HH:MM>`

## Goal

## Key Decisions & Reasoning

## What Changed

## Current State

## Next Steps
```

### 写作约束

- 只写时间线中有据可查的内容，**不得**补写推测。
- `Key Decisions & Reasoning`：每条写成「选择 X，因为 Y。放弃了 Z，因为 …」；没有取舍记录就写「未记录取舍依据」。
- `What Changed`：每条以文件路径开头；路径取 `Turn actions` 中的文件变更行。
- `Current State`：分「已完成」与「未完成或风险」两组。
- `Next Steps`：用 `- [ ]` 列出；无从推断时写「（本会话未涉及）」。
- 任一小节无内容写「（本会话未涉及）」。
- 全篇 60–200 行；不得出现工具原始日志、密钥、大段代码或 token 用量明细。

### 完成报告（精确文本模式）

向用户报告：产物绝对路径、命中候选数、`turns` 与 `chars`、是否发生截断（`truncated` / `dropped_commentary` / `omitted_turns`）。

---

## 工作区模式

枚举 `session_meta.cwd` 与该工作区**精确相等**的全部会话，逐个精简提取后汇总。

范围边界（**不**在此模式内）：不沿 `forked_from_id` 回溯、不纳入子代理线程、不做子目录或同仓库工作树扩展。

### W1 · 枚举

```bash
"${PY[@]}" "$SKILL_DIR/scripts/workspace.py" [--target "<目标路径>"]
```

输出字段：`target`、`target_source`（`argument` / `cwd`）、`root`、`scanned_files`、`elapsed_s`、`sessions[]`（每个含 `path/thread_id/session_id/thread_name/start/end/duration_s/duration/size_bytes/mtime/cwd/repo/branch/originator/cli_version`）、`totals{sessions,bytes,duration_s,span_start,span_end}`、`excluded{subagent_files,other_cwd_files}`、`error`。

`sessions` 已按 `start`（会话创建时间）升序排列。

### W2 · 空结果

`error` 非空 → 报告 `error.code` 与 `error.message`，停止。

`sessions == []` → 报告「该工作区没有历史会话」，附 `target` 与 `excluded` 统计，并提示：

- 目标路径若含符号链接或末尾多写 `/`，改用真实路径重试；
- 若 `excluded.other_cwd_files > 0`，说明本机确有 Codex 会话但都不在此路径下；同仓库的 Orca 工作树可能位于其他目录，可分别对它们运行本模式。

停止，不写产物。

### W3 · 确认门（硬门，不得跳过）

把 `totals.sessions`、`totals.bytes`（换算为 MB）、`totals.span_start` → `totals.span_end`、`totals.duration_s`（用 `rollout.format_duration_secs` 的规则呈现）、以及按 W4 公式算出的 `batch_count` 汇总成一段说明，用 `ask` 让用户选择：

- 「开始打捞」——推荐项；
- 「缩小范围」——用户改传更具体的工作区路径后回到 W1；
- 「取消」——停止，不写任何产物。

用户未作答或选择取消 → 停止。

### W4 · 切批

```
batch_size  = min(8, max(5, ceil(N / 24)))     # N = totals.sessions
batch_count = ceil(N / batch_size)
```

取 `sessions`（已按 start 升序），从头部起连续切批，第 i 批记为 `batches[i]`（`batch_index = i`）。批数超过 32 时按批序分批提交，不改变切批结果。

### W5 · 委派

对每批提交一个 subagent 任务，提示词逐字采用下节模板。当前环境无 subagent 能力时，主 agent 按同一格式逐个提取，并在完成报告中说明未委派。

主 agent 侧约束：

- MUST NOT 把多批会话合并进一个 subagent；
- MUST NOT 让 subagent 写最终报告；
- 批内会话顺序由主 agent 决定，subagent 不得重排。

### W6 · 汇总

按 `batch_index` 升序拼接各 subagent 返回的 markdown 段（**不按返回时间**）。缺失或返回为空的批次，由主 agent 自己按同一格式补齐；仍失败则记入报告的「提取失败或跳过」小节。

### W7 · 产物（工作区模式）

- 路径：`<当前工作目录>/codex-salvage-workspace-<slug>-<YYYYMMDD>.md`，其中 `slug = os.path.basename(target.rstrip("/")) or "root-workspace"`。
- 已存在同名文件 → 追加 `-2`、`-3`…，**绝不覆盖**。写入前先 `read` 一次目标路径确认。
- 报告骨架（标题文本、顺序、表格列均不得改写）：

```markdown
# Codex 工作区会话打捞：<slug>

- 工作区路径：`<target>`
- 匹配方式：`session_meta.cwd` 精确相等
- 会话数量：<N> 个（另有 <excluded.subagent_files> 个子代理线程、<excluded.other_cwd_files> 个其他工作区文件已排除）
- 时间跨度：<totals.span_start> → <totals.span_end>
- 会话时长合计：<totals.duration_s 按 format_duration_secs 规则呈现；无法计算时写「—」>
- 原始 rollout 目录：`<root>`
- 打捞时间：<YYYY-MM-DD HH:MM>（UTC）

## 会话总览

| 起始时间 | 会话 | 时长 | 目标 |
|---|---|---|---|
| <YYYY-MM-DD HH:MM>Z | `<thread_id 前8位>` | <duration，无则写「—」> | <一句话目标，≤40 字> |

## 会话明细

<各 subagent 返回的段落，按起始时间升序>

## 提取失败或跳过

<仅当存在时输出；每行：`- \`<thread_id 前8位>\` — <原因>`>
```

`## 会话总览` 的每行对应一个会话（按起始时间升序），「目标」列取该会话明细段的「目标」内容；「时长」列取 `workspace.py` 给出的 `duration`。明细段格式由 subagent 产出，主 agent 不重写。「提取失败或跳过」小节仅在存在失败项时输出。

### 完成报告（工作区模式）

向用户报告：产物绝对路径、会话数、批数、整体时间跨度，以及有多少会话的提取失败或走了中段省略。

---

## subagent 委派提示词（工作区模式，逐字使用）

占位符：`<B>` 批内会话数、`<TARGET>` 工作区路径、`<SKILL_DIR>` 本 SKILL.md 所在目录、`<PY_CMD>` 已探测的解释器命令（如 `uv run --project=/home/joshua/.ar --locked -- python`）、`<LIST>` 批内会话清单。

```
你是 codex-salvager 工作区打捞模式的提取 subagent。你只负责分配给你的 <B> 个会话，不写最终报告。

工作区：<TARGET>
技能目录：<SKILL_DIR>
解释器命令：<PY_CMD>

分配给你的会话（已按起始时间升序，你必须保持该顺序）：
<LIST>

对每个会话依次执行：
  <PY_CMD> "<SKILL_DIR>/scripts/parse.py" --rollout "<绝对路径>" --layout brief
取 stdout JSON 的 timeline_path，用 read 工具分段读完该文件（每次 ≤400 行，按需续读）。

禁止：读取 rollout .jsonl 原文；调用 parse.py 以外的脚本；写入任何文件；写入时间线中没有依据的内容。

对每个会话产出一段 markdown，格式严格如下（标题的 `### ` 前缀、` · ` 分隔符、`**目标**` 等字样均不得改写）：

### <start 的 YYYY-MM-DD HH:MM>Z · `<thread_id 前8位>` · <duration>

- **目标**：<一句话，取自 User requests 中最早一条的意图>
- **结论**：<一句话，取自 Final answers 的最终结果；无则写「未记录结论」>
- **产出**：<最多 3 个关键文件路径，取自 Files changed；无则写「无文件变更」>

规则：
- 「目标」「结论」各不超过 60 字，不得复制时间线原文长句。
- 「产出」只列路径，不加描述。
- 若 timeline 头部有 omitted 行，在「结论」后追加 `（中段省略 <N> 轮）`。
- 若 parse.py 返回非空 error，该段改为：
  ### <start 的 YYYY-MM-DD HH:MM>Z · `<thread_id 前8位>` · ?
  然后一行 `- **提取失败**：<error.code>`
- 若 timeline 头部 turns 为 0、或整份文件没有 User requests 段，该段改为一行 `- **无有效内容**`。
- 最终回复只含这些 markdown 段；不要前言、不要总结、不要用代码块包裹。
```

`<LIST>` 的每行格式固定为：`- path: <绝对路径> | thread_id: <id> | start: <ISO8601>`。

## 排障

解析结果异常（缺命令、缺文件变更、字段为空）、工作区枚举结果与预期不符，或需要确认某 Codex 版本的 rollout 差异时，读 `references/rollout-schema.md`。
