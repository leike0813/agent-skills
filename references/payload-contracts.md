# Payload Contracts

本文件定义 skill 执行过程中所有脚本的输入/输出 JSON schema。在以下时机读取：
- 创建翻译批次前：确认 batch payload 格式。
- 运行 quality_gate 前：确认输入文件格式。
- 拼接前：确认翻译结果格式。
- 质量门禁阅读输出时：理解各 check 字段含义。

## Blockify Output Format

由 `blockify.py` 生成。读取路径 `.literature_translator_tmp/blocked.md`。

blockify.py 的输出是一个 Markdown 文件，其中每个 block 被 `<!-- BLOCK: ... -->` 和 `<!-- BLOCK_END: ... -->` 标记包围。此格式直接由 `sentencify.py` 消费，因此无独立的 JSON schema。

blockify.py 的 stdout 输出（机器可读）：

成功时：

```json
{
  "status": "ok",
  "blocks": 137,
  "by_type": {"heading": 12, "paragraph": 72, "equation": 15, "table": 2, "figure_caption": 8, "bib_item": 26, "abstract": 1, "list": 1},
  "heading_strategy": "proper_nesting",
  "output": "/abs/path/blocked.md"
}
```

失败时：

```json
{
  "error": "input file not found: /path/to/input"
}
```

## Sentence JSON Schema

## Sentence JSON Schema

由 `sentencify.py` 生成。读取路径 `.literature_translator_tmp/sentences.json`。

```json
{
  "blocks": {
    "b_001": {
      "type": "paragraph",
      "heading": "Introduction",
      "sentences": [
        "This is the first sentence.",
        "This is the second sentence."
      ]
    },
    "b_002": {
      "type": "equation",
      "heading": "",
      "sentences": [
        "E = mc^2"
      ]
    }
  },
  "stats": {
    "no_split": 1,
    "split": 1,
    "total_sentences": 3
  }
}
```

### 字段语义

| 字段 | 类型 | 说明 |
|------|------|------|
| `blocks` | object | key 为 block_id，value 为块数据 |
| `blocks[].type` | string | 块类型：paragraph/heading/equation/code/table/... |
| `blocks[].heading` | string | 所属章节标题（如有） |
| `blocks[].sentences` | string[] | 句级拆分后的句子数组 |
| `stats` | object | 拆分统计 |

## Batch Payload Schema

由 `partition_batches.py` 生成。读取路径 `.literature_translator_tmp/batches/batch_<N>.json`。

### 单批格式

```json
{
  "batch_id": "batch_0001",
  "block_ids": ["b_005", "b_006", "b_007"],
  "total_chars": 1432,
  "blocks": {
    "b_005": {
      "type": "paragraph",
      "sentence_count": 3,
      "sentences": [
        "First sentence of block b_005.",
        "Second sentence.",
        "Third sentence."
      ]
    },
    "b_006": {
      "type": "paragraph",
      "sentence_count": 2,
      "sentences": [
        "Another block's first sentence.",
        "Another block's second sentence."
      ]
    }
  }
}
```

### Total Manifest

```json
{
  "batch_count": 6,
  "target_size_chars": 1500,
  "batches": [
    {
      "batch_id": "batch_0001",
      "block_count": 3,
      "total_chars": 1432,
      "block_ids": ["b_005", "b_006", "b_007"],
      "payload_path": "/abs/path/batches/batch_0001.json"
    }
  ]
}
```

## Translation Result Schema

翻译执行后写入 `.literature_translator_tmp/translations/batch_<N>_translated.json`。

```json
{
  "batch_id": "batch_0001",
  "original_batch": "batch_0001",
  "blocks": {
    "b_005": {
      "type": "paragraph",
      "sentences": [
        "b_005 的第一句译文。",
        "b_005 的第二句译文。",
        "b_005 的第三句译文。"
      ]
    },
    "b_006": {
      "type": "paragraph",
      "sentences": [
        "b_006 的译文。"
      ]
    }
  }
}
```

