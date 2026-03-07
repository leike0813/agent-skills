---
name: literature-digest
description: Generate a paper digest (Markdown) and extract reference entries (structured JSON array) from a source file. Use when invoked as $literature-digest with a prompt-embedded JSON payload containing source_path.
compatibility: Requires local filesystem read access to source_path; no network required.
---

# literature-digest（literature_digest_v1）

本 skill 运行于后台自动化场景：**不得向用户提问做决策**。遇到分支/不确定性时，必须按“默认行为协议”继续执行，并输出 schema 兼容 JSON。

## 输入（prompt payload）

从 prompt 中读取：
- `source_path`：待解析的输入文件路径；可能是 Markdown、PDF，或无扩展名文件。
- `language`： 论文总结及参考文献分析使用的语言。

约束：
- `source_path` 是唯一内容来源。
- 不得依赖扩展名判断格式；必须优先调用 dispatcher 脚本读取文件内容做协议探测：
  - 文件头命中 `%PDF-` 时按 PDF 处理；
  - 否则尝试按 UTF‑8 文本处理；
  - 若两者都不成立，则按“默认行为协议”失败返回。
- 无论输入类型为何，都必须先统一生成 `<cwd>/.literature_digest_tmp/source.md`；后续所有 Markdown 处理仅消费这个固定路径。
- `language` 可以是任意包含“语言”语义的字符，推荐采用 `BCP 47` 语言标签，例如：
  - `zh-CN`（默认）
  - `en-US`
  - `fr-FR`
  - ...
  无法解析或未显式给出时，回退为默认值 `zh-CN`（只影响 `digest` 和 `citation_analysis` 语言）。

## 输出

### stdout 输出格式

stdout **只能**输出一个 JSON 对象（不得夹杂日志/解释文本）。

输出 JSON 必须包含（即使为空也要存在）：

- `digest_path`：输出文件路径（内容为 Markdown 纯文本；**不包含**插件侧协议头；协议头由插件端组装写入 Zotero note）
- `references_path`：输出文件路径（内容为 UTF‑8 JSON 数组）
- `citation_analysis_path`：输出文件路径（内容为 UTF‑8 JSON 对象，见下文“Citation Analysis”）
- `provenance.generated_at`：UTC ISO‑8601
- `provenance.input_hash`：`sha256:<hex>`（对原始 `source_path` 文件 bytes 计算）
- `provenance.model`：解析使用的模型
- `warnings`：数组
- `error`：`object|null`

### 输出物化（避免 stdout 截断）：

- 为避免 stdout 截断，**必须将主要分析结果写入文件而非在stdout输出**，当用户没有额外指示时，可以参考以下输出路径：
  - `digest_path=<dir_of_source_path>/digest.md`
  - `references_path=<dir_of_source_path>/references.json`
  - `citation_analysis_path=<dir_of_source_path>/citation_analysis.json`
- 文件名固定：`digest.md`、`references.json`、`citation_analysis.json`（UTF‑8）。

### reference 文件格式

`references_path` 指向的文献内容必须是 JSON 数组对象，其中每条必须包含：
- `author: string[]`（作者，字符串数组，每个作者一项）
- `title: string`（标题，字符串）
- `year: number|null`（年份，数字）
- `raw: string`（原始文本）
- `confidence: number`（0~1）

可选扩展字段（尽量对齐 Zotero；缺失允许；重要性由高到低排列）：
- `publicationTitle`（期刊名称，如 `Information Processing & Management`）、`conferenceName`（会议名称，如 `NeurIPS`、`Proceedings of the IEEE/CVF conference on computer vision and pattern recognition`，一般在著录中记为 `In: NeurIPS` 或 `In Proceedings of the IEEE/CVF conference on computer vision and pattern recognition`）、`archiveID`（文献ID，一般见于arXiv预印本，如 `arXiv:2511.09554`）、`university`（大学，如 `Havard University`）
- `volume`（卷，数字）、`issue`（期，数字）、`pages`（页码，由于现代电子期刊往往不再使用连续页码，而是给每篇文章分配一个唯一的“文章编号”，如 `Article 103286`。因此 `pages` 采用字符串记录，例如 `346-362`、`114361` 或 `Article 103286` 都是合法的）、`numPages`（总页数，数字）
- `DOI`（大写，注意不要误用为 `doi` 字段）、`url`
- `publisher`、`place`、`ISBN`、`ISSN`

