---
name: literature-digest-lite
description: Generate a paper digest (Markdown) from a source file using a simplified runtime without SQLite-gating.
compatibility: Requires local filesystem read access to source_path; no network required.
---

# literature-digest-lite

本 skill 运行于后台自动化场景：不得向用户提问做决策。stdout 只能输出一个 JSON 对象。

## 核心执行指令

1. 先读 `SKILL.md`。
2. 从 prompt payload 读取 `source_path` 和 `language`。
3. 调用 `scripts/run_digest.py --mode normalize` 进行输入标准化。
4. 生成结构化 `digest_slots + section_summaries`（**必须由 LLM 完成**）。
5. 准备运行时模板：`en-*` / `zh-*` 直接复制仓库模板；其他语言由 **agent 直接翻译**。
6. 调用 `scripts/run_digest.py --mode render` 渲染最终 digest.md 并输出 JSON。

## LLM 与脚本职责边界

**必须由 LLM 完成**：
- digest 槽位内容生成（`digest_slots + section_summaries`）
- 模板翻译（非 en/zh 语言时，翻译固定标题文本）

**必须由脚本完成**：
- 输入协议探测与标准化
- 模板渲染（基于结构化数据生成 Markdown）
- 输出 JSON 合法性检查

**绝对禁止**：
- 用脚本替代 LLM 做摘要、大纲、语义分类
- 脚本调用外部 LLM API

## 输入输出硬契约

- 输入只读取 prompt payload 中的 `source_path` 与 `language`
- `source_path` 是唯一内容来源；输入可为 Markdown、PDF、单文件 `.tex`、LaTeX 工程目录或无扩展名文件
- `language` 控制 digest 语言；若用户显式指定则直接使用，否则先从 prompt 主要语言推断，仅在无法稳定判断时回退 `zh-CN`
- stdout 必须包含：
  - `digest_path`
  - `provenance.generated_at`
  - `provenance.input_hash`
  - `warnings`
  - `error`
- 最终公开产物固定为：
  - `digest.md`

## 参数词表

- `source_path`：源文件路径，用户传入的唯一内容来源。
- `language`：输出语言；可以是任意字符，推荐采用 BCP 47 语言标签；缺省回退 `zh-CN`。
- `digest_slots`：最终 digest 的结构化内容槽位集合。
  - 固定槽位：`tldr`、`research_question_and_contributions`、`method_highlights`、`key_results`、`limitations_and_reproducibility`
- `section_summaries`：按大纲顺序组织的章节级摘要列表。

## Digest 生成细则

### Digest 输出结构（Markdown）

**language=zh-CN 时**：
- 必须严格使用如下标题（顺序与标题文本均固定）：
  - `## TL;DR`（建议 8~15 行；覆盖问题/方法/结果/局限与可复现性线索）
  - `## 研究问题与贡献`
  - `## 方法要点`
  - `## 关键结果`
  - `## 局限与可复现性线索`
  - `## 分章节总结`
- 不要输出额外的顶层标题（例如 `# 文献摘要`）或"论文信息/元数据"区块
- 全局总结（`## TL;DR` 到 `## 局限与可复现性线索`）的总输出量应显著增加：相较"精简版"约提升至约 3 倍信息量
- `## 分章节总结` 必须存在，并尽可能细化章节切分：
  - 优先按"全文大纲骨架"的章节标题逐章总结（推荐使用 `### <原文章节标题>`）
  - 章节粒度要求：尽量覆盖主要一级章节；若某一级章节过长或包含多个子主题，优先进一步拆成二级小节（`#### <子节标题或子主题>`）
  - 数量要求：至少输出 8 个章节/小节块（`###` 或 `####`），并尽量更多
  - 内容要求：分章节总结的总输出量应显著增加：相较"精简版"约提升至约 5 倍信息量
  - 若无法可靠识别大纲：退化为 `### 片段 1/2/3...` 的分段总结，并将片段数量提升（至少 8 段）

**language=en-US 时**：
- Must use the exact headings below (fixed order and text):
  - `## TL;DR` (prefer 8–15 lines)
  - `## Research Question & Contributions`
  - `## Method Highlights`
  - `## Key Results`
  - `## Limitations & Reproducibility`
  - `## Section-by-Section Summary`
- Do not add an extra top-level title or a "Paper Info/Metadata" section
- The overall "global summary" volume should be ~3× a short version
- `## Section-by-Section Summary` must exist and be as fine-grained as possible:
  - Prefer `### <Original section heading>` in outline order
  - If a section is long or covers multiple themes, split further into `#### <subtopic>` blocks
  - Output at least 8 section/subsection blocks (`###` or `####`) and preferably more
  - Fallback to `### Segment 1/2/3...` with at least 8 segments if headings are unreliable

### 结构化 payload 契约

LLM 必须提供结构化 payload：

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

**约束**：
- `digest_slots` 必须完整覆盖 5 个固定槽位
- `section_summaries` 必须按大纲顺序提供
- 最终 digest 直接由 `digest_slots + section_summaries` 渲染
- LLM 只负责槽位内容，不负责最终标题文本与排版

**各槽位内容要求**：
- `tldr.paragraphs`：全局摘要，8-15 行，覆盖问题/方法/结果/局限与可复现性线索
- `research_question_and_contributions.research_question`：研究问题，1 句清晰表述
- `research_question_and_contributions.contributions`：核心贡献，2-5 个要点
- `method_highlights.items`：方法要点，3-6 个具体技术点
- `key_results.items`：关键结果，2-5 个定量或定性结果
- `limitations_and_reproducibility.items`：局限与可复现性线索，1-3 个诚实的局限性
- `section_summaries[*].source_heading`：对应原文章节标题
- `section_summaries[*].items`：该章节的要点列表，细粒度覆盖

