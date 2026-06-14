# Subagent Delegation Protocol

本文档定义 subagent 委派翻译的完整协议。在 Phase 7 准备委派 subagent 前读取。

## Availability

Subagent 委派是**可选路径**：

```
If the current environment can delegate to subagents, use the delegation path below.
If subagents are unavailable, process the same batches serially in the main agent and do not block the workflow.
```

## Payload File Format

每个 batch 的 payload 已由 `partition_batches.py` 生成，位于 `workspace/batches/batch_<N>.json`。无需主 agent 额外创建 payload。

### 供 subagent 使用的上下文

subagent 需要以下信息：
- Batch payload 文件（已存在）
- 术语表文件路径：`workspace/glossary.json`
- 目标语言
- 全局翻译约束（见下文）

## 建议委派 Prompt

```markdown
You are a subagent working on one delegated translation batch for the literature-translator skill.

Read the batch payload at:
<workspace>/batches/<batch_N>.json

Read the glossary at:
<workspace>/glossary.json

Your task:
- Translate all sentences in each block of the batch from the source language to <target_language>.
- Follow the glossary: terms defined in glossary.json must be used as specified.
- DO NOT translate formula or code blocks. Keep their content exactly as-is.
- DO NOT skip, summarize, or omit any content. Translate every sentence faithfully.
- Maintain the original sentence count per block. Each original sentence must have exactly one translated sentence.
- Maintain the original block structure. Output must preserve all block_ids.

### Step 0: Write capability probe

Before translating, try to create an empty temp file to probe write capability:

```bash
touch /tmp/subagent_<batch_N>_probe.tmp
```
If the file was created successfully (you can check with `test -f` or equivalent), writing to disk is allowed.
If the probe fails (permission denied, read-only filesystem, etc.), you MUST use stdout delivery instead.

Delete the probe file after the check: `rm -f /tmp/subagent_<batch_N>_probe.tmp`.

### Output delivery

Based on the probe result:

- **If writing is allowed:** write the result to `<workspace>/translations/<batch_N>_translated.json` and return only `{"delivery": "file", "path": "<absolute_path>", "status": "ok"}`.
- **If writing is NOT allowed:** return the full result JSON directly in stdout.

### Output format

```json
{
  "batch_id": "<original batch_id>",
  "original_batch": "<original batch_id>",
  "blocks": {
    "<block_id>": {
      "type": "<block type>",
      "sentences": ["<translated sentence 1>", "<translated sentence 2>", ...]
    }
  }
}
```

Rules:
- Each block's sentences array must have the SAME length as the original.
- For blocks of type "equation" or "code", output the original sentences unchanged.
- Do not add explanations, notes, or commentary outside the JSON structure.

If blocked:
- Return a structured blocker with batch_id, reason, missing_input, and suggested_next_step.
```

## 结果返回协议

Subagent 须先在 prompt 指导下执行写文件探测（Step 0），再根据探测结果选择交付路径。

### 写文件交付（优先）

Subagent 尝试写临时文件成功 → 翻译完成后将结果写入 `workspace/translations/<batch_N>_translated.json`，返回 JSON：

```json
{"delivery": "file", "path": "<absolute_path>", "status": "ok"}
```

### Stdout 交付（退路）

Subagent 尝试写临时文件失败（无写权限/只读文件系统等）→ 在 stdout 中输出与文件格式一致的完整 JSON 结构。主 agent 读取 stdout 后，代为写入 `workspace/translations/<batch_N>_translated.json`。

## 验收与失败处理

### 主 agent 验收

每个 subagent 返回后（无论文件还是 stdout），主 agent 必须：

1. 确认结果 JSON 可解析、包含所有必需字段。
2. 调用 `scripts/quality_gate.py` 校验翻译质量。
3. 校验通过：确认结果已写入 `workspace/translations/<batch_N>_translated.json`。
4. 校验失败：将失败详情发给 subagent（或串行重翻），要求修正后重新提交。

### Subagent 不可用时的退路

若当前环境不支持 subagent 委派（通过 Phase 0 的环境分析确定），主 agent 按相同流程串行翻译每个 batch：

1. 读取 batch payload（`workspace/batches/batch_<N>.json`）。
2. 读取术语表（`workspace/glossary.json`）。
3. 翻译所有句子。
4. 构造与 subagent 输出相同结构的 JSON。
5. 写入 `workspace/translations/batch_<N>_translated.json`。
6. 调用 `quality_gate.py` 校验。

### 结果缺失或格式错误

- 若 subagent 未返回结果或结果格式错误：要求重新提交，或由主 agent 串行翻译该 batch。
- 连续 2 次格式错误：改为主 agent 串行处理，不再委派该 batch。

### 冲突处理

- subagent 返回的 `batch_id` 必须与委派的 batch 一致。
- 返回的 block_id 集合必须覆盖 batch 中的所有 block_id。
- 返回的 sentences 数组长度必须与原始 batch 一一对应。
- 主 agent 保留最终裁决权：发现明显错误时修正翻译内容。