不输出字段：
- `citationKey`（由 Better BibTeX 负责）

### citation_analysis 输出格式

`citation_analysis_path` 指向的文件内容必须是 JSON 对象，至少包含：
- `meta`：
  - `language`（`zh-CN`/`en-US`/...）
  - `scope`：`{ "section_title": "<citation-scope-title>", "line_start": <int>, "line_end": <int> }`
- `items`：数组（按被引文献聚合）
- `unmapped_mentions`：数组（无法稳定映射到 `references.json`）
- `report_md`：markdown 字符串（可直接作为 note 正文）

#### `items` 数组中条目的最小结构

- `ref_index`（0-based，对应 `references.json` 下标；核心关联字段）
- `ref_number`（numeric 体例可填；author-year 可为 null）
- `reference`（从 `references.json[ref_index]` 拷贝的快照；至少含 `author/title/year`）
- `mentions` 数组（与`unmapped_mentions[]`同构），每个条目包含：
  - `mention_id`、`marker`、`style`（`numeric`/`author-year`/`unknown`）
  - `line_start`、`line_end`（必须落在 `meta.scope` 内）
  - `snippet`（短上下文，避免长段原文）
- `function`（该被引文献对于目标文献的意义分类，`background/baseline/contrast/component/dataset/tooling/historical/other`）
- `summary`（该被引文献在分析范围内的综合总结，1~2 句）
- `confidence`（0~1，整体置信度）

#### `report_md` 建议结构（示例，允许更丰富但不应删减核心）

```md
## 文献综述章节引文线索

### 按功能归类
- Background:
- Baseline:
- Contrast:
- Component:
- Dataset:
- Tooling:
- Historical:

### 按引用编号/作者-年份列举
- [5] ...（一句话：本文如何定位这篇）
- (Smith, 2020) ...（若未映射成功则提示 unmapped）
```

## 处理步骤（建议工作流）

1) 解析 prompt，做最小校验与默认值回退。
2) 读取 `source_path` 并调用 `scripts/dispatch_source.py` 做协议探测，统一生成 `<cwd>/.literature_digest_tmp/source.md`：
   - Markdown / UTF‑8 文本：直接复制为 `source.md`
   - PDF：优先尝试 `pymupdf4llm` 转 Markdown；失败则使用标准库兜底解析；两者都失败才返回错误
3) 对原始 `source_path` 计算 `input_hash`（sha256）。
4) 使用统一后的 `source.md` 生成“结构化骨架”（建议为 JSON）：包含大纲、references 区块位置，以及可能承担文献综述职责的章节范围（例如 Introduction、Related Works、Background 等，按原始 md 行号 1-based）。
5) 基于骨架：
   - 生成 digest（全局总结 + 分章节总结）
   - 定位 references 区块并抽取条目（结构化引文条目）
   - 由 LLM 从骨架中生成**唯一 `citation_scope` 定义对象**（可覆盖一个或多个章节）并覆盖必要子章节，再执行抽取与分析（详见后文“Citation Analysis 执行流水线”）
6) 对输出做最小自检与修正（schema/类型/范围），确保可被严格 JSON 解析。
   - 推荐使用 `scripts/validate_output.py` 做格式验证与自动修复（见下文）。

## LLM 与脚本的职责边界（重要）

为避免某些 agent 在运行时“越界”导致质量下降，需强制遵守以下边界：

- **必须由 LLM 执行（不得用脚本替代）**：
  - 基于全文理解生成 digest（全局总结 + 分章节总结）
  - 基于全文理解生成结构化骨架（大纲、references 区块定位、候选综述章节定位）
  - 基于骨架生成 citation analysis 最终范围定义（`citation_scope`，可跨多个章节）
  - 参考文献条目的语义级字段推断（作者/标题等）在规则不稳时的补全
  - 基于预处理产物做 citation semantics（function 分类、文献定位总结、report_md 组织）

