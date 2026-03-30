# Stage 0 Playbook

Stage 0 对应 `stage_0_bootstrap`。

## 唯一正式写库动作

- `bootstrap_runtime_db`

## 进入方式

- 新任务必须先运行：
  - `gate_runtime.py --source-path <SOURCE_PATH>`
- 当 gate 返回 `next_action=bootstrap_runtime_db` 时，再执行 bootstrap。

## 动作职责

- 初始化 workspace 根目录
- 创建 `paper-condenser.db`
- 初始化 SQLite schema
- 写入 `runtime_workspace` 与 `manuscript_source`
- 首次渲染只读视图

## 何时必须从 `--source-path` 启动

- 当前 workspace 尚不存在
- 当前 `.paper-condenser-tmp/<document-slug>/paper-condenser.db` 尚不存在
- 需要为新的原稿路径启动新的 runtime

## 完成标准

- gate 不再停留在 `stage_0_bootstrap`
- `paper-condenser.db` 已建立
- 后续阶段可从 `--artifact-root` 恢复执行
