---
name: skill-converter-agent
description: 目录优先的 Skill 转换代理，将普通 skill 改造为 Skill-Runner 可执行 skill 包。
---

# 目标

本 Skill 的目标是将符合 Open Agent Skills 规范的普通 Skill 包转换为适合 Skill-Runner 执行的 AutoSkill 包，且转换流程需同时考虑 `auto` 与 `interactive` 两种执行模式。

## 输入

- `{{ parameter.source_skill_path }}`：源 skill 根目录路径（目录模式）。
- `{{ input.source_skill_package }}`：源 skill zip 包（zip 模式）。

约束：
- 两个输入二选一；若同时提供，立即失败。
- 若仅提供其一但未声明类型，可由 Agent 读取输入后自动判定。

## 总流程

1. **解析来源与执行上下文**
   - 目录模式：
     - 目标目录为 `{{ parameter.source_skill_path }}`。
   - zip 模式：
     - 先解包到固定目录（例如 `{{ run_dir }}/work/source_skill`）：
       ```bash
       python3 {{ skill_dir }}/scripts/zip_directory_wrapper.py \
         --mode unpack \
         --zip-path "{{ input.source_skill_package }}" \
         --dest-dir "{{ run_dir }}/work/source_skill"
       ```
     - 使用解包结果中的 `skill_dir` 作为后续目录改造目标。

2. **读取规范依据**
   - 必读：
     - `{{ skill_dir }}/references/autoskill_package_guide.md`
     - `{{ skill_dir }}/references/file_protocol.md`
   - 可选：
     - `{{ skill_dir }}/references/skill-runner_api_reference.md`

3. **基础结构检查**
   - 目录必须存在并至少包含 `SKILL.md`。
   - 若已有 `assets/`，读取现有 schema/runner；否则准备新增。
   - 若结构不完整且无法补救，进入 `not_convertible`。

4. **任务类型判断（必须给依据）**
   - 归类为：
     - `直接返回结果型`
     - `产出文件型`
     - `修改文件型`
   - 输出不少于 3 条判断依据（动词模式、输入依赖、输出声明等）。

5. **双模式独立适配性评估（先评估，再分类）**
   - 独立输出以下结论与依据：
     - `auto_suitability`: `suitable | unsuitable`
     - `interactive_suitability`: `suitable | unsuitable`
   - 每个结论至少给出 3 条依据，覆盖：
     - 输入输出边界稳定性
     - 关键步骤是否依赖实时用户决策
     - 是否能定义可验证失败路径

6. **分类决策（固定三类）**
   - 仅允许输出：
     - `not_convertible`
     - `convertible_with_constraints`
     - `ready_for_auto`
   - 映射规则：
     - auto=unsuitable 且 interactive=unsuitable -> `not_convertible`
     - auto=unsuitable 且 interactive=suitable -> `convertible_with_constraints`
     - auto=suitable 且 interactive=unsuitable -> `ready_for_auto`
     - auto=suitable 且 interactive=suitable -> `ready_for_auto`
   - 若 `not_convertible`：立即终止，仅返回失败原因。

7. **execution_modes 生成规则**
   - auto=suitable 且 interactive=suitable -> `["auto","interactive"]`
   - auto=suitable 且 interactive=unsuitable -> `["auto"]`
   - auto=unsuitable 且 interactive=suitable -> `["interactive"]`

8. **约束决策策略**
   - 当 `classification=convertible_with_constraints`：
     - 目录模式：先向用户确认约束再改造。
     - zip 模式：Agent 直接选择保守、可验证约束并继续。

9. **目录内改造（核心执行）**
   - 在目标目录直接执行：
     - patch `SKILL.md`（保留领域语义，补齐可执行约束）
     - 生成/更新 `assets/input.schema.json`
     - 生成/更新 `assets/parameter.schema.json`
     - 生成/更新 `assets/output.schema.json`
     - 生成/更新 `assets/runner.json`（写入第 7 步确定的 `execution_modes`）
   - 复制参考文档到目标目录：
     - `references/file_protocol.md`
   - 确保目标 `SKILL.md` 明确提到：
     - “如需 schema/runner 细节，请参考 `references/file_protocol.md`”

10. **Patch 策略约束**
    - `SKILL.md` 补丁重点：
      - 明确输入、参数、输出、失败路径。
      - 将临时决策改为参数化或固定规则。
      - 给出稳定 JSON 输出结构。
    - schema 补丁重点：
      - 仅保留必要字段。
      - artifact 字段使用 `x-type`、`x-role`、`x-filename`。
      - `required` 必须与真实可产出路径一致。
      - 禁止将 `result.json` 标记为 artifact。

11. **最终验证门（必须执行）**
    - 目录改造完成后执行：
      ```bash
      python3 {{ skill_dir }}/scripts/validate_converted_skill.py \
        --skill-path "<converted_skill_directory>" \
        --source-type directory \
        --require-version true
      ```
    - 校验失败则整体失败。

12. **转换报告**
    - 生成转换报告：
      - `converted_skill_directory/references/conversion_report.md`
      - `{{ run_dir }}/artifacts/conversion_report.md`（副本）

13. **zip 产物收敛（目录/zip 模式都执行）**
    - 成功时都需产出 install-ready zip：
      ```bash
      python3 {{ skill_dir }}/scripts/zip_directory_wrapper.py \
        --mode pack \
        --source-dir "<converted_skill_directory>" \
        --zip-path "{{ run_dir }}/artifacts/converted_skill.zip"
      ```

## 输出契约

- `not_convertible`：
  - `status`: `"failed"`
  - `classification`: `"not_convertible"`
  - `failure_reason`: 字符串

- 成功（`convertible_with_constraints` / `ready_for_auto`）：
  - `status`: `"succeeded"`
  - `classification`: 成功分类之一
  - `converted_skill_directory_path`: 转换后目录路径
  - `conversion_report_path`: `{{ run_dir }}/artifacts/conversion_report.md`
  - `converted_skill_package_path`: `{{ run_dir }}/artifacts/converted_skill.zip`

## 参考规则

若 schema 或 runner 生成细节存在不确定性，必须参考：
- `references/file_protocol.md`
