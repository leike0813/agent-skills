---
name: tag-regulator
description: 在严格受控词表（`valid_tags`）约束下，利用 LLM 语义理解对 Zotero tags 进行规范化，并可基于元数据推断（infer_tag）标签。作为 `$tag-regulator` 被调用，从 prompt payload 读取 `metadata`/`input_tags`/`valid_tags`/`infer_tag`，stdout 必须且只能输出一个 JSON 对象。
metadata:
  author: joshua
  version: "0.1.0"
---

# tag-regulator

## 目的

给定 prompt 内的 payload：

- `{{ input.metadata }}`：论文元数据（允许自由类型，只要语义明确即可，推荐：JSON/文本/bibtex-like）
- `{{ input.input_tags }}`：待规范的原始 tag 列表（字符串数组）
- `{{ parameter.infer_tag }}`：是否从元数据推断 tag（布尔语义；默认行为见下）
- `{{ parameter.valid_tags_format }}`：受控词表文件格式（`yaml|json|auto`），默认 `yaml`
- `{{ input.valid_tags }}`：受控词表文件路径

在 stdout 输出**且只能输出一个 JSON 对象**，描述：

- 需要从输入列表中移除哪些 tag（`remove_tags`）
- 需要新增哪些受控 tag（`add_tags`，且必须属于 `valid_tags`）
- 需要建议哪些“已规范但不在受控词表中”的 tag（`suggest_tags`）

这是一个 **Agent Skill**：核心工作依赖语义理解（同义、改写、隐含含义），脚本仅用于校验/格式化等辅助，不承担语义决策。
发布包内仅保留运行时必需脚本：
- `tag-regulator/scripts/validate_valid_tags.py`（执行开始阶段校验 `valid_tags`）
- `tag-regulator/scripts/normalize_output.py`（输出前做确定性收敛）

## 强约束（必须遵守）

1) 非交互：不得提问；遇到分歧/不确定性采用保守默认行为并完成运行。
2) stdout：**只输出一个 JSON 对象**（不得输出日志、解释、Markdown code fence 或多段 JSON）。
3) 输出 JSON 必须包含下列 key（即使为空也必须存在）：
   - `metadata`（回显；必须与输入一致，不得改写）
   - `input_tags`（回显；必须与输入一致，不得改写）
   - `remove_tags`（数组；元素必须来自 `input_tags` 原始条目）
   - `add_tags`（数组；不重复；每个元素必须属于 `valid_tags`）
   - `suggest_tags`（数组；不重复；按命名规范输出；且不得包含任何已在 `valid_tags` 中的 tag）
   - `provenance.generated_at`（UTC ISO-8601 字符串，以 `Z` 结尾）
   - `warnings`（数组）
   - `error`（`object|null`）
4) 失败兜底：
   - 读取 `input_tags` 失败，或读取/解析 `{{ input.valid_tags }}` 失败（缺失/不可读/类型错误/编码异常/格式不符）时，必须返回 schema 兼容 JSON：
     - `remove_tags=[]`，`add_tags=[]`
     - `error` 为非空对象，至少包含 `{ "type": "...", "message": "..." }`
     - 仍需包含 `warnings`、`provenance.generated_at`，并在可用时回显 `metadata`/`input_tags`
5) 受控词表：
   - `add_tags ⊆ valid_tags` 为硬约束。
   - 不在 `valid_tags` 但语义相关的候选 tag 只能进入 `suggest_tags`（先按命名规范归一化）。

## `infer_tag` 默认行为（必须遵守）

判断是否启用推断（inference）：

1) 若 `metadata` 缺失或为空 → 强制 `infer_tag=false`（忽略用户意图）。
2) 否则，若 `infer_tag` 可被解释为真/假 → 采用该语义。
3) 否则，若显式提供了 `infer_tag` 但无法解释为真/假 → 默认 `infer_tag=true`。
4) 否则，若未提供 `infer_tag` 且 `metadata` 非空 → 默认 `infer_tag=true`。

