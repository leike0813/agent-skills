# Codex rollout 文件结构

排障用参考。文中所有 schema 断言均来自对本机 `~/.codex/sessions` 全库（2095 个文件、7.69 GB、cli 0.71.0 → 0.153.4）的实际扫描。

## 1. 文件布局与命名

```
$CODEX_HOME/sessions/YYYY/MM/DD/rollout-<本地时间>-<thread_id>.jsonl   # 默认 CODEX_HOME=~/.codex
$CODEX_HOME/archived_sessions/rollout-*.jsonl                          # 归档，同格式
$CODEX_HOME/session_index.jsonl                                        # thread_id -> thread_name
```

- 一个 rollout 文件 = 一个线程。文件名中的 UUID 等于首条 `session_meta.payload.id`。
- 搜索范围只用 `sessions/`，不含 `archived_sessions/`。
- 规模参考：中位 1.27 MB，p90 7.8 MB，最大 157 MB（58444 行）。

## 2. 行格式与顺序保证

一行一条 JSON，顶层恒为四个字段：

```json
{"timestamp":"2026-09-10T04:36:13.621Z","ordinal":0,"type":"session_meta","payload":{…}}
```

- 单文件内 `ordinal` 从 0 严格递增且唯一。
- 单文件内 `timestamp` 单调不减。
- 因此文件行序即会话顺序，无需按时间重排。

## 3. 顶层 type 与 payload

| type | 说明 |
|---|---|
| `session_meta` | 文件身份，见下文 |
| `response_item` | API 形态的消息流：`message` / `reasoning` / `function_call(_output)` / `custom_tool_call(_output)` / `web_search_call` / `tool_search_call(_output)` / `agent_message` |
| `event_msg` | 语义化事件：`task_started` / `task_complete` / `turn_aborted` / `item_completed` / `token_count` / `thread_settings_applied` / `thread_goal_updated` |
| `turn_context` | 每轮环境快照：`cwd` `approval_policy` `sandbox_policy` `model` `effort` `summary` `collaboration_mode` `workspace_roots` `current_date` `timezone` |
| `world_state` | 注入态快照：`full`(bool) + `state{agents_md,skills,plugins_instructions,apps_instructions,environments,permissions,…}` |
| `compacted` | 上下文压缩事件 |
| `token_usage_record` | 用量记账（0.153+） |
| `inter_agent_communication_metadata` | 子代理通信触发标记 |

### session_meta

`session_id`（根线程）· `id`（本线程）· `parent_thread_id` · `forked_from_id` · `source`（`"cli"`/`"vscode"`/`"exec"` 或 `{"subagent":{"thread_spawn":{depth,agent_path,agent_nickname}}}`）· `thread_source`（`user`/`subagent`）· `cwd` · `originator` · `cli_version` · `git{commit_hash,branch,repository_url}` · `history_mode`（恒 `paginated`）· `base_instructions` · `context_window`

两个专有名词：

- **双 meta 文件**（195/2095）：ordinal 0 是自身，ordinal 1 是父线程快照（`meta2.id == meta1.parent_thread_id`）。**身份只取 ordinal 0。**
- **`thread_source` 可能缺失**：实测 84 个用户线程文件该字段为 null，因此子代理判定必须同时看 `source.subagent` 与 `parent_thread_id`。

### response_item.message

`role` ∈ `user` / `assistant` / `developer`；`content[]` 块类型 `input_text` / `output_text` / `input_image` / `encrypted_content`；`phase` ∈ `commentary` / `final_answer` / 缺失。

`role=developer` 是系统注入，不是人写的。

### response_item.reasoning

`summary[]{type:"summary_text", text}` 为明文摘要；`content` 常为 null；`encrypted_content` 是 1 KB 级密文，不可读。

### event_msg.item_completed

`payload{turn_id, started_at_ms, completed_at_ms, item{type,id,…}}`。`item.type` 全集与关键字段：

