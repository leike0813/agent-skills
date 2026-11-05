# Paper Scoring

本文件补充 `persist_literature_score` 的语义判断方法。进入评分阶段、填写 review draft、修复 `score_review_invalid`，或判断 applicability 与 confidence 时读取；主路径、CLI 来源与 stdout 契约以 `SKILL.md` 为准。

## 评分目标

评分表达当前 normalized source 能支持的质量判断：

- `overall_score`：文本所展示的研究质量，范围 0–100。
- `confidence`：agent 对质量判断的把握，范围 0–1。
- `confidence_adjusted_score`：runtime 计算的 `overall_score × confidence`。

confidence 不能代替质量分。论文设计可能清楚但输入缺页、OCR 差或附录不可见；此时质量分可以较高，confidence 应降低。证据完整也不等于质量高：若原文明确展示薄弱设计，质量分应低而 confidence 可以高。

只判断当前 source 能支持的内容。作者、机构、期刊、会议名气、引用量、搜索热度和外部评价都不是评分证据。

## 前置条件与 Prepare

normal mode 必须已在同一 run 完成 classification 与 `persist_digest`；score-only 在 classification 后直接进入本阶段。

```bash
python scripts/run_analysis.py persist_literature_score --db-path "<db_path>"
```

prepare 返回：

- `scoring_review_form_path`：runtime 生成的不可编辑原始表单，是 locked-field 校验和恢复真源。
- `scoring_review_draft_path`：填写用草稿；相同 `form_id` 再次 prepare 时保留已有答案。
- `editable_fields`：允许编辑的字段。
- `submit_command`：将当前 draft 作为 `--payload-file` 提交的完整命令。

从 DB 的 normalized source 读取论文，只编辑 draft。提交时直接执行 prepare 返回的命令，不新建另一份评分对象。

`form_id` 由 normalized source、locked classification 与 resolved rubric 派生。same source + same classification + same rubric 重复 prepare 返回同一 identity 与路径；任何一项变化都会生成新的 form。

## Locked Fields

以下内容由 runtime 锁定：

- `form_id`
- `literature_classification`
- rubric 与 `rubric_id`
- dimension/criterion keys、names、prompts、配置权重、满分与数组顺序
- criterion 的 `max_score`
- evidence 行号、criterion status、effective weights、dimension/overall/confidence/adjusted aggregates

prepare 锁定 classification snapshot 与 selected rubric；criterion 的语义答案仍按表单填写。

只允许编辑：

- `dimension_reviews[*].confidence`
- `dimension_reviews[*].summary`
- `criterion_reviews[*].applicable`
- `criterion_reviews[*].score`
- `criterion_reviews[*].reason`
- `criterion_reviews[*].evidence_quotes`

locked field 变动返回 `score_review_invalid` 与 `locked_field_changed`。source、classification 或 rubric 变化后，此前的 draft 返回 `stale_form`。

## Selected Rubric

Canonical 定义位于 `assets/literature_profiles.json`。prepare 从 SQLite `literature_classification` 中选中的 `rubric` 快照生成本次表单；`scoring_rubric_path` 只是审计镜像。不要从本文档手抄 key、weight 或 criterion；以 runtime contract 和表单内容为准。

八个 profile 都使用固定六维 rubric。dimension 顺序与权重固定为 25/20/15/15/15/10，最后一项为 `writing_quality`；dimension key、name 与 criteria 按所选 profile 定义，相同数组位置不代表跨 profile 同义。

- 不同 profile/rubric 的公开分数含义不同；没有明确映射时，不把 `overall_score` 或 dimension scores 直接横向排序。

classification confidence 与 scoring confidence 相互独立。`confidence=low` 已在分类阶段回退为 effective `general`，并保留 warning；该回退不直接扣减质量分。

## Criterion Evaluation

逐项阅读表单内 `prompt`，先完成 criterion，再写 dimension summary 与 confidence：

1. 判断该 criterion 对当前材料是否存在合理评价对象。
2. 有评价对象时保持 `applicable=true`，填写合法整数 `score`、非空 `reason`，并按需加入原文 quotes。
3. 无合理评价对象时设置 `applicable=false`、`score=null`，在 reason 中说明该 criterion 为何不适用于当前材料或论证方式。
4. 在同一证据边界下可评价的 criterion 上完成评分。
5. 汇总本 dimension 的优势、缺口与证据限制。
6. 若 dimension 至少一个 criterion applicable，填写 0–1 confidence；全部不适用时 confidence 为 `null`。

不要为了得到预期总分反向调整 criterion。runtime 负责归一化、N/A 权重处理与聚合。

## Score Calibration

每项使用表单预填的 `max_score`，按可观察满足程度保持一致：

- 0：没有支持，或原文直接显示严重缺失。
- 约 25%：只有弱信号，尚不足以承担该要求。
- 约 50%：基本满足，仍有明显缺口。
- 约 75%：大部分满足，缺口有限。
- 100%：证据清楚完整，且与 prompt 要求高度一致。

方法复杂不等于严谨，研究范围窄也不自动等于低质量。经验研究、历史阐释、规范论证和形式证明按其自身证据标准判断，不把“没有实验”当作人文或理论材料的自动缺陷。

## Applicability Boundary

`applicable=false` 只表示 criterion 对当前材料没有合理评价对象。下列情况仍保持 `applicable=true` 并按实际表现给分：

- 作者没有报告相关信息。
- 原文证据很弱。
- agent 不确定。
- 输入转换质量差。
- 该项得分会拉低总分。

部分 criterion 不适用时，runtime 用 dimension 剩余 applicable maximum points 归一化，configured weight 不变。整个 dimension 不适用时：

