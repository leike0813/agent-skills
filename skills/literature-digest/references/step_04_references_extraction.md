# Step 04: References Extraction

本文件按 `SKILL.md` 的“参数词表（全项目统一）”定义；这里只补 stage 4 的额外约束，不重复定义字段基础含义。

本文件定义 `reference 文件格式`、`参考文献抽取细则`、5 个抽取示例，以及 references 阶段的当前 DB-first 写入要求。

## reference 文件格式

`references_path` 指向的文献内容必须是 JSON 数组对象，其中每条必须包含：
- `author: string[]`（作者，字符串数组，每个作者一项）
- `title: string`（标题，字符串）
- `year: number|null`（年份，数字）
- `raw: string`（原始文本）
- `confidence: number`（0~1）

可选扩展字段（尽量对齐 Zotero；缺失允许；重要性由高到低排列）：
- `publicationTitle`、`conferenceName`、`archiveID`、`university`
- `volume`、`issue`、`pages`、`numPages`
- `DOI`、`url`
- `publisher`、`place`、`ISBN`、`ISSN`

不输出字段：
- `citationKey`

## 参考文献抽取细则

### References 抽取原则

- 无法定位 references 区块：`references=[]`（digest 可正常生成）
- 多个候选 references：默认选择“最后一个且长度合理”的区块
- 条目分割不稳定：保留 `raw`，并输出 `author=[]`、`title=""`、`year=null`，`confidence` 置低（例如 0.1）
- 必填字段保持不变（`author/title/year/raw/confidence`），但这只是最低下限，不是目标上限。
- **注意区分 reference 条目的类型**：常见的 reference 主要分以下几类：
  1. 期刊论文：title 后一般跟随期刊名称，对应 `publicationTitle`
  2. 会议论文：title 后一般跟随会议名称，常以 `In` 起头，对应 `conferenceName`
  3. 预印本：常见 `arXiv preprint`，对应 `archiveID`
  4. 学位论文：常含大学和地点，对应 `university` 与 `place`
- **高价值可选字段提取优先级（有证据就应输出，禁止“只做最低限度”）**：
  1. `publicationTitle`、`conferenceName`、`archiveID`、`university`
  2. `volume`、`issue`、`pages`
  3. `DOI`、`url`
  4. `publisher`、`place`
- **反偷懒约束（重要）**：
  - 若 `raw` 中已出现明确证据（如 `In: <venue>`、`vol.`、`no.`、`pp.`、`doi`、`https://...`、`Publisher`、`University` 等），应尽量填入对应可选字段。
  - 不允许在有明确证据时仅输出必填字段。
- **反臆造约束（重要）**：
  - 可选字段仍为可选；证据不足时可以省略。
  - 不要为了“字段完整”而凭空生成 metadata。
- 在参考文献条目抽取中遇到体例识别、条目切分或字段边界问题时，可参考：`references/bibliography_formats.md`
- **作者字段抽取（非常重要，避免丢失名缩写）**：
  - `author[]` 的目标是保留**可直接展示/匹配**的作者字符串；优先按 `raw` 中出现的形式保存。
  - 不要只输出姓；必须尽量保留 given name 的缩写/首字母。
  - 对 `et al.` / `等`：仅表示作者被截断；可以作为最后一项，或写入 `warnings` 并降低 `confidence`，但不要擅自补全不存在的作者。
- **保守模式（强制允许）**：
  - 当作者细拆不稳定时，允许把 `author` 保守写成单元素数组，例如 `["Smith, J.; Doe, K."]`。
  - 此时优先保住 `raw`、`title`、`year`、`confidence` 的稳定性，不要为了“更漂亮的作者数组”引入错误。
  - 进入保守模式时，应降低 `confidence`，并允许脚本补 `reference_parse_low_confidence` warning。
