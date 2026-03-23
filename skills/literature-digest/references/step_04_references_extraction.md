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

### `persist_references` 结构化持久化契约

本阶段输入必须是结构化 payload：

```json
{
  "entries": [
    { "entry_index": 0, "raw": "[1] Smith. Paper A. 2020." }
  ],
  "batches": [
    { "batch_index": 0, "entry_start": 0, "entry_end": 0 }
  ],
  "items": [
    {
      "ref_index": 0,
      "author": ["Smith"],
      "title": "Paper A",
      "year": 2020,
      "raw": "[1] Smith. Paper A. 2020.",
      "confidence": 0.9
    }
  ]
}
```

用途：
- 从 `section_scopes.references_scope` 读取参考文献范围
- 将 raw entry 顺序写入 `reference_entries`
- 将批次边界与进度写入 `reference_batches`
- 将结构化结果写入 `reference_items`
- 仅在顺序、字段与门禁校验通过后，才允许后续 render 阶段发布最终 `references.json`

要求：
- 条目顺序必须保持原文顺序
- `reference_entries` 与 `reference_items` 的 `ref_index` 必须可稳定对应
- references 范围只能来自 `section_scopes.references_scope`，不得在本阶段重新显式传入 scope
- merge 失败时不得发布最终 `references.json`
- 当作者拆分不稳时，允许 `author` 为单元素数组；这是合法的保守模式，不应被视为格式错误

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
  - `reference_items`
- `references.json` 是 `stage_6_render_and_validate` 从 `reference_items` 渲染得到的公开产物
- `prepare_citation_workset` 必须直接复用 `reference_items` 做 mention -> reference 解析，不得重新回到原始 references 文本做重复关联
- 本阶段不直接发布公开文件，也不得把 `references.json` 当作后续内部分析真源

## 当前阶段动作提示

适用 gate 阶段：
- `stage_4_references`
