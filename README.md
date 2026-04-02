# agent-skills

This repo aggregates skills as git submodules.

## Available Skills

| Skill-ID | 说明 |
|----------|------|
| greeting-generator | 节日祝福生成器 - 根据用户提供的节日信息、个人画像及发送对象列表，批量生成得体且富有文采的个性化祝福语。 |
| literature-digest | Generate a paper digest (Markdown), structured references (JSON), and citation analysis artifacts from a source file using a SQLite-gated runtime. |
| literature-explainer | 学术论文分析与问题回答助手，以状态化流程、证据约束、脚本化记忆与验证支撑论文理解、问答和学习笔记生成。 |
| literature-match | Match Markdown reference entries/参考文献 to Zotero Better BibTeX items (citekey as SSOT) and output match_result.json with candidates, itemKey, zotero_tags, and pdf_attachments. |
| paper-condenser | 交互式学术论文凝缩转写 Skill。Use when Codex needs to guide a user through staged manuscript understanding, target-setting, style analysis, condensation planning, and final journal-paper drafting with a SQLite single source of truth and strict gate-driven progression. |
| review-master | 适用于 LaTeX 论文原稿与 Markdown/txt 审稿意见文件的交互式审稿回复流程。运行时以 SQLite 为唯一真源，gate-and-render 核心脚本负责状态门禁、视图重渲染和下一步指令输出。 |
| skill-converter-agent | 目录优先的 Skill 转换代理，将普通 skill 改造为 Skill-Runner 可执行 skill 包。 |
| tag-regulator | 在严格受控词表（`valid_tags`）约束下，利用 LLM 语义理解对 Zotero tags 进行规范化，并可基于元数据推断（infer_tag）标签。 |