- **年份抽取优先级（强制）**：
  - 优先取条目末尾的出版年份。
  - 不要误取 arXiv 标识中的数字前缀，例如 `arXiv:1704.04861` 里的 `1704` 不是出版年。
  - 若 `raw` 的条目末尾存在更可信的出版年份，优先使用它。

### References 抽取示例

#### 示例1（预印本）

原文本：
```text
Howard, A. G., Zhu, M., Chen, B., Kalenichenko, D., Wang, W., Weyand, T., et al. (2017). Mobilenets: Efficient convolutional neural networks for mobile vision applications. arXiv preprint arXiv:1704.04861.
```

抽取结果：
```json
{
  "author": ["Howard, A. G.", "Zhu, M.", "Chen, B.", "Kalenichenko, D.", "Wang, W.", "Weyand, T.", "et al."],
  "title": "Mobilenets: Efficient convolutional neural networks for mobile vision applications",
  "year": 2017,
  "archiveID": "arXiv:1704.04861",
  "raw": "Howard, A. G., Zhu, M., Chen, B., Kalenichenko, D., Wang, W., Weyand, T., et al. (2017). Mobilenets: Efficient convolutional neural networks for mobile vision applications. arXiv preprint arXiv:1704.04861.",
  "confidence": 0.9
}
```

#### 示例2（会议论文）

原文本：
```text
[24] Chien-Yao Wang, Alexey Bochkovskiy, and HongYuan Mark Liao. Yolov7: Trainable bag-of-freebies sets new state-of-the-art for real-time object detectors. In Proceedings of the IEEE/CVF conference on computer vision and pattern recognition, pages 7464–7475, 2023. 1, 2
```

抽取结果：
```json
{
  "author": ["Chien-Yao Wang", "Alexey Bochkovskiy", "HongYuan Mark Liao"],
  "title": "Yolov7: Trainable bag-of-freebies sets new state-of-the-art for real-time object detectors",
  "year": 2023,
  "conferenceName": "Proceedings of the IEEE/CVF conference on computer vision and pattern recognition",
  "pages": "7464-7475",
  "raw": "[24] Chien-Yao Wang, Alexey Bochkovskiy, and HongYuan Mark Liao. Yolov7: Trainable bag-of-freebies sets new state-of-the-art for real-time object detectors. In Proceedings of the IEEE/CVF conference on computer vision and pattern recognition, pages 7464–7475, 2023. 1, 2",
  "confidence": 0.85
}
```

#### 示例3（会议论文）

原文本：
```text
Shaoqing Ren, Kaiming He, Ross Girshick, and Jian Sun. Faster r-cnn: Towards real-time object detection with region proposal networks. In NeurIPS, 2015.
```

抽取结果：
```json
{
  "author": ["Shaoqing Ren", "Kaiming He", "Ross Girshick", "Jian Sun"],
  "title": "Faster r-cnn: Towards real-time object detection with region proposal networks",
  "year": 2015,
  "conferenceName": "NeurIPS",
  "raw": "Shaoqing Ren, Kaiming He, Ross Girshick, and Jian Sun. Faster r-cnn: Towards real-time object detection with region proposal networks. In NeurIPS, 2015.",
  "confidence": 0.9
}
```

#### 示例4（期刊论文）

原文本：
```text
Yu, F., Huang, J., Luo, Z., Zhang, L., & Lu, W. (2023). An effective method for figures and tables detection in academic literature. Information Processing & Management, 60(3), Article 103286.
```

抽取结果：
```json
{
  "author": ["Yu, F.", "Huang, J.", "Luo, Z.", "Zhang, L.", "Lu, W."],
  "title": "An effective method for figures and tables detection in academic literature",
  "year": 2023,
  "publicationTitle": "Information Processing & Management",
  "volume": 60,
  "issue": 3,
  "pages": "Article 103286",
  "raw": "Yu, F., Huang, J., Luo, Z., Zhang, L., & Lu, W. (2023). An effective method for figures and tables detection in academic literature. Information Processing & Management, 60(3), Article 103286.",
  "confidence": 0.8
}
```

