---
name: literature-digest
description: 从 Markdown、PDF、LaTeX 或纯文本文献生成结构化 Markdown 摘要；仅在需要核心内容与分章覆盖时使用。
---

# literature-digest

本 skill 在后台自动运行，全程不得向用户提问。stdout 只能输出一个 JSON 对象。

## 目标与非目标

目标是从单一文献源生成结构化 `digest.md`：先标准化输入，由 LLM 判断文献类型并生成内容槽位，再由脚本读取包内 profile registry、固定标题并以 Jinja 模板渲染。

非目标包括论文质量评分、引文分析、参考文献提取、论文元数据生成，以及输出分类报告或其它公开产物。脚本不得生成摘要、判断文献类型、用关键词替代分类或调用 LLM API。

## 输入与输出

从 prompt payload 读取：

- `source_path`：唯一内容来源。支持 Markdown、PDF、单文件 `.tex`、LaTeX 工程目录和无扩展名 UTF-8 文本。
- `language`：输出语言。显式给出时直接使用；否则根据 prompt 主语言推断，仍无法判断时回退 `zh-CN`。

成功时公开产物只有源文件所在目录的 `digest.md`。render 模式 stdout 固定为：

```json
{
  "digest_path": "/abs/source/digest.md",
  "provenance": {
    "generated_at": "2026-11-04T10:00:00Z",
    "input_hash": "sha256:..."
  },
  "warnings": [],
  "error": null
}
```

`input_hash` 对标准化后的正文计算。不要增加分类结果文件，也不要改变公开文件名和输出目录。

## LLM 与脚本边界

LLM 负责：

- 按论证方式和证据结构选择 8 个 profile 之一；
- 生成 `digest_slots`、按原文顺序生成 `section_summaries`；
- 非 `zh` / `en` 语言时提交六个标题翻译。

脚本负责：

- 输入探测、PDF/LaTeX 标准化和正文 hash；
- 校验 payload 与分类字段；
- 从包内 `assets/literature_profiles.json` 读取 effective profile；
- 选择标题、构建渲染上下文、执行模板并写出 Markdown。

LLM 只提交结构化内容。最终标题、section 顺序和 Markdown 版式均由脚本与模板决定。

## 文献分类

`literature_classification` 必须包含：

- `disciplines`：短学科标签 `string[]`，可以为空数组；
- `profile_id`：下列枚举之一；
- `confidence`：`high`、`medium` 或 `low`；
- `reason`：非空分类理由，说明证据与方法结构。

按论文的主要论证和证据类型分类，不以题名、关键词或学科名称机械匹配。

| `profile_id` | 主要依据 |
| --- | --- |
| `quantitative_empirical` | 观察或实验数据、测量、统计推断、定量模型检验及其经验结果。 |
| `qualitative_empirical` | 访谈、观察、田野、案例或文本材料等经验证据，并通过系统的质性分析形成解释。 |
| `interpretive_historical` | 以文本、档案、历史脉络和语境进行阐释，核心在于理解材料的意义与形成过程。它与规范论证、形式证明的经验依据不同。 |
| `conceptual_normative` | 概念辨析、规范论证和价值判断，重点是为义务、权利、正当性或应然安排给出理由。 |
| `formal_theoretical` | 形式模型、定义、定理、证明或推导构成主要论证，不以经验数据为主要依据。 |
| `review_synthesis` | 围绕既有研究进行系统或叙述综合、比较与整合，包括叙述性文献综述。 |
| `mixed_methods` | 定量与质性方法或证据在同一个核心论证中实质整合；并列汇报两类材料但未整合时不应仅因此选择此项。 |
| `general` | 没有专门 profile 明显占主导，或证据不足以可靠选择专门类型。 |

`confidence=low` 时，脚本把 effective profile 改为 `general`，并在 stdout 的 `warnings` 中加入 `classification_low_confidence`。该回退只选择通用标题，不作质量评分。

## 内容 payload

完整 payload 的最小形状如下；`digest_slots` 与 `section_summaries` 的条目数组都至少包含一个非空字符串：

