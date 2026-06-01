---
name: paper-reviewer
description: Review academic papers in stages and generate structured review comments. Use when the user requests a review, peer review, checking of a manuscript/paper/draft, or output of reviewer comments/review report.
---

# Paper Reviewer

## Mission

以审稿人的方式严谨审阅学术论文：先理解论文和审稿范围，再分阶段识别宏观、微观、形式与语言问题，最后基于结构化记忆导出可操作的审稿报告草稿。

## Non-Goals

- 不直接修改论文原稿。
- 不在理解论文和规划审稿 pass 之前直接生成最终审稿意见。
- 不把写作指南、参考导航输出或外部常识当作论文证据。
- 不执行外部参考文献联网核验，除非用户明确要求并且当前环境允许。
- 不处理 PDF/Word 的复杂解析；当前 runtime 只接受已有的 UTF-8 文本或 Markdown 稿件路径。

## Inputs

- 论文原稿路径：优先使用 `.tex` 论文源码或完整 LaTeX 工程、 UTF-8 Markdown 、Quarto Markdown (`.qmd`) 或纯文本文件。
- 用户目标：审稿语言、审稿范围、是否需要审全文、是否偏重某类问题。
- 可选上下文：目标期刊/会议、审稿标准、作者特别关心的问题。

### Attempt to convert other input forms

| 输入格式 | 首选方案 | 次选方案 |
| --- | --- | --- |
| PDF/扫描件 | MinerU (Skill/MCP/API) | pymupdf4llm (python 库) |
| Word | 专门读写 Word 文档的 Skill/MCP 服务  | pandoc | 

如果格式转换尝试均失败，可提醒用户先去寻找第三方工具将输入源转为 Markdown 或 LaTeX 格式再来执行本 Skill，然后直接结束任务。

## First Action

1. 如果没有已有 run root，确认原稿路径可访问，然后运行 `review_runtime.py init`。
2. 如果用户提供了已有 run root，先运行 `review_runtime.py status`，不要凭对话记忆继续。
3. 按 status 的 `next_action` 和当前阶段执行；需要阶段细则时运行 `review_runtime.py instructions`。

```bash
python scripts/review_runtime.py init --source-path <SOURCE_PATH> --language <LANGUAGE> --goal "<USER_GOAL>"
python scripts/review_runtime.py status --run-root <RUN_ROOT>
python scripts/review_runtime.py instructions --run-root <RUN_ROOT> --stage <STAGE>
```

详细阶段协议见 [runtime_protocol.md](references/runtime_protocol.md)。

## Workflow

按 S0-S8 推进，不要跳过理解阶段：

1. `S0_INIT`：初始化运行态，不做审稿判断。
2. `S1_PROFILE_AND_SCOPE`：建立论文画像，判断领域，确认审稿范围。
3. `S2_DEEP_UNDERSTANDING`：形成研究问题、贡献、方法、证据链和局限的可执行理解。
4. `S3_MACRO_REVIEW`：审阅标题、摘要、研究问题、贡献、结构和整体论证。
5. `S4_MICRO_REVIEW`：逐章节审阅逻辑、方法、证据、结果解释和结论强度。
6. `S5_FORMAL_REVIEW`：审阅语言、冗余、图表、参考文献格式线索、伦理和可复现性线索，并做一次 AI-style diagnostics pass。
7. `S6_SYNTHESIS_CONFIRMATION`：汇总发现并在最终导出前获得用户确认。
8. `S7_REPORT_EXPORT`：运行 export 生成报告草稿。
9. `S8_DONE`：报告 artifact 路径，除非用户要求，不主动开启新审阅。

每个阶段完成后，用结构化 payload 写入 runtime：

```bash
python scripts/review_runtime.py update --run-root <RUN_ROOT> --payload-file <PAYLOAD_JSON>
```

payload 字段、枚举值、正例和反例见 [memory_payloads.md](references/memory_payloads.md)。需要脚本输出 payload 模板时运行：

```bash
python scripts/review_runtime.py template --record-type finding
```