#### 示例5（学位论文）

原文本：
```text
Fielding, Roy Thomas. Architectural styles and the design of network-based software architectures. University of California, Irvine, 2000.
```

抽取结果：
```json
{
  "author": ["Fielding, Roy Thomas"],
  "title": "Architectural styles and the design of network-based software architectures",
  "year": 2000,
  "university": "University of California",
  "place": "Irvine",
  "raw": "Fielding, Roy Thomas. Architectural styles and the design of network-based software architectures. University of California, Irvine, 2000.",
  "confidence": 0.9
}
```

## References 阶段持久化要求

按 `SKILL.md` 的“参数词表（全项目统一）”定义，本阶段已经改成“正常直通、异常复核”的双路径：

- 默认切分策略固定为 `line-first`：
  - 先按行切
  - 单行内若明显存在第二条文献起点，再做 inline split
  - 若像跨行续写，只打标，不自动合并
- Deterministic preprocess 会执行以下稳定清理与候选增强：
  - 过滤图片、HTML 表格、Figure/Table 标题、附录标题等非参考文献行
  - 清理明显尾部页码/页眉噪声
  - 在候选生成前保护英文作者 initials，避免 `K. He` 被错误当作句界
  - 增加 IEEE quoted-title、venue-marker、CJK/fullwidth/type-marker 候选
  - 对 CJK/全角参考文献先做全角标点标准化；`［J］` / `［C］` / `［D］` / `［EB/OL］` 等类型标记可作为 title/container 边界
  - 对被过切分的 CJK + Latin 双语条目做 deterministic 合并
- 真正的跨行合并只允许出现在 `persist_reference_entry_splits` 的 `resolution="merge"` 复核结果中。

1. `prepare_references_workset`
   - 脚本先按行切分 `source_documents.normalized_source` 与 `section_scopes.references_scope`，把每个非空行视为一个候选 block
   - 若单行明显包含多条文献，脚本会在该行内部继续做 inline split
   - 若出现疑似跨行续写，脚本只打标，不自动合并
   - 脚本为每个 `entry` 生成多组 `patterns[]` 候选，并写入 `reference_parse_candidates`
   - 若 deterministic splitting 后仍有 grouped-entry 风险，脚本会返回 `requires_split_review=true`
   - 脚本同时写入 `reference_preprocess_quality`，包含 `file_quality_low` 与触发的文件级质量信号
2. `persist_reference_entry_splits`（仅在 `requires_split_review=true` 时出现）
   - agent 只复核 suspect blocks 的 raw entry 边界，不抽 `author/title/year`
   - `blocks[*].entries[]` 必须保持原文顺序与原文文本，只允许改变分条边界
3. `persist_references`
   - agent 只在候选中选择 `selected_pattern`
   - agent 在选中候选的基础上 refine 完整 `author[] / title / year`
   - 脚本校验后写入最终 `reference_items`

当 `file_quality_low=true` 时，gate 会在 `persist_reference_entry_splits` / `persist_references` 之前先返回 `decide_reference_extraction`。agent 必须显式选择：

- `continue`：继续正常 references 抽取；后续仍执行 split review、reference quality gate 和严格 `ref_index` citation 映射。
- `abandon`：放弃本文件 references 抽取；只有当 DB 中存在 deterministic preprocess 写入的 `file_quality_low=true` 快照时脚本才接受，payload 自报无效。

### `prepare_references_workset` 预解析契约

脚本必须至少尝试以下 pattern：

- `ieee_quote_title`
- `venue_marker`
- `cjk_type_marker_entry`
- `authors_period_title_period_venue_year`
- `authors_colon_title_in_year`
- `authors_year_paren_title_venue`
- `thesis_or_book_tail_year`
- `fallback_raw_split`

若一个条目命中多个 pattern，必须全部保留，不得只留下“最像的一条”。

完整导出中的每个条目必须带：

- `entry_index`
- `raw`
- `detected_ref_number`
- `patterns[]`

