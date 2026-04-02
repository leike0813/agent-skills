# Step 01: Bootstrap And Source Normalization

本文件按 `SKILL.md` 的“参数词表（全项目统一）”定义；这里只补 stage 1 的额外约束，不重复定义字段基础含义。

本文件描述输入读取、目录确认、协议探测、标准化、输入类默认行为，以及 `stage_runtime.py` 中 `confirm_runtime_paths` / `bootstrap_runtime_db` / `normalize_source` 的当前运行时要求。

## 输入（prompt payload）

从 prompt 中读取：
- `source_path`：待解析的输入文件路径；可能是 Markdown、PDF，或无扩展名文件。
  也可以是单文件 `.tex` 或 LaTeX 工程目录。
- `language`：论文总结及参考文献分析使用的语言。

约束：
- `source_path` 是唯一内容来源。
- 不得依赖扩展名判断格式；必须通过 `stage_runtime.py normalize_source` 读取文件内容并做协议探测：
  - 文件头命中 `%PDF-` 时按 PDF 处理；
  - 目录且包含 `.tex` 时按 LaTeX 工程处理；
  - 文件内容命中 `\documentclass` / `\begin{document}` 或扩展名为 `.tex` 时按单文件 LaTeX 处理；
  - 否则尝试按 UTF‑8 文本处理；
  - 若两者都不成立，则按“默认行为协议”失败返回。
- 运行时真源始终是 `source_documents.normalized_source`。
- `source.md` 只是不改变语义的可选物化副产物，供审计、调试或人工查看；后续阶段不得把它当作过程真源。
- `language` 可以是任意包含“语言”语义的字符，推荐采用 `BCP 47` 语言标签，例如：
  - `zh-CN`
  - `en-US`
  - `fr-FR`
  - ...
  若用户显式指定目标语言则直接使用；否则由 agent 从 prompt 主要语言推断；仅在无法稳定判断时回退 `zh-CN`（只影响 `digest` 和 `citation_analysis` 语言）。

## 处理步骤（建议工作流）中的前置阶段

1) 在调用任何 skill 脚本之前，先在当前 shell 显式执行一次 `cwd()` / `pwd`，取得当前工作目录。
2) 不得先 `cd` 到 skill 包目录或其它目录，不得先调用 `gate_runtime.py`，也不得先调用 `bootstrap_runtime_db`。
3) 用上一步得到的目录立即调用 `scripts/stage_runtime.py confirm_runtime_paths`，固化本次 run 的：
   - `working_dir`
   - `tmp_dir`
   - `db_path`
   - `result_json_path`
   - `output_dir`
4) 再执行 `bootstrap_runtime_db`，写入输入文件与最终选定的语言。
5) 立刻执行 `scripts/stage_runtime.py persist_render_templates`，把本次 run 要使用的 digest / citation Markdown 模板写入 `<tmp_dir>/templates/`，并把：
   - `runtime_inputs.digest_template_path`
   - `runtime_inputs.citation_analysis_template_path`
   固化到 DB。
