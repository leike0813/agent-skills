# Review Quality Checklist

## Purpose

导出报告前读取本文件，用于检查审稿意见是否有证据、可操作、分级合理，并且没有把参考指南误当论文证据。

## Before Export

确认以下条件：

- 已完成论文画像和审稿范围确认。
- 已完成 deep understanding，且没有把论文摘要当作唯一理解来源。
- Major findings 都有明确位置、论文证据、影响和修订方向。
- Low-confidence findings 已标记为 `candidate` 或转为 `open_question`。
- 所有参考指南内容都只作为审稿标准，不作为 `paper_evidence`。
- 不存在没有定位的泛泛批评，例如 “结构混乱”“创新不足” 但没有对应章节或证据。
- 没有直接修改论文原稿。

## Finding Quality Gate

每条 finding 应回答：

- 问题是什么？
- 在哪里出现？
- 论文材料中的证据是什么？
- 为什么影响论文质量或读者判断？
- 作者可以怎么修？
- 严重程度为什么是 major / minor / note？
- 置信度为什么是 high / medium / low？

如果不能回答其中任一项，不要写成 confirmed finding；改成 candidate 或 open question。

## Severity Calibration

Use `major` when:

- 问题影响研究问题、贡献有效性、方法可信度、证据链、结论强度或伦理/合规核心要求。
- 缺失会阻止读者判断论文主张是否成立。

Use `minor` when:

- 问题影响清晰度、局部论证、局部报告完整性或可复现细节，但不直接推翻核心主张。

Use `note` when:

- 问题是风格、表达、轻微格式、可选补充或审稿人提醒。

Do not inflate severity just because a guideline recommends best practice. Severity must be grounded in the manuscript's actual risk.

## Evidence Rules

Acceptable `paper_evidence`:

- 论文中的章节、段落、表格、图、公式、实验设置、结果描述。
- 论文参考文献条目的可见格式或缺失信息。
- 用户提供的补充材料内容。

Unacceptable `paper_evidence`:

- `reference_guide.py nav` 的候选 heading。
- 写作指南原文。
- 仅凭外部常识或模型记忆得出的断言。
- 未经联网或用户提供材料核验的 DOI、期刊、引用真实性判断。

## Near-Miss Cases

Near miss: 用户说“帮我总结这篇论文”。

- Do not trigger full paper review unless the user asks for critique, reviewer comments, acceptance recommendation, or problems.
- Offer summary directly or ask whether they want review-mode critique.

Near miss: 用户说“润色这篇论文”。

- Do not use this skill to edit the manuscript.
- You may use review findings to suggest revision directions, but not rewrite the original file.

Near miss: 用户只问“这个摘要怎么样”。

- Use a scoped review run or lightweight answer focused on the abstract.
- Do not claim full manuscript review coverage.

Near miss: 用户要求“核验参考文献真伪”。

- This skill can flag visible format problems.
- Full external verification requires explicit browsing/tool permission and should be treated as an added task, not baseline runtime behavior.

## Final Report Check

Before presenting the exported report:

- Read `status` and confirm `current_stage` is `S8_DONE`.
- Confirm `findings_exported` is non-zero, or clearly tell the user no findings were recorded.
- If open questions remain, keep them visible rather than silently resolving them.
- When rewriting the draft for the user, do not add new findings outside the structured memory.