每个 `pattern` 候选至少带：

- `candidate_index`
- `pattern`
- `author_text`
- `author_candidates`
- `title_candidate`
- `year_candidate`
- `confidence`
- `metadata.split_basis`

轻量审阅视图只保留：

- `entry_index`
- `detected_ref_number`
- `raw`
- `pattern_summaries`

脚本还会额外输出：

- `entry_style`
- `split_mode`
- `grouping_suspect_count`
- `requires_split_review`
- `suspect_blocks`
- `file_quality`
- `file_quality_low`

其中 `requires_split_review=true` 表示当前 workset 仍存在边界存疑的 block，此时不得直接进入 `persist_references`。

### 文件级质量检测

Deterministic preprocess 会在 workset 末尾计算 5 个文件级信号，并写入 `reference_preprocess_quality`：

| 信号 | 触发条件 | 含义 |
|---|---:|---|
| `fallback_best_ratio` | `> 0.50` | 多数条目的最佳候选只能落到 fallback |
| `year_ratio` | `< 0.20` | 只有很少条目能提取有效年份 |
| `warning_density` | `> 1.0` | 平均每条超过 1 个 warning |
| `numbering_anomaly` | `true` | 编号不从 1 开始、不连续或不递增 |
| `empty_title_ratio` | `> 0.30` | 多数最佳候选没有可用标题 |

至少 4 个信号触发时，`file_quality_low=true`。这不是普通 soft warning，而是一个 gate decision point：可以继续修复，也可以在 DB 证明存在时放弃 references 抽取。

低质量 decision payload 示例：

```json
{
  "decision": "abandon",
  "reason": "The reference section is too noisy to recover reliable reference rows.",
  "acknowledged_file_quality_low": true
}
```

反例：如果 DB 没有 `reference_preprocess_quality.file_quality_low=true`，即使 payload 写了 `acknowledged_file_quality_low=true`，脚本也必须拒绝。

### LaTeX bibliography 入口

当 references scope 来自 LaTeX fenced source 时，脚本增加两类 deterministic splitting：

- `\bibitem{...}` splitting
  - 若 scope 内包含 `\bibitem{...}`，脚本按 `\bibitem` 起点切条
  - `bibitem_key` 会写入 entry / candidate metadata，供后续 citation 映射使用