## Tag 命名规范（生成 `suggest_tags` 时必须应用）

遵循仓库中的规则（参考 `references/tag_standard.md`；受控词表内容以 `{{ input.valid_tags }}` 为准）：

- 统一格式：`facet:value` 或 `facet:path`（`facet` 永远小写）
- 层级使用 `/`（例如 `field:CE/UG/Tunnel`）
- 多词使用 `-`（例如 `topic:face-stability`）
- 注册缩写必须大写（例如 `DL`、`ML`、`CV`、`FE`、`MC`、`TBM`、`NATM`）
- 非缩写部分一律小写
- 详细规则参考 `references/tag_standard.md`

## 执行流程

### Step 0：读取并校验 payload

- 确保 `input_tags` 为字符串数组。
- `metadata` 允许自由类型（JSON 对象、纯文本、bibtex-like 字符串均可）。
- 读取 `{{ input.valid_tags }}` 文件路径，确定 `valid_tags_format`（默认 `yaml`）。
- 若 `input_tags` 缺失/非法，或 `{{ input.valid_tags }}` 读取/解析/结构校验失败 → 按“失败兜底”直接返回错误输出。

#### valid_tags_format 解析规则（必须遵守）

- 默认 `valid_tags_format=yaml`。
- 支持：`yaml|json|auto`。**（不支持 markdown / txt 这类无结构约束的文本文件，因为当文件损坏时容易形成误解析，导致产出错误，污染 tag）**
- 当 `valid_tags_format` 为 `yaml|json` 且解析失败：**不得尝试其它格式，直接失败兜底（返回 `error`）**。
- 当且仅当 `valid_tags_format=auto`（显式指定）时，才允许按 `yaml -> json` 顺序尝试；并在 `warnings` 中记录最终采用的格式。

YAML（推荐）：

- 文件内容顶层为字符串列表，例如：
  - `- field:CS/AI/CV`

JSON：

- 文件内容顶层为字符串数组，例如：
  - `["field:CS/AI/CV", "model:DL/Transformer"]`

#### Step 0.5：运行时前置校验脚本（必须先执行）

- 在进入语义规范化前，先调用：
  - `python tag-regulator/scripts/validate_valid_tags.py --valid-tags "{{ input.valid_tags }}" --format "<resolved_valid_tags_format>"`
- 脚本职责只有两件事：
  - 按允许格式（`yaml|json|auto`）解析 `valid_tags` 文件；
  - 断言解析结果是“顶层字符串数组”。
- 若脚本返回非 0：立即走“失败兜底”，不得进入后续语义流程。
- 若运行环境无法调用脚本：必须执行等价回退校验（按同样格式规则解析并断言“顶层字符串数组”）；回退失败同样直接兜底。
- 仅在前置校验成功后，才把解析结果作为 `valid_tags` 进入 Step 1。

### Step 1：以 `valid_tags` 建立规范化目标集合

- 将 `valid_tags` 视为唯一允许写入 `add_tags` 的规范 tag 集合。
- 在做语义映射时，优先在 `valid_tags` 内寻找最佳匹配。

### Step 2：对 `input_tags` 做语义驱动规范化

对 `input_tags` 中每个 tag `t`，选择以下一种处理：

1) **保持不变**（不产生变更）：
   - 若 `t` 与某个 `valid_tags` 条目完全相同，则对此 tag 不做任何处理。

2) **映射为受控 tag**：
   - 若 `t` 是某个受控 tag `v ∈ valid_tags` 的大小写/空格/标点变体或语义同义表达，则：
     - 将 `t` 放入 `remove_tags`
     - 将 `v` 放入 `add_tags`
   - 保守处理：仅在把握较高时才将 `v` 加入 `add_tags`。

