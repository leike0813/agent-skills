# Digest Generation

本文件补充 `persist_digest`。本阶段只提交结构化 digest payload；最终 Markdown 标题、顺序与排版由 renderer/template 从 DB 渲染。

## LLM And Script Responsibilities

Script/runtime owns:

- Payload shape validation, fixed-slot enforcement, representative image field validation, DB persistence, and final Markdown rendering.
- Template headings, section order, JSON/stdout validation, and renderer-owned artifact creation.

LLM/agent owns:

- Writing `digest_slots`, `section_summaries`, and `representative_image.selection_reason` from the normalized source.
- Judging whether a figure is representative based on textual evidence.
- Preserving uncertainty honestly when source evidence is thin.

Do not use a temporary script to summarize sections, choose contributions, invent key results, select the representative image, or generate final Markdown. Scripts may only serialize the already-reviewed digest payload or call `run_analysis.py`.

## Output Structure

The agent writes structured payload only. Final Markdown headings and layout are rendered from templates.

For `zh-*`, rendered `digest.md` uses fixed sections:

- `## TL;DR`
- `## 研究问题与贡献`
- `## 方法要点`
- `## 关键结果`
- `## 局限与可复现性线索`
- `## 分章节总结`

For `en-*`, rendered `digest.md` uses fixed sections:

- `## TL;DR`
- `## Research Question & Contributions`
- `## Method Highlights`
- `## Key Results`
- `## Limitations & Reproducibility`
- `## Section-by-Section Summary`

Do not add a top-level title such as `# 文献摘要` / `# Paper Digest`, and do not add a paper metadata block unless a future public contract explicitly adds one.

## Content Density Rules

`TL;DR` should be materially richer than a short abstract:

- Prefer 8-15 lines when source length permits.
- Cover problem, method, result, limits, and reproducibility clues.
- Include concrete terms, modules, datasets, metrics, losses, or assumptions when they appear in source.
- Do not hallucinate missing quantitative results.

`section_summaries` should be fine-grained:

- Follow persisted `outline_nodes` order.
- Prefer original source headings.
- Cover all major non-reference sections when source structure permits.
- If a major section is long or contains multiple subthemes, split into smaller entries using source headings or clear subtopic labels.
- Prefer at least 8 section/subsection summaries for normal-length papers.
- If headings are unreliable, use `Segment 1`, `Segment 2`, etc., and explain the fallback in the summary wording.

## Slot Requirements

`digest_slots` must include exactly the five fixed semantic slots:

- `tldr.paragraphs`: global summary paragraphs/lines.
- `research_question_and_contributions.research_question`: one clear sentence.
- `research_question_and_contributions.contributions`: 2-5 contribution bullets.
- `method_highlights.items`: 3-6 concrete method points.
- `key_results.items`: 2-5 quantitative or qualitative findings.
- `limitations_and_reproducibility.items`: 1-3 honest limitations or reproducibility clues.

Mapping to final Markdown:

- `tldr.paragraphs` -> final `## TL;DR`.
- `research_question_and_contributions.research_question` -> research question sentence.
- `research_question_and_contributions.contributions` -> contribution bullets.
- `method_highlights.items` -> method highlights.
- `key_results.items` -> key results.
- `limitations_and_reproducibility.items` -> limitations and reproducibility clues.
- `section_summaries[*]` -> section-by-section summary in outline order.

The payload must not contain final Markdown headings.

## Legal Payload Example

