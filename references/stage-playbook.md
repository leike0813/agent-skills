# Stage Playbook

各阶段的详细操作细则。仅在进入对应阶段发现需要细化指导时读取。

## Phase 2: 宏观分析与术语表细则

### 宏观分析报告格式

写为 `.literature_translator_tmp/analysis.md`，包含以下章节：

```markdown
## 源语言
<检测到的源语言>

## 文献类型
<journal paper / conference paper / book chapter / technical report / thesis / other>

## 研究领域
<一级领域，如 Natural Language Processing>

## 研究方向
<二级方向，如 Machine Translation>

## 全文概要
<3-5 句概括>
```

### 术语表规范

格式为 JSON 文件 `.literature_translator_tmp/glossary.json`：

```json
{
  "Transformer": "Transformer",
  "attention mechanism": "注意力机制",
  "BERT": "BERT",
  "Yoshua Bengio": "Yoshua Bengio",
  "encoder": "编码器",
  "decoder": "解码器",
  "token": "词元"
}
```

术语表构建规则：

1. **不应翻译的术语**（原文=译文）：
   - 模型/方法名称：Transformer, BERT, GPT, LSTM, ResNet
   - 专有名词：ImageNet, SQuAD, Wikipedia
   - 作者名称（学术文献中的作者姓名一般都不要翻译）
   - 缩写：除非目标语言社区有稳定翻译（如 NLP → 自然语言处理），否则保留原文

2. **应翻译的术语**：
   - 通用技术名词：encoder/编码器, attention/注意力, embedding/嵌入
   - 方法论术语：fine-tuning/微调, pre-training/预训练
   - 在目标语言领域有稳定译法的专业词汇

3. **大小写敏感**：术语表匹配时区分大小写 `attention` ≠ `Attention`。

4. **短语级别**：若短语有多重含义，添加注释（不写入 JSON，记在 agent 的宏观分析记录中）。

## Phase 4: 块级拆分细则

### 块标记格式

```html
<!-- BLOCK: <block_id> | type: <type> | heading: <heading> -->
<块内容>
<!-- BLOCK_END: <block_id> -->
```

`block_id` 命名：`b_<三位数字>`，如 `b_001`, `b_042`。按文档中出现顺序编号。

### 脚本可可靠识别的块类型

以下结构由 `scripts/blockify.py` 确定性识别，通常无需 agent 修正：

| 类型 | 识别特征 | 可靠性 |
|------|----------|--------|
| `heading` | `# `, `## `, `### ` 等 markdown 标题（支持 proper_nesting / flat_single_hash 两种模式） | 高 |
| `equation` | `$$...$$` 定界符（支持多行、`\tag{N}`） | 高 |
| `table` | `<table>...</table>` HTML 表格标签 | 高 |
| `figure_caption` | `![](...)` 图片引用 + 后续说明文本 | 高 |
| `code` | ` ``` ` 围栏或 `\begin{verbatim}` | 高 |
| `paragraph` | 非上述结构的正文文本 | 高 |

### 需要 Agent 核验的块类型

以下类型的识别基于启发式规则，agent 应在 Step 4b 中重点核验：

| 类型 | 识别方法 | 常见遗漏原因 |
|------|----------|-------------|
| `abstract` | 关键词匹配（"Abstract"/"摘要"在 heading 或首个文本块中） | 无显式 Abstract 标题的论文 |
| `list` | 常见前缀匹配（`- `, `* `, `• `, `1. `, `1)`） | 非标准前缀（箭头、特殊符号） |
| `bib_item` | 在 References 标题下按 `[N]` 或 `N.` 模式匹配 | 非标准引用格式 |
| `table_caption` | `Table N:` / `表格 N:` 关键词匹配 | 无显式关键词的表格说明 |
| `heading` 级别 | proper_nesting（`#` 计数）或 flat_single_hash（编号推断） | 全部使用单 `#` 且编号不标准 |

### 两类标题策略

Academic paper Markdown 存在两种标题格式，脚本自动检测并采用不同策略：

1. **Proper nesting**（嵌套格式）：论文正确使用 `##`、`###` 表示章节级别。脚本按 `#` 计数确定级别。
2. **Flat single-hash**（扁平格式）：全部标题使用单 `#`，通过编号推断级别（`# 1`=L1, `# 2.1`=L2, `# 4.2.1`=L3）。无编号关键词（"Abstract"、"Introduction"、"References"等）一律判为 L1。

