# Source And Analysis Plan

本文件补充 `init_runtime` 与 `persist_analysis_plan`。这两个阶段先由脚本固化 runtime 与 normalized source，再由 agent 提交结构化 plan。

## 输入协议

Prompt payload 只读取：

- `source_path`：唯一内容来源；可以是 Markdown、PDF、单文件 `.tex`、LaTeX 工程目录、无扩展名文本文件。
- `language`：digest 与 citation report 的目标语言。用户显式指定时直接使用；否则从 prompt 主要语言推断；无法稳定判断时回退 `zh-CN`。

`source_path` 约束：

- 不得用用户声称的扩展名覆盖内容判断。
- 后续阶段不得重新读取任意 source 文件；只能读 DB 中的 `source_documents.normalized_source`。
- `source.md`、`source_meta.json`、workset exports 都只是审计副产物，不是过程真源。

## LLM And Script Responsibilities

Script/runtime owns:

- Source type detection, PDF/Markdown/LaTeX normalization, `.bib` append, UTF-8 decoding, input hash, runtime paths, DB bootstrap, and source profile.
- Line numbering over `source_documents.normalized_source`.
- Schema validation for the submitted plan payload.

LLM/agent owns:

- Reading the normalized source and deciding `outline_nodes`, `references_scope`, `citation_scope`, and `literature_matching_metadata`.
- Explaining fallback scope choices in `metadata.selection_reason`.
- Keeping parent/child section coverage coherent.

Do not use a temporary script to infer outline, references scope, citation scope, or matching metadata from headings alone. Scripts may count lines or serialize the final plan after the agent has made the semantic decisions.

## Source Normalization Contract

`init_runtime` 是唯一允许没有 agent 语义 payload 的阶段。它合并 runtime path confirmation、DB bootstrap、template persistence 与 source normalization。

Content-first detection rules:

- PDF signature `%PDF-` 优先于扩展名。
- 目录且可识别主入口 `.tex` 时按 LaTeX 工程目录处理。
- 文件内容命中 `\documentclass`、`\begin{document}` 或扩展名为 `.tex` 时按单文件 LaTeX 处理。
- 其它可读 UTF-8 文件按 Markdown / plain text 处理。
- 文件既不可读、也不是可识别 PDF/LaTeX/UTF-8 文本时，返回 schema-compatible error。

Normalization behavior:

- Markdown / UTF-8 plain text：直接标准化后写入 DB。
- PDF：优先使用可用 PDF-to-Markdown 转换；失败时降级文本抽取；仍不足以形成 normalized source 时失败。
- 单文件 `.tex`：原文包入 ` ```tex ` fence。
- LaTeX 工程目录：检测主入口，展平 `\input` / `\include`，整体包入 ` ```tex ` fence。
- LaTeX bibliography：若检测到 `\bibliography{...}` 或 `\addbibresource{...}`，把 `.bib` 原文追加为 ` ```bibtex ` fence，并标明其为 raw bib source。
- 无扩展名文件：若为 UTF-8 文本，按 Markdown/plain text 处理。

## Runtime Path Contract

`init_runtime` 固化：

- `working_dir`
- `tmp_dir`
- `db_path`
- `result_json_path`
- `output_dir`
- `source_path`
- `language`
- `generated_at`
- `input_hash`
- `digest_template_path`
- `citation_analysis_template_path`

If `output_dir` is omitted, use `working_dir`. Final render reads the DB value; later stages must not override it.

After `init_runtime`, later stages may depend only on:

- runtime path keys listed above
- `source_documents.normalized_source`
- `source_profile`

They must not pass a new `source_path`, `language`, output directory, template path, or normalized source override.

## Analysis Plan Payload

`persist_analysis_plan` writes the agent's semantic skeleton. It must submit a structured payload:

```json
{
  "outline_nodes": [
    {
      "node_id": "n1",
      "heading_level": 1,
      "title": "Introduction",
      "line_start": 1,
      "line_end": 48,
      "parent_node_id": null,
      "metadata": {}
    }
  ],
  "references_scope": {
    "section_title": "References",
    "line_start": 201,
    "line_end": 260,
    "metadata": {}
  },
  "citation_scope": {
    "section_title": "Introduction + Related Work",
    "line_start": 1,
    "line_end": 80,
    "metadata": {
      "selection_reason": "综述职责覆盖引言与相关工作",
      "covered_sections": ["Introduction", "Related Work"]
    }
  },
  "literature_matching_metadata": {
    "schema": "literature_matching_metadata.v1",
    "key_terms": ["citation-aware literature review"],
    "methods": ["dense retrieval"],
    "problems": ["evidence synthesis"],
    "datasets": [],
    "exclude_terms": ["clinical trial matching"]
  }
}
```

`outline_nodes[*]` fields:

- `node_id`: stable unique ID in this payload.
- `heading_level`: integer heading level.
- `title`: source heading text.
- `line_start` / `line_end`: 1-based line range in `normalized_source`.
- `parent_node_id`: parent ID or `null`.
- `metadata`: object, at least `{}`.

Hard constraints:

- `outline_nodes` 不接受只有标题字符串的简写。
- `references_scope` / `citation_scope` 不接受章节名列表或纯语义描述。
- `parent_node_id` 必须显式出现；一级标题写 `null`。
- `metadata` 必须显式出现；没有补充信息时传 `{}`。
- `literature_matching_metadata` 必须显式出现；不得省略或留到 finalization 临时补写。

## Scope Decision Rules

`references_scope`:

- Prefer the final valid references/bibliography block.
- Titles may be `References`, `REFERENCES`, `Bibliography`, `Works Cited`, `参考文献`, or `引用文献`.
- Multiple candidates: choose the last reasonable block near document end.
- Include continuation lines until the actual reference list ends.
- If no reliable bibliography block exists, write the best auditable empty/low-confidence state in later reference stage; do not invent a scope.

`citation_scope`:

- Should cover the review/background argument, not arbitrary experimental citations.
- It is one definition object, but may cover multiple sections such as `Introduction + Related Work`.
- If review discourse spans Introduction and Related Work, include both.
- parent-section selection includes all child subsections until the next same-or-higher heading.
- If a selected parent section has child subsections but the scope only covers the first paragraph, the scope is invalid.
- If headings are unreliable, use line ranges and explain fallback in `metadata.selection_reason`.
- If no reliable review-like scope exists, fail early with a structured error rather than letting citation preprocessing guess.

Invalid payload examples:

```json
{"outline_nodes": ["Introduction", "Related Work"]}
```

```json
{
  "references_scope": "References",
  "citation_scope": ["Introduction", "Related Work"]
}
```

## Literature Matching Metadata

This sidecar supports downstream candidate discovery; it is not reading evidence and does not replace digest artifacts.

Fields:

- `schema`: fixed `literature_matching_metadata.v1`.
- `key_terms`: up to 12 short topic/method/task terms.
- `methods`: up to 8 model, algorithm, mechanism, or technical route names.
- `problems`: up to 8 task, challenge, or objective phrases.
- `datasets`: up to 8 datasets, benchmarks, corpora, or resources; use `[]` if absent.
- `exclude_terms`: up to 6 terms that would retrieve unrelated domains; use `[]` if absent.

Writing rules:

- Use short phrases, not full sentences.
- Strings may contain Chinese, English, hyphenated terms, abbreviations, and formal dataset names.
- Do not copy long abstracts or source paragraphs.
- Do not add `bm25_text`.
- Avoid empty strings; scripts may trim and drop them.
- Do not include citation keys or full reference strings.

Good:

```json
{
  "schema": "literature_matching_metadata.v1",
  "key_terms": ["non-autoregressive neural machine translation", "sequence-level knowledge distillation"],
  "methods": ["fertility prediction", "parallel decoding"],
  "problems": ["machine translation latency", "multimodality in translation"],
  "datasets": ["WMT14 English-German"],
  "exclude_terms": ["medical image segmentation"]
}
```

Bad:

```json
{
  "schema": "literature_matching_metadata.v1",
  "key_terms": ["This paper proposes a very good method and achieves strong results on many benchmarks."],
  "methods": "transformer",
  "problems": [],
  "datasets": [],
  "exclude_terms": [],
  "bm25_text": "..."
}
```

## Representative Image Planning

The final `representative_image` is persisted in `persist_digest`, but plan-stage reading should note candidate figure evidence:

- Markdown image syntax: `![caption](path)`
- HTML images: `<img src="...">`
- LaTeX image commands: `\includegraphics{...}`
- PDF figure captions and page hints

Keep only text evidence. Do not extract, inspect, or validate image binaries.

## Failure Semantics And Recovery

`init_runtime` failures:

- Missing source file: return schema-compatible JSON with empty output paths and structured `error`.
- Permission or encoding failure: do not continue to semantic stages.
- Unsupported source: fail unless PDF/LaTeX/UTF-8 detection can recover enough text.
- PDF conversion warnings: continue only if `normalized_source` has enough text for outline and scope decisions.

`persist_analysis_plan` failures:

- Scope out of range: re-read `normalized_source` line numbers and resubmit plan.
- Missing `metadata`: provide `{}`.
- Invalid `literature_matching_metadata` schema: use `literature_matching_metadata.v1`.
- Citation scope too narrow: expand to cover child sections or adjacent review sections.
- References scope guessed without evidence: re-evaluate bibliography candidates; prefer an explicit low-confidence downstream reference state over invented lines.
