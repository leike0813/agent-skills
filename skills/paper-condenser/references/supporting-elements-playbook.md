# Supporting Elements Playbook

本文件说明图、表、citation、bibliography 在 DB runtime 中的横切处理方式。

## Stage 1

- `persist_intake_and_inventory` 负责 deterministic extraction。
- inventory 真源在 `supporting_elements_inventory`。
- 只读视图渲染到 `06-supporting-elements-inventory.md`。

## Stage 2

- `persist_raw_scope_segments` 切分时，`figure` / `table` / `display_block` 必须独立成段。
- raw supporting elements 必须保留 `scope_role=main|aux`，以便后续判断它们来自主转写范围还是支撑范围。
- supporting elements 不能被 paragraph 吞并。
- `persist_semantic_source_units` 可将 figure / table / citation / bibliography 线索吸收到 semantic unit 中。

## Stage 5

- `persist_section_rewrite_plan` 必须显式记录某个目标 section 绑定了哪些图、表、citation 或 bibliography 线索。
- 不得只在整体方案里口头提及 supporting elements。

## Stage 6

- section 审阅工件必须展示本节使用到的 supporting elements 溯源。
- `render_final_output_bundle` 必须遵循已批准的 supporting-elements 方案。
- 最终稿实际引用到的图片必须复制到用户输出目录的 `images/` 中，并改写最终 LaTeX 的图像路径。

## 禁止事项

- 不得把 inventory 留在聊天上下文，不写 DB。
- 不得在 Stage 6 静默丢弃已批准保留的 supporting elements。
- 不得让最终稿继续直接引用原稿图片路径。
