---
name: literature-translator
description: Translate academic literature (Markdown/PDF/LaTeX) between languages with glossary management, deterministic block-level splitting + agent review, sentence-level script splitting, subagent-assisted batch translation, and script-enforced quality gates. Use when the user provides a source_path and target_language for literature translation, including papers, articles, theses, books, technical reports, and academic documents. Covers near-synonyms: translate paper, convert article to Chinese, academic translation, 翻译论文, 翻译文献.
compatibility: Requires local filesystem read access to source_path; no network required.
---

# Literature Translator

## Mission

将学术文献（Markdown / PDF / LaTeX / LaTeX 工程目录 / 无扩展名文本文件）从源语言高质量翻译为目标语言。全程自动化运行，中途不询问用户。最终产出与原文结构对应的完整译文文档。

## Inputs

按以下来源读取（优先级从高到低：prompt payload > parameter schema > 默认值）：

### From Input (input.schema.json)

- `source_path`（required）：输入文献的绝对路径。可以是 `.md`、`.pdf`、`.tex` 单文件、无扩展名文本文件，或包含 `.tex` 文件的目录。
- `source_language`（optional）：源语言名称（BCP-47 代码）。若提供且等于 target_language，将在 Phase 1.5 触发快速退出。

### From Parameter (parameter.schema.json)

- `target_language`（default: `zh-CN`）：目标语言名称。从 parameter 读取，若 prompt 中显式指定则覆盖默认值。
- `source_language`（optional）：同上，作为 input 的备用来源。

### 降级策略

- 若 `source_path` 无法访问，报告 blocker 并输出 failed 状态的 stdout JSON。
- 若 `source_language` 未提供，由 agent 在宏观分析阶段推断。
- 任何分支不得询问用户。

## Workflow

总共 12 个阶段（v2 新增 Phase 1.5、5a、8a、8b、11）。每个阶段有明确产出物，完成后才进入下一阶段。

中间文件统一写入 `.literature_translator_tmp/` 目录。最终产物输出到当前工作目录（CWD）。

最终 assistant 输出必须是单一 JSON 对象，符合 `assets/output.schema.json` 定义的契约。不得输出解释文本、日志或多段输出。三种状态：
- `status=success`：翻译完成，产出物路径全部为绝对路径
- `status=cancelled`：被取消（如语言相等），产出物路径为 null
- `status=failed`：不可恢复错误

### Phase 0: 环境分析

分析当前执行环境：可访问的文件范围、可用工具与 shell 命令、能否联网搜索、能否委派 subagent。

### Phase 1: 输入解析与规范化

1. 调用 `scripts/parse_input.py` 检测输入类型。
2. 根据输入类型做规范化：
   - **Markdown (.md/.txt/无扩展名)**: 校验有效性，复制到临时目录。
   - **PDF (.pdf)**: 调用 mineru 技能或其它可用的 PDF 提取工具转换为 Markdown。
   - **单文件 LaTeX (.tex)**: 解析为结构化 Markdown。
   - **LaTeX 工程目录**: 定位主 `.tex` 文件，解析为结构化 Markdown。
3. 将规范化后的全文内容写为中间工件 `.literature_translator_tmp/normalized.md`。
4. 输出元信息文件 `.literature_translator_tmp/source_meta.json`（格式见 references）。

Stop and report a blocker if: 输入格式无法识别、文件无法访问、PDF 提取后内容为空。

### Phase 1.5: 语言快速退出

判断是否可以在不进入翻译流程的情况下立即退出。

判断逻辑：

1. 取 `source_language`（优先级：input.source_language > parameter.source_language > 未提供）
2. 取 `target_language`（来自 parameter.target_language）
3. 如果两者均非空且相等（大小写不敏感），输出 cancelled 状态的 stdout JSON，立即终止：

```json
{
  "status": "cancelled",
  "reason": "source_language equals target_language",
  "output_path": null,
  "alignment_path": null,
  "glossary_path": null,
  "qa_report_path": null,
  "provenance": {
    "source_path": "<source_path>",
    "source_language": "<detected>",
    "target_language": "<target>"
  }
}
```

4. 否则进入 Phase 2（由 LLM 做精确语言检测）。

Phase 3 保留为安全网——Phase 2 检测后再次做精确比较。

### Phase 2: 宏观分析与术语表

1. **通读全文**（`.literature_translator_tmp/normalized.md`），生成宏观分析报告，包含：
   - 源语言（若未提供则推断）
   - 文献类型（期刊论文、会议论文、书籍章节、技术报告等）
   - 研究领域与研究方向
   - 全文概要
