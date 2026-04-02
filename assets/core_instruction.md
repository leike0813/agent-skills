## 核心执行指令

1. 先读 `SKILL.md`，不要预读整个 `references/` 目录。
2. 在调用任何 skill 脚本之前，先在当前 shell 执行一次 `cwd()` / `pwd`，取得当前工作目录；不要先 `cd` 到别处。
3. 首个脚本动作必须是 `confirm_runtime_paths`，并把上一步得到的 cwd 作为 `--working-dir` 写入 DB。
4. 在 `bootstrap_runtime_db` 之前先确定目标语言：用户显式指定时直接使用；否则从 prompt 主要语言推断；仅在无法稳定判断时回退 `zh-CN`。
5. `bootstrap_runtime_db` 之后必须先执行 `persist_render_templates`，把本次 run 要使用的 digest / citation Markdown 模板写入 `<tmp_dir>/templates/`。
6. `confirm_runtime_paths` 之后，以及每次正式写库后，都必须重新运行 `scripts/gate_runtime.py`。
7. 只能执行 gate 返回的 `next_action`。
8. 同时遵守 gate 返回的 `instruction_refs`、`core_instruction` 与 `execution_note`。
9. 所有语义判断结果都必须先整理为结构化 payload，再通过 `scripts/stage_runtime.py <next_action>` 写入 SQLite。
10. 一旦某项决策已经在前序阶段写入 DB，后续阶段只能从 DB 读取，不能重新指定。
11. 不要直接写 SQLite 表来伪造阶段完成；阶段推进必须由对应脚本动作成功写库。
12. 最终公开产物只能由 `render_and_validate --mode render` 从 DB 与已固化的运行时模板渲染生成。
13. **最终 assistant 输出必须是一个 JSON 对象，并且必须满足 stdout schema。**

成功态 stdout JSON 示例：

```json
{
  "digest_path": "/abs/path/digest.md",
  "references_path": "/abs/path/references.json",
  "citation_analysis_path": "/abs/path/citation_analysis.json",
  "citation_analysis_report_path": "/abs/path/citation_analysis.md",
  "provenance": {
    "generated_at": "2026-03-31T09:00:00Z",
    "input_hash": "sha256:0123456789abcdef",
    "model": "gpt-5.4"
  },
  "warnings": [],
  "error": null
}
```
