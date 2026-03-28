# Step 06: Render And Validate

本文件按 `SKILL.md` 的“参数词表（全项目统一）”定义；这里只补 stage 6 的额外约束，不重复定义字段基础含义。

本文件描述输出结构、输出物化、自检修复、默认行为中的输出回退，以及 `scripts/stage_runtime.py render_and_validate` 的当前运行时要求。

## 输出

### stdout 输出格式

stdout **只能**输出一个 JSON 对象（不得夹杂日志/解释文本）。

输出 JSON 必须包含（即使为空也要存在）：
- `digest_path`
- `references_path`
- `citation_analysis_path`
- `provenance.generated_at`
- `provenance.input_hash`
- `provenance.model`
- `warnings`
- `error`

### 输出物化（避免 stdout 截断）

- 为避免 stdout 截断，**必须将主要分析结果写入文件而非在stdout输出**
- 当用户没有额外指示时，可以参考以下输出路径：
  - `digest_path=<dir_of_source_path>/digest.md`
  - `references_path=<dir_of_source_path>/references.json`
  - `citation_analysis_path=<dir_of_source_path>/citation_analysis.json`
- 如存在外部注入要求改写输出目录，可在正式发布命令中追加 `--out-dir "<dir>"`；这只改变目录，不改变固定文件名
- 文件名固定：`digest.md`、`references.json`、`citation_analysis.json`（UTF‑8）。

## 默认行为协议（输出相关部分）

- 任何字段抽取不可靠时：宁可留空 + 降低置信度，也不要臆造
- 若仍无法得到合法输出，应回退到最小可用输出（空 digest/空 references/空 citation_analysis + error）

## 脚本说明

### `scripts/stage_runtime.py render_and_validate`

用途：
- 校验输出是否满足 schema（字段存在、类型正确、范围正确）
- 在校验失败时做“可解释的自动修复”（例如补齐缺失字段、类型纠正、旧字段迁移、将过长输出物化到文件），并将修复记录写入 `warnings`
- 在 `--mode render` 下，从 DB 渲染最终 artifacts、登记 `artifact_registry`，并返回最终 stdout payload

## 主发布路径

正式发布路径只有：

- `scripts/stage_runtime.py render_and_validate --mode render`

在该路径下：

- `digest.md` 必须由 `digest_slots + digest_section_summaries` 渲染
- `references.json` 必须由 `reference_items` 渲染
- `citation_analysis.json.summary` 必须由 `citation_summary` 读取
- `citation_analysis.json.items` 必须由 `citation_workset_items + citation_items` join 渲染
- `citation_analysis.json.report_md` 必须由 `citation_summary + citation_items + citation_unmapped_mentions + citation_scope` 派生
- `citation_analysis.md` 必须与该 `report_md` 完全一致
- `--mode render` 不得再接受显式 `source_path`、`preprocess_artifact` 或 stdin payload；这些输入必须来自 DB
- `--mode render` 可选接受 `--out-dir`，仅覆盖最终输出目录

## 当前 DB-first runtime 的最终发布要求

- 最终渲染由 `scripts/stage_runtime.py render_and_validate --mode render` 完成
- renderer 必须先校验 render context schema，再渲染最终文件
- JSON 渲染结果必须重新 parse 一次
- `digest.md` 必须由 `digest_slots + digest_section_summaries` 渲染得到
- `citation_analysis.json.summary` 必须由 `citation_summary` 渲染得到
- `citation_analysis.json.report_md` 必须由 `citation_summary + citation_items + citation_unmapped_mentions + citation_scope` 派生得到
- `citation_analysis.md` 内容必须与 `citation_analysis.json.report_md` 完全一致
- `render_and_validate --mode fix|check` 负责检查 stdout 契约与文件一致性
- `artifact_registry` 至少登记：
  - `digest_path`
  - `references_path`
- `citation_analysis_path`
- 若 renderer 生成了非空 `report_md`，还要登记：
  - `citation_analysis_report_path`
- renderer 还应汇总非阻塞语义 warning，例如：
  - `scope_fallback_used`
  - `reference_numbering_anomaly_detected`
  - `reference_parse_low_confidence`
  - `citation_false_positive_filtered`
  - `no_mentions_found_in_review_scope`
  - `digest_undercoverage`

### `artifact_registry` source table 示例

- `digest_path`
  - `source_table = digest_slots`
- `references_path`
  - `source_table = reference_items`
- `citation_analysis_path`
  - `source_table = citation_summary`
- `citation_analysis_report_path`
  - `source_table = citation_summary`

## 辅助校验路径

辅助路径包括：

- `scripts/stage_runtime.py render_and_validate --mode fix`
- `scripts/stage_runtime.py render_and_validate --mode check`

它们的职责是：

- 校验公共 payload 与文件一致性
- 做有限的输出修复与 schema 校验

它们不是生成最终内容的主机制；正式发布仍以 `--mode render` 为准。

## 当前阶段动作提示

适用 gate 阶段：
- `stage_6_render_and_validate`
- `stage_7_completed`

常见动作：
- `render_and_validate`
- `repair_db_state`