```json
{
  "digest_slots": {
    "tldr": {
      "paragraphs": [
        "本文提出一种面向低延迟推理的模型结构。",
        "核心方法通过分层模块与蒸馏损失减少计算量。"
      ]
    },
    "research_question_and_contributions": {
      "research_question": "如何在保持精度的同时降低推理成本？",
      "contributions": ["提出新架构", "给出新的训练策略"]
    },
    "method_highlights": {
      "items": ["使用分层模块", "引入蒸馏损失", "保留端到端训练流程"]
    },
    "key_results": {
      "items": ["在数据集 A 上提升 2%", "推理延迟下降 15%"]
    },
    "limitations_and_reproducibility": {
      "items": ["未开源训练代码", "消融实验覆盖有限"]
    }
  },
  "section_summaries": [
    {"source_heading": "Introduction", "items": ["定义问题背景", "总结主要挑战"]},
    {"source_heading": "Method", "items": ["解释模块结构", "说明训练目标"]}
  ],
  "representative_image": {
    "status": "selected",
    "source_kind": "markdown_image_ref",
    "label": "Figure 2",
    "caption_quote": "Overview of the proposed pipeline",
    "section_hint": "Methods",
    "page_hint": 4,
    "markdown_src_hint": "figures/overview.png",
    "selection_reason": "该图概括论文核心方法流程。",
    "confidence": "medium"
  }
}
```

## Illegal Payload Examples

Final-Markdown-shaped payload:

```json
{
  "sections": [
    {"heading": "## TL;DR", "body_md": "..."}
  ]
}
```

Missing fixed slots:

```json
{
  "digest_slots": {
    "tldr": {"paragraphs": ["..."]}
  },
  "section_summaries": []
}
```

Representative image without evidence:

```json
{
  "representative_image": {
    "status": "selected",
    "source_kind": "markdown_image_ref",
    "markdown_src_hint": "guessed/path.png",
    "selection_reason": "Looks useful",
    "confidence": "high"
  }
}
```

## Representative Image Selection

The agent must actively inspect text evidence for a representative image candidate. Do not return `{"status":"none"}` merely because the image binary cannot be viewed.

Candidate evidence:

- Markdown image reference: `![caption](figures/foo.png)`.
- HTML image reference: `<img src="figures/foo.png">`.
- LaTeX image commands: `\includegraphics{...}` or `\includegraphics[...]{...}`.
- PDF text containing figure label, caption, or page hints.

Recall keywords:

- English: `overview`, `framework`, `architecture`, `pipeline`, `method`, `model`, `workflow`, `system`, `design`, `approach`, `results`, `main`, `overall`, `proposed`.
- Chinese: `概览`、`框架`、`架构`、`流程`、`方法`、`模型`、`系统`、`设计`、`总体`、`提出`、`结果`.

Selection priority:

- Prefer method, architecture, pipeline, model overview, system diagram, experimental setup, or central result figures.
- Method / architecture / pipeline figures outrank ordinary result plots.
- Avoid tables, equation-only figures, decorative images, logos, cover images, or low-information screenshots.
- If multiple candidates exist but evidence is uneven, choose the best textual candidate with `medium` or `low` confidence instead of returning `none`.
- `none` is only valid when there is no reliable text evidence or all candidates are clearly low information.

When `selected`, include:

- `source_kind`: `markdown_image_ref` or `pdf_figure_caption`.
- `label`: source label such as `Figure 1`, `Fig. 2`, `Figure 3a`.
- `caption_quote`: short source quote; do not rewrite it.
- `section_hint`: nearby section name when known.
- `page_hint`: 1-based page number when reliable.
- `markdown_src_hint`: raw path from Markdown, HTML, or LaTeX source when available.
- `selection_reason`: one sentence explaining why this figure best represents the paper.
- `confidence`: `high`, `medium`, or `low`.

Path rules:

- For Markdown/HTML, `markdown_src_hint` must come from the original source; do not rewrite it as an absolute path.
- For LaTeX `\includegraphics{...}`, preserve the raw path as `markdown_src_hint`; do not complete extensions, rewrite directories, or check file existence.
- For PDF, do not extract images; use only figure label/caption/page text and `source_kind="pdf_figure_caption"`.

## Failure Semantics

- Missing any fixed slot: `persist_digest` should fail or request a corrected payload.
- Slot shape invalid: resubmit structured `digest_slots`; do not submit Markdown sections.
- Empty fixed slot: treat as failure or high-severity warning depending on source length.
- Section undercoverage: add `section_summaries` for major non-reference sections.
- Representative image selected without source evidence: correct fields or use `{"status":"none"}`.
- The agent must not generate final `digest.md`; final layout is produced from DB and templates.
