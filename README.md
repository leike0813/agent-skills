# agent-skills

This repo aggregates skills as git submodules.

## Available Skills

| Skill-ID | 说明 |
|----------|------|
| autoskill-converter | Transform an ordinary skill that conforms to the Open Agent Skills specification into an AutoSkill package with input/output/execution contracts. Use this skill when you need to convert an ordinary Skill into an executable business package for Skill-Runner or Zotero-Agents, or to normalize the input/output of other skills. |
| greeting-generator | Holiday Greeting Generator – Batch-generates personalized, appropriate, and elegantly written greetings based on user-provided holiday information, personal profiles, and recipient lists. Use this skill when users need to generate holiday greeting messages in bulk. |
| literature-digest | Generate a paper digest (Markdown), structured references (JSON), and citation analysis artifacts from a source literature(.md/.pdf/latex). Use this skill when you need to extract the core content of the literature, extract structured references, and perform citation context analysis. |
| literature-digest-lite | Generate a paper digest (Markdown) from a source literature(.md/.pdf/latex). Use this skill when you only need to extract the core content of the literature. |
| literature-explainer | An academic paper analysis and question-answering assistant that supports paper comprehension, Q&A, and study note generation through stateful workflows, evidence constraints, scripted memory, and verification. Use this skill when users want to ask questions about the content of a paper and obtain reliable answers. |
| literature-match | Match Markdown reference entries/参考文献 to Zotero Better BibTeX items (citekey as SSOT) and output match_result.json with candidates, itemKey, zotero_tags, and pdf_attachments. Use when you need to mapping citations to citeKeys in your local Zotero library. |
| mineru | Convert PDFs, scanned documents, images, Word (DOC/DOCX), PowerPoint (PPT/PPTX), Excel (XLS/XLSX), and web pages into clean Markdown, HTML, LaTeX, or DOCX. Use this skill when dealing with complex layouts, tables/formulas, and requiring high-fidelity, academic-grade document conversion. |
| paper-condenser | Interactive Academic Paper Condensation and Rewriting Skill. Use this skill when you need to distill a draft of a journal paper from a voluminous book, report, or dissertation. |
| review-master | Interactive Academic Paper Revision Assistant – Extracts and systematically organizes reviewer comments on a paper, devises a revision plan, interactively guides the user in creating a strategy card for each comment, and ultimately generates revision instructions for the original manuscript along with an execution flowchart. These are then handed over to an Agent for step-by-step, Human-in-the-Loop execution, resulting in a revised manuscript and a corresponding response letter. Use this skill when the user has received reviewer comments and needs to revise the paper. |
| skill-converter-agent | 目录优先的 Skill 转换代理，将普通 skill 改造为 Skill-Runner 可执行 skill 包。 |
| tag-regulator | Literature Tag Normalization Skill. Normalizes input tags input_tags into entries from a controlled vocabulary valid_tags, and can infer tags based on bibliographic metadata or literature digests, yielding tag suggestions suggest_tags that conform to the controlled vocabulary protocol. It can also operate in pure inference mode without providing valid_tags. Suitable for use with Zotero, but can also be applied to tag inference for any literature (as long as the original text can be converted to Markdown and directly supplied as digest_markdown). |