### 字段约束

- `batch_id`: 必须与原始 batch 的 batch_id 一致。
- `blocks`: key 为 block_id，必须覆盖原始 batch 中所有 block_id。
- `blocks[].sentences`: 数组长度必须与原始 batch 中对应块的 sentences 长度一致（quality_gate 会检查）。
- `blocks[].type`: 应与原始 batch 中对应块的类型一致。

## Quality Gate Input/Output Schema

### 输入

通过命令行参数传入：
- `--original`: batch JSON 路径（Batch Payload Schema）
- `--translation`: 翻译结果 JSON 路径（Translation Result Schema）
- `--glossary`: 术语表 JSON 路径
- `--target-lang`: 目标语言代码

### 输出（stdout JSON）

```json
{
  "passed": true,
  "batch_id": "batch_0001",
  "checks": {
    "sentence_count": {
      "passed": true,
      "original_count": 5,
      "translated_count": 5
    },
    "lazy_translation": {
      "passed": true,
      "ratio": 0.85,
      "min_threshold": 0.3,
      "max_threshold": 3.0,
      "original_chars": 320,
      "translated_chars": 272
    },
    "term_consistency": {
      "passed": true,
      "violations": [],
      "violation_count": 0
    },
    "language": {
      "passed": true,
      "cjk_ratio": 0.85,
      "note": "expected CJK characters for zh-CN"
    }
  }
}
```

### Check 字段

| Check | 失败时的常见原因 | 处理方式 |
|-------|------------------|----------|
| `sentence_count` | 漏译句子、合并句子、拆句不当 | 检查翻译是否逐句对应 |
| `lazy_translation` | 译文过短（总结式翻译）或过长（添加无关内容） | 确认翻译是否完整，不要总结 |
| `term_consistency` | 术语翻译不一致、不应翻译的术语被错误翻译 | 按术语表修正 |
| `language` | 语言误判、输出保留源语言 | 检查目标语言是否用对 |

## Concatenate Output Schema

### 输出（stdout JSON）

成功：

```json
{
  "status": "ok",
  "applied_blocks": 35,
  "output_path": "/abs/path/assembled.md"
}
```

部分缺失（拼接仍执行，但汇报警告）：

```json
{
  "status": "incomplete",
  "applied_blocks": 33,
  "missing_blocks": ["b_012", "b_028"],
  "output_path": "/abs/path/assembled.md",
  "warning": "2 block(s) missing translation"
}
```

失败：

```json
{
  "error": "no translations loaded from directory",
  "path": "/abs/path/translations/"
}
```

### 字段语义

| 字段 | 类型 | 说明 |
|------|------|------|
| `status` | string | `ok` / `incomplete` |
| `applied_blocks` | int | 已拼接的块数 |
| `missing_blocks` | string[] | 缺少译文的 block_id 列表 |
| `output_path` | string | 拼接产物绝对路径 |
| `error` | string | 失败原因（仅失败时） |
| `warning` | string | 部分失败时的提示（仅 incomplete 时） |

## Sentence JSON Schema (v2)

由 `sentencify.py`（v2）生成。读取路径 `.literature_translator_tmp/sentences.json`。

```json
{
  "format": "v2",
  "blocks": {
    "b_001": {
      "type": "paragraph",
      "heading": "Introduction",
      "sentences": [
        [1, "This is the first sentence."],
        [2, "This is the second sentence."]
      ],
      "sentence_count": 2
    },
    "b_002": {
      "type": "equation",
      "heading": "",
      "sentences": [
        [1, "E = mc^2"]
      ],
      "sentence_count": 1
    }
  },
  "stats": {
    "no_split": 1,
    "split": 1,
    "total_sentences": 3
  }
}
```

### v2 变更说明

- 顶层新增 `"format": "v2"` 标记
- `sentences` 数组从 `string[]` 改为 `[index, text][]`（1-based 局部句号）
- `equation`、`code` 类型 block 的 sentences 也使用 `[index, text]` 格式
- 新增 `sentence_count` 字段