Agent 需要核验 flat 模式下的级别推断是否正确。

### 重要约束

（同前）

## Phase 7: 翻译执行细则

### 分批原则

- 保持块完整性：一个块的所有句子必须在同一 batch 中。
- 每批 1500 token 是默认值；如果某块较大导致 batch 过大（> 3000 token），由 partition_batches.py 自动分配为大块单独一批。
- 总批次数一般在 5-20 批之间，取决于文献长度。

### 翻译批次执行（无 subagent 时）

当不能委派 subagent 时，主 agent 按顺序串行翻译每个 batch：

1. 读取 `.literature_translator_tmp/batches/batch_<N>.json` 获取待翻译句子。
2. 结合术语表进行翻译。
3. 翻译后构造翻译结果 JSON（格式见 [payload-contracts.md](payload-contracts.md)）。
4. 调用 `quality_gate.py` 校验。
5. 通过后写入 `.literature_translator_tmp/translations/batch_<N>_translated.json`。

### 术语一致性

- 翻译时，术语表中的 entry 必须在译文中按约定使用。
- `{"Transformer": "Transformer"}` 意味着原文中的 "Transformer" 在译文中保留为 "Transformer"（不翻译为"变换器"）。
- `{"attention mechanism": "注意力机制"}` 意味着原文中的 "attention mechanism" 必须在译文中翻译为"注意力机制"。

### 公式/代码处理

- 公式块：原文保留，不做任何修改。
- 代码块：原文保留，不做任何修改。包括其中的注释、字符串、变量名等。

## Phase 5a: 占位符保护细则

### 受保护的行内元素（按替换优先级）

```text
优先级1: 行内公式 $...$ → <MATH_NNN>
         注意：$$ display math 已在 blockify 阶段整块保护
优先级2: URL (http/https) → <URL_NNN>
         DOI (10.xxxx/xxxxx) → <DOI_NNN>
优先级3: 引用编号 [1], [1, 2], [1-3] → <REF_NNN>
优先级4: Fig. N / Figure N → <FIG_NNN>
         Table N → <TBL_NNN>
         Eq. (N) / Equation N → <EQ_REF_NNN>
         Section N.N / Sec. N.N → <SEC_NNN>
         Appendix X → <APP_NNN>
优先级5: LaTeX 变量命令 \alpha, \mathbf{x} → <VAR_NNN>
优先级6: 百分比 95% / p < 0.05 / 范围 5-10 / 科学计数法 → <NUM_NNN>
         裸数字（≥1000 或含小数）→ <NUM_NNN>
优先级7: 已知实体名（从 glossary.keep_english 提取）→ <ENT_NNN>
```

### 替换规则

1. 同类型占位符编号全局递增。
2. 相同原文去重：同一原文映射到同一占位符。
3. 替换在 `sentences.json` 上原地进行，不改变 block 结构。
4. 不替换 display math `$$...$$`（已在 block 级保护）。
5. 不替换代码块内容（已在 block 级保护）。

### 还原规则

1. 翻译完成后，用 `restore_placeholders.py` 将译文中的占位符替换回原始值。
2. 不替换译文中的合法新增内容（翻译引入的目标语言文本）。
3. 如果某个占位符在译文中不存在（被翻译 worker 丢弃），使用原始值回填并标记为 risky。

## Phase 8a: Reviewer 审查细则

### 审查输入构建

将所有 batch 的翻译结果汇总，按 block 组织为 source-translation pairs。

输入结构：

```json
{
  "task": "review_translation",
  "context_profile": { "...": "..." },
  "glossary": { "locked": {...}, "keep_english": [...] },
  "blocks": [
    {
      "b": 23,
      "type": "paragraph",
      "heading": "3.2 Experimental Setup",
      "pairs": [
        {"i": 1, "src": "We evaluate the model...", "tgt": "我们在三个下游任务上评估该模型。"},
        {"i": 2, "src": "However, the results...", "tgt": "然而，可以解读这些结果。"}
      ]
    }
  ]
}
```

### Reviewer 输出解读