2. **构建结构化上下文档案** `.literature_translator_tmp/context_profile.json`：
   - field：研究领域
   - topic：研究方向/主题
   - paper_type：文献类型（journal/conference/book_chapter/technical_report/thesis）
   - writing_style：写作风格（如 technical academic prose）
   - source_language：检测到的源语言
   - target_language：目标语言
   - core_entities：核心实体列表（模型名、数据集名等）
   - translation_principles：翻译原则列表（忠实翻译、保留不确定性等）
   - warning_markers：需注意保留的不确定性标记（may, might, suggest 等）
   - abbreviations：文中出现的缩写及其全称
3. **构建术语表** `.literature_translator_tmp/glossary.json`：
   - 使用三级结构：
     - `locked`：必须使用指定译法的术语（如 `{"benchmark contamination": "基准污染"}`）
     - `provisional`：建议优先使用的术语（如 `{"alignment": "对齐"}`）
     - `keep_english`：保留英文原文的词列表（如 `["Transformer", "BERT", "RLHF"]`）
   - 不应翻译的词放入 `keep_english`（模型名、数据集名、作者名）
   - 术语表**大小写敏感**
4. 输出宏观分析报告到 `.literature_translator_tmp/analysis.md`。

### Phase 3: 源目标语言判断

如果源语言 == 目标语言，则终止执行。输出 cancelled 状态的 stdout JSON（符合 output.schema.json），`reason` 说明原因：

```json
{
  "status": "cancelled",
  "reason": "source_language equals target_language",
  "output_path": null,
  "alignment_path": null,
  "glossary_path": null,
  "qa_report_path": null,
  "provenance": {
    "source_path": "<original_path>",
    "source_language": "<detected>",
    "target_language": "<target>"
  }
}
```

否则继续。

### Phase 4: 块级拆分（脚本拆分 + Agent 复核）

块级拆分分为两个子步骤：

**Step 4a: 脚本拆分。** 调用 `scripts/blockify.py` 对 `.literature_translator_tmp/normalized.md` 进行确定性块级拆分：

```bash
python3 scripts/blockify.py --input .literature_translator_tmp/normalized.md --output .literature_translator_tmp/blocked.md
```

脚本通过状态机识别以下结构，插入块级标记：

```
<!-- BLOCK: <block_id> | type: <type> | heading: <heading> -->
<!-- BLOCK_END: <block_id> -->
```

支持的块类型：

| Type | 含义 | 处理方式 | 脚本识别可靠性 |
|------|------|----------|---------------|
| `heading` | 章节标题 | 翻译 | 高（`#` 标记） |
| `paragraph` | 普通段落 | 翻译 | 高（默认文本） |
| `equation` | display equation | **不翻译** | 高（`$$` 定界符） |
| `code` | 代码块 | **不翻译** | 高（围栏/verbatim） |
| `table` | 表格 | 表格内文本翻译 | 高（`<table>` 标签） |
| `figure_caption` | 图片标题 | 翻译 | 高（`![]()` 标记） |
| `table_caption` | 表格标题 | 翻译 | 中（关键词匹配） |
| `bib_item` | 参考文献条目 | **不翻译** | 中（`[N]` 模式） |
| `abstract` | 摘要 | 翻译 | 低（关键词启发式） |
| `list` | 列表 | 翻译 | 低（常见前缀匹配） |

**Step 4b: Agent 复核。** 主 agent 通读 `.literature_translator_tmp/blocked.md`，校验块标记的准确性并修正以下问题：

1. **标题遗漏或级别错误** — 脚本可能漏标部分标题（特别是使用全部 `#` 的论文），或不一致的数字编号模式。agent 需检查完整章节结构。
2. **公式边界** — 确认多行公式被完整包含，无片段泄露到相邻段落。
3. **表格/图片标题** — 确认 `table_caption` 和 `figure_caption` 的分类正确，没有误标为 `paragraph`。
4. **摘要标记** — 确认摘要被标记为 `abstract`。脚本可能错过无关键词的摘要段。
5. **列表检测** — 使用非标准前缀（箭头、特殊符号）的列表可能被误标为 `paragraph`。
6. **参考文献拆分** — 确认参考文献被正确拆分为独立的 `bib_item` 块，特别是多行条目。
7. **段落合并** — 相邻同类型短块（如同属一个语义段落的连续段落）应合并为一个 block。

修正方式：直接编辑 `.literature_translator_tmp/blocked.md`，修改 `type:` 字段值、插入或删除块标记、调整 block_id 编号。

