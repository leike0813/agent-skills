## 核心执行指令

1. 先读 `SKILL.md`，不要预读整个 `references/` 目录。
2. 所有运行时阶段都通过 `scripts/run_analysis.py` 执行。
3. 首个脚本动作必须是 `init_runtime`，并传入 prompt payload 中的 `source_path` 与目标 `language`。
4. SQLite 是过程真源；语义判断结果必须整理为当前阶段的结构化 payload 后写入 runtime。
5. 不要直接写 SQLite 表，不要手工编辑最终公开 artifacts。
6. Reference title 必须保持 raw reference 中的原始语言和文字系统；不得翻译、英文化、罗马化，或用 placeholder 字符串代替未知题名。
7. Reference review、metadata review、citation semantic review 若适合并行，应优先按 runtime 返回的 batch work packages 委派给 subagent；主 agent 合并后按阶段回合提交。
8. `persist_references` 先提交 `reference_reviews[]` core fields；runtime 返回 `metadata_review_packages` 后，再单独提交 `metadata_reviews[]`。需要修边界时先提交 `split_reviews[]`。
9. `persist_citation_analysis` 使用 `citation_semantic_reviews[]`、`timeline_summaries` 与全局 `summary`。
10. Payload 文件必须是 UTF-8 JSON；复杂 payload 使用 JSON-safe 方式生成，不要手写容易破坏转义的超长 shell 字符串。
11. Metadata subagent drafts 必须覆盖 runtime 返回的 metadata packages，并优先使用 canonical 字段：`publicationTitle`、`DOI`、`ISBN`、`ISSN`、`archiveID`、`url`、`publisher`、`place`、`pages`、`volume`、`issue`、`itemType`、`date`。
12. 最终公开产物只能由 runtime renderer 从 DB 与运行时模板生成。
13. 最终 assistant 输出必须是一个 JSON 对象，并且必须满足 stdout schema。

成功态 stdout JSON 示例：

```json
{
  "digest_path": "/abs/path/digest.md",
  "references_path": "/abs/path/references.json",
  "citation_analysis_path": "/abs/path/citation_analysis.json",
  "literature_matching_metadata_path": "/abs/path/literature_matching_metadata.json",
  "citation_analysis_report_path": "/abs/path/citation_analysis.md",
  "provenance": {
    "generated_at": "2026-03-31T09:00:00Z",
    "input_hash": "sha256:0123456789abcdef",
    "model": "gpt-5.4"
  },
  "warnings": [],
  "error": null
}
```
