---
name: codex-salvager
description: Salvage one Codex session from local rollout files by exact text match and distill it into a structured Markdown digest. Use when the user asks to recover, salvage, or summarize a past Codex session found by a keyword or quoted passage.
argument-hint: "<关键词或一段精确文本>"
disable-model-invocation: true
---

# codex-salvager

从本机 Codex 的 rollout 文件中按**精确文本**定位**一个**会话，解析成时间线，总结为结构化 markdown。

## 触发与前置

用户发起时需提供**一个关键词或一段精确文本**（要求原文一致，不做模糊匹配）。若未提供，先向用户索取——这是本流程除候选歧义外唯一允许的提问点。

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

两个脚本的 stdout 都只输出**一个 JSON 对象**；解析失败、无命中、参数错误一律通过该 JSON 的 `error` 字段表达，进程退出码恒为 0。

## Step 1 · 搜索

```bash
"${PY[@]}" "$SKILL_DIR/scripts/search.py" --query "<用户提供的文本>"
```

输出字段：`candidates[]`（每个含 `path/thread_id/thread_name/role/phase/match_count/match_count_by_role/line/ordinal/timestamp/snippet/cwd/git/cli_version/originator/start/end/human_messages/noise_matches/forked_from_id`）、`scanned_files`、`elapsed_s`、`truncated_candidates`、`excluded{subagent_files,noise_only_files}`、`error`。

`role` 表示命中位置的语义，可信度由高到低：`user` > `assistant_final` > `plan` > `assistant_commentary` > `reasoning` > `tool_input` > `tool_output` > `noise`。

## Step 2 · 分派（硬规则，不得自由发挥）

1. `error` 非空 → 报告 `error.code` 与 `error.message`，停止。
2. `candidates` 为空 → 报告「未命中」，并给出 `excluded` 统计；若 `excluded.subagent_files > 0`，说明命中只落在子代理线程，可提示用户加 `--include-subagents` 查看文件名（但本流程不支持打捞子代理会话）；否则提示用户改用更短或更独特的片段。**不要**自动做模糊搜索、**不要**自动加 `--include-subagents`，停止。
3. `candidates` 恰好 1 个 → 进入 Step 3。
4. `candidates` ≥ 2 个 → 逐个预解析：

   ```bash
   "${PY[@]}" "$SKILL_DIR/scripts/parse.py" --rollout "<候选 path>" --preview --query "<用户提供的文本>"
   ```

   预解析不写任何文件。把每个候选汇总成一张表（`thread_name` | `cwd` | 时间跨度 | `role` | 片段），然后用 `ask` 单选让用户选定，推荐项＝`role` 优先级最高者（并列时取 `match_count` 更大者）。用户未选 → 停止，不写产物。

## Step 3 · 解析整个会话

```bash
"${PY[@]}" "$SKILL_DIR/scripts/parse.py" --rollout "<选定的 path>"
```

读取 stdout JSON：`timeline_path`、`stats_path`、`turns`、`chars`、`truncated`、`dropped_commentary`、`omitted_turns`、`budget_exceeded`、`error`。

`timeline.md` 是喂给总结的中间产物，包含：头部元信息、逐轮的 `### User` / `### Assistant (commentary)` / `### Assistant (final)` / `### Plan` / `### Turn actions`。它已剔除系统注入、压缩回放和工具输出正文。

**禁止**直接读 rollout `.jsonl` 原文。

## Step 4 · 读时间线并总结

用 `read` 分段读 `timeline.md`（每次 ≤400 行，按需续读；`stats.json` 只在需要时读）。然后写产物。

若 `omitted_turns > 0`，时间线中间省略了部分轮次——在产物的「Current State」里明确写出省略的轮次数。

## 产物

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

## 写作约束

- 只写时间线中有据可查的内容，**不得**补写推测。
- `Key Decisions & Reasoning`：每条写成「选择 X，因为 Y。放弃了 Z，因为 …」；没有取舍记录就写「未记录取舍依据」。
- `What Changed`：每条以文件路径开头；路径取 `Turn actions` 中的文件变更行。
- `Current State`：分「已完成」与「未完成或风险」两组。
- `Next Steps`：用 `- [ ]` 列出；无从推断时写「（本会话未涉及）」。
- 任一小节无内容写「（本会话未涉及）」。
- 全篇 60–200 行；不得出现工具原始日志、密钥、大段代码或 token 用量明细。

## 完成报告

向用户报告：产物绝对路径、命中候选数、`turns` 与 `chars`、是否发生截断（`truncated` / `dropped_commentary` / `omitted_turns`）。

## 排障

解析结果异常（缺命令、缺文件变更、字段为空）或需要确认某 Codex 版本的 rollout 差异时，读 `references/rollout-schema.md`。
