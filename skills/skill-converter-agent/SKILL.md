---
name: skill-converter-agent
description: 目录优先的 Skill 转换代理，将普通 skill 改造为 Skill-Runner 可执行 skill 包。
---

# 目标

本 Skill 的目标是将符合 Open Agent Skills 规范的普通 Skill 包转换为适合采用 Skill-Runner 自动执行的 AutoSkill 包。

## 输入

- `{{ parameter.source_skill_path }}`：源 skill 根目录路径。
- `{{ input.source_skill_package }}`：源 skill zip 包。

**注意**: 两个输入为“二选一”的关系。用户应在 prompt 中显式声明输入的类型。如果用户提供了单一输入源，但没有显示声明，Agent 可以通过读取输入源来判定用户输入是“skill根目录”还是“skill zip包”；如果用户同时提供了两个输入源，Agent 应该立即终止本次执行并抛出错误。

推荐用户采用 JSON payload 形式提供输入以避免歧义。

## 总流程

1. **解析来源**
   - 当输入源为 skill 根目录路径时：
     - 默认为**交互式执行模式**，允许在需要决策时向用户提问。
     - 直接使用 `{{ parameter.source_skill_path }}` 作为目标目录。
   - 当输入源为 skill zip 包时：
     - 默认为**自动执行模式**，不允许向用户提问，所有需要决策的部分应由 Agent 自行判断。
     - 运行脚本将 zip 解包到固定工作目录（例如 `{{ run_dir }}/work/source_skill`）：
       ```bash
       python3 {{ skill_dir }}/scripts/zip_directory_wrapper.py \
         --mode unpack \
         --zip-path "{{ input.source_skill_package }}" \
         --dest-dir "{{ run_dir }}/work/source_skill"
       ```
     - 从脚本 JSON 输出中获取 `skill_dir` 作为后续目录改造目标。

2. **文档读取**
   - （必选）读取 `{{ skill_dir }}/references/autoskill_package_guide.md`（AutoSkill包构建指南）
   - （必选）读取 `{{ skill_dir }}/references/file_protocol.md`（AutoSkill包文件协议）
   - （可选）读取 `{{ skill_dir }}/references/skill-runner_api_reference.md`（Skill-Runner API文档）

3. **结构检查**
   - 确认目录存在且至少包含 `SKILL.md`。
   - 若已有 `assets/`，读取现有 schema/runner；若无，准备新增。
   - 若目录结构明显不完整且无法补救，进入 `not_convertible`。

4. **任务类型判断（必须输出判断依据）**
   - 将源 skill 主任务归类到以下之一：
     - `直接返回结果型`：主要输出文本/JSON，不依赖文件产出。
     - `产出文件型`：核心价值是生成一个或多个文件。
     - `修改文件型`：核心价值是对输入文件做变更并输出结果文件。
   - 输出不少于 3 条依据，例如：
     - 指令中的动词模式（“生成/写入/修改/提取/汇总”）
     - 输入依赖（是否显式依赖上传文件）
     - 输出声明（是否已有 artifact 约定）

5. **可转换性判定（三分类）**
   - 只能输出以下之一：
     - `not_convertible`
     - `convertible_with_constraints`
     - `ready_for_auto`
   - 判定标准：
     - `not_convertible`：
       - 关键步骤必须依赖实时人工决策，且无法通过参数/规则固化；
       - 输出无法稳定结构化，无法定义可验证 schema；
       - 无法定义可复现的执行边界和失败条件。
     - `convertible_with_constraints`：
       - 可转换，但需增加明确约束（例如固定输入格式、限定输出字段、收敛中间分支）。
     - `ready_for_auto`：
       - 输入输出边界清晰，可稳定自动化执行并可验证。
   - 若 `not_convertible`：立即终止，只返回失败原因。

6. **约束决策策略**
   - 当 `classification=convertible_with_constraints`：
     - 如果处于交互式执行模式，则先向用户确认约束后再改造。
     - 如果处于自动执行模式，则由 Agent 自行选择保守且可验证的约束，直接执行。

7. **目录内改造（核心执行）**
   - 在目标目录中直接执行：
     - patch `SKILL.md`（保留领域语义，加入自动执行约束）
     - 生成/更新 `assets/input.schema.json`
     - 生成/更新 `assets/parameter.schema.json`
     - 生成/更新 `assets/output.schema.json`
     - 生成/更新 `assets/runner.json`
   - 复制参考文档到目标目录：
     - `references/file_protocol.md`
   - 确保目标 `SKILL.md` 明确提到：
     - “如需 schema/runner 细节，请参考 `references/file_protocol.md`”

8. **Patch 提示词策略（执行时必须遵循）**
   - 对 `SKILL.md` 的补丁重点：
     - 明确输入、参数、输出、失败路径；
     - 消除“请用户在执行中临时决策”的模糊指令，改为可参数化行为；
     - 明确最终输出 JSON 的稳定结构。
     - **不要在 `SKILL.md` 中注入 `Skill-Runner` 及 `AutoSkill` 协议的相关信息，这些信息与 Agent Skill 本体无关。**
   - 对 schema 的补丁重点：
     - 只保留必要字段；
     - artifact 使用 `x-type=artifact`、`x-role`、`x-filename` 明确约束；
     - `required` 与实际可执行路径一致，禁止“永远无法产出”的必填项。
     - **绝对禁止将 `result.json` 标记为 artifact。**

9. **简短示例（用于约束输出风格）**
   - 示例 A：直接返回结果型
     - 在 `output.schema.json` 定义 `summary`（string）与 `status`（enum）。
   - 示例 B：产出文件型
     - 在 `output.schema.json` 定义 `report_path` 为 artifact，并在 runner artifacts 声明 `report.md`。
   - 示例 C：修改文件型
     - 在 `input.schema.json` 定义输入文件；
     - 在 `output.schema.json` 定义 `patched_file_path` artifact 与变更摘要字段。

10. **最终验证门（必须执行）**
   - 目录改造完成后，必须执行：
     ```bash
     python3 {{ skill_dir }}/scripts/validate_converted_skill.py \
       --skill-path "<converted_skill_directory>" \
       --source-type directory \
       --require-version true
     ```
   - 失败则整体失败，并返回校验原因。

11. **生成转换报告**
   - 生成转换报告，写入 `converted_skill_directory` (Skill 包目录)中的 `references/conversion_report.md`。在 `{{ run_dir }}/artifacts/` 目录中抄写一份副本。

12. **zip 收敛（仅自动执行模式）**
   - 当输入源为 skill zip 包（处于自动执行模式）时，执行打包：
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
  - `conversion_report_path`: 转换报告路径，即`{{ run_dir }}/artifacts/` 目录中的转换报告副本。
  - `converted_skill_package_path`: 可选，仅在执行zip打包时提供

## 参考规则

若 schema 或 runner 生成细节存在不确定性，必须参考：
- `references/file_protocol.md`