## Protected Sentences JSON Schema

由 `protect_placeholders.py` 生成。读取路径 `.literature_translator_tmp/protected/sentences.json`。

结构与 Sentence JSON Schema (v2) 相同，但句子文本中的行内元素已被替换为占位符。

```json
{
  "format": "v2",
  "blocks": {
    "b_001": {
      "type": "paragraph",
      "heading": "Experimental Setup",
      "sentences": [
        [1, "We evaluate <ENT_001> on <NUM_001> downstream tasks."],
        [2, "<MATH_001> is set to <NUM_002> for all experiments."]
      ],
      "sentence_count": 2
    }
  },
  "stats": {}
}
```

## Placeholder Map JSON Schema

由 `protect_placeholders.py` 生成。读取路径 `.literature_translator_tmp/protected/placeholder_map.json`。

```json
{
  "version": "1",
  "entries": {
    "<MATH_001>": "$\\\\alpha$",
    "<MATH_002>": "$\\\\mathbf{x}_i$",
    "<REF_001>": "[1, 2]",
    "<FIG_001>": "Fig. 3",
    "<NUM_001>": "0.01",
    "<NUM_002>": "95%",
    "<ENT_001>": "Transformer",
    "<ENT_002>": "ImageNet"
  },
  "metadata": {
    "total_placeholders": 8,
    "by_type": {
      "MATH": 2,
      "REF": 1,
      "FIG": 1,
      "NUM": 2,
      "ENT": 2
    },
    "source_file": "/path/to/sentences.json"
  }
}
```

### 字段语义

| 字段 | 类型 | 说明 |
|------|------|------|
| `version` | string | 映射表格式版本 |
| `entries` | object | 占位符 → 原始值的映射 |
| `entries.<PH>` | string | 占位符对应的原始文本 |
| `metadata.total_placeholders` | int | 占位符总数 |
| `metadata.by_type` | object | 按类型统计的占位符数量 |

## Translation Result Schema (v2)

翻译执行后写入 `.literature_translator_tmp/translations/batch_<N>_translated.json`。v2 格式使用 `[index, text]` 对。

```json
{
  "batch_id": "batch_0001",
  "original_batch": "batch_0001",
  "blocks": {
    "b_005": {
      "type": "paragraph",
      "sentences": [
        [1, "b_005 的第一句译文。"],
        [2, "b_005 的第二句译文。"],
        [3, "b_005 的第三句译文。"]
      ]
    },
    "b_006": {
      "type": "paragraph",
      "sentences": [
        [1, "b_006 的译文。"]
      ]
    }
  }
}
```

### 字段约束

- `batch_id`: 必须与原始 batch 的 batch_id 一致。
- `blocks`: key 为 block_id，必须覆盖原始 batch 中所有 block_id。
- `blocks[].sentences`: 数组长度必须与原始 batch 中对应块的 sentences 长度一致。每个元素为 `[index, text]` 对，index 为 1-based 局部句号。
- `blocks[].type`: 应与原始 batch 中对应块的类型一致。

## Quality Gate Output Schema (v2)

由 `quality_gate.py`（v2 增强版）输出。

```json
{
  "passed": false,
  "batch_id": "batch_0001",
  "checks": {
    "sentence_count": {
      "passed": true,
      "original_count": 5,
      "translated_count": 5
    },
    "lazy_translation": {
      "passed": true,
      "ratio": 0.85,
      "min_threshold": 0.3,
      "max_threshold": 3.0,
      "original_chars": 320,
      "translated_chars": 272
    },
    "term_consistency": {
      "passed": true,
      "violations": [],
      "violation_count": 0
    },
    "language": {
      "passed": true,
      "cjk_ratio": 0.85,
      "note": "v2 check (allowlist applied), expected CJK for zh-CN"
    },
    "placeholder_preservation": {
      "passed": true,
      "expected_count": 5,
      "found_count": 5,
      "missing": [],
      "unexpected": []
    },
    "numeric_preservation": {
      "passed": true,
      "expected_count": 3,
      "found_count": 3,
      "missing": []
    },
    "non_translation_phrases": {
      "passed": true,
      "violations": []
    },
    "length_check": {
      "passed": false,
      "is_weak": true,
      "warnings": [
        {
          "block_id": "b_005",
          "sentence_index": 1,
          "type": "paragraph",
          "ratio": 2.6,
          "threshold": {
            "min_ratio": 0.25,
            "max_ratio": 2.50
          }
        }
      ],
      "warning_count": 1
    }
  }
}
```