- 该 dimension 仍保留在固定六项 `dimensions` 数组中。
- dimension score 与 confidence 为 `null`。
- effective weight 为 0。
- configured weight 按比例分配给其他 active dimensions。
- runtime 添加 N/A warning。

所有 dimension 都无 applicable criterion 时，payload 返回 `score_payload_invalid`。

## Evidence Quotes

`evidence_quotes` 是字符串数组。每条 quote 最长 500 字符，直接复制 normalized source 中短而有辨识度的片段；不要填写行号。

定位顺序：

1. 对 quote 和连续 1–5 行 source window 做 NFKC、case folding、空白与标点归一化后精确匹配。
2. 未精确命中且规范化 quote 至少 8 字符时，runtime 使用字符 n-gram 相似度寻找候选。
3. 相似度达到 0.45 时接受；并列候选按最早位置确定。
4. 低于阈值时拒绝，错误详情给出 criterion、quote 序号、最佳相似度和候选行范围。

证据数组可以为空。若判断依据是“全文未报告某项内容”，reason 应说明可观察的缺失，不要虚构一句否定性原文。Runtime 只定位 quote；quote 是否真正支持 score 仍由 agent 负责。

示例：

```json
{
  "applicable": true,
  "score": 4,
  "reason": "作者说明材料边界，并用连续案例支持解释。",
  "evidence_quotes": ["The archive contains correspondence from 1932 to 1938."]
}
```

## Confidence

每个 active dimension 填写 0–1 confidence，综合考虑：

- 输入是否覆盖主体、附录、图表、脚注和必要文本。
- 相关信息是直接出现还是依赖推断。
- OCR、公式、表格或版面转换是否损坏关键证据。
- 多处材料是否相互一致。
- 当前 criterion 是否能由 source 中的实际证据判断。

建议区间：

- 0.90–1.00：直接证据完整，几乎无需推断。
- 0.75–0.89：证据较充分，仅有小范围缺口。
- 0.55–0.74：有可用证据，但关键细节缺失或需要明显推断。
- 0.30–0.54：只能做初步判断，输入或信息缺口较大。
- 0.00–0.29：有评价对象，但现有文本几乎不足以稳定判断。

全部 criterion 不适用时 confidence 必须为 `null`，不得填 0。0 表示有评价对象但把握极低。

## Draft Shape

保留 prepare 生成的完整 draft 与全部 locked fields，只改下列语义值：

```json
{
  "dimension_reviews": [
    {
      "confidence": 0.86,
      "summary": "材料范围与解释路径清楚，反例讨论仍有限。"
    }
  ],
  "criterion_reviews": [
    {
      "applicable": true,
      "score": 4,
      "reason": "原文说明了材料边界，并用同类材料验证解释。",
      "evidence_quotes": ["The archive contains correspondence from 1932 to 1938."]
    }
  ]
}
```

实际提交使用原表单的完整对象；上例省略 locked keys，不可作为替代模板。

## Output Contract

submit 成功后 runtime 计算、渲染并登记 `literature_score.json`。当前 schema 为 `literature_score.v2`，包含：

- `schema`
- `rubric_id`
- `literature_classification`
- `overall_score`
- `confidence`
- `confidence_adjusted_score`
- selected rubric 的 `dimensions`（固定 6 项）

每个 dimension 保留 canonical key、name、configured/effective weight、raw/applicable maximum、score、confidence、summary 和 criteria；key/name 与 criteria 随所选 profile 定义。每个 criterion 保留 key、name、status、score、maximum、reason 与定位后的 evidence。not-applicable criterion 留在产物中，score 为 `null`。

Runtime 将 score round 到 0.1、confidence 到 0.01、weights 到 6 位小数，并让公开维度与 rubric snapshot 精确一致。不得手写或修改聚合值。

full mode 提交成功后进入 references；score-only 提交成功后直接返回最终 JSON，且只有 `literature_score_path` 非空。

## Failure And Recovery

- `classification_required`：先完成 `persist_literature_classification`，不要用默认 category 猜测。
- `score_prerequisite_missing`：normal mode 先完成 `persist_digest`；确认 normalized source 已写入。
- `scoring_context_failed`：检查 runtime rubric snapshot、review-form 目录和原始表单是否可读。
- `score_review_invalid`：逐条读取 `error.details`。
  - `stale_form`：重新 prepare，使用新 `scoring_review_draft_path`。
  - `locked_field_changed`：从 `scoring_review_form_path` 恢复 locked fields，只保留允许编辑的语义答案。
  - `incomplete_answer`：补齐指出的 score、reason、summary、confidence 或 applicability 约束。
  - `evidence_not_found`：按候选行范围复制更准确、辨识度更高的 source quote。
- `score_payload_invalid`：确认至少一个 criterion applicable，且合法的 issue 不是所有维度都无法评分。
- `score_render_failed`：不要手改 `literature_score.json`；检查 DB score state、runtime template 与 render schema 后重跑评分或 finalization。

## Completion Check

提交成功后确认：

- `literature_score_path` 是绝对路径，文件名为 `literature_score.json`。
- 产物含 `literature_score.v2`、`rubric_id`、`literature_classification`、三个 aggregate 值与固定 6 项 dimensions。
- dimensions 的顺序、keys 与各 profile 的 criteria 匹配本次 locked rubric。
- not-applicable criterion 的 status 为 `not_applicable`，score 为 `null`，reason 保留。
- configured/effective weights、evidence 行号与 aggregate values 来自 runtime。
- score-only stdout 中其他公开产物路径为空字符串。
- result JSON mirror 与最终 stdout 一致。
