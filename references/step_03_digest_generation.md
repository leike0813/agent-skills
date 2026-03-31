# Step 03: Digest Generation

本文件按 `SKILL.md` 的“参数词表（全项目统一）”定义；这里只补 stage 3 的额外约束，不重复定义字段基础含义。

本文件定义 `文献 Digest 总结细则`、结构化 digest 写库契约与最终 Markdown 渲染约束。

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

## 结构化写库契约

`stage_runtime.py persist_digest` 要求 LLM 提供结构化 payload：

```json
{
  "digest_slots": {
    "tldr": { "paragraphs": ["...", "..."] },
    "research_question_and_contributions": {
      "research_question": "...",
      "contributions": ["...", "..."]
    },
    "method_highlights": { "items": ["...", "..."] },
    "key_results": { "items": ["...", "..."] },
    "limitations_and_reproducibility": { "items": ["...", "..."] }
  },
  "section_summaries": [
    { "source_heading": "Introduction", "items": ["...", "..."] }
  ]
}
```

约束：

- 本步只接受 `digest_slots + section_summaries`
- `digest_slots` 必须完整覆盖 5 个固定槽位
- `section_summaries` 必须按大纲顺序提供
- 最终 digest 直接由 `digest_slots + section_summaries` 渲染
- LLM 只负责槽位内容，不负责最终标题文本与排版
- `language` 不来自本阶段 payload；最终标题语言只允许来自 `runtime_inputs.language`

### LLM 实际提交内容与最终 Markdown 的映射关系

- `tldr.paragraphs`
  - 对应最终 `## TL;DR`
- `research_question_and_contributions.research_question`
  - 对应最终 `## 研究问题与贡献` 中的研究问题句
- `research_question_and_contributions.contributions`
  - 对应最终 `## 研究问题与贡献` 下的要点列表
- `method_highlights.items`
  - 对应最终 `## 方法要点`
- `key_results.items`
  - 对应最终 `## 关键结果`
- `limitations_and_reproducibility.items`
  - 对应最终 `## 局限与可复现性线索`
- `section_summaries[*]`
  - 对应最终 `## 分章节总结` 下按大纲顺序展开的章节块

### 失败语义

- 缺少任一固定 slot、slot 形状不合法、或 `section_summaries` 结构错误时，属于 `persist_digest` 阶段失败
- 固定 slot 为空、或 `section_summaries` 对主要章节覆盖不足时，也属于 `persist_digest` 阶段失败或 warning
- 失败后不得猜测性生成最终 digest 文本

### 合法结构化 payload 示例

```json
{
  "digest_slots": {
    "tldr": { "paragraphs": ["本文提出...", "实验表明..."] },
    "research_question_and_contributions": {
      "research_question": "如何在保持精度的同时降低推理成本？",
      "contributions": ["提出新架构", "给出新的训练策略"]
    },
    "method_highlights": { "items": ["使用分层模块", "引入蒸馏损失"] },
    "key_results": { "items": ["在数据集A上提升2%", "推理延迟下降15%"] },
    "limitations_and_reproducibility": { "items": ["未开源训练代码"] }
  },
  "section_summaries": [
    { "source_heading": "Introduction", "items": ["定义问题背景", "总结主要挑战"] }
  ]
}
```

### 非法 payload 示例

```json
{
  "sections": [
    { "section_key": "tldr", "heading": "## TL;DR", "body_md": "..." }
  ]
}
```

## 最终排版来源

- 最终 digest 排版由 renderer 和模板文件决定：
  - `assets/templates/digest.zh-CN.md.j2`
  - `assets/templates/digest.en-US.md.j2`
- 本文档不内嵌最终 Markdown 模版骨架，避免被误读为 LLM 输入模版。
- agent 在本阶段只应提交结构化 `digest_slots + section_summaries`，不得直接提交接近最终成品的 Markdown。

## 当前阶段动作提示

适用 gate 阶段：
- `stage_3_digest`

说明：
- 当前 renderer 通过模板系统输出最终 Markdown。
- 模板只负责固定标题、顺序和排版。
- 真正进入最终成品的内容必须先落入 `digest_slots` 与 `digest_section_summaries`。