- `bibtex` splitting
  - 若 scope 落在 ` ```bibtex ` fence 内，脚本按顶层 `@type{key,` 起点切条
  - `citekey` 与 `entry_type` 会写入 metadata
  - 同时补一条 deterministic candidate，直接从 bib 字段读取 `author/title/year/container`

这意味着 `.bib` 条目不再走普通 line-first bibliography splitting，也不要求 LLM 自己从整块 `.bib` 里找边界。

### author-year 段落式 references 额外规则

对 author-year bibliography，脚本不能只依赖空行切分。若 references 中出现“多条 `Author. Title. Venue, Year.` 连续排在一个段落或少数段落中”的情况，脚本必须：

- 先按行切分
- 单行内若明显出现第二条文献起点，再做 inline split
- 对疑似跨行续写只做 suspicion 检测，不自动合并
- 若仍可疑，则把对应 block 放入 `suspect_blocks` 并要求进入 `persist_reference_entry_splits`

以 SOPSeg 这类 remote sensing 论文为例，下面这些都应被视为单条文献内部结构，而不是自动切分点：

- `Li, C.; ... 2020. Feature-Attentioned ... In 2020 IEEE ...`
- `Milletari, F.; ... 2016. V-net ... In 2016 fourth ...`
- `Su, H.; ... 2019. ... IGARSS 2019 ...`

允许的 year-tail 至少包括：

- `2020.`
- `2017a.`
- `2017b.`
- `(2020).`
- `In ECCV, 2020.`
- `arXiv preprint arXiv:2004.08483, 2020.`

对真实运行中常见的 author-year references 段落，正确结果应是“每条文献独立成一个 `entry`”，而不是把整段 5-20 条著录吞成一个大块。

### `persist_reference_entry_splits` 结构化复核契约

本阶段输入必须是结构化 payload：

```json
{
  "review_generation_id": "review-0123abcd",
  "blocks": [
    {
      "block_index": 3,
      "resolution": "split",
      "entries": [
        "Joshua Ainslie, Santiago Ontanon, Chris Alberti, Philip Pham, Anirudh Ravula, and Sumit Sanghai. Etc: Encoding long and structured data in transformers. arXiv preprint arXiv:2004.08483, 2020.",
        "Iz Beltagy, Matthew E Peters, and Arman Cohan. Longformer: The long-document transformer. arXiv preprint arXiv:2004.05150, 2020."
      ]
    }
  ]
}
```

要求：

- 这一步只修 entry boundary，不抽 `author[] / title / year`
- `review_generation_id` 可选；若提供，必须匹配当前 gate / workset 返回的 suspect set
- `blocks[*].block_index` 必须来自 gate 返回的 `suspect_blocks`
- `blocks[*].resolution` 只允许 `split` / `keep` / `merge` / `force_keep`
- `force_keep` 用于确认当前 suspect block 是假阳性；脚本会按单条 entry 接受并记录 warning
- 全部 `blocks[*].entries[]` 规范化后连接起来，必须与对应 suspect block 的 `source_text` 完全一致
- 若复核后仍残留 grouped-entry suspicion，脚本必须以 `reference_entry_splitting_failed` 阻断本阶段

### `persist_references` 结构化持久化契约

本阶段输入必须是结构化 payload：

```json
{
  "items": [
    {
      "entry_index": 10,
      "selected_pattern": "authors_colon_title_in_year",
      "author": ["Gu, J.", "Bradbury, J.", "Xiong, C.", "Li, V.O.", "Socher, R."],
      "title": "Non-autoregressive neural machine translation",
      "year": 2018,
      "conferenceName": "ICLR",
      "pages": "12-20",
      "DOI": "10.1000/example",
      "raw": "[11] Gu, J., Bradbury, J., Xiong, C., Li, V.O., Socher, R.: Non-autoregressive neural machine translation. In: ICLR, pp. 12-20. doi:10.1000/example (2018)",
      "confidence": 0.9
    }
  ]
}
```

用途：
- 从 `reference_parse_candidates` 中显式选择 `selected_pattern`
- 将 refine 后的结构化结果写入 `reference_items`
- 仅在顺序、字段与门禁校验通过后，才允许后续 render 阶段发布最终 `references.json`

要求：
- 条目顺序必须保持原文顺序
- `ref_index` 由脚本按 `entry_index` 稳定生成
- references 范围只能来自 `section_scopes.references_scope`，不得在本阶段重新显式传入 scope
- merge 失败时不得发布最终 `references.json`
- 若 `prepare_references_workset` 已返回 `requires_split_review=true`，必须先执行 `persist_reference_entry_splits`
- 若 `selected_pattern` 缺失、无效，或 `title` 以前导逗号/句点/分号/冒号开头，必须直接失败
- `publicationTitle`、`conferenceName`、`archiveID`、`university`、`volume`、`issue`、`pages`、`numPages`、`DOI`、`url`、`publisher`、`place`、`ISBN`、`ISSN` 都可作为顶层字段提交；raw/candidate 有明确证据时应提交，最低字段只是无证据时的下限
- 保守模式现在是 candidate 级：可以先保住 `author_text` 边界稳定，但最终 `author[]` 仍应尽量完整，不能默认只留第一作者
- 若 `pattern_candidate.author_candidates` 已经给出稳定作者边界，最终 `author[]` 必须保持同级边界；允许轻微规范化，但不得把 `Gu, J.`、`Al-Rfou, R.` 这类作者再次拆成多个数组元素
- 一句话硬规则：已经稳定的单个作者边界，最终 `author[]` 不得再次拆成多个数组元素
- 脚本会拦截明显的二次误拆，并以 `reference_author_refinement_invalid` 失败，而不是静默自动修正
- `title` 必须保持 raw reference 中的原始语言和文字系统；不得为了通过质量门禁而翻译、英文化或罗马化题名

### Reference quality gate

`persist_references` 在写入 `reference_items` 前后会运行 reference quality classifier。这个 classifier 只判断“当前 row 是否足以作为 citation / discovery 的结构化 reference”，不替代 agent 对原文的语义判断。

输入字段优先级：

- title：`title || parsed_title || parsedTitle || paper_title`
- raw：`raw || raw_reference || reference`
- authors：`authors || author`
- year：显式 `year`，否则从 raw 中取第一个 `19xx/20xx`

`normalizedTitle` 规则：

- trim 并 collapse whitespace
- NFKC normalize
- English lowercase
- punctuation / symbol 替换为空格
- 再次 collapse whitespace

`contentTokens` 使用 Unicode-aware tokenizer：

- 保留 Unicode letter runs，因此中文、日文、韩文等非拉丁文字标题可产生可用 token。
- 保留 ASCII mixed alnum token，例如 `yolov7`。
- 纯数字 token 丢弃。
- ASCII stopwords 会被过滤。stopwords 固定包含：`a`、`an`、`and`、`for`、`in`、`of`、`on`、`the`、`to`、`with`、`vol`、`volume`、`no`、`issue`、`pp`、`pages`、`proceedings`、`conference`、`journal`、`preprint`、`arxiv`、`doi`。
- 包含至少 4 个非 ASCII 字母的标题不会因为只有一个连续 token 而触发 `short_title_requires_context`。

中文标题示例：

```json
{
  "author": ["张三", "李四"],
  "title": "基于深度学习的文本分类方法",
  "year": 2020,
  "raw": "张三，李四。基于深度学习的文本分类方法。计算机研究，2020。",
  "confidence": 0.85
}
```

上例中的 `title` 必须保留中文原文，不得改写为 `Text classification method based on deep learning`、拼音或其它罗马化形式。

仍应被拒绝的反例：

```json
[
  {"title": "https://doi.org/10.1000/xyz", "reason_code": "bare_identifier_or_url_title"},
  {"title": "unknown", "reason_code": "placeholder_title"},
  {"title": "N.A.", "reason_code": "placeholder_title"},
  {"title": "2020.", "reason_code": "no_usable_title_tokens"},
  {"author": ["张三"], "title": "张三", "reason_code": "author_only_title"}
]
```

Hard block reason codes：

- `empty_title`
- `placeholder_title`
- `bare_identifier_or_url_title`
- `publication_metadata_only_title`
- `author_only_title`
- `no_usable_title_tokens`

若存在任一 hard block：

- `persist_references` 不写入 `reference_items`
- runtime 写入 active `reference_quality_issues`
- workflow 保持在 `stage_4_references / persist_references`
- gate 返回 `quality_directives`，逐条列出 `issue_id`、`entry_index/ref_index`、`reason_code`、`field`、`current_value`、`raw_excerpt` 和 `recommendation`
- agent 必须重新提交完整 `persist_references` payload；能修复则恢复 raw reference 中原始语言/文字系统的 cited title，无法可靠修复则从下一次完整 `items[]` payload 中省略该 hard row

Soft warning reason codes：

- `bibliographic_suffix_in_title`
- `possible_author_prefix_noise`
- `very_long_title`
- `short_title_requires_context`
- `missing_year`
- `missing_authors`
- `rich_metadata_evidence_missing`

若只有 soft warning：

- `persist_references` 会写入 `reference_items`
- 受影响 item 写入 `metadata.title_quality = {"status": "warning", "flags": [...]}`
- workflow 推进到 `review_reference_quality`
- gate 返回 `quality_directives` 要求逐条 inspect，能修则 corrected，不能修且可接受时显式 `accept_warning`

Hard block gate 示例：

```json
{
  "quality_directives": {
    "kind": "stage4_reference_quality",
    "severity": "hard_block",
    "instruction": "Repair the listed reference rows before continuing. Resubmit persist_references with corrected rows; omit unrecoverable hard rows from that full payload.",
    "issues": [
      {
        "issue_id": 1,
        "entry_index": 3,
        "ref_index": 3,
        "severity": "hard_block",
        "reason_code": "bare_identifier_or_url_title",
        "field": "title",
        "current_value": "https://doi.org/10.1000/xyz",
        "raw_excerpt": "Doe. Actual Work Title. 2020. https://doi.org/10.1000/xyz",
        "recommendation": "Use the raw reference and prepared candidates to recover the cited work title in its original language/script; keep DOI/URL only as metadata, or omit this row if unrecoverable."
      }
    ]
  }
}
```

Soft warning review payload 示例：

```json
{
  "resolutions": [
    {"issue_id": 1, "resolution": "accept_warning"}
  ]
}
```

Soft warning corrected payload 示例：

```json
{
  "resolutions": [
    {
      "issue_id": 1,
      "resolution": "corrected",
      "reference": {
        "author": ["Doe, J."],
        "title": "Actual Work Title",
        "year": 2020,
        "raw": "Doe, J. Actual Work Title. 2020.",
        "confidence": 0.9
      }
    }
  ]
}
```

### 编号质量检查

在写入 `reference_entries` / `reference_items` 前，脚本必须额外检查：

- 编号是否单调递增
- 编号是否连续
- 是否存在明显脏编号

若发现异常：

- 写入 `reference_entries.metadata.numbering`
- 写入 `reference_items.metadata.numbering`
- 写入 `runtime_warnings`
- citation 阶段若检测到 numeric mentions，应把 `mapping_reliability` 降级并追加 warning

### 运行时真源与渲染关系

- references 的内部真源是：
  - `reference_entries`
  - `reference_batches`
  - `reference_parse_candidates`
  - `reference_items`
- `references.json` 是 `stage_6_render_and_validate` 从 `reference_items` 渲染得到的公开产物
- `prepare_citation_workset` 必须直接复用 `reference_items` 做 mention -> reference 解析，不得重新回到原始 references 文本做重复关联
- 本阶段不直接发布公开文件，也不得把 `references.json` 当作后续内部分析真源

### 多作者冒号体例示例

对如下条目：

```text
[11] Gu, J., Bradbury, J., Xiong, C., Li, V.O., Socher, R.: Non-autoregressive neural machine translation. In: ICLR (2018)
```

脚本至少应保留一个 `authors_colon_title_in_year` 候选，使 agent 能够在 refine 时得到：

```json
{
  "author": ["Gu, J.", "Bradbury, J.", "Xiong, C.", "Li, V.O.", "Socher, R."],
  "title": "Non-autoregressive neural machine translation",
  "year": 2018
}
```

不得出现“只拆出第一作者，剩余作者全吞进 title”的退化结果。

对如下候选：

```json
{
  "author_candidates": ["Al-Rfou, R.", "Choe, D.", "Constant, N.", "Guo, M.", "Jones, L."],
  "pattern": "authors_colon_title_in_year",
  "title_candidate": "Character-level language modeling with deeper self-attention",
  "year_candidate": 2019
}
```

最终合法 refine：

```json
{
  "author": ["Al-Rfou, R.", "Choe, D.", "Constant, N.", "Guo, M.", "Jones, L."],
  "title": "Character-level language modeling with deeper self-attention",
  "year": 2019
}
```

最终非法 refine：

```json
{
  "author": ["Al-Rfou", "R.", "Choe", "D.", "Constant", "N.", "Guo", "M.", "Jones", "L."],
  "title": "Character-level language modeling with deeper self-attention",
  "year": 2019
}
```

## 当前阶段动作提示

适用 gate 阶段：
- `stage_4_references`