- **允许用脚本执行（确定性/可重复）**：
  - 读取 `source_path`、探测输入协议、生成统一 `source.md`
  - 对原始 `source_path` 计算 sha256、生成 `provenance`
  - 在 LLM 给定的 `citation_scope` 内做 citation mention 抽取与标准化（numeric + author-year）
  - 输出 schema 校验、字段迁移、类型纠正、将过长输出物化到文件（`digest_path`/`references_path`/`citation_analysis_path`）

- **绝对禁止**：
  - 不得在运行时临时创建 Python/JS/Bash 脚本去“替代 LLM 的摘要/大纲/语义判断工作”。
  - 不得将语义判断伪装成“确定性规则”绕过 LLM。

## 文献 Digest 总结细则

### Digest 输出结构（Markdown）

`language=zh-CN` 时：
- 必须严格使用如下标题（顺序与标题文本均固定）：
  - `## TL;DR`（建议 8~15 行；比之前更详尽，覆盖问题/方法/结果/局限与可复现性线索）
  - `## 研究问题与贡献`
  - `## 方法要点`
  - `## 关键结果`
  - `## 局限与可复现性线索`
  - `## 分章节总结`
- 不要输出额外的顶层标题（例如 `# 文献摘要`）或“论文信息/元数据”区块；论文题目、作者等信息不强制输出（避免格式漂移）。
- 全局总结（`## TL;DR` 到 `## 局限与可复现性线索`）的总输出量应显著增加：相较“精简版”约提升至约 3 倍信息量（更多要点、更多关键细节与限定条件，但仍避免臆造）。
- `## 分章节总结` 必须存在，并尽可能细化章节切分（根据提取出来的大纲）：
  - 优先按“全文大纲骨架”的章节标题逐章总结（推荐使用 `### <原文章节标题>`）
  - 章节粒度要求：尽量覆盖主要一级章节；若某一级章节过长或包含多个子主题，优先进一步拆成二级小节（`#### <子节标题或子主题>`）
  - 数量要求：至少输出 8 个章节/小节块（`###` 或 `####`），并尽量更多
  - 内容要求：分章节总结的总输出量应显著增加：相较“精简版”约提升至约 5 倍信息量（更细粒度、更具体的术语/变量/设置/结论/边界条件；必要时引用原文中的关键符号/损失项/模块名/数据集名，但不要贴长段原文）
  - 若无法可靠识别大纲：退化为 `### 片段 1/2/3...` 的分段总结，并将片段数量提升（至少 8 段），以覆盖全文主要内容

`language=en-US` 时：
- Must use the exact headings below (fixed order and text):
  - `## TL;DR` (prefer 8–15 lines; more detailed than a short summary)
  - `## Research Question & Contributions`
  - `## Method Highlights`
  - `## Key Results`
  - `## Limitations & Reproducibility`
  - `## Section-by-Section Summary`
- Do not add an extra top-level title (e.g. `# Paper Digest`) or a “Paper Info/Metadata” section.
- The overall “global summary” volume (from `## TL;DR` to `## Limitations & Reproducibility`) should be ~3× a short version: add more concrete details and qualifiers without hallucinating.
- `## Section-by-Section Summary` must exist and be as fine-grained as possible based on the extracted outline:
  - Prefer `### <Original section heading>` in outline order
  - If a section is long or covers multiple themes, split further into `#### <subtopic>` blocks
  - Output at least 8 section/subsection blocks (`###` or `####`) and preferably more
  - Make the section-by-section part ~5× a short version: more specifics (modules, losses, datasets, settings, claims, limits); avoid long verbatim quotes
  - Fallback to `### Segment 1/2/3...` with at least 8 segments if headings are unreliable

### Digest 模版（建议直接填充，不要改标题，以zh-CN为例）