### Phase 5: 句级拆分（脚本执行）

调用 `scripts/sentencify.py` 对 `.literature_translator_tmp/blocked.md` 进行句级拆分。

输入：`.literature_translator_tmp/blocked.md`（含块级标记）
输出：`.literature_translator_tmp/sentences.json`

格式见 [references/payload-contracts.md](references/payload-contracts.md) 中的 Sentence JSON Schema。

**公式块、代码块的句级拆分规则：** 这类块整体作为一个"句"保留，不做内部拆分。

### Phase 5a: 行内元素占位符保护（脚本执行）

对句级拆分后的句子中的行内元素进行占位符保护，防止翻译过程中被误改。

调用 `scripts/protect_placeholders.py`：

```bash
python3 scripts/protect_placeholders.py \
  --input .literature_translator_tmp/sentences.json \
  --output-dir .literature_translator_tmp/protected/ \
  --glossary .literature_translator_tmp/glossary.json
```

保护对象（按替换优先级排列）：

1. 行内公式 `$...$` → `<MATH_NNN>`
2. URL / DOI → `<URL_NNN>` / `<DOI_NNN>`
3. 引用编号 `[1]`、`[1, 2]` → `<REF_NNN>`
4. 图号/表号/公式号/章节号 → `<FIG_NNN>` / `<TBL_NNN>` / `<EQ_REF_NNN>` / `<SEC_NNN>`
5. LaTeX 变量命令 → `<VAR_NNN>`
6. 数字（百分比/p-value/范围/科学计数法）→ `<NUM_NNN>`
7. 已知实体名（模型名、数据集名）→ `<ENT_NNN>`

输出：
- `.literature_translator_tmp/protected/sentences.json`（带占位符的句子，保持与原 sentences.json 相同结构）
- `.literature_translator_tmp/protected/placeholder_map.json`（占位符→原始值的映射表）

`keep_english` 中的词已知实体名自动提取为保护对象。

Stop and report a blocker if: 输入格式错误。

### Phase 6: 翻译批次分割

调用 `scripts/partition_batches.py` 根据目标批次大小（默认每批 1500 字符）对带占位符的句子进行均衡分区。

```bash
python3 scripts/partition_batches.py \
  --sentences .literature_translator_tmp/protected/sentences.json \
  --workspace .literature_translator_tmp/batches/ \
  --target-size 1500
```

输出：`.literature_translator_tmp/batches/` 目录下若干 `batch_<N>.json` 文件（每个句子为 `[index, text]` 格式），以及 `.literature_translator_tmp/batches/manifest.json` 总清单。

格式见 [references/payload-contracts.md](references/payload-contracts.md) 中的 Batch Payload Schema。

### Phase 7: 翻译执行与质量门禁

对每个 batch，按以下流程处理：

1. **执行翻译**（两种路径选一）：
   - 如果环境支持 subagent，按 [references/subagent-protocol.md](references/subagent-protocol.md) 委派翻译。翻译 prompt 使用增强版 [references/translation-prompt.md](references/translation-prompt.md)。
   - 否则由主 agent 串行翻译每个 batch，遵循相同的翻译约束。
2. **质量门禁（v2 增强版）**：翻译完成后，调用 `scripts/quality_gate.py` 校验：

   ```bash
   python3 scripts/quality_gate.py \
     --original .literature_translator_tmp/batches/batch_<N>.json \
     --translation .literature_translator_tmp/translations/batch_<N>_translated.json \
     --glossary .literature_translator_tmp/glossary.json \
     --target-lang <target_language> \
     --placeholder-map .literature_translator_tmp/protected/placeholder_map.json
   ```

   检查项（共 8 项）：
   - **句数一致性**：译文句数 == 原文句数。
   - **偷懒检测**：原文与译文字符长度比在 [0.3, 3.0] 范围内。
   - **术语一致性**：glossary.locked 中的术语在译文中被正确使用（通过 placeholder_map 解析占位符后校验）。
   - **语言正确性**：译文语言与 target_language 匹配（含 keep_english 豁免列表）。
   - **占位符保持**：输入端占位符全部出现在译文，译文中无非法占位符。
   - **数字/引用保持**：数字类占位符（NUM, REF, FIG, TBL, EQ_REF）全部保留。
   - **非翻译性语言检测**：译文中不得出现解释性短语（"大意是""可以理解为"等）。
   - **长度类型检查**（弱校验）：按 block 类型分阈值检查长度比，仅作为 warning。