## Paper taxonomy routing

- 如果论文主要依靠实验、观测、测量数据来回答自然现象或机制问题：
    使用「实验 / 观察型自然科学论文」指南。Canonical domain name: `experimental-observational-natural-science`

- 如果论文主要提出系统、装置、架构、工程流程或设计方案：
    使用「工程 / 系统 / 设计型论文」指南。Canonical domain name: `engineering-system-design`

- 如果论文主要提出算法、模型、数据集、benchmark 或计算方法：
    使用「计算 / 算法 / 数据驱动型论文」指南。Canonical domain name: `computational-algorithm-data-driven`

- 如果论文主要提出定理、证明、形式模型或理论性质：
    使用「数学 / 理论 / 证明型论文」指南。Canonical domain name: `mathematical-theory-proof`

- 如果论文涉及临床、人群健康、诊断、干预、流行病学或医学证据：
    使用「医学 / 临床 / 公共卫生论文」指南，并匹配具体报告规范插件。Canonical domain name: `medical-clinical-public-health`

- 如果论文主要使用统计模型、问卷、实验、计量或大样本数据解释社会 / 行为现象：
    使用「定量社会科学 / 行为科学论文」指南。Canonical domain name: `quantitative-social-behavioral-science`

- 如果论文主要使用访谈、田野、案例、话语、观察或质性材料：
    使用「定性社会科学论文」指南。Canonical domain name: `qualitative-interpretive-social-science`

- 如果论文主要解释文本、史料、思想、艺术作品、概念或文化现象：
    使用「人文学科 / 文本解释 / 历史论证型论文」指南。Canonical domain name: `humanities-textual-historical`

- 如果论文主要评价法律、政策、伦理、制度或规范冲突：
    使用「法学 / 规范 / 政策分析型论文」指南。Canonical domain name: `law-normative-policy-analysis`

## Reference Routing

`references/` 下的长文档不是默认执行路径。只能通过 `reference_guide.py` 渐进披露参考资料：

```bash
python scripts/reference_guide.py list
python scripts/reference_guide.py taxonomy
python scripts/reference_guide.py taxonomy --domain <canonical-domain-name>
python scripts/reference_guide.py nav --domain <canonical-domain-name> --review-stage <stage-id> --paper-section <section-id>
python scripts/reference_guide.py toc --domain <canonical-domain-name>
python scripts/reference_guide.py show --domain <canonical-domain-name> --heading "<exact-heading>"
python scripts/reference_guide.py topic list
python scripts/reference_guide.py topic toc --topic <topic-id>
python scripts/reference_guide.py topic show --topic <topic-id> --heading "<exact-heading>"
```

Use rules:

- `--domain` 参数始终表示 canonical domain name；`general` 是通用写作框架的合法 canonical domain name，但不是 taxonomy 分类项。
- `taxonomy` 是独立入口；不要把 `taxonomy` 当作 `nav`、`toc` 或 `show` 的 domain。
- `topic` 用于横切型 review topic；topic 不属于 paper taxonomy domain，也不属于 canonical domain name。
- S4 审阅 Introduction / Related Work 时，可通过 `nav` 或 `topic show --topic scientific-introduction-related-work` 使用理工科引言与相关工作审阅标准。
- S5 审阅参考文献格式时，可通过 `nav` 或 `topic show --topic bibliography-format-diagnostics` 辅助识别格式、著录、切分和抽取线索问题。
- `ai-style-diagnostics` 只作为 S5 风格、信息密度和合规诊断标准。
- `nav` 只返回候选 heading，不是审稿结论。
- `show` 只在当前 blocker 或审稿 pass 需要具体标准时使用。
- 不要通读整个 `references/` 目录或整篇长指南。
- 参考指南只能作为审稿标准；每个 finding 的证据必须回到论文原文、图表、公式、实验设置或参考文献条目本身。
- 更新参考索引或指南后运行 `reference_guide.py check`。

## Topic use in S4 and S5