6) 读取 `source_path` 并调用 `scripts/stage_runtime.py normalize_source` 做协议探测，生成标准化 Markdown 并写入 `source_documents.normalized_source`：
   - Markdown / UTF‑8 文本：直接标准化后写库
   - PDF：优先尝试 `pymupdf4llm` 转 Markdown；失败则使用标准库兜底解析；两者都失败才返回错误
   - 单文件 `.tex`：原文直接复制到 `source.md` 的 ` ```tex ` fence 中
   - LaTeX 工程目录：自动检测主入口 `.tex`，展平 `\input` / `\include` 后整体包进 ` ```tex ` fence
   - 若发现 `.bib`：把 `.bib` 原文追加到 `source.md` 尾部的 ` ```bibtex ` fence，并注明该块直接复制自 `.bib`
   - 若调用方需要，才额外物化 `<tmp_dir>/source.md`
6) 对原始 `source_path` 计算 `input_hash`（sha256）。

在当前 SQLite runtime 中，这些动作对应：
- 先通过 `confirm_runtime_paths` 初始化或恢复 `<working_dir>/.literature_digest_tmp/literature_digest.db`
- 写入 `runtime_inputs.working_dir`
- 写入 `runtime_inputs.tmp_dir`
- 写入 `runtime_inputs.db_path`
- 写入 `runtime_inputs.result_json_path`
- 写入 `runtime_inputs.source_path`
- 写入 `runtime_inputs.language`
- 写入 `runtime_inputs.digest_template_path`
- 写入 `runtime_inputs.citation_analysis_template_path`
- 写入 `runtime_inputs.output_dir`
- 通过 `stage_runtime.py normalize_source` 生成标准化内容后写入 `source_documents.normalized_source`
- 登记 `generated_at` 与 `input_hash`

## 本阶段对后续阶段提供的契约

本阶段完成后，后续阶段只能依赖以下 DB 真源：

- `runtime_inputs.working_dir`
- `runtime_inputs.tmp_dir`
- `runtime_inputs.db_path`
- `runtime_inputs.result_json_path`
- `runtime_inputs.source_path`
- `runtime_inputs.language`
- `runtime_inputs.digest_template_path`
- `runtime_inputs.citation_analysis_template_path`
- `runtime_inputs.generated_at`
- `runtime_inputs.input_hash`
- `runtime_inputs.output_dir`
- `source_documents.normalized_source`

可选物化副产物：

- `source.md`
- `source_meta.json`

它们可用于审计与人工检查，但不构成后续阶段的过程真源。

硬约束：

- `confirm_runtime_paths` 是唯一允许确定 `working_dir`、`tmp_dir`、`db_path`、`result_json_path`、`output_dir` 的步骤
- `bootstrap_runtime_db` 是唯一允许确定 `source_path`、`language`、`generated_at`、`input_hash` 的步骤
- `persist_render_templates` 是唯一允许确定 `digest_template_path`、`citation_analysis_template_path` 的步骤
- `stage_1_normalize_source` 之后，后续主路径不得再通过 CLI / JSON 覆盖这些字段

## 默认行为协议（必须遵守）

- 读取 `source_path` 失败（不存在/无权限/编码异常）：
  - 输出 schema 兼容 JSON
  - `digest_path=""`
  - `references_path=""`
  - `citation_analysis_path=""`
  - `error` 填充 `{code,message}`
- 输入内容既非 PDF 签名、也不是可读取的 UTF‑8 文本：
  - 且也不是可识别的 LaTeX 工程目录 / `.tex` 文件：
  - 输出 schema 兼容 JSON
  - `digest_path=""`
  - `references_path=""`
  - `citation_analysis_path=""`
  - `error` 填充 `{code,message}`
- `language` 无法从 prompt 稳定推断时：回退 `zh-CN` 并写入 `warnings`

读取失败时的最小失败态 stdout JSON 示例：

```json
{
  "digest_path": "",
  "references_path": "",
  "citation_analysis_path": "",
  "provenance": {
    "generated_at": "",
    "input_hash": "",
    "model": ""
  },
  "warnings": [],
  "error": {
    "code": "normalize_source_failed",
    "message": "read source failed: [Errno 2] No such file or directory"
  }
}
```

## 脚本（可选但推荐）

本 skill 推荐使用 **skill 包内预置脚本** 承担确定性工作（审计信息生成、状态推进、输出格式验证、自我修复），以降低 LLM 负担并提高一致性。

临时产物目录约定：
- 新 run 固定使用 `confirm_runtime_paths` 已写入 DB 的 `tmp_dir`
- 在当前 DB-first runtime 中，中间 JSON/MD 不再作为过程真源；`source.md` 与 `source_meta.json` 仅是标准化输入的物化副产物

### `scripts/stage_runtime.py confirm_runtime_paths`

用途：
- 在任何其他 skill 脚本之前，固化本次 run 的目录集合
- 写入 `runtime_inputs.working_dir`
- 写入 `runtime_inputs.tmp_dir`
- 写入 `runtime_inputs.db_path`
- 写入 `runtime_inputs.result_json_path`
- 写入 `runtime_inputs.output_dir`
- 将工作流推进到 `stage_0_bootstrap -> bootstrap_runtime_db`

推荐命令：

```bash
pwd
python scripts/stage_runtime.py confirm_runtime_paths \
  --working-dir "<PWD_FROM_SHELL>" \
  --output-dir "/abs/path/artifacts"