| item.type | 关键字段 |
|---|---|
| `UserMessage` | `content[].text` |
| `AgentMessage` | `content[]{type:"Text", text}`；`phase` |
| `Reasoning` | `summary_text[]`, `raw_content[]` |
| `CommandExecution` | `command[]`(argv), `cwd`(file:// URI), `parsed_cmd`, `status`, `aggregated_output`, `exit_code`, `duration` |
| `FileChange` | `changes{<绝对路径>:{type:add\|update\|delete, content}}`, `status`, `stdout`, `stderr` |
| `McpToolCall` | `server`, `tool`, `arguments`, `result`, `status`, `duration`, `error` |
| `Plan` | `text`（markdown 计划全文） |
| `WebSearch` | `query`, `action` |
| `Extension` | `kind`, `query`, `action`, `results[]` |
| `SubAgentActivity` | `kind`, `agent_thread_id`, `agent_path` |
| `CollabAgentToolCall` | `tool`, `sender_thread_id`, `receiver_thread_ids`, `agents_states` |
| `ContextCompaction` | 无（仅 `id`） |
| `ImageView` | `path` |
| `FunctionCallOutput` | `name`, `namespace`, `output` |

### event_msg.task_started / task_complete / turn_aborted

- `task_started{turn_id, started_at, model_context_window, collaboration_mode_kind}`
- `task_complete{turn_id, last_agent_message, duration_ms, time_to_first_token_ms, error}`
- `turn_aborted{turn_id, reason, duration_ms}`

`task_complete.last_agent_message` 是该轮收尾正文，可作为 `final_answer` 的兜底。旧文件 `turn_id` 形如 `rollout-4`，新文件是 UUID。

### compacted

`message`（摘要，实测多为空串）· `replacement_history[]` · `compaction_response_id` · `latest_token_usage_record` · `window_number` / `window_id` / `previous_window_id` / `first_window_id` · `guardian_history`。

`replacement_history` 条目类型：`message(user)`、`message(assistant)`、`message(developer)`、`compaction{encrypted_content}`。**它是历史回放，不是本文件新增内容**，且压缩摘要为密文——想要摘要只能靠 `AgentMessage` / `final_answer` / `task_complete.last_agent_message`。

### token_usage_record

`thread_id` · `turn_id` · `session_id` · `root_turn_id` · `response_id` · `usage` · `turn_token_usage` · `thread_token_usage`，后三者形如 `{input_tokens, cached_input_tokens, cache_write_input_tokens, output_tokens, reasoning_output_tokens, total_tokens}`。

## 4. 版本兼容表

| cli | 关键差异 |
|---|---|
| 0.71.0 / 0.89.0 | 只有 `session_meta` + `response_item.message`，无 `event_msg`，无 `phase`；这类文件可能整份只有系统注入（无人类输入），此时解析应报 `empty_timeline` |
| 0.78.0–0.86.0 | 出现 `task_started`/`task_complete`/`item_completed`；工具名为 `shell_command` / `apply_patch`；item 仅 `UserMessage` / `Reasoning` / `AgentMessage` |
| 0.108+ | assistant message 出现 `phase`；出现 `Plan` item |
| 0.118+ | 出现 `CommandExecution` / `FileChange` / `WebSearch` item（此前命令只记录在 `function_call`） |
| 0.140+ | 出现 `McpToolCall` item |
| 0.144+ | 工具名为 `exec` / `wait`；`custom_tool_call` 成为主导 |
| 0.149+ | 出现 `SubAgentActivity` / `CollabAgentToolCall` item 与 `collaboration.*` 工具 |
| 0.153+ | 出现 `token_usage_record`、`agent_message`、`inter_agent_communication_metadata` |

按文件数分代：旧代（<0.144，130 个）／中代（0.144–0.151，1678 个）／新代（0.153+，287 个）。

## 5. 已知陷阱

1. **双流重复**：同一动作同时写在 `response_item` 与 `event_msg.item_completed`，内容等价（同一行号成对出现）。择一即可，否则内容翻倍。
2. **`role=user` 里大量是系统注入**：`# AGENTS.md instructions`、`<environment_context>`、`<recommended_plugins>`、`<skill>`、`<subagent_notification>`、`<turn_aborted>`、`<user_instructions>`、`<plugins_instructions>`、`<apps_instructions>`、`<filesystem>`、`<workspace_roots>`、`<permission_profile>`、`You are working inside Orca`。
3. **IDE 包裹**：真实人类请求常被包在 `# Context from my IDE setup:` 里，以 `## My request for Codex:` 为分隔（实测 3529 个包裹块中 3517 个含该标记，另 12 个无标记）。
4. **轮次边界在版本间不一致**：新版本是 `task_started` → 提示 → 回复；旧版本（如 0.78.0）会把**下一条**用户提示写在上一轮的 `task_complete` **之前** 与其 `task_started` 之前。判定轮次必须以「新的用户提示文本出现」为界，而不是以记录顺序。
5. **`forked_from_id` 不复放历史**：fork/resume 产生的新文件只含新内容，前序片段留在被 fork 的那个文件里。
6. **`compacted.replacement_history` 是回放**，不应计入本文件的新增事件。
7. **字段随版本漂移**：`message.id` 时有时无、`turn_id` 格式变化、`item_completed` 里 `item` 偶缺、`thread_source` 可能为 null。解析必须容错，未知 type 跳过而非报错。
8. **体量集中且价值低**：`aggregated_output` / `output` / `FileChange.changes[].content` 占文件主体积；`FileChange.changes` 才是真实产出。
9. **性能**：单文件最大 157 MB，须流式逐行读；全库 7.69 GB，`mmap` + `bytes.find` 串行扫描约 3.8 s。
10. **文本匹配须按 JSON 转义形态**：多行查询在 JSONL 中存为转义形态，需同时用原始形态与 `json.dumps(...)[1:-1]` 形态搜索。