### LLM 提交内容与最终 Markdown 的映射关系

- `tldr.paragraphs` → 对应最终 `## TL;DR`
- `research_question_and_contributions.research_question` → 对应最终 `## 研究问题与贡献` / `## Research Question & Contributions` 中的研究问题句
- `research_question_and_contributions.contributions` → 对应最终贡献要点列表
- `method_highlights.items` → 对应最终 `## 方法要点` / `## Method Highlights`
- `key_results.items` → 对应最终 `## 关键结果` / `## Key Results`
- `limitations_and_reproducibility.items` → 对应最终 `## 局限与可复现性线索` / `## Limitations & Reproducibility`
- `section_summaries[*]` → 对应最终 `## 分章节总结` / `## Section-by-Section Summary` 下按大纲顺序展开的章节块

### 失败语义

- 缺少任一固定 slot、slot 形状不合法、或 `section_summaries` 结构错误时，属于 digest 生成失败
- 固定 slot 为空、或 `section_summaries` 对主要章节覆盖不足时，也属于 digest 生成失败或 warning
- 失败后不得猜测性生成最终 digest 文本

### 合法 payload 示例

```json
{
  "digest_slots": {
    "tldr": { "paragraphs": ["本文提出...", "实验表明..."] },
    "research_question_and_contributions": {
      "research_question": "如何在保持精度的同时降低推理成本？",
      "contributions": ["提出新架构", "给出新的训练策略"]
    },
    "method_highlights": { "items": ["使用分层模块", "引入蒸馏损失"] },
    "key_results": { "items": ["在数据集 A 上提升 2%", "推理延迟下降 15%"] },
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

### 最终排版来源

- 最终 digest 排版由 renderer 和模板文件决定：
  - `assets/templates/digest.zh-CN.md.j2`
  - `assets/templates/digest.en-US.md.j2`
- 模板只负责固定标题、顺序和排版
- 真正进入最终成品的内容必须先落入 `digest_slots` 与 `section_summaries`

## 执行主路径

### 1. 输入标准化

调用命令：
```bash
python scripts/run_digest.py --mode normalize --source-path "/abs/path/paper.md"
```

脚本完成：
- 读取 `source_path`
- 协议探测与标准化：
  - PDF: 优先 `pymupdf4llm`，失败则兜底解析
  - LaTeX (`.tex` 或目录): 展平 `\input` / `\include`，包进 ` ```tex ` fence
  - Markdown/文本：直接读取
- 计算 `input_hash` (sha256)

### 2. 生成 digest 内容（LLM 职责）

agent 调用 LLM，传入标准化后的文本和 `language`，生成结构化 payload：

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

### 3. 准备运行时模板（agent 职责）

**模板翻译规则**：
- 若 `language.lower().startswith("en")`：复制 `digest.en-US.md.j2`
- 若 `language.lower().startswith("zh")`：复制 `digest.zh-CN.md.j2`
- 其他语言：**agent 直接翻译**仓库模板的固定标题文本（保留 Jinja2 语法）

**翻译原则**：
- 仅翻译固定标题文本（如 `## TL;DR`、`## 研究问题与贡献`）
- 保留 Jinja2 模板语法：`{% ... %}`、`{{ ... }}`、`{# ... #}`
- 保留变量名和循环结构
- 保留注释

### 4. 渲染并输出

调用命令：
```bash
python scripts/run_digest.py --mode render \
  --source-path "/abs/path/paper.md" \
  --language "zh-CN" \
  --payload-file /tmp/digest_payload.json \
  --template-file /tmp/digest.runtime.md.j2
```

脚本完成：
- 读取 payload（`digest_slots + section_summaries`）
- 读取运行时模板
- 渲染最终 `digest.md`
- 输出 stdout JSON

成功态 stdout JSON 示例：
```json
{
  "digest_path": "/abs/path/digest.md",
  "provenance": {
    "generated_at": "2026-04-02T10:00:00Z",
    "input_hash": "sha256:0123456789abcdef"
  },
  "warnings": [],
  "error": null
}
```

失败态 stdout JSON 示例：
```json
{
  "digest_path": "",
  "provenance": {
    "generated_at": "",
    "input_hash": ""
  },
  "warnings": [],
  "error": {
    "code": "normalize_source_failed",
    "message": "read source failed: [Errno 2] No such file or directory"
  }
}
```

## 默认行为协议

- 读取 `source_path` 失败 → `digest_path=""`，填充 `error`
- 无法识别输入格式 → 同上
- `language` 为空 → 回退 `zh-CN`
- payload 格式错误 → 返回 `error`
- 模板渲染失败 → 返回 `error`

## 脚本 CLI 说明

### `--mode normalize`

输入标准化模式。

参数：
- `--source-path`（必需）：源文件路径

输出：
- stdout: JSON 结果（包含 `normalized_text`, `input_hash`, `source_type` 等）

### `--mode render`

渲染输出模式。

参数：
- `--source-path`（必需）：源文件路径
- `--language`（可选）：输出语言，默认 `zh-CN`
- `--payload-file`（必需）：包含 `digest_slots + section_summaries` 的 JSON 文件
- `--template-file`（可选）：运行时模板路径，默认根据 language 选择仓库模板

输出：
- stdout: JSON 结果（`digest_path`, `provenance`, `warnings`, `error`）