3) **建议（不在受控词表中）**：
   - 若 `t` 表达的概念与任务相关，但无法映射到任何 `v ∈ valid_tags`，则：
     - 当 `t` 非标准/噪声/重复时，将 `t` 放入 `remove_tags`
     - 生成一个按命名规范归一化后的候选，放入 `suggest_tags`
   - `suggest_tags` 用于后续词表治理；除非其已存在于 `valid_tags`，否则不得加入 `add_tags`。

4) **作为噪声移除**：
   - 若 `t` 与任务无关、格式异常或冗余，则将其放入 `remove_tags`。

约束：

- `remove_tags` 中的元素必须严格从 `input_tags` 原始条目中选择（不得发明新字符串）。
- `add_tags` 不得重复，且每个元素必须属于 `valid_tags`。
- `suggest_tags` 不得重复，且不得包含任何已在 `valid_tags` 中的条目。

### Step 3：从 `metadata` 推断 tag（若启用）

若启用推断，从以下字段（若存在）提取语义并推断候选 tag，优先级如下：

1) `title`
2) `abstract`
3) `keywords`
4) `conference_name`
5) `publication_title`

推断规则：

- 推断结果必须优先映射到 `valid_tags`（即：只把受控词表支持的 tag 写入 `add_tags`）。
- 若某个概念很相关但不在 `valid_tags`，则将其归一化后写入 `suggest_tags`，不得写入 `add_tags`。
- 若不确定，倾向于不添加，并在 `warnings` 中说明不确定性。

### Step 4：确定性输出整形（稳定排序）

输出需稳定、适合批处理自动化：

- `remove_tags`：按 `input_tags` 中出现顺序输出，并去重。
- `add_tags`：去重后按字典序排序。
- `suggest_tags`：去重后按字典序排序。

### Step 4.5：运行时脚本调用时机（若可用）

- 在得到候选输出 JSON 后、最终写入 stdout 前，调用 `tag-regulator/scripts/normalize_output.py` 对输出进行收敛。
- 输入：候选输出 JSON（文件形式或等价内存对象）。
- 期望效果：`remove_tags` 顺序/去重一致，`add_tags` 与 `suggest_tags` 去重并稳定排序。
- 调用失败时不得中断主流程：记录一条 `warnings`，并执行“无脚本回退流程”。

### Step 4.6：无脚本回退流程（必须可执行）

当运行环境无法调用 `tag-regulator/scripts/normalize_output.py` 时，必须执行等价规则：

- `remove_tags`：按 `input_tags` 原始顺序过滤并去重。
- `add_tags`：去重后按字典序排序。
- `suggest_tags`：去重后按字典序排序。

回退后仍必须满足全部契约：stdout 单 JSON、required keys 完整、`add_tags ⊆ valid_tags`、`remove_tags ⊆ input_tags`。

### Step 5：输出 JSON

输出且仅输出一个 JSON 对象，包含：

- required keys（全部必须存在）
- `provenance.generated_at` 为 UTC ISO-8601（例如 `2026-02-11T12:34:56Z`）
- `warnings`：描述不确定性或降级行为
- 成功时 `error=null`

## 输出 schema（required keys）

```json
{
  "metadata": {},
  "input_tags": [],
  "remove_tags": [],
  "add_tags": [],
  "suggest_tags": [],
  "provenance": { "generated_at": "YYYY-MM-DDTHH:MM:SSZ" },
  "warnings": [],
  "error": null
}
```

## 示例（锚定示例）

### 示例 A：无变更（已受控；metadata 为空会禁用推断）

输入 payload：

```json
{
  "metadata": {},
  "input_tags": ["status:2-to-read", "field:CE/UG/Tunnel"],
  "infer_tag": true,
  "valid_tags_format": "yaml",
  "valid_tags": "/abs/path/to/uploads/valid_tags"
}
```

- `valid_tags`: 
```yaml
- status:2-to-read
- field:CE/UG/Tunnel
- ...
```