```md
## TL;DR
（建议 8~15 行；更具体、更完整）

## 研究问题与贡献
- 
- 
- 

## 方法要点
- 
- 
- 

## 关键结果
- 
- 
- 

## 局限与可复现性线索
- 
- 
- 

## 分章节总结
### （章节1标题）
- 
- 
- 

### （章节2标题）
- 
- 
- 

### （章节3标题）
- 
- 
- 

### （章节4标题）
- 
- 
- 

### （章节5标题）
- 
- 
- 

### （章节6标题）
- 
- 
- 

### （章节7标题）
- 
- 
- 

### （章节8标题）
- 
- 
- 
```

## 参考文献抽取细则

### References 抽取原则

- 无法定位 references 区块：`references=[]`（digest 可正常生成）
- 多个候选 references：默认选择“最后一个且长度合理”的区块
- 条目分割不稳定：保留 `raw`，并输出 `author=[]`、`title=""`、`year=null`，`confidence` 置低（例如 0.1）
- 必填字段保持不变（`author/title/year/raw/confidence`），但这只是最低下限，不是目标上限。
- **注意区分 reference 条目的类型**：常见的 reference 主要分以下几类：
  1. 期刊论文，特征是 title 后一般跟随期刊名称，例如 `Yu, F., Huang, J., Luo, Z., Zhang, L., & Lu, W. (2023). An effective method for figures and tables detection in academic literature. Information Processing & Management, 60(3), Article 103286.`。期刊论文对应的出处信息为 `publicationTitle`，一般还会包含 `volume`、`issue`、`pages` 等版次定位信息。

  2. 会议论文，特征是 title 后一般跟随会议名称，常以“In”起头，例如 `Shaoqing Ren, Kaiming He, Ross Girshick, and Jian Sun. Faster r-cnn: Towards real-time object detection with region proposal networks. In NeurIPS, 2015.` 和 `Chien-Yao Wang, Alexey Bochkovskiy, and HongYuan Mark Liao. Yolov7: Trainable bag-of-freebies sets new state-of-the-art for real-time object detectors. In Proceedings of the IEEE/CVF conference on computer vision and pattern recognition, pages 7464–7475, 2023.`。会议论文对应的出处信息为 `conferenceName`，注意 `conferenceName` 必然不包含起头的“In”或“In:”。

  3. 预印本，特征是带有“preprint”字样，以 arXiv preprint 为绝对主流，例如 `Howard, A. G., Zhu, M., Chen, B., Kalenichenko, D., Wang, W., Weyand, T., et al. (2017). Mobilenets: Efficient convolutional neural networks for mobile vision applications. arXiv preprint arXiv:1704.04861.`。预印本对应的出处信息为 `archiveID` （文献ID）, arXiv preprint的文献ID一般为 `arXiv:<编号>` 形式，例如 `arXiv:1704.04861`）。

  4. 学位论文，特征是多数情况为单一作者，且带有大学名称和地点字样，例如 `Fielding, Roy Thomas. Architectural styles and the design of network-based software architectures. University of California, Irvine, 2000.`。学位论文的出处信息为 `university`，一般还会包含 `place`（地点）和 `year`（年份）。

- **高价值可选字段提取优先级（有证据就应输出，禁止“只做最低限度”）**：
  1. 容器/出处信息：`publicationTitle`、`conferenceName`、`archiveID`、`university`（期刊名、会议名、学校/机构名等）
  2. 版次定位信息：`volume`、`issue`、`pages`
  3. 标识与链接：`DOI`、`url`
  4. 出版与机构信息：`publisher`、`place`
- **反偷懒约束（重要）**：
  - 若 `raw` 中已出现明确证据（如 `In: <venue>`、`vol.`、`no.`、`pp.`、`doi`、`https://...`、`Publisher`、`University` 等），应尽量填入对应可选字段。
  - 不允许在有明确证据时仅输出必填字段。
- **反臆造约束（重要）**：
  - 可选字段仍为可选；证据不足时可以省略。
  - 不要为了“字段完整”而凭空生成 metadata。
