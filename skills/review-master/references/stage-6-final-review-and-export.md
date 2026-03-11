# 阶段六：成文、总复核与双阶段导出

本阶段使用的正式术语、脚本称呼、action id 和最终导出产物命名以：

- `review-master/references/workflow-glossary.md`

为准。

## 目标

- 在最终导出前，先把 Stage 5 草案提升为与用户原文风格一致的最终文案
- 让最终 Response Letter 回到原始 `thread_id` 索引层，并采用固定 4 列 point-to-point 表格结构
- 先导出 marked manuscript，再在最终确认后导出 clean manuscript 与双格式 Response Letter
- 让最终 manuscript 与 response letter 严格使用文本语言

## 子步骤

### Stage 6A：风格画像与去 AI 化约束

必须先建立两份全局风格画像：

- `manuscript` 风格画像
- `response_letter` 风格画像

并把规则写入：

- `style_profiles`
- `style_profile_rules`

风格画像必须覆盖：

- 常用句式与节奏
- 术语偏好
- 论证强度
- 是否偏保守 / 直接 / 谨慎
- 去 AI 化约束

去 AI 化约束至少要避免：

- 模板腔
- 重复句式
- 无来源夸张语
- 解释性废话
- 与原稿明显不一致的“AI 风格自信语气”

### Stage 6B：最终稿落地文案版本生成

文案版本生成以 `strategy_card_actions` 的 `target_location` 为粒度，而不是按 `comment_id` 或 `thread_id` 粒度。

这里的 3 个版本，指的是 **最终稿里真正要落下去的 manuscript 文案版本**，不是：

- 策略版本
- response-side 方案版本

每个 action 的每个 target location 都必须生成：

- 3 个 manuscript-side 最终落地文案版本

这些版本写入：

- `action_copy_variants`

用户最终选择写入：

- `selected_action_copy_variants`

若某个 action 的某个 target location 还没有达到“3 个 manuscript 最终文案版本”，不得进入 row-level 组装。

这里的最终文案必须使用文本语言，而不是继续保留 Stage 5 的工作语言草案。

### Stage 6C：thread-level response row 组装

最终 Response Letter 仍然以原始 `thread_id` 为正式索引。

必须先写入：

- `response_thread_resolution_links`
- `response_thread_rows`

组装规则：

- 先按 reviewer / editor 分组
- 再按 `thread_order` 输出
- 一条原始 reviewer thread 对应一条最终表格行
- 每行聚合其下关联的 canonical atomic item、Stage 5 已确认的策略/草案，以及用户已选中的 manuscript 最终文案

最终 response row 的 `response_explanation` 必须来自单一路径：

- Stage 5 已确认的策略与草案
- Stage 6 已选中的 manuscript 文案
- `thread_id` 级别聚合

不得把 Response Letter 理解成“从 response-side 文案版本中挑一个”。

不得直接按 `comment_id` 顺序输出最终 Response Letter。

`response_thread_rows` 与最终导出的 Markdown / LaTeX response letter 固定使用文本语言。

### Stage 6D：marked manuscript 导出

marked manuscript 使用 `changes` 宏包作为唯一标准路径。

这一阶段必须先在数据库中写入：

- `export_patch_sets`
- `export_patches`

然后调用：

- `review-master/scripts/export_manuscript_variants.py`

导出：

- 完整的 `marked_manuscript`

但这一步完成后：

- 仍不能视为最终导出完成
- 必须先让用户复核 marked manuscript 与 thread-level response rows

额外要求：

- marked manuscript 必须是完整稿件，不得只导出局部摘录
- 所有修改位置都必须通过 `changes` 宏包标记
- 导出脚本只允许对导出副本执行显式锚点补丁，不得直接改动输入原稿

### Stage 6E：clean manuscript + 双格式 Response Letter 导出

只有在最终确认通过后，才允许导出：

- clean manuscript
- Markdown Response Letter
- LaTeX Response Letter

这些文件必须写入独立输出目录，不得覆盖原始输入文件。

clean manuscript 必须和用户确认后的 marked manuscript 在内容上完全一致，只去掉 `changes` 标记。

## 固定表格结构

Markdown 与 LaTeX 版本统一采用 4 列固定表头：

1. 原始意见
2. 修改位置/范围
3. 关键修改片段
4. 回复说明

固定约束：

- 一条原始 reviewer thread 对应一条表格行
- 必须引用修改过的原文段落
- 若引用过长，可以只保留关键片段，但必须说明修改范围
- LaTeX 版中“关键修改片段”和“回复说明”必须有格式区分
- `response_latex` 必须是完整可编译文件，至少包含：
  - `\documentclass`
  - 必要 `\usepackage`
  - `\begin{document}` / `\end{document}`
  - 最小 front matter
  - point-to-point 表格正文

## 必读视图

Stage 6 至少要同时查看：

- `08-style-profile.md`
- `09-action-copy-variants.md`
- `10-response-letter-outline.md`
- `11-export-patch-plan.md`
- `12-response-letter-table-preview.md`
- `13-response-letter-table-preview.tex`
- `16-final-assembly-checklist.md`

## 何时必须向用户提问

- 风格画像仍不稳定，无法判断最终文风
- 用户尚未从 3 个版本中选定最终文案
- thread-level 聚合仍有歧义
- 最终回复语气或立场仍需用户授权
- 输出目录或最终文件形态仍不明确

## 禁止动作

- 未完成风格画像就进入版本生成
- 未为每个 target location 生成 3 个 manuscript 最终文案版本就让用户选版本
- 未完成用户版本选择就组装最终 row
- 未建立 export patch 真源就导出 manuscript
- marked manuscript 只导出局部摘录
- 未完成 marked manuscript 复核就导出 clean manuscript
- 未经最终确认就导出 final 文件
- 用 `comment_id` 顺序替代 `thread_id` 顺序输出最终 Response Letter
- 覆盖原始输入稿件或原始评论文件

## 完成标准

- `style_profiles` 与 `style_profile_rules` 已完成
- 每个 strategy action 的每个 target location 都有 3 个 manuscript 最终文案版本
- 用户已完成版本选择
- 每个 `thread_id` 都有一条 `response_thread_rows`
- marked manuscript 已导出并经过用户复核
- final checklist 的导出门禁全部闭环
- clean manuscript、Markdown Response Letter、LaTeX Response Letter 已导出到独立输出目录
- `response_latex` 已是带 front matter 的独立可编译文件
