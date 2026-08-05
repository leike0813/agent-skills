---
name: paper-humanizer
description: Reduce AI-like patterns in prose while preserving meaning, facts, information density, voice, and structure. Use when drafting, reviewing, diagnosing, or humanizing plain text, Markdown, Quarto, or LaTeX through reference, review, or full mode.
license: MIT
compatibility: Reference mode is instruction-only; review and full modes require Python 3.11 or later.
metadata:
  baseline: humanizer-2.9.1
---

# Paper Humanizer

Remove recognizable AI-writing patterns without replacing the author's text with a generic idea of “good writing.” Style is evidence for revision, not proof of authorship.

## Non-negotiable invariants

1. Preserve every claim, fact, number, date, name, citation, qualification, negation, comparison, and causal relation.
2. Preserve information density. Do not remove a distinct idea for brevity or add explanation, evidence, examples, specificity, or interpretation.
3. Preserve genre, register, voice, section order, paragraph purpose, and document structure. A note remains a note; a methods section remains a methods section.
4. Preserve deliberate irregularity: defensible repetition, mixed sentence lengths, asides, uncertainty, field terminology, and author-specific punctuation.
5. Humanization is not fact-checking, copy-editing, argument repair, translation, or general quality improvement. Keep separately requested substantive edits outside the humanization scope.
6. Never claim to identify whether a person or model wrote the text. Describe localized prose as formulaic, uniform, inflated, or AI-like.
7. Prefer leaving a span unchanged when a safe edit is uncertain. In review or full mode, record the uncertainty.

For any rewrite, map the source's information units first. Every source unit must remain in the candidate, and every candidate unit must come from the source or a separately authorized edit. Compare both directions.

## Route the request

Choose by requested outcome, not by whether the user pasted text or named a file.

| Request | Mode | Read beyond this file | Result |
|---|---|---|---|
| Draft or revise prose inside another task; no diagnostic report requested | **Reference** | Nothing | Only the surrounding task's deliverable |
| Inspect, review, diagnose, or list AI-like features and suggestions | **Review** | `agents/review.md`, then `references/diagnostic-guidance.md` and `references/document-yaml-contract.md` | Exhaustive review; never edit the source |
| Humanize a text end to end or produce a final revised version | **Full** | `agents/review.md`, `agents/full.md`, then `references/diagnostic-guidance.md` and `references/document-yaml-contract.md` | Review, iterative plan gate, bounded rewrite, verification, and user acceptance |

Reference mode treats this Skill as a writing aid. Do not announce the mode, add an audit, calculate sentence statistics, or interrupt the surrounding task. It must work from this file alone.

Review mode may recommend changes but must not rewrite or modify the supplied source. Full mode treats the initial request as approval to review and negotiate a plan. It requires explicit approval of the current plan before editing and explicit acceptance of the verified candidate before completion.

## Reference-mode process

1. Read the input for meaning, genre, voice, and protected content.
2. Identify instances of the 39 patterns below. Require a real local mechanism or a cluster; a watched word alone is not evidence.
3. Draft or revise only as the surrounding task calls for. Use the smallest safe edit and keep the author's lexical level.
4. Ask privately: “What still sounds formulaic here?” and “Did this version add, remove, strengthen, or weaken any information?”
5. Repair any remaining supported pattern or semantic drift. Return only the requested deliverable.

If the prose already fits its purpose and has no supported pattern cluster, leave it alone.

When the user requests substantive editing alongside humanization, keep the scopes separate. Apply separately authorized substantive changes only as requested, and keep the humanization edits semantically neutral.

## Content patterns

### 1. Inflated significance and legacy claims

**Watch for:** stands as, serves as, is a testament to, plays a vital/significant/crucial role, underscores its importance, pivotal moment, enduring legacy, deeply rooted, profound.

AI prose enlarges ordinary facts into claims about importance. Replace the ceremony with the concrete fact already present. Keep a significance claim when evidence, attribution, or the author's argument supports it.

> Before: The registry stands as a testament to the region's enduring commitment to conservation.
>
> After: The registry records the region's conservation areas.

### 2. Notability claims through vague media coverage

**Watch for:** independent coverage, local/regional media outlets, leading publication, notable outlets, music and culture publications.

Do not replace cited reporting with a generic claim that coverage exists. Name the relevant source and what it reported when the text already supplies that information. Never invent attribution.

### 3. Superficial participial analysis

**Watch for:** highlighting, underscoring, emphasizing, reflecting, showcasing, ensuring, symbolizing, contributing to, fostering.

AI prose often adds a trailing `-ing` phrase that merely asserts importance or consequence. Remove it or turn a supported relation into a direct clause.

### 4. Promotional or brochure language

**Watch for:** boasts, vibrant, rich, profound, enhancing, fostering, showcasing, nestled, breathtaking, renowned, must-visit, stunning, groundbreaking, commitment to excellence.

Use neutral, specific description unless the source's genre and voice are intentionally promotional.

### 5. Vague attribution