3. **门禁结果处理**：
   - 全部通过：将翻译结果写入 `.literature_translator_tmp/translations/batch_<N>_translated.json`。
   - 有失败项：阅读 stdout JSON 中的失败详情，修正翻译后重试。同一 batch 连续失败 3 次后报 blocker。
   - 弱校验失败（length_check）不作为打回依据。
4. 所有 batch 通过后，将 `.literature_translator_tmp/translations/manifest.json` 标记为 `complete`。

### Phase 8a: 结构化 Review

所有 batch 通过质量门禁后，进行结构化语义审查。

审查方式：委派受限 subagent 执行，使用 [references/reviewer-prompt.md](references/reviewer-prompt.md) 中的审查指令。

构建审查输入 `.literature_translator_tmp/review_input.json`，将待审查的 source/translation pairs 与 context_profile、glossary 一起提交：

```json
{
  "task": "review_translation",
  "context_profile": {...},
  "glossary": {...},
  "blocks": [
    {
      "b": 23,
      "type": "paragraph",
      "heading": "3.2 Experimental Setup",
      "pairs": [
        {"i": 1, "src": "...", "tgt": "..."},
        {"i": 2, "src": "...", "tgt": "..."}
      ]
    }
  ]
}
```

Reviewer 输出结构化错误报告，错误类型包括：omission, addition, mistranslation, terminology, polarity, modality, relation, structure, placeholder, style。

如果 verdict 为 pass（无错误），直接进入 Phase 9。
如果 verdict 为 fail，进入 Phase 8b 局部修复。

### Phase 8b: 局部修复

根据 reviewer 的错误报告进行局部修复，不重译整个 block。

修复方式：委派受限 subagent 执行，使用 [references/repairer-prompt.md](references/repairer-prompt.md) 中的修复指令。

构建修复输入：
- 只修复 reviewer 指出的失败句（severity medium 或 high）
- 已通过的句子不做修改

修复后，重新过质量门禁（quality_gate.py），然后再次进入 reviewer 审查。

修复循环规则：
- 最多 2 轮修复。
- 同一句子连续 2 次修复后 reviewer 仍返回 fail，标记为 risky。
- 超过 50% 的句子需要修复时，退回到整 batch 重翻（而非逐句修复）。
- Risky 句子的策略：保留最佳译文 + 原文，在 QA 报告中标记需要人类注意。

### Phase 9: 占位符还原与译文拼接

**Step 9a: 占位符还原。** 调用 `scripts/restore_placeholders.py`，将翻译结果中的占位符替换回原始值。

```bash
python3 scripts/restore_placeholders.py \
  --translations-dir .literature_translator_tmp/translations/ \
  --placeholder-map .literature_translator_tmp/protected/placeholder_map.json \
  --output-dir .literature_translator_tmp/translations_restored/
```

**Step 9b: 译文拼接。** 调用 `scripts/concatenate.py` 按原始块顺序拼接所有还原后的译文。

```bash
python3 scripts/concatenate.py \
  --blocked .literature_translator_tmp/blocked.md \
  --translations-dir .literature_translator_tmp/translations_restored/ \
  --output .literature_translator_tmp/assembled.md
```

输入：
- `.literature_translator_tmp/blocked.md`（含块级标记的原文）
- `.literature_translator_tmp/translations_restored/` 下所有还原后的 `*_translated.json`

输出：`.literature_translator_tmp/assembled.md`

Stop and report a blocker if: 某块的译文缺失，无法拼接。

### Phase 10: 最终复核（确定性润色）

主 agent 通读 `.literature_translator_tmp/assembled.md`，**仅做语言通顺性修改**。

**允许的修改：**
- 语序调整（使符合中文表达习惯）
- 标点符号修正（中文使用中文标点，英文使用英文标点）
- 连接词优化（使段落间逻辑更清晰）

**禁止的操作：**
- ❌ 合并或拆分段落
- ❌ 删除或添加内容
- ❌ 重写/重组句子结构
- ❌ 修改公式、代码、引用编号、图表编号
- ❌ 修改标题层级、章节编号
- ❌ 改变 glossary 要求的术语

结构以 `concatenate.py` 的权威输出为准。确认无误后，复制到当前工作目录的 `output_<target_language>.md`。

### Phase 11: 导出结构化产物

数据就绪后，导出供后续 skill 使用的结构化文件。

**Alignment 文件：** 调用 `scripts/export_alignment.py` 生成双语对齐数据：

