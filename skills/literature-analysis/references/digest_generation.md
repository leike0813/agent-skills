# Digest Generation

本文件补充 `persist_digest`。该阶段只提交结构化内容；最终标题、section 顺序与 Markdown 由 runtime 根据 selected profile、DB 内容和 persisted template 渲染。

## LLM And Script Responsibilities

Script/runtime owns:

- 读取 persisted `literature_classification`、有效 profile、normalized source、outline 和 runtime template。
- 校验五个固定 slot、`section_summaries`、标题翻译和 representative image。
- 从 profile 生成 `digest_sections`，选择目标语言标题，写入 DB 并渲染最终 Markdown。
- 检查主要非 reference 章节覆盖，生成 undercoverage warning。

LLM/agent owns:

- 按 runtime 返回的四个 `digest_sections[*].prompt` 写 `focus`、`basis`、`analysis`、`limits`。
- 写 `tldr.paragraphs` 与按原文顺序的 `section_summaries`。
- 非 zh/en 语言时翻译六个固定标题键。
- 基于文本证据判断 representative image。

不要用临时脚本生成摘要、拆分章节、选择代表图或拼最终 Markdown。脚本只序列化已经审核的 payload 或调用 `run_analysis.py`。

## Structured Payload

`persist_digest` 不重新提交 `literature_classification`。它读取 classification 阶段已持久化的 effective profile，因此 digest 与 scoring 使用同一分类快照。

payload 的最小完整形状：

```json
{
  "digest_slots": {
    "tldr": {
      "paragraphs": ["本文研究……，主要依据……，得到……，并受……限制。"]
    },
    "focus": {
      "items": ["研究问题、核心主张或主要贡献。"]
    },
    "basis": {
      "items": ["支撑论证的材料、方法、数据、文本或来源。"]
    },
    "analysis": {
      "items": ["主要分析路径、证据、结果或形式推导。"]
    },
    "limits": {
      "items": ["适用范围、不确定性、反例或复现条件。"]
    }
  },
  "section_summaries": [
    {
      "source_heading": "Introduction",
      "items": ["本节界定问题并提出核心主张。"]
    }
  ]
}
```

约束：

- `digest_slots` 必须恰好包含 `tldr`、`focus`、`basis`、`analysis`、`limits`，五个键都必须非空。
- `tldr` 只使用 `paragraphs`；其他四个 slot 只使用 `items`。
- `section_summaries` 必须是按原文大纲顺序排列的数组；每项含非空 `source_heading` 与至少一个非空 `items` 字符串。
- `representative_image` 可选。
- payload 只提交 `digest_slots`、`section_summaries` 与可选 `representative_image`；最终 heading/body Markdown 由 renderer 生成。
- 最终 Markdown 不含顶层论文标题与 paper metadata block。

## Profile Headings

selected profile 的 `digest_sections` 固定四个 slot key 和顺序：

1. `focus`
2. `basis`
3. `analysis`
4. `limits`

classification 与 `status` 返回每项的 `heading`、`prompt` 和 `slot_key`。agent 按 `prompt` 写对应 slot；不得更换 key、重排 section，或把内容写进最终 Markdown。

`language` 以 `zh` 开头时：

- `tldr` 标题固定为 `TL;DR`。
- 中间四节使用 profile 的 `zh-CN` 标题。
- `section_summaries` 标题固定为 `分章节总结`。

`language` 以 `en` 开头时：

- `tldr` 标题固定为 `TL;DR`。
- 中间四节使用 profile 的 `en-US` 标题。
- `section_summaries` 标题固定为 `Section-by-Section Summary`。

Other languages:

- `persist_digest` 必须提交 `heading_translations`。
- 键必须恰好覆盖 `tldr`、`focus`、`basis`、`analysis`、`limits`、`section_summaries`。
- 六个值都必须是非空字符串。
- 翻译只替换标题文本；不得改变 slot keys、section 顺序、数组内容或 Jinja 模板结构。

示例：

```json
{
  "heading_translations": {
    "tldr": "Résumé",
    "focus": "Question et apport",
    "basis": "Fondement",
    "analysis": "Analyse",
    "limits": "Limites",
    "section_summaries": "Résumé par section"
  }
}
```