**Watch for:** experts argue, observers note, industry reports, some critics, many believe, research suggests.

Name an existing source or state the claim directly at its supported strength. If the source is absent, do not manufacture one.

### 6. Formulaic challenge-and-future sections

**Watch for:** despite its success, faces several challenges, future outlook, nevertheless continues to thrive, challenges and legacy.

Replace generic balance with the concrete difficulty, response, or plan already in the source. Do not add optimism to close a section.

## Language and grammar patterns

### 7. Stock AI vocabulary

**Watch for clusters of:** additionally, align with, crucial, delve, emphasizing, enduring, enhance, fostering, garner, highlight, interplay, intricate, landscape, pivotal, showcase, tapestry, testament, underscore, valuable, vibrant.

One ordinary use is not a defect. When several appear as interchangeable prestige words, use the simplest accurate wording that matches the author's register.

### 8. Copula avoidance

AI prose replaces `is`, `are`, or `has` with `serves as`, `represents`, `marks`, `boasts`, or `features`. Restore the plain verb when the elaborate predicate adds no meaning.

### 9. Negative parallelisms and tailing negations

**Watch for:** not only ... but, it is not just ... it is, no guessing, no wasted motion.

State the positive claim directly or write the trailing fragment as a real clause. Preserve a deliberate contrast that genuinely distinguishes two propositions.

### 10. Rule-of-three overuse

Do not force ideas into triads for rhythm or a false sense of completeness. Keep real taxonomies, three actual findings, and lists whose membership matters.

### 11. Elegant variation

AI repetition penalties produce synonym cycling: `the protagonist`, `the central figure`, `the hero`. Repeat the stable term when it maintains reference clarity.

### 12. False ranges

**Watch for:** from X to Y when X and Y do not define a scale, progression, or meaningful span.

List the actual topics or state their relationship.

### 13. Passive voice and subjectless fragments

Restore the actor when the source identifies one and active voice improves clarity. Keep functionally motivated passive voice in academic methods, results, or places where the actor is unknown or irrelevant.

## Style patterns

### 14. Em-dash and en-dash overuse

Repeated dashes used as all-purpose clause separators are an AI-like rhythm cue. Replace only unsupported or clustered uses with a period, comma, colon, parentheses, or a recast sentence. Preserve ranges, conventional typography, and an author's demonstrated punctuation habits. A dash alone proves nothing.

### 15. Mechanical boldface

Remove emphasis that decorates routine terms or makes every list label look important. Preserve boldface with a real semantic or document-structure role.

### 16. Inline-header vertical lists

AI prose often turns a short sequence into bullets beginning with bold labels and colons. Use prose when the list has no navigational or taxonomic value; retain lists that users need to scan or reference.

### 17. Title case in headings

Match the document's language and heading convention. Do not mechanically convert title case when the style guide requires it.

### 18. Decorative emojis

Remove emojis used as generic heading or bullet ornaments unless they belong to the author's voice, interface convention, or requested genre.

### 19. Mechanical quotation-mark normalization

Curly quotation marks are not an AI signal by themselves. Keep the document's established typography or required style; normalize only inconsistent or clearly generated formatting.

## Communication patterns

### 20. Chatbot correspondence artifacts

**Watch for:** I hope this helps, Of course!, Certainly!, You're absolutely right!, Would you like, Want me to, Should I continue, let me know, here is a.

Remove assistant-to-user conversation that has been pasted into the target content. Preserve direct address when the genre itself is correspondence or instruction.

### 21. Knowledge-cutoff disclaimers and speculative gap-filling

**Watch for:** up to my last update, while details are limited, based on available information, maintains a low profile, likely grew up, it is believed that.

State only what the source supports. Say that information is unavailable when that fact matters; otherwise omit the filler. Never replace a gap with a plausible biography or fact.

### 22. Sycophantic or servile tone

Remove reflexive praise such as “Great question” or “You're absolutely right” when it is not part of the content. Respond to the substance at the appropriate interpersonal register.

## Filler and hedging patterns

### 23. Filler phrases

Prefer `to` over `in order to`, `because` over `due to the fact that`, `now` over `at this point in time`, and `can` over `has the ability to` when the shorter form preserves tone and emphasis.

### 24. Excessive hedging

Compress stacked qualifiers such as `could potentially possibly be argued`. Preserve each hedge that encodes real uncertainty, scope, causal caution, or disciplinary convention.

### 25. Generic positive conclusions

End on the last concrete claim or supported plan. Remove vague send-offs about a bright future, continued journeys, or steps in the right direction.

### 26. Hyphenated word-pair overuse

Check compounds such as `data-driven`, `high-quality`, and `cross-functional` in context. Keep conventional attributive hyphens and terminology; do not apply one hyphenation pattern indiscriminately in predicate position.

### 27. Persuasive-authority tropes

**Watch for:** the real question, at its core, in reality, what really matters, fundamentally, the deeper issue, the heart of the matter.

State the actual claim without pretending to reveal a hidden truth.

### 28. Signposting and announcements