```json
{
  "literature_classification": {
    "disciplines": ["社会学"],
    "profile_id": "qualitative_empirical",
    "confidence": "high",
    "reason": "核心材料为访谈，并通过质性编码形成解释。"
  },
  "digest_slots": {
    "tldr": {"paragraphs": ["全文一句话结论。"]},
    "focus": {"items": ["研究问题与核心主张。"]},
    "basis": {"items": ["材料、方法与证据来源。"]},
    "analysis": {"items": ["主要分析路径与发现。"]},
    "limits": {"items": ["适用范围与可复现性线索。"]}
  },
  "section_summaries": [
    {"source_heading": "Methods", "items": ["本节的方法与样本说明。"]}
  ]
}
```

`digest_slots` 的五个键必须齐全且内容非空：

- `tldr.paragraphs`：覆盖问题、依据、主要结论和限制的全局摘要；
- `focus.items`：研究问题、核心主张或贡献；
- `basis.items`：材料、方法、数据、文本或来源基础；
- `analysis.items`：关键论证、解释、结果或形式推导；
- `limits.items`：证据边界、不确定性、反例或复现条件。

各 profile 的四节标题和写作提示由 registry 提供；`slot_key` 固定为 `focus`、`basis`、`analysis`、`limits`，顺序不可改。

摘要密度随原文的实质信息量调整。更多彼此独立的方法、证据、章节、案例或结论可以支持更细的条目；排版、附录和重复表述不构成扩写理由。不要按页数或字数设置机械阈值，也不要为达到篇幅加入原文没有的内容。

`section_summaries` 按原文大纲顺序覆盖主要非参考文献章节。长章节或包含多个主题的章节应拆分；无法可靠识别标题时使用连续片段，并为每个片段写非空 `source_heading` 和 `items`。

## 标题与翻译

包内 `assets/literature_profiles.json` 是四个 profile section 标题的唯一来源，不从同仓库其它 skill 读取。

- `language` 以 `zh` 开头时选择 registry 的 `zh-CN` 标题；TL;DR 标题为 `TL;DR`，章节汇总标题为 `分章节总结`。
- `language` 以 `en` 开头时选择 registry 的 `en-US` 标题；TL;DR 标题为 `TL;DR`，章节汇总标题为 `Section-by-Section Summary`。
- 其它语言必须在 payload 提供 `heading_translations`，值均为非空字符串，键必须完整包含 `tldr`、`focus`、`basis`、`analysis`、`limits`、`section_summaries`。

任意语言的标题示例：

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

翻译只替换标题文本；不得改动 `slot_key`、模板循环或内容结构。

## 执行步骤

1. 调用 normalize，取得标准化正文：

```bash
python scripts/run_digest.py --mode normalize \
  --source-path "/abs/path/paper.pdf"
```

normalize stdout 包含 `normalized_text`、`input_hash`、输入类型、`warnings` 和 `error`。

2. LLM 阅读标准化正文，依据上表完成分类；`confidence=low` 时按 `general` 处理。随后读取包内 registry 中 effective profile 的四个 `digest_sections[*].prompt`，按固定 `slot_key` 顺序生成 `digest_slots`、`section_summaries` 和所需标题翻译，写入临时 JSON 文件。

3. 调用 render：

```bash
python scripts/run_digest.py --mode render \
  --source-path "/abs/path/paper.pdf" \
  --language "zh-CN" \
  --payload-file "/tmp/digest_payload.json"
```

`--template-file` 可覆盖包内模板。自定义模板可读取 `language`、`digest_slots`、`section_summaries`、`digest_sections`、`tldr_heading` 和 `section_summaries_heading`；标题与 section 顺序仍由脚本传入的上下文决定。

4. 只在 render 返回 `error: null` 后报告 `digest_path`。

## 错误处理

payload、分类字段、内容列表、标题翻译、registry 或模板无效时，render 返回稳定 JSON 形状，不写出新的 digest：

```json
{
  "digest_path": "",
  "provenance": {"generated_at": "", "input_hash": ""},
  "warnings": [],
  "error": {"code": "render_failed", "message": "具体原因"}
}
```

源文件不存在、不可读或格式无法识别时，normalize 同样返回 schema-compatible JSON，并在 `error` 中说明原因。失败时不要猜测摘要，不要手写最终 Markdown，也不要向用户询问后续决策。