- 在参考文献条目抽取中遇到体例识别、条目切分或字段边界问题时，可参考：`references/bibliography_formats.md`
- **作者字段抽取（非常重要，避免丢失名缩写）**：
  - `author[]` 的目标是保留**可直接展示/匹配**的作者字符串；优先按 `raw` 中出现的形式保存（常见为 `Surname, Initials.` 或 `Initials. Surname`）。
  - 不要只输出姓（例如把 `Al-Rfou, R.` 简化为 `Al-Rfou`）；必须尽量保留 given name 的缩写/首字母（如 `R.`、`Q.V.`、`L.S.`）。
  - 对 `et al.` / `等`：仅表示作者被截断；可以将 `et al.` 作为作者列表中的最后一项（例如 `"et al."`），或写入 `warnings` 并降低 `confidence`，但不要擅自补全不存在的作者。
  - 例（期望输出）：
    - `raw`: `Bahdanau, D., Cho, K., Bengio, Y.: ...` → `author`: `["Bahdanau, D.", "Cho, K.", "Bengio, Y."]`
    - `raw`: `Bodla, N., ... Davis, L.S.: ...` → `author`: `["Bodla, N.", "...", "Davis, L.S."]`
    - `raw`: `Le, Q.V.: ...` → `author`: `["Le, Q.V."]`（注意不要拆丢 `Q.V.`）

### References 抽取示例

#### 示例1（预印本）

- 原文本：
```text
  Howard, A. G., Zhu, M., Chen, B., Kalenichenko, D., Wang, W., Weyand, T., et al. (2017). Mobilenets: Efficient convolutional neural networks for mobile vision applications. arXiv preprint arXiv:1704.04861.
```
- 抽取结果：
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

- 原文本：
```text
[24] Chien-Yao Wang, Alexey Bochkovskiy, and HongYuan Mark Liao. Yolov7: Trainable bag-of-freebies sets new state-of-the-art for real-time object detectors. In Proceedings of the IEEE/CVF conference on computer vision and pattern recognition, pages 7464–7475, 2023. 1, 2
```
- 抽取结果：
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

- 原文本：
```text
Shaoqing Ren, Kaiming He, Ross Girshick, and Jian Sun. Faster r-cnn: Towards real-time object detection with region proposal networks. In NeurIPS, 2015.
```
- 抽取结果：
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

- 原文本：
```text
Yu, F., Huang, J., Luo, Z., Zhang, L., & Lu, W. (2023). An effective method for figures and tables detection in academic literature. Information Processing & Management, 60(3), Article 103286.
```
- 抽取结果：
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

- 原文本：
```text
Fielding, Roy Thomas. Architectural styles and the design of network-based software architectures. University of California, Irvine, 2000.
```
- 抽取结果：
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

## Citation Analysis（Dynamic Citation Scope）细则

目标：辅助用户撰写文献综述。仅基于论文中的“文献综述职责范围”（由 LLM 动态生成 `citation_scope`）整理：
- 本文引用了哪些文献（与 `references.json` 关联）
- 本文在该范围内如何介绍/定位这些被引工作（背景/基线/对比/组件等）

### 执行流水线（强制，按顺序）

1) **范围决策阶段（LLM）**
- 先让 LLM 抽取“结构化骨架”：至少包含
  - `outline`（大纲，需保留标题层级关系）
  - `references_scope`（参考文献章节范围）
  - `review_scope_candidates`（候选综述章节范围，含标题、层级、行号）
- 再让 LLM 基于骨架生成 `citation_scope`（最终分析范围定义）。
- `citation_scope` 是**单一定义对象**，但语义上可覆盖**多个章节**（例如 `Introduction + Related Works`），不是“只能单章”。
- **禁止双层 scope 决策**：不得再输出 `review_scopes + analysis_scope` 两段式决策结果，应直接输出 `citation_scope`。
- **子章节覆盖规则（强制）**：
  - 若 `citation_scope` 选中了父章节（例如 `Related Works`、`Background`、`Prior Work`），则必须覆盖其全部子章节正文；
  - 结束边界应为“下一个同级或更高层级标题之前”，不得只截取父章节标题下的首段；
  - 若父章节存在多个子标题而 scope 未覆盖这些子标题内容，视为范围无效（过窄）。