## Content Density

Digest 深度由 normalized source 的实质信息量决定。材料、论证、证据、章节和独立结论越多，条目可以越细；排版、附录重复和同义改写不构成扩写理由。

`tldr.paragraphs`:

- 通常覆盖问题、中心主张、依据、主要结论和边界。
- 可以用多个短段落，但每段都要增加独立信息。
- 不猜造原文没有的定量结果、实验或材料。

四个 profile section:

- 每项围绕 runtime prompt 写具体内容，避免只换写法的重复 bullet。
- 定量实证可覆盖设计、数据、测量、对照、统计和稳健性。
- 质性实证可覆盖取样、材料获取、编码、解释路径、反例和研究者位置。
- 历史阐释可覆盖史料范围、语境、解释步骤、竞争解释和证据边界。
- 概念/规范论证可覆盖概念区分、前提、推理链、反例和应用边界。
- 形式理论可覆盖定义、假设、定理、证明结构、适用范围和未决问题。
- 综述综合可覆盖检索或选择范围、组织框架、证据分歧、综合结论和缺口。
- 混合方法还应说明两类证据如何连接、互证或处理冲突。
- 人文、规范、历史和理论研究没有实验、代码、数据集或 reproducible pipeline 是材料特征，不构成缺陷。只有原文主张了这些内容却未提供时，才写为局限。

`section_summaries`:

- 跟随 persisted `outline_nodes` 的顺序。
- 优先使用原文 heading；长章节含多个独立主题时拆成相邻条目。
- 覆盖所有主要非 references/bibliography 章节。无法可靠识别 heading 时，用连续 source segment 作为 `source_heading`。
- 不用页数或固定条数机械控制覆盖；以主要论证和章节结构为准。

## Representative Image

Agent 必须主动检查文本中的代表图证据，不能因为无法读取图片二进制就直接返回 `none`。

Candidate evidence:

- Markdown：`![caption](figures/foo.png)`
- HTML：`<img src="figures/foo.png">`
- LaTeX：`\includegraphics{...}` 或 `\includegraphics[...]{...}`
- PDF text：figure label、caption、section、page hint

Selection priority:

- 优先选择 method、framework、architecture、pipeline、model overview、system design 或 central result。
- 人文、历史、规范或理论材料没有图时，`{"status":"none"}` 合法；不要为了凑图选择装饰图、表格、公式或低信息截图。
- 多个候选证据不均时选最可靠的一项，并将 confidence 设为 `medium` 或 `low`。

`status="selected"` 时填写：

- `source_kind`：`markdown_image_ref` 或 `pdf_figure_caption`。
- `label`：原文图号。
- `caption_quote`：简短原文 caption，不改写。
- `section_hint`：附近章节，未知时可省略。
- `page_hint`：可靠的 1-based 页码，未知时 `null`。
- `markdown_src_hint`：Markdown/HTML/LaTeX 原始路径；PDF caption 选择不得包含该字段。
- `selection_reason`：一句话说明为何最能代表材料。
- `confidence`：`high`、`medium` 或 `low`。

Path rules:

- 不得把 Markdown/HTML/LaTeX 路径改写成绝对路径。
- 不补扩展名、不重写目录、不检查文件是否存在、不提取图片本体。
- PDF 只使用文本中的 figure label/caption/page evidence。

## Failure Semantics

- 缺 slot、slot 名称错误或必要列表为空：修正结构后重交。
- 提交最终 Markdown sections：改为 `digest_slots + section_summaries`。
- 非 zh/en 缺 `heading_translations` 或键不全：补齐六个值。
- selected profile 与 persisted classification 不一致：重新读取 `status`；不要在同一 run 内另选 profile。
- 章节覆盖不足：按 outline 补齐主要非 reference 章节。
- representative image 缺证据或字段不合法：改为证据充分的对象或 `{"status":"none"}`。
- 分类已改变或 source 已重新归一化：旧 digest 失效；从 `status.next_action` 重新开始。
- agent 不直接生成 `digest.md`；最终布局由 runtime 与模板生成。