**Watch for:** let's dive in, let's explore, let's break this down, here's what you need to know, now let's look at, without further ado.

Do the promised work directly. Keep signposting that genuinely helps readers navigate a long or technical argument.

### 29. Fragmented headers

Remove a one-line warm-up that only restates the heading before the real paragraph. Keep a short orienting sentence when it defines scope or supplies needed context.

### 30. Diff-anchored writing

Outside changelogs, release notes, and migration guides, describe the current system instead of narrating what was added, changed, or replaced.

### 31. Manufactured punchlines and staccato drama

Several clipped declarations in a row can make ordinary claims sound staged. Reconnect them when they share one proposition. Preserve an occasional short sentence used deliberately.

### 32. Aphorism formulas

**Watch for:** X is the Y of Z, X becomes a trap, not a tool but a mirror, the language of, the currency of, the architecture of.

Replace a generic metaphor with the concrete relationship it gestures at. Preserve original imagery that carries real argumentative or literary work.

### 33. Conversational rhetorical openers

**Watch for standalone hooks:** Honestly?, Look, Here's the thing, The thing is, Let's be honest, Real talk.

Remove fake-candid pauses before routine claims. Preserve natural conversational markers when they belong to the author's established voice.

## Additional evidence-backed patterns

These extend the Humanizer backbone where the bundled research and workflow references identify recurring gaps.

### 34. Semantic repetition and zero-information expansion

Map adjacent sentences to propositions. Flag restatement only when the later wording adds no evidence, boundary, stance, implication, or rhetorical function. Delete or merge the redundant span without discarding an information unit.

### 35. Nominalization and weak-verb chains

**Watch for:** conduct an analysis of, provide an explanation of, achieve an improvement in, the implementation of X leads to.

Restore a precise verb when a noun chain hides agency or pads a simple relation. Keep established technical nominalizations and wording whose abstraction level matters.

### 36. Connector density and paragraph templates

Look across a region for repeated generic transitions, identical topic-support-summary movement, and mechanically uniform openings or conclusions. Change only connectors or paragraph moves that do no logical work. Do not disturb a required academic or legal template.

### 37. Uniform sentence rhythm

Long runs of similar sentence lengths, openings, clause depth, or punctuation can sound generated. In reference mode, judge rhythm qualitatively; never chase a target score. Vary a run only when a natural split or merge preserves meaning and voice.

### 38. Generic background framing and cross-language academic templates

**Watch for clusters such as:** In recent years, with the rapid development of, against the backdrop of, 在当今……背景下, 随着……不断发展, 值得注意的是, 不难发现, 综上所述, 具有重要的理论意义和现实意义, 为……提供有益借鉴, translation-shaped abstract-noun chains, and repeated four-character endings.

When a generic background delays the actual topic without adding a bounded time, mechanism, source, or scope, begin with the concrete claim already present. Preserve field conventions, required thesis formulas, accurate translated terminology, and the author's established register.

### 39. Erased author stance and sterile neutrality

Academic prose can sound generated when it systematically turns an existing authorial judgment into anonymous encyclopedia language, distributes the same cautious neutrality across every claim, or permits first person only for procedural acts while hiding the paper's stated interpretation.

Restore or clarify stance only when the source or explicit user input already supports it. Match assertion strength to the evidence. If the needed judgment, disagreement, limitation, or reaction is absent, do not invent it; leave the wording unchanged in reference mode and mark the case unresolved in review or full mode.

## False positives to protect

Do not flag these in isolation:

- perfect grammar, consistent style, formal vocabulary, or dry prose;
- mixed formal and casual registers;
- one transition word, em dash, curly quote, short emphatic sentence, or rhetorical question;
- passive voice used for a clear genre function;
- clean formatting, correct tables, headings, or lists;
- quotations, titles, proper names, terminology, citations, source examples, and mandated wording;
- uncertainty that accurately reflects the evidence;
- neutral or impersonal prose whose genre calls for it, and the absence of first person by itself;
- repeated terms that preserve reference stability.

Look for clusters and mechanisms. Preserve human signals: specific odd details, mixed feelings, unresolved tension, dated references, defensible first-person choices, genuine asides and self-corrections, and naturally varied rhythm.

## Protected content

Unless the user explicitly places it in scope, do not alter verbatim quotations, bibliography data, identifiers, URLs, code, math, citation keys, labels, cross-references, raw markup, or examples whose wording is under discussion.

- In Markdown, protect frontmatter, fences, inline code, HTML, link destinations, image paths, and formatting markers. Visible link text can remain eligible prose.
- In Quarto, also protect shortcodes, citation and cross-reference identifiers, attributes, and fenced div markers. Prose inside a fenced div remains eligible when it can be separated from the markers.
- In LaTeX, protect commands, environment syntax, formulas, keys, and identifiers. Prose inside supported headings, captions, emphasis, and footnotes remains eligible while its wrapper stays fixed.
- If syntax and prose cannot be separated confidently, keep the span unchanged and report the ambiguity in review or full mode.
