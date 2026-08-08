# Paper Scoring

本文件补充 `persist_literature_score` 的语义判断方法。进入评分阶段、填写 review draft、修复 `score_review_invalid`，或需要判断 applicability 与 confidence 时读取；执行顺序、CLI 和最终 stdout 契约以 `SKILL.md` 为准。

## 评分目标

评分同时表达论文文本呈现的质量与判断把握：

- `overall_score`：当前原文所展示的科学质量，范围 0–100。
- `confidence`：agent 对上述判断的把握，范围 0–1。
- `confidence_adjusted_score`：runtime 计算的 `overall_score × confidence`。

不要用 confidence 代替质量分。论文可能设计良好，但原文缺页、OCR 较差或关键附录不可见；此时质量分可以较高，confidence 应降低。证据完整也不等于质量高：证据若清楚展示一个薄弱设计，质量分应低而 confidence 可以高。

只判断当前 normalized source 能支持的内容。作者、机构、期刊、会议名气、引用量、搜索热度和外部评价都不是评分证据。

## Prepare 与 Submit

Prepare：

```bash
python scripts/run_analysis.py persist_literature_score --db-path "<db_path>"
```

读取 stdout 中的：

- `scoring_review_form_path`：runtime 生成的不可编辑原始表单，是 locked-field 校验和恢复真源。
- `scoring_review_draft_path`：填写用草稿；同一 `form_id` 再次 prepare 时不会覆盖已有答案。
- `editable_fields`：允许修改的字段集合。
- `submit_command`：将当前 draft 直接作为 `--payload-file` 提交的完整命令。

从 `init_runtime` 返回的 normalized-source path 读取论文，只编辑 draft。提交时直接执行 prepare 返回的命令，不另建一份评分对象。

表单绑定当前 normalized source 与 rubric snapshot。`form_id`、paper-type 选项、dimension/criterion key、名称、prompt、权重、满分及数组顺序均由 runtime 锁定。不要改写、删除、重排或补充这些字段。

允许编辑的内容只有：

- 在 `paper_type_choices[*].selected` 中选择一个且仅一个选项；
- `paper_type_reason`；
- `dimension_reviews[*].confidence` 与 `summary`；
- `criterion_reviews[*].applicable`、`score`、`reason` 与 `evidence_quotes`。

## 论文类型选择

逐项阅读表单中的 paper-type `description`，选择最能描述主要论证方式的一项。`paper_type_reason` 简短说明判断依据。论文类型用于解释 criterion 是否有评价对象，不直接增加或降低分数。

不要手写 paper-type 字符串。选择值来自被勾选条目的 locked `paper_type`。

## Dimension 与 Criterion 判断

`scoring_rubric.json` 是 paper-type 选项、名称、prompt、顺序、权重和满分的唯一事实源；prepare 已将本次 snapshot 的全部定义写入表单。逐项依据表单内的 `prompt` 判断，不从本文档复制 key、满分或维度配置。

评分时先完成 criterion，再写 dimension summary 与 confidence：

1. 判断该 criterion 对当前论文是否有合理评价对象。
2. 若有，保持 `applicable=true`，填写合法整数 score、非空 reason，并按需加入原文 quote。
3. 若没有，设置 `applicable=false`、`score=null`，并用 reason 说明为什么论文类型使该项没有评价对象。
4. 汇总本维度的优势、缺口与证据边界。
5. 若本维度至少一个 criterion applicable，填写 0–1 confidence；若全部不适用，confidence 保持 null。

不要为了让总分“看起来合理”反向调整 criterion。逐项依据原文评分，runtime 负责归一化、权重重分配和聚合。

## 分数校准

每项使用表单预填的 `max_score`。可按满分比例保持判断一致：

- 0：没有支持，或文本直接显示严重缺失。
- 约 25%：有弱信号，但不足以承担该项要求。
- 约 50%：基本满足，仍有明显缺口。
- 约 75%：大部分满足，缺口有限。
- 100%：证据清楚、完整，且与要求高度一致。

方法复杂不等于方法严谨，研究范围窄也不自动等于低质量。判断应落到 prompt 所问的可观察表现。

## Applicability 边界

`applicable=false` 表示该 criterion 对当前论文类型没有合理评价对象。下列情况仍应保持 `applicable=true` 并按实际缺失给低分：

- 作者没有报告相关信息；
- 原文证据很弱；
- agent 不确定；
- 输入转换质量差；
- 该项得分会拉低总分。

部分 criterion 不适用时，runtime 用该维度剩余 applicable maximum points 归一化，维度权重不变。整个维度都不适用时，score 与 confidence 为 null，effective weight 为 0，configured weight 按比例分配到其他 active dimensions，并写入 warning。所有维度均无 applicable criterion 时提交会被拒绝。

## Evidence Quotes

