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
- 真正的跨行合并只允许出现在 `persist_reference_entry_splits` 的 `resolution="merge"` 复核结果中。

1. `prepare_references_workset`
   - 脚本先按行切分 `source_documents.normalized_source` 与 `section_scopes.references_scope`，把每个非空行视为一个候选 block
   - 若单行明显包含多条文献，脚本会在该行内部继续做 inline split
   - 若出现疑似跨行续写，脚本只打标，不自动合并
   - 脚本为每个 `entry` 生成多组 `patterns[]` 候选，并写入 `reference_parse_candidates`
   - 若 deterministic splitting 后仍有 grouped-entry 风险，脚本会返回 `requires_split_review=true`
2. `persist_reference_entry_splits`（仅在 `requires_split_review=true` 时出现）
   - agent 只复核 suspect blocks 的 raw entry 边界，不抽 `author/title/year`
   - `blocks[*].entries[]` 必须保持原文顺序与原文文本，只允许改变分条边界
3. `persist_references`
   - agent 只在候选中选择 `selected_pattern`
   - agent 在选中候选的基础上 refine 完整 `author[] / title / year`
   - 脚本校验后写入最终 `reference_items`

### `prepare_references_workset` 预解析契约

脚本必须至少尝试以下 pattern：

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

其中 `requires_split_review=true` 表示当前 workset 仍存在边界存疑的 block，此时不得直接进入 `persist_references`。

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
- `blocks[*].block_index` 必须来自 gate 返回的 `suspect_blocks`
- `blocks[*].resolution` 只允许 `split` / `keep` / `merge`
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
      "raw": "[11] Gu, J., Bradbury, J., Xiong, C., Li, V.O., Socher, R.: Non-autoregressive neural machine translation. In: ICLR (2018)",
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
- 保守模式现在是 candidate 级：可以先保住 `author_text` 边界稳定，但最终 `author[]` 仍应尽量完整，不能默认只留第一作者
- 若 `pattern_candidate.author_candidates` 已经给出稳定作者边界，最终 `author[]` 必须保持同级边界；允许轻微规范化，但不得把 `Gu, J.`、`Al-Rfou, R.` 这类作者再次拆成多个数组元素
- 一句话硬规则：已经稳定的单个作者边界，最终 `author[]` 不得再次拆成多个数组元素
- 脚本会拦截明显的二次误拆，并以 `reference_author_refinement_invalid` 失败，而不是静默自动修正

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