### v2 新增 Check 说明

| Check | 说明 | 是否强校验 |
|-------|------|-----------|
| `placeholder_preservation` | 输入端占位符全部出现在译文中 | 是 |
| `numeric_preservation` | 数字类占位符（NUM/REF/FIG/TBL/EQ_REF）全部保留 | 是 |
| `non_translation_phrases` | 检测解释性短语（"大意是""可以理解为"等） | 是 |
| `length_check` | 按 block 类型分阈值检查长度比 | 弱校验 |

## Alignment JSON Schema

由 `export_alignment.py` 生成。输出路径 `.literature_translator_tmp/alignment.json`。

```json
{
  "format": "v1",
  "doc_id": "D1",
  "source_language": "en",
  "target_language": "zh-CN",
  "metadata": {
    "glossary_version": "glossary_v1"
  },
  "blocks": [
    {
      "b": "b_023",
      "type": "paragraph",
      "heading": "3.2 Experimental Setup",
      "pairs": [
        {
          "i": 1,
          "src": "We evaluate the model on three downstream tasks.",
          "tgt": "我们在三个下游任务上评估该模型。",
          "status": "passed",
          "repair_count": 0
        },
        {
          "i": 2,
          "src": "However, the results should be interpreted with caution.",
          "tgt": "然而，应谨慎解读这些结果。",
          "status": "repaired",
          "repair_count": 1
        }
      ]
    }
  ]
}
```

### 字段语义

| 字段 | 类型 | 说明 |
|------|------|------|
| `doc_id` | string | 文档标识符 |
| `blocks[].pairs` | array | 句级双语对 |
| `pairs[].i` | int | 局部句号（1-based） |
| `pairs[].src` | string | 原文句子 |
| `pairs[].tgt` | string | 译文句子 |
| `pairs[].status` | string | `passed` / `repaired` / `risky` |
| `pairs[].repair_count` | int | 修复次数 |

## QA Report JSON Schema

由 `export_qa_report.py` 生成。输出路径 `.literature_translator_tmp/qa_report.json`。

```json
{
  "format": "v1",
  "doc_id": "D1",
  "summary": {
    "total_blocks": 128,
    "translated_blocks": 112,
    "passthrough_blocks": 16,
    "total_units": 642,
    "passed_units": 617,
    "repaired_units": 23,
    "risky_units": 2
  },
  "checks": {
    "sentence_count": "passed",
    "lazy_translation": "passed",
    "term_consistency": "passed",
    "language": "passed",
    "placeholder_preservation": "passed",
    "numeric_preservation": "passed",
    "non_translation_phrases": "passed",
    "length_check": "warning"
  },
  "repaired_items": [
    {
      "b": "b_023",
      "i": 2,
      "error_type": "modality",
      "repair_count": 1
    }
  ],
  "risky_items": [
    {
      "b": "b_041",
      "i": 3,
      "reason": "modality uncertainty remained difficult to verify",
      "source": "The method may improve robustness under certain conditions.",
      "best_translation": "该方法在某些条件下可能提高鲁棒性。"
    }
  ]
}
```

### 字段语义

| 字段 | 类型 | 说明 |
|------|------|------|
| `summary` | object | 总体统计 |
| `checks` | object | 各检查项的最终状态（passed/warning/failed/skipped） |
| `repaired_items` | array | 经局部修复后通过的句子记录 |
| `risky_items` | array | 持续失败、需人类注意的句子记录 |