`evidence_quotes` 是字符串数组：

```json
{
  "applicable": true,
  "score": 4,
  "reason": "论文比较了三个基线，并报告了主要结果。",
  "evidence_quotes": [
    "We compare the proposed method against three baselines."
  ]
}
```

每条 quote 最长 500 字符。直接复制 normalized source 中短而有辨识度的片段；不要填写行号，runtime 会定位并生成公开产物的 `line_start` / `line_end`。

定位顺序：

1. 对 quote 和连续 1–5 行 source window 做 NFKC、case folding、空白与标点归一化后精确匹配。
2. 未精确命中且规范化 quote 至少 8 字符时，runtime 使用字符 n-gram 相似度寻找候选。
3. 相似度达到 0.45 时接受；并列候选按最早位置确定。
4. 低于阈值时拒绝，错误详情给出 criterion、quote 序号、最佳相似度和候选行范围。

证据数组可以为空。若判断依据是“全文未报告某项内容”，reason 应清楚说明可观察到的缺失，不要虚构一句否定性原文。

Runtime 只确认 quote 能否定位。quote 是否真的支持 score，仍由 agent 负责。

## Confidence 校准

每个 active dimension 填写 0–1 confidence。综合考虑：

- 当前输入是否覆盖主体、附录和图表文字；
- 相关信息是直接出现还是依赖推断；
- OCR、公式、表格或版面转换是否损坏关键证据；
- 多处文本是否相互一致；
- 当前论文类型是否容易从文本判断该维度。

建议区间：

- 0.90–1.00：直接证据完整，几乎无需推断。
- 0.75–0.89：证据较充分，仅有小范围缺口。
- 0.55–0.74：有可用证据，但关键细节缺失或需要明显推断。
- 0.30–0.54：只能做初步判断，输入或信息缺口较大。
- 0.00–0.29：维度有评价对象，但现有文本几乎不足以稳定判断。

全维度不适用时 confidence 必须为 null。不要填写 0；0 表示维度有评价对象但判断把握极低。

## 完整填写示意

下面仅展示表单中需要编辑的语义值。实际提交必须保留 prepare 生成的完整对象和全部 locked fields：

```json
{
  "paper_type_choices": [
    {"paper_type": "<locked>", "description": "<locked>", "selected": true}
  ],
  "paper_type_reason": "论文以实验比较检验主要主张。",
  "dimension_reviews": [
    {
      "dimension_key": "<locked>",
      "name": "<locked>",
      "configured_weight": "<locked>",
      "prompt": "<locked>",
      "confidence": 0.86,
      "summary": "直接证据较充分，但关键参数选择依据仍不完整。"
    }
  ],
  "criterion_reviews": [
    {
      "criterion_key": "<locked>",
      "dimension_key": "<locked>",
      "name": "<locked>",
      "max_score": "<locked>",
      "prompt": "<locked>",
      "applicable": true,
      "score": 4,
      "reason": "研究目标和约束在引言中直接说明。",
      "evidence_quotes": ["We study how to reduce inference cost while preserving accuracy."]
    }
  ]
}
```

## 常见失败与恢复

- `score_prerequisite_missing`：确认 normalized source 已写入；full mode 还需先完成 `persist_digest`。
- `scoring_context_failed`：检查 runtime rubric snapshot、review-form 目录和原始表单是否可读。
- `score_review_invalid`：逐条读取 `error.details[*].reason`：
  - `stale_form`：重新 prepare，使用新 `scoring_review_draft_path`；不要把旧答案覆盖到新 locked fields。
  - `locked_field_changed`：从 `scoring_review_form_path` 恢复 locked 字段，只保留允许编辑的语义答案。
  - `invalid_selection`：只保留一个 paper-type `selected=true`。
  - `incomplete_answer`：补齐指出的 score、reason、summary、confidence 或 applicability 约束。
  - `evidence_not_found`：根据候选行范围从 normalized source 复制更准确、辨识度更高的短 quote。
- `score_render_failed`：不要手改 `literature_score.json`；检查 DB 评分状态、runtime template 和 render schema 后重跑评分或 finalization。
- whole-dimension N/A warning：确认所有 criterion 的确没有合理评价对象；若只是未报告，应恢复 `applicable=true` 并给低分。

## 完成检查

提交成功后确认：

- `literature_score_path` 是绝对路径，文件名为 `literature_score.json`；
- 文件包含 `overall_score`、`confidence`、`confidence_adjusted_score`；
- 所有 canonical dimensions 与 criteria 均保留；
- inapplicable criterion 的公开 status 为 `not_applicable` 且 score 为 null；
- configured/effective weights、证据行号与 aggregate values 来自 runtime；
- score-only stdout 中其他公开产物路径为空字符串；
- result JSON mirror 与最终 stdout 内容一致。