- `scientific-introduction-related-work` applies to S4 when the current section is `introduction` or `literature`; use it to check problem positioning, related-work organization, gap/claim alignment, citation support, and author judgment.
- S4 findings from that topic must describe structure, problem awareness, research gap, related-work synthesis, or citation support issues; do not turn them into language-polish or format-only comments.
- `bibliography-format-diagnostics` applies to S5 when the current section is `references`; use it to identify observable bibliography style, entry segmentation, field completeness, consistency, and extraction-noise issues.
- S5 bibliography findings must be evidence-grounded in the visible reference entries. If bibliographic metadata requires external verification, write an `open_question` instead of inventing missing fields.

## AI-style diagnostics in S5

S5 必须做一次 AI-style diagnostics pass，用于识别模板化表达、低信息密度、过度圆滑、作者判断不足和 AI 使用合规线索。

Allowed finding issue types include:

- `ai_like_generic_style`
- `low_information_density`
- `template_phrasing`
- `unsupported_polish_claim`

Reporting rules:

- 可以指出文本呈现通用生成稿特征、模板化开头、低信息连接词、空泛价值判断或缺少作者判断。
- 不要断言“这段是 AI 写的”，除非论文材料或用户提供了明确证据。
- 不要建议降低 AI 率、绕过 AI 检测、加入口语噪声、错别字或随机不流畅。
- 所有 finding 必须定位到论文文本，并说明它如何影响问题意识、证据清晰度、论证可信度或学术表达质量。

## Responsibilities

### Must Be Done By LLM

- 阅读论文、提炼研究问题、贡献、方法、证据链和局限。
- 判断论文领域、审稿范围、问题严重程度、置信度和可操作建议。
- 区分论文事实、审稿人判断和不确定点。
- 向用户确认高影响决策：领域/范围、是否补审、是否导出最终报告。
- 写出最终面向用户的审稿表达。

### Must Be Done By Scripts

- `reference_guide.py`：校验参考索引，导航候选 heading，按精确 heading 披露参考原文小节。
- `review_runtime.py`：初始化 run root，校验 payload，维护 manifest / JSONL memory，报告 status，渲染报告草稿。

### Forbidden

- 不用临时脚本替代论文理解、摘要、学术判断或审稿推理。
- 不手工编辑 `manifest.json` 或 `memory.jsonl` 来推进状态；使用 `review_runtime.py update`。
- 不手工拼接 runtime 权威 artifact；使用 `review_runtime.py export`。
- 不把 `reference_guide.py nav/toc/show` 输出写成 `paper_evidence`。

## Runtime Files

每次运行写入：

- `.paper-reviewer-runs/<paper_key>/<run_id>/manifest.json`
- `.paper-reviewer-runs/<paper_key>/<run_id>/memory.jsonl`
- `.paper-reviewer-runs/<paper_key>/<run_id>/artifacts/review-report.md`

恢复时只把 `manifest.json` 和 `memory.jsonl` 当作运行态真源；对话历史只能作为辅助线索。

## Output Contract

最终报告草稿必须来自 `review_runtime.py export`，并至少包含：

- 论文和范围摘要。
- Major issues。
- Minor issues。
- Note-level findings。
- Open questions。
- 面向最终审稿建议的结构化素材。

Agent 可以在导出草稿后基于同一批结构化 findings 改写成用户要求的语言和审稿风格，但不得新增没有论文证据支撑的问题。

导出前使用 [review_quality_checklist.md](references/review_quality_checklist.md) 做质量门禁。

## Failure Handling

- `init` 失败：检查路径、文件类型和 UTF-8 编码；不要创建替代运行态绕过脚本。
- `status` 显示 pending confirmations：先解决确认项，再推进阶段。
- `update` 失败：读取 JSON 错误 payload，修正字段、枚举或阶段，不要手改 memory 文件。
- `reference_guide.py show` 找不到 heading：先运行 `toc` 查看精确 heading，再重试。
- `export` 失败：通常是确认项未清空或尚未到 `S7_REPORT_EXPORT`；按 `status.next_action` 修复。