- **跨章节覆盖规则（强制）**：
  - 当骨架显示文献综述职责分布在多个章节（如 `Introduction` 与 `Related Works`）时，`citation_scope` 必须覆盖这些章节，而不是只保留其中之一。
  - 若章节之间是连续的，可用一个连续行号范围覆盖；`section_title` 可写为组合名称（如 `Introduction + Related Works`）。
- 若 `citation_scope` 无法可靠确定，必须回退为失败输出（`error` 非空），不得让脚本盲猜。

2) **预处理阶段（确定性）**
- 运行 `scripts/citation_preprocess.py` 生成预处理产物：`<cwd>/.literature_digest_tmp/citation_preprocess.json`。
- 该产物至少包含：`meta.scope`、`mentions[]`、`stats.total_mentions`。
- scope 由 LLM 先给定（统一 `citation_scope` 定义，可覆盖多章节），再由脚本在该 scope 内抽取 mention。
- 任何语义分析前，都必须先有这个产物。

3) **映射阶段（规则优先）**
- 输入只允许使用：`references.json` + `citation_preprocess.json` + mention 所在 snippet。
- numeric 先按 `ref_number -> ref_index`；author-year 先按 `year + first-author surname`。
- 若多候选冲突或证据不足，不可硬猜，直接进入 `unmapped_mentions`。

4) **语义阶段（LLM）**
- 仅对“已抽取的 mentions”执行语义任务，不得再做全文盲扫补引用。
- 对每个 mapped item 生成：`function`、`summary`、`confidence`。
- `summary` 必须是“该引用在当前 `citation_scope` 中的作用”，不能写成泛化的文献简介。
- `report_md` 必须覆盖关键 mapped 项与重要 unmapped 风险点。

5) **门禁阶段（必须通过）**
- 计算 `coverage = consumed_mentions / extracted_mentions`：
  - `extracted_mentions = preprocess.stats.total_mentions`
  - `consumed_mentions = sum(len(item.mentions)) + len(unmapped_mentions)`
- 必须满足 `coverage == 1.0`；否则视为失败回退（见下文）。

### 预处理结果契约（用于语义阶段输入）

`citation_preprocess.json` 推荐字段：
- `meta.scope`：`{ section_title, line_start, line_end }`
- `meta.scope_source`：`agent` 或 `intro_fallback`
- `mentions[]`：每条至少含 `mention_id`、`marker`、`style`、`line_start`、`line_end`、`snippet`
- `stats`：至少包含 `total_mentions`，可扩展 `numeric_mentions`、`author_year_mentions`

### 支持的引文体例（必须同时支持）

1) numeric（编号型）：
- 支持：`[5, 36]`、`[4,15,38]`、`[40-42]`、`[40–42]`（需要展开为 40/41/42）
- 映射：优先 `ref_number -> ref_index`（通常 `ref_index = ref_number - 1`）；若编号异常，以 `references.json` 顺序为准并降低 `confidence`。

2) author-year（作者-年份型，高质量要求）：
- 必须识别：`(Smith, 2020)`、`Smith et al. (2020)`、`(Smith & Jones, 2020; Brown, 2019)` 等
- 映射规则（禁止硬猜）：
  - 优先在 `references.json` 中按 `year + first-author surname` 匹配。
  - 必要时结合 `raw` 和 snippet 做二次判别。
  - 无法可靠映射时写入 `unmapped_mentions`，并给出 `reason`（`no_match/ambiguous/parse_failed/reference_unavailable` 等）。

### 边界情况判定与回退

- `citation_scope` 不存在或范围不可判定：
  - 输出 schema 兼容 JSON，`citation_analysis_path=""`，`error={code,message}`。
- `citation_scope` 过窄（例如仅覆盖父章节首段、遗漏其子章节主体，或在应跨章节时只覆盖单章）：
  - 输出 schema 兼容 JSON，`citation_analysis_path=""`，`error={code,message}`。
- `citation_scope` 存在但未检测到任何 citation：
  - 允许输出空 `items=[]`、`unmapped_mentions=[]`，并在 `report_md` 明确“本章节未检测到稳定引用标记”。