```

规则：
- 必须先在 shell 里执行 `pwd`
- 不要先 `cd`
- 不要先运行 `gate_runtime.py`
- 不要先运行 `bootstrap_runtime_db`
- `--output-dir` 可选；若缺省，脚本直接把 `working_dir` 写入 `runtime_inputs.output_dir`

### `scripts/stage_runtime.py bootstrap_runtime_db`

用途：
- 写入 `runtime_inputs.source_path`、`runtime_inputs.language`
- 写入 `runtime_inputs.generated_at`、`runtime_inputs.input_hash`
- 将工作流推进到 `stage_1_normalize_source -> persist_render_templates`

推荐命令：

```bash
python scripts/stage_runtime.py bootstrap_runtime_db \
  --source-path "/abs/path/paper.md" \
  --language "<TARGET_LANGUAGE_FROM_PROMPT>"
```

规则：
- 本步必须在 `confirm_runtime_paths` 之后执行
- 本步不再决定任何目录
- 本步之前必须先确定最终 `language`：先用用户显式指定值，否则从 prompt 主要语言推断，仅在无法稳定判断时回退 `zh-CN`
- 后续 `render_and_validate --mode render` 只读取 DB 中已经固化的目录信息

### `scripts/stage_runtime.py persist_render_templates`

用途：
- 将本次 run 要使用的 digest/citation Markdown 模板写入 `<tmp_dir>/templates/`
- 写入 `runtime_inputs.digest_template_path`
- 写入 `runtime_inputs.citation_analysis_template_path`
- 将工作流推进到 `stage_1_normalize_source -> normalize_source`

推荐命令：

```bash
python scripts/stage_runtime.py persist_render_templates \
  --db-path "/abs/path/run-root/.literature_digest_tmp/literature_digest.db" \
  --payload-file "/tmp/render_templates.json"
```

规则：
- 本步必须在 `bootstrap_runtime_db` 之后执行
- `target_language` 必须与 bootstrap 已写入的 `language` 一致
- `en-*` / `zh-*` 目标语言直接复制仓库 source template
- 其它语言先翻译仓库 source template，再把最终模板字符串写入 payload
- `render_and_validate --mode render` 只读取 DB 中固化的运行时模板，不再直接读取仓库模板目录

### `scripts/stage_runtime.py normalize_source`

用途：
- 对 `source_path` 做内容探测（优先于扩展名）
- 将标准化结果写入 `source_documents.normalized_source`
- 可选产出 `<tmp_dir>/source.md`
- 可选产出 `<tmp_dir>/source_meta.json`
- 计算并持久化 `runtime_inputs.generated_at` 与 `runtime_inputs.input_hash`

规则：
- 只允许从 `runtime_inputs.source_path` 与 `runtime_inputs.language` 读取输入，不接受后续阶段的显式覆盖
- 输入若命中 PDF 签名 `%PDF-`，则按 PDF 处理
- 输入若是单文件 `.tex` 或包含 `.tex` 的目录，则按 LaTeX 处理
- 否则尝试按 UTF‑8 文本处理
- PDF 主路径优先使用 `pymupdf4llm`
- `pymupdf4llm` 不可用或失败时，使用标准库兜底解析，并写入 `warnings`
- LaTeX 主路径不做重型语义转写，只生成 fenced raw source，并在 metadata 中记录 `source_type`、`main_tex_path`、`included_tex_files`、`bib_files`
- 下游流程不得直接消费原始 `source_path`，而是只消费 DB 中的 `source_documents.normalized_source`

## 当前阶段动作提示

适用 gate 阶段：
- `stage_0_bootstrap`
- `stage_1_normalize_source`

常见动作：
- `confirm_runtime_paths`
- `bootstrap_runtime_db`
- `normalize_source`
- `repair_workflow_state`
- `repair_db_state`