```bash
python3 scripts/export_alignment.py \
  --sentences .literature_translator_tmp/sentences.json \
  --translations-dir .literature_translator_tmp/translations_restored/ \
  --qa-report .literature_translator_tmp/qa_report.json \
  --output .literature_translator_tmp/alignment.json \
  --source-lang <source> --target-lang <target>
```

输出到 CWD 的 `alignment.json`，包含每句的原文、译文、状态（passed/repaired/risky）。

**QA Report 文件：** 调用 `scripts/export_qa_report.py` 生成质量报告：

```bash
python3 scripts/export_qa_report.py \
  --block-stats .literature_translator_tmp/block_stats.json \
  --translations-dir .literature_translator_tmp/translations/ \
  --output .literature_translator_tmp/qa_report.json
```

输出到 CWD 的 `qa_report.json`，包含所有检查结果、修复记录、高风险项。

任务完成，输出最终产物路径。

## Reference Loading Guide

| 需要解决的问题 | 读取 |
|---|---|
| 宏观分析报告、术语表规范、上下文档案格式 | [references/stage-playbook.md](references/stage-playbook.md) |
| 块级拆分细化规则与每类块的处理细则 | [references/stage-playbook.md](references/stage-playbook.md) |
| 翻译阶段的分批原则、目标批次大小、均衡标准 | [references/stage-playbook.md](references/stage-playbook.md) |
| 润色阶段的具体检查清单与约束 | [references/stage-playbook.md](references/stage-playbook.md) |
| Reviewer/Repairer 阶段的操作细则 | [references/stage-playbook.md](references/stage-playbook.md) |
| 增强版翻译 worker prompt | [references/translation-prompt.md](references/translation-prompt.md) |
| 结构化 reviewer prompt | [references/reviewer-prompt.md](references/reviewer-prompt.md) |
| 局部修复模块 prompt | [references/repairer-prompt.md](references/repairer-prompt.md) |
| Batch payload、sentence JSON、quality gate 输入/输出、concatenate 产物的 schema | [references/payload-contracts.md](references/payload-contracts.md) |
| Subagent 委派 prompt 模板、payload 文件示例、结果返回协议 | [references/subagent-protocol.md](references/subagent-protocol.md) |

## Formal Entrypoints

### `scripts/parse_input.py`

- Path: `scripts/parse_input.py`
- Purpose: 检测输入类型、验证文件可访问性、输出规范化 markdown 和元数据。不做语义判断。

Command:

```bash
python3 scripts/parse_input.py --source "/path/to/paper.pdf" --workspace ".literature_translator_tmp/"
```

Input:
- `--source`: 源文件或目录路径（required）
- `--workspace`: 工作目录路径（required）

Output:
- 写入 `.literature_translator_tmp/normalized.md`（规范化后的 markdown 全文）
- 写入 `.literature_translator_tmp/source_meta.json`（元信息）

On success: 读取 `.literature_translator_tmp/normalized.md` 进入 Phase 2。
On failure: 报告具体的不可恢复错误（文件不存在、格式不支持、提取后内容为空）。

### `scripts/blockify.py`

- Path: `scripts/blockify.py`
- Purpose: 对规范化后的 Markdown 进行确定性块级拆分。识别章节标题、公式（`$$`）、表格（`<table>`）、图片（`![]()`）、代码块（` ``` ` / `\begin{verbatim}`）、列表和参考文献结构。不做语义判断。

Command:

```bash
python3 scripts/blockify.py --input ".literature_translator_tmp/normalized.md" --output ".literature_translator_tmp/blocked.md"
```

Input:
- `--input`: 规范化后的 markdown 文件路径（required）
- `--output`: 含块级标记的输出文件路径（required）
- `--stats`: （可选）输出块统计信息 JSON 路径

Output:
- 写入 `.literature_translator_tmp/blocked.md`（含 `<!-- BLOCK: ... -->` 标记的文档）
- 若指定 `--stats`，写入对应统计 JSON

On success: 读取 `.literature_translator_tmp/blocked.md` 进入 Step 4b（Agent 复核）。
On failure: 检查输入文件格式。

### `scripts/sentencify.py`

- Path: `scripts/sentencify.py`
- Purpose: 对已标记 block 的文件进行句级拆分。不做语义分析。

Command:

```bash
python3 scripts/sentencify.py --input ".literature_translator_tmp/blocked.md" --output ".literature_translator_tmp/sentences.json"
```

Input:
- `--input`: 含块级标记的 markdown 文件（required）
- `--output`: 输出 JSON 路径（required）

Output:
- JSON 文件，key 为 block_id，value 为句子数组

On success: 读取 `.literature_translator_tmp/sentences.json` 进入 Phase 6。
On failure: 检查 blocked.md 的块标记格式是否正确。

### `scripts/partition_batches.py`

- Path: `scripts/partition_batches.py`
- Purpose: 按字符阈值均衡分区所有句子块。不做语义判断。

Command:

```bash
python3 scripts/partition_batches.py --sentences ".literature_translator_tmp/sentences.json" --workspace ".literature_translator_tmp/batches/" --target-size 1500
```

Input:
- `--sentences`: sentencify.py 的输出 JSON（required）
- `--workspace`: batches 输出目录（required）
- `--target-size`: 目标批次大小（字符数，默认 1500）

Output:
- `.literature_translator_tmp/batches/manifest.json`（批次总清单）
- `.literature_translator_tmp/batches/batch_<N>.json`（各批次 payload）

On success: 读取 manifest.json 开始分发翻译。
On failure: 检查 sentences.json 格式。

### `scripts/quality_gate.py`

- Path: `scripts/quality_gate.py`
- Purpose: 校验翻译质量（句数一致性、偷懒检测、术语一致性、语言正确性）。不做语义判断，不评价翻译优劣。

Command:

```bash
python3 scripts/quality_gate.py \
  --original ".literature_translator_tmp/batches/batch_1.json" \
  --translation ".literature_translator_tmp/translations/batch_1_translated.json" \
  --glossary ".literature_translator_tmp/glossary.json" \
  --target-lang "zh-CN"
