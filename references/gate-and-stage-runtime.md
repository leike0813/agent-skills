# Gate And Stage Runtime

本文件只负责补充 CLI、gate discipline 与恢复执行细则。默认先读 `SKILL.md`；只有当你需要核对正式入口、恢复方式、gate 错误处理或阶段文档映射时，再按需读取本文件。

## 正式入口

### Gate

首次进入：

```bash
python -u paper-condenser/scripts/gate_runtime.py --source-path <SOURCE_PATH>
```

恢复执行：

```bash
python -u paper-condenser/scripts/gate_runtime.py --artifact-root <ARTIFACT_ROOT>
```

### Stage Write

bootstrap：

```bash
python -u paper-condenser/scripts/stage_runtime.py bootstrap_runtime_db --source-path <SOURCE_PATH>
```

其他动作：

```bash
python -u paper-condenser/scripts/stage_runtime.py <ACTION> --artifact-root <ARTIFACT_ROOT> [--payload-file <PAYLOAD_JSON>]
```

## 执行纪律

1. 先跑 gate
2. 读取 `next_action`
3. 只执行这个 action
4. action 写库后重新跑 gate
5. 继续直到 `stage_7_completed`

## 何时必须重新跑 gate

- bootstrap 之后
- intake / inventory 之后
- manuscript analysis 之后
- raw main/aux scope segmentation 之后
- semantic source units 持久化之后
- target settings 之后
- style profile 之后
- condensation plan 之后
- section rewrite plan 之后
- 每次 section draft 写入之后
- 每次 section 审批之后
- output target 持久化之后
- final bundle 渲染之后
- 中断恢复时

## 错误处理

- 若 stage write 不是 gate 返回的 `next_action`，脚本必须失败。
- 若前序门禁不满足，脚本必须失败。
- 若 `pending_confirmations` 未清空，gate 必须继续停留在当前阶段。
- 若当前 active section 字数校验未通过，gate 必须把 `next_action` 锁回 `persist_section_draft`。
- 若当前 active section 未批准，gate 必须把 `next_action` 锁回 `approve_section_draft`。

## 阶段文档映射

- `stage_0_bootstrap` → `references/stage0-playbook.md`
- `stage_1_intake_and_inventory` → `references/stage1-playbook.md`
- `stage_2_manuscript_analysis` → `references/stage2-playbook.md`
- `stage_3_target_settings` → `references/stage3-playbook.md`
- `stage_4_style_profile` → `references/stage4-playbook.md`
- `stage_5_condensation_plan` → `references/stage5-playbook.md`
- `stage_6_final_drafting` → `references/stage6-playbook.md`