```yaml
verdict: fail
errors:
  - b: 23
    i: 2
    type: modality
    severity: high
    source_span: "should be interpreted with caution"
    translation_span: "可以解读"
    issue: "译文丢失了原文中的谨慎性要求。"
    repair: "应保留'应谨慎解读'的含义。"
```

### 错误类型说明

| 类型 | 含义 | 示例 |
|------|------|------|
| omission | 漏译 | 原文句子在译文中无对应内容 |
| addition | 添加 | 译文中出现原文没有的信息 |
| mistranslation | 误译 | 语义错误 |
| terminology | 术语不一致 | glossary.locked 术语未按指定译法 |
| polarity | 否定关系错误 | not → 是 |
| modality | 不确定性被改变 | may → 一定 |
| relation | 逻辑关系错误 | 因果/条件/转折/比较被改变 |
| structure | 结构破坏 | 句子合并/拆分/删除/重排 |
| placeholder | 占位符破坏 | <MATH_001> 丢失或改坏 |
| style | 风格问题 | 语义正确但不符合学术中文 |

### 审查轮次

- 只做 1 轮审查。
- 如果 verdict=fail，进入 Phase 8b 修复。
- 修复后需要重新过 quality gate 和 reviewer。
- 最多 2 轮修复 → review 循环。

## Phase 8b: 局部修复细则

### 修复输入构建

只提取 reviewer 中指出的 medium/high severity 错误，构建修复列表。

```json
{
  "repair_items": [
    {
      "b": 23,
      "i": 2,
      "source": "However, the results should be interpreted with caution.",
      "current_translation": "然而，可以解读这些结果。",
      "issue": "译文丢失了原文中的谨慎性要求。",
      "repair_instruction": "应保留'应谨慎解读'的含义。"
    }
  ]
}
```

### 修复合并逻辑

修复后，将修复结果合并回原翻译结果。合并规则：

1. 只替换指定句号对应的句子文本。
2. 不修改其他句子的译文。
3. 不改变句子的编号和顺序。
4. 合并后翻译结果应保持合法结构。

### 失败处理

| 条件 | 处理 |
|------|------|
| 单个句子连续 2 次修复失败 | 标记为 risky，保留最佳译文 |
| 超过 50% 的句子有错误 | 退回到整 batch 重翻 |
| reviewer 返回 verdict=pass | 修复循环结束，进入 Phase 9 |

### Risky 句子标记

在 QA 报告中记录：
- block_id 和句号
- 错误原因
- 原文
- 最佳译文（即使未完全修复）
- 需要人类注意提示

## Phase 10: 润色检查清单与约束

### 允许的操作

1. **语序调整**：使译文符合目标语言表达习惯。
2. **标点符号修正**：中文使用中文标点（，。：；""），英文使用英文标点。
3. **连接词优化**：使段落间逻辑更清晰。

### 禁止的操作

```text
❌ 合并或拆分段落
❌ 删除或添加内容
❌ 重写/重组句子结构
❌ 修改公式、代码、引用编号、图表编号
❌ 修改标题层级、章节编号
❌ 改变 glossary 要求的术语
```

### 检查清单

1. **语言通顺性**：是否存在生硬直译、不通顺的长句。
2. **术语一致性**：全文使用的术语是否统一（仅限锁定术语）。
3. **标点符号**：使用了正确的目标语言标点。
4. **公式/代码完整性**：公式和代码块被完整保留。
5. **数字与单位**：数字和单位之间的格式一致。
6. **章节结构**：标题层级、编号完整，与原文一致。
7. **参考文献**：参考文献格式保留，引用编号与原文一致。
8. **漏翻检查**：快速扫描是否有未翻译的原文片段残留。无残留。

## Phase 11: 导出细则

### Alignment 文件用途

`alignment.json` 为后续文献精读 skill 提供基础数据：
- 双语对照阅读
- 逐句解释
- 术语悬浮提示
- 关键句标注
- 问答定位

### QA Report 用途

`qa_report.json` 提供翻译质量的可追溯数据：
- 每个检查项的通过情况
- 每句译文的修复记录
- 高风险句列表（需人工介入）
- 可用于迭代改进翻译流程

### 导出注意事项

- alignment 使用还原后的译文（占位符已恢复）。
- qa_report 使用翻译后的文件统计（占位符保护阶段的数据）。
- 如果某文件缺失（如 block_stats.json 不存在），导出脚本应优雅降级。
