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
2. 先读取 `runtime_digest`
3. 再读取 `next_action`
4. 若该动作需要 payload，先读取 `next_action_payload_example`
5. 只执行这个 action
6. action 写库后重新跑 gate
7. 继续直到 `stage_6_completed`

## Gate 返回中的 runtime digest

- gate 现在会返回顶层字段 `runtime_digest`
- 它是独立静态维护的运行摘要，不是从 `SKILL.md` 动态解析得到的
- 其用途是帮助 Agent 在长上下文或跨轮恢复时重新想起 skill 的核心纪律
- 它不是新的真源，也不替代 `SKILL.md`

## Gate 返回中的 payload 示例

- gate 现在会和 `next_action` 一起返回 `next_action_payload_example`
- 若该动作不需要 payload，该字段为 `null`
- 若该动作需要 payload，该字段提供一个最小可执行 JSON 样例
- 默认先看这个样例；只有当样例仍不足以执行时，再读对应 `stageN-playbook.md`
- 对 `confirm_language_context`，样例中的 `working_language` 应优先视为“基于当前对话推断的默认值”，必要时再由用户修正

## 何时必须重新跑 gate

- bootstrap 之后
- intake / inventory 之后
- language context 确认之后
- runtime template translation 之后
- manuscript analysis 之后
- raw main/aux scope segmentation 之后
- semantic source units 持久化之后
- style profile 之后
- target settings 最终确认之后
- condensation plan 之后
- section rewrite plan 之后
- 每次 section draft 写入之后
- 每次 section 审批之后
- output target 持久化之后
- translated sections 持久化之后
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
- `stage_4_condensation_plan` → `references/stage4-playbook.md`
- `stage_5_final_drafting` → `references/stage5-playbook.md`