输出（stdout；仅 JSON）：

```json
{
  "metadata": {},
  "input_tags": ["status:2-to-read", "field:CE/UG/Tunnel"],
  "remove_tags": [],
  "add_tags": [],
  "suggest_tags": [],
  "provenance": { "generated_at": "2026-02-11T00:00:00Z" },
  "warnings": ["metadata 为空；已禁用推断"],
  "error": null
}
```

### 示例 B：同义/非标准写法规范化为受控 tag (JSON valid_tags 输入)

输入 payload：

```json
{
  "metadata": { "title": "Tunnel inspection with deep learning" },
  "input_tags": ["field:tunneling", "tool:pytorch"],
  "infer_tag": false,
  "valid_tags_format": "json",
  "valid_tags": "/abs/path/to/uploads/valid_tags"
}
```

- `valid_tags`: 
```json
[
  "field:CE/UG/Tunnel",
  "tool:PyTorch"
]
```

输出：

```json
{
  "metadata": { "title": "Tunnel inspection with deep learning" },
  "input_tags": ["field:tunneling", "tool:pytorch"],
  "remove_tags": ["field:tunneling", "tool:pytorch"],
  "add_tags": ["field:CE/UG/Tunnel", "tool:PyTorch"],
  "suggest_tags": [],
  "provenance": { "generated_at": "2026-02-11T00:00:00Z" },
  "warnings": [],
  "error": null
}
```

### 示例 C：推断新增受控 tag；不在词表中的概念进入建议

输入 payload：

```json
{
  "metadata": {
    "title": "Crack segmentation in tunnel linings using UNet",
    "keywords": ["tunnel", "crack", "segmentation"]
  },
  "input_tags": ["topic:cracking"],
  "infer_tag": true,
  "valid_tags_format": "yaml",
  "valid_tags": "/abs/path/to/uploads/valid_tags"
}
```

- `valid_tags`:
```yaml
- field:CE/UG/Tunnel
- topic:crack
- ai_task:segmentation
- model:DL/UNet
```

输出：

```json
{
  "metadata": {
    "title": "Crack segmentation in tunnel linings using UNet",
    "keywords": ["tunnel", "crack", "segmentation"]
  },
  "input_tags": ["topic:cracking"],
  "remove_tags": ["topic:cracking"],
  "add_tags": ["ai_task:segmentation", "field:CE/UG/Tunnel", "model:DL/UNet", "topic:crack"],
  "suggest_tags": [],
  "provenance": { "generated_at": "2026-02-11T00:00:00Z" },
  "warnings": ["推断具有启发式性质；如结果异常请人工复核"],
  "error": null
}
```

## 失败模式示例（锚定示例）

### 失败 A：`valid_tags` 缺失/非法

输入 payload：

```json
{ "metadata": {}, "input_tags": ["status:2-to-read"] }
```

输出：

```json
{
  "metadata": {},
  "input_tags": ["status:2-to-read"],
  "remove_tags": [],
  "add_tags": [],
  "suggest_tags": [],
  "provenance": { "generated_at": "2026-02-11T00:00:00Z" },
  "warnings": [],
  "error": { "type": "invalid_input", "message": "`valid_tags` is required and must be a list of strings" }
}
```

### 失败 B：metadata 缺失会禁用推断（即使显式请求推断）

输入 payload：

```json
{
  "input_tags": [],
  "infer_tag": true,
  "valid_tags_format": "yaml",
  "valid_tags": "/abs/path/to/uploads/valid_tags"
}
```

- `valid_tags`:
```yaml
- field:CE/UG/Tunnel
```

输出：

```json
{
  "metadata": null,
  "input_tags": [],
  "remove_tags": [],
  "add_tags": [],
  "suggest_tags": [],
  "provenance": { "generated_at": "2026-02-11T00:00:00Z" },
  "warnings": ["metadata 缺失/为空；已禁用推断"],
  "error": null
}
```