```

Input:
- `--original`: 原始 batch payload JSON（required）
- `--translation`: 翻译结果 JSON（required）
- `--glossary`: 术语表 JSON（required）
- `--target-lang`: 目标语言代码（required）

Output:
- stdout JSON with `{"passed": true/false, "checks": {...}}`
- 不写文件（调用者处理结果）

On success (passed=true): 进入下一 batch 或 Phase 8。
On failure (passed=false): 阅读 stdout 输出中的具体失败项，修正翻译后重试。

### `scripts/concatenate.py`

- Path: `scripts/concatenate.py`
- Purpose: 按原始块顺序拼接所有译文。不做语义修正。

Command:

```bash
python3 scripts/concatenate.py \
  --blocked ".literature_translator_tmp/blocked.md" \
  --translations-dir ".literature_translator_tmp/translations/" \
  --output ".literature_translator_tmp/assembled.md"
```

Input:
- `--blocked`: 含块级标记的原文文件（required）
- `--translations-dir`: 翻译结果目录（required）
- `--output`: 拼接后的输出路径（required）

Output:
- 写入 `.literature_translator_tmp/assembled.md`

On success: 读取 `.literature_translator_tmp/assembled.md` 进入 Phase 10。
On failure: 检查缺失翻译的 block_id。

### `scripts/protect_placeholders.py`

- Path: `scripts/protect_placeholders.py`
- Purpose: 对句级拆分后的句子进行行内元素占位符保护（公式、变量、引用、数字、URL、实体名）。

Command:

```bash
python3 scripts/protect_placeholders.py \
  --input .literature_translator_tmp/sentences.json \
  --output-dir .literature_translator_tmp/protected/ \
  --glossary .literature_translator_tmp/glossary.json
```

Input:
- `--input`: sentencify.py 输出的 sentences.json（required）
- `--output-dir`: 输出目录（required）
- `--glossary`: 术语表 JSON（用于提取 keep_english 实体）

Output:
- `.literature_translator_tmp/protected/sentences.json`（带占位符的句子）
- `.literature_translator_tmp/protected/placeholder_map.json`（占位符映射表）

On success: 读取 `.literature_translator_tmp/protected/sentences.json` 进入 Phase 6。
On failure: 检查输入格式。

### `scripts/restore_placeholders.py`

- Path: `scripts/restore_placeholders.py`
- Purpose: 翻译完成后将占位符还原为原始值。

Command:

```bash
python3 scripts/restore_placeholders.py \
  --translations-dir .literature_translator_tmp/translations/ \
  --placeholder-map .literature_translator_tmp/protected/placeholder_map.json \
  --output-dir .literature_translator_tmp/translations_restored/
```

Input:
- `--translations-dir`: 翻译结果目录（required）
- `--placeholder-map`: placeholder_map.json 路径（required）
- `--output-dir`: 还原后文件输出目录（required）

Output:
- `.literature_translator_tmp/translations_restored/` 目录下还原后的翻译 JSON 文件

On success: 进入 Phase 9b 拼接。
On failure: 检查 placeholder_map.json 格式。

### `scripts/export_alignment.py`

- Path: `scripts/export_alignment.py`
- Purpose: 导出双语对齐数据供下游精读 skill 使用。

Command:

```bash
python3 scripts/export_alignment.py \
  --sentences .literature_translator_tmp/sentences.json \
  --translations-dir .literature_translator_tmp/translations_restored/ \
  --output .literature_translator_tmp/alignment.json
