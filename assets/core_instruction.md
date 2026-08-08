## 核心执行指令

1. 先读 `SKILL.md`，不要预读整个 `references/` 目录。
2. 所有运行时阶段都通过 `scripts/run_analysis.py` 执行。
3. 首个脚本动作必须是 `init_runtime`，并传入 prompt payload 中的 `source_path`、目标 `language`、非空时的 `identifier`，以及为 true 时的 `score_only`。
4. SQLite 是过程真源；语义判断结果必须整理为当前阶段的结构化 payload 后写入 runtime。
5. 不要直接写 SQLite 表，不要手工编辑最终公开 artifacts。
6. Reference title 必须保持 raw reference 中的原始语言和文字系统；不得翻译、英文化、罗马化，或用 placeholder 字符串代替未知题名。
7. Reference review、Reference Metadata Evidence Review、citation semantic review 若 runtime 返回 batch file paths 且环境支持 subagent，必须默认按 runtime 预切 batch 委派；每个 batch 最多 10 条。主 agent 不得手工切 full workset；subagent 读取被分配的 batch JSON 文件，只返回 batch draft；主 agent 是唯一 DB writer，合并后按阶段回合提交。
8. 禁止用临时脚本、正则批处理或批量规则代替 LLM/subagent 填写 reference core fields、Reference Metadata Evidence Review、citation semantic review、timeline narratives 或全局 summary；脚本只能做 JSON 序列化、key 覆盖检查、draft 合并和 runtime 调用等确定性支持。
9. 正常路径在 `persist_digest` 后执行 `persist_literature_score`；prepare 会返回 locked scoring review form、可复用 draft、可编辑字段和 submit 命令。agent 只填写 draft 中的语义字段，不手写 paper-type 值、key、满分、权重、status 或证据行号。`score_only=true` 时跳过 plan、digest、references 和 citation，评分提交成功后直接输出最终 JSON。
10. `persist_references` prepare 在确定性 entries/candidates 生成后、split package 外部化前，由 runtime 依据 DOI/arXiv 尝试公开 API 解析。仅当 suspect block 内全部条目 accepted 时跳过该块；部分 accepted 仍按完整 block 提交 `split_reviews[]`。只对 `reference_core_batch_paths` 中未解决条目提交 `reference_reviews[]`。Runtime 返回 `metadata_evidence_review_manifest_path` / `metadata_evidence_batch_paths` 后，再单独提交 `metadata_evidence_reviews[]`。Reference Metadata Evidence Review 只使用 batch JSON 本地证据，禁止自行访问外部服务。
11. `persist_citation_analysis` 使用 `citation_semantic_reviews[]`、`timeline_summaries` 与全局 `summary`；该阶段是 tolerant best-effort，空字段和部分覆盖合法，runtime 不为缺失 review 生成替代语义。
12. Payload 文件必须是 UTF-8 JSON；复杂 payload 使用 JSON-safe 方式序列化已经审核过的决策，不要手写容易破坏转义的超长 shell 字符串。
13. Metadata subagent drafts 必须覆盖 runtime metadata manifest 中的 coverage keys，并优先使用 canonical 字段：`publicationTitle`、`DOI`、`ISBN`、`ISSN`、`archiveID`、`url`、`publisher`、`place`、`pages`、`volume`、`issue`、`itemType`、`date`。
14. 最终公开产物只能由 runtime renderer 从 DB 与运行时模板生成。
15. 最终 assistant 输出必须是一个 JSON 对象，并且必须满足 stdout schema。

成功态 stdout JSON 示例：

```json
{
  "digest_path": "/abs/path/digest.md",
  "references_path": "/abs/path/references.json",
  "citation_analysis_path": "/abs/path/citation_analysis.json",
  "literature_matching_metadata_path": "/abs/path/literature_matching_metadata.json",
  "literature_score_path": "/abs/path/literature_score.json",
  "citation_analysis_report_path": "/abs/path/citation_analysis.md",
  "provenance": {
    "generated_at": "2026-03-31T09:00:00Z",
    "input_hash": "sha256:0123456789abcdef",
    "model": "gpt-5.4"
  },
  "warnings": [],
  "error": {}
}
```
