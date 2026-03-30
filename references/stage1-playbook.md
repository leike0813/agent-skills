# Stage 1 Playbook

Stage 1 对应 `stage_1_intake_and_inventory`。

## 唯一正式写库动作

- `persist_intake_and_inventory`

## 动作职责

- 读取原稿文件
- 统计 `source_stats`
- 生成 `content_preview`
- 提取 figure / table / citation / bibliography inventory
- 重渲染：
  - `02-manuscript-profile.md`
  - `06-supporting-elements-inventory.md`

## 写入真源

- `manuscript_intake`
- `supporting_elements_inventory`

## 完成标准

- `manuscript_intake.intake_status=complete`
- `supporting_elements_inventory.status=complete`

## 禁止事项

- 不得直接编辑只读视图
- 不得在 deterministic intake 完成前进入语义分析