```

Input:
- `--sentences`: 原始 sentences.json（required）
- `--translations-dir`: 还原后的翻译结果目录（required）
- `--output`: alignment.json 输出路径（required）
- `--qa-report`: 可选 QA report 路径（用于状态信息）

Output:
- `alignment.json`（双语对齐数据）

### `scripts/export_qa_report.py`

- Path: `scripts/export_qa_report.py`
- Purpose: 导出结构化质量报告。

Command:

```bash
python3 scripts/export_qa_report.py \
  --block-stats .literature_translator_tmp/block_stats.json \
  --translations-dir .literature_translator_tmp/translations/ \
  --output .literature_translator_tmp/qa_report.json
```

Input:
- `--block-stats`: block 统计数据（required）
- `--translations-dir`: 翻译结果目录（required）
- `--output`: qa_report.json 输出路径（required）

Output:
- `qa_report.json`（质量报告）

## Subagent Delegation

Subagent 委派是可选路径。如果当前环境支持委派 subagent，使用以下协议；否则由主 agent 串行翻译每个 batch。

详细协议见 [references/subagent-protocol.md](references/subagent-protocol.md)，包括：
- Payload 文件格式（`batch_<N>.json`）
- 建议委派 prompt（含写文件探测 Step 0）
- 结果返回协议（写文件交付 + stdout 退路，通过临时文件探测决定）
- 失败处理

## LLM And Script Responsibilities

### LLM Must

- 宏观分析报告撰写与术语表构建。
- 校验 blockify.py 的拆分结果，修正误分类和边界错误（Phase 4b 块级校验步骤）。
- 翻译执行（每个 batch 的忠实翻译）。
- 翻译复核（检查语义正确性、逻辑一致性）。
- 最终润色（语言通顺性、自然度）。
- 翻译困难时的判断与坚持（不得擅自终止）。

### Scripts Must

- `parse_input.py`: 输入类型检测、格式规范化、文件复制。
- `blockify.py`: 对规范化文本进行确定性块级拆分，识别公式、表格、图片、代码块、标题的结构边界。
- `sentencify.py`: 对已标记 block 按标点边界做句级拆分，输出 `[index, text]` 格式。
- `protect_placeholders.py`: 对句子中的行内元素（公式、变量、引用、数字、URL、实体名）做占位符替换。
- `restore_placeholders.py`: 翻译完成后将占位符还原为原始值。
- `partition_batches.py`: 按字符阈值均衡分区带占位符的句子。
- `quality_gate.py`: 8 项检查——句数校验、偷懒检测、术语一致性、语言正确性、占位符保持、数字/引用保持、非翻译性语言检测、长度类型检查。
- `concatenate.py`: 按块顺序拼接译文。
- `export_alignment.py`: 导出双语对齐数据。
- `export_qa_report.py`: 导出结构化质量报告。

### Never

- 用临时脚本替代 LLM 做语义理解、摘要、翻译或润色。
- 让 LLM 手工拼接已规定由 concatenate.py 生成的权威译文产物。
- 绕过 quality_gate.py 手动标记 batch 为通过。
- 将公式块、代码块交给脚本做句级拆分（sentencify.py 应整体保留）。
- 让 subagent 推进质量门禁或拼接最终产物。
- 让 LLM 跳过 Phase 4a 直接手工写块标记（必须先运行 blockify.py 再复核）。
- 跳过 protect_placeholders.py 直接翻译（行内元素无法保护）。
- 在 Phase 10 修改 concatenate.py 输出的结构（仅允许语言通顺性修改）。
- reviewer subagent 不应拥有工具或代码执行能力（受限 worker）。

## Output Contract

### Success

翻译完成时，以下文件就绪（输出到当前工作目录）：

- `output_<target_language>.md`: 最终译文文档（Markdown 格式，保留原文章节结构）。
- `glossary.json`: 使用的术语表（v2 三级结构）。
- `alignment.json`: 双语对齐数据（每句原文、译文、QA 状态），可供下游精读 skill 使用。
- `qa_report.json`: 结构化质量报告（所有检查结果、修复记录、高风险项）。

Agent 应向用户汇报：最终输出路径、翻译统计（总字符数/总块数/总批次数）、已知保留项（公式/代码原文保留说明）、质量报告概览。

### Cancelled

源语言 == 目标语言时，输出 cancelled 状态的 stdout JSON（符合 output.schema.json）：

```json
{
  "status": "cancelled",
  "reason": "source_language equals target_language",
  "output_path": null,
  "alignment_path": null,
  "glossary_path": null,
  "qa_report_path": null,
  "provenance": {
    "source_path": "<path>",
    "source_language": "<detected>",
    "target_language": "<target>"
  }
}
```

### Failure

不可恢复错误时，输出 failed 状态的 stdout JSON（符合 output.schema.json）：

```json
{
  "status": "failed",
  "reason": "<error_description>",
  "output_path": null,
  "alignment_path": null,
  "glossary_path": null,
  "qa_report_path": null,
  "provenance": {
    "source_path": "<path>",
    "source_language": "<detected>",
    "target_language": "<target>"
  }
}
```

## Constraints

- **全程自动化**：不得中途询问用户任何问题，包括术语确认、风格偏好、范围确认等。
- **禁止偷懒**：所有原文必须逐句翻译，禁止总结式"翻译"，禁止直接输出原文，禁止通过脚本调用第三方翻译 API。
- **公式保护**：所有公式（display 和 inline）必须原文保留，不得翻译为任何文字描述。LaTeX 标记保持原样。
- **代码保护**：代码块必须原文保留，不得翻译注释或字符串内容。
- **作者名称**：一般保留原文，不翻译。
- **术语一致**：术语表中定义的翻译必须在全文统一使用。
- **不可终止**：不得因为翻译困难、内容偏多或任何难度原因擅自终止任务。
- **中间工件**：鼓励创建中间工件来强化记忆。所有中间文件放在 `.literature_translator_tmp/` 目录下。
- **脚本调用**：仅在有脚本入口的阶段调用脚本。LLM 不得在无脚本定义的阶段随机调用脚本。
- **UTF-8**：所有文件的读写使用 UTF-8 编码。

## Examples

### Happy Path

Input:

```text
source_path: /home/user/papers/attention_paper.pdf
target_language: zh-CN
```

Expected workflow:

1. Phase 1: parse_input.py 检测为 PDF → 调用 mineru 提取 markdown → normalized.md 就绪。
2. Phase 2: 通读全文，生成分析报告和术语表（含 `{"Transformer": "Transformer", "attention": "注意力"}` 等条目）。
3. Phase 3: 源语言 `en` != 目标语言 `zh-CN`，继续。
4. Phase 4a: blockify.py 按结构拆分成约 45 个 block → blocked.md。
   Phase 4b: agent 复核，合并 5 处相邻段落，修正 2 个列表类型 → 最终约 40 个 block。
5. Phase 5: sentencify.py 拆分为约 300 句 → sentences.json。
6. Phase 6: partition_batches.py 分为 6 批 → batches/ 目录。
7. Phase 7: 委派 subagent 逐批翻译，quality_gate.py 逐批校验 → 全部通过。
8. Phase 8: 主 agent 复核，修正 2 处术语不一致。
9. Phase 9: concatenate.py 拼接 → assembled.md。
10. Phase 10: 润色后输出 `output_zh-CN.md`。

### Near Miss / Failure

Input:

```text
source_path: /home/user/papers/english_note.txt
target_language: en
```

Expected behavior:

Phase 3 检测到源语言 == 目标语言 (`en`)，终止执行。输出 cancelled JSON，不进入翻译流程。

### Near Miss / Failure

Input:

```text
source_path: /home/user/papers/image.png
target_language: zh-CN
```

Expected behavior:

Phase 1 parse_input.py 返回格式不支持错误。Agent 报告 blocker 并退出。

## Failure Handling

- **Phase 1 输入格式不支持**: 报告具体的不可恢复错误，输出 failure JSON。
- **Phase 3 语言相等**: 正常终止，输出 cancelled JSON（不是错误）。
- **Phase 7 质量门禁失败**: 阅读失败详情修正翻译后重试。同一 batch 连续失败 3 次则报告 blocker。
- **Phase 7 subagent 不可用**: 主 agent 串行翻译，不阻塞流程。
- **Phase 9 译文缺失**: 报告缺失的 block_id，回到 Phase 7 补充翻译。
- **任何阶段文件损坏/格式错误**: 检查文件内容，必要时删除中间文件重新生成。
- **Agent 上下文不足**: 压缩早期中间产物（如已完成的翻译结果），释放上下文。