- `references.json` 缺失/不可读：
  - mention 仍需抽取；无法映射的 mention 全部进入 `unmapped_mentions(reason=reference_unavailable)`。
- 门禁失败（`coverage < 1.0`）：
  - 必须回退为失败输出（`error` 非空），不得“假成功”返回 citation_analysis。

## 默认行为协议（必须遵守）

- 读取 `source_path` 失败（不存在/无权限/编码异常）：
  - 输出 schema 兼容 JSON
  - `digest_path=""`
  - `references_path=""`
  - `citation_analysis_path=""`
  - `error` 填充 `{code,message}`
- 输入内容既非 PDF 签名、也不是可读取的 UTF‑8 文本：
  - 输出 schema 兼容 JSON
  - `digest_path=""`
  - `references_path=""`
  - `citation_analysis_path=""`
  - `error` 填充 `{code,message}`
- `language` 非支持值：回退 `zh-CN` 并写入 `warnings`
- 任何字段抽取不可靠时：宁可留空 + 降低置信度，也不要臆造

## 脚本（可选但推荐）

本 skill 推荐使用 **skill 包内预置脚本** 承担确定性工作（审计信息生成、输出格式验证、自我修复、citation 预处理），以降低 LLM 负担并提高一致性。

临时产物目录约定：
- 固定使用 `<cwd>/.literature_digest_tmp/`
- `citation_preprocess.py` 的默认输出为 `<cwd>/.literature_digest_tmp/citation_preprocess.json`
- 临时文件默认保留，不做自动清理（避免清理失败导致主流程异常）

### `scripts/provenance.py`

用途：
- 计算 `provenance.input_hash`（对原始 `source_path` 文件 bytes 的 `sha256:<hex>`）
- 生成 `provenance.generated_at`（UTC ISO‑8601）

### `scripts/dispatch_source.py`

用途：
- 对 `source_path` 做内容探测（优先于扩展名）
- 统一产出 `<cwd>/.literature_digest_tmp/source.md`
- 统一产出 `<cwd>/.literature_digest_tmp/source_meta.json`

规则：
- 输入若命中 PDF 签名 `%PDF-`，则按 PDF 处理
- 否则尝试按 UTF‑8 文本处理
- PDF 主路径优先使用 `pymupdf4llm`
- `pymupdf4llm` 不可用或失败时，使用标准库兜底解析，并写入 `warnings`
- 下游流程不得直接消费原始 `source_path`，而是只消费统一后的 `source.md`

### `scripts/validate_output.py`

用途：
- 校验输出是否满足 schema（字段存在、类型正确、范围正确）
- 在校验失败时做“可解释的自动修复”（例如补齐缺失字段、类型纠正、旧字段迁移、将过长输出物化到文件），并将修复记录写入 `warnings`

建议用法：
1) 先生成一个候选输出 JSON（可能不完美）
2) 使用 `scripts/validate_output.py --mode fix --source-path <cwd>/.literature_digest_tmp/source.md` 输出修复后的 JSON
3) 再用 `scripts/validate_output.py --mode check` 校验必须通过；若仍失败，回退到最小可用输出（空 digest/空 references/空citation_analysis + error）

### `scripts/citation_preprocess.py`

用途：
- 在 LLM 指定的 `citation_scope` 内做确定性 citation mention 抽取（numeric + author-year）
- 生成语义阶段输入产物 `citation_preprocess.json`（含 `meta.scope`、`mentions[]`、`stats`）

调用方式（推荐）：
- 先由 LLM 输出 `citation_scope.json`（至少含 `line_start`/`line_end`/`section_title`；跨章节时 `section_title` 可为组合名称）
- 再调用：
  - `scripts/citation_preprocess.py --md-path <cwd>/.literature_digest_tmp/source.md --scope-file <citation_scope.json> --out <cwd>/.literature_digest_tmp/citation_preprocess.json`
- 若未提供 scope 参数，脚本会回退到 Introduction 自动识别（仅兼容旧流程；新流程应始终由 LLM 提供 `citation_scope`）


