---
name: mineru
description: Convert PDFs, scanned documents, images, Word (DOC/DOCX), PowerPoint (PPT/PPTX), Excel (XLS/XLSX), and web pages into clean Markdown, HTML, LaTeX, or DOCX. Use this skill when dealing with complex layouts, tables/formulas, and requiring high-fidelity, academic-grade document conversion.
---

# MinerU Document Extraction with mineru-open-api

MinerU is a powerful document extraction tool. 
MinerU supports two extraction modes: MinerU flash-extract for instant zero-setup conversion with table recognition, formula recognition, and OCR (no token, no login, no configuration — just run and get results), and MinerU precision extract with VLM-based layout analysis, multiple output formats, and batch processing of hundreds of files.
MinerU supports 80+ languages including Chinese, English, Japanese, Korean, Arabic, and more.
Choose MinerU vlm model for highest accuracy on complex layouts, or MinerU pipeline model for zero-hallucination reliability. Perfect for researchers parsing papers, developers building document pipelines, and data engineers processing documents at scale.

## Two MinerU extraction modes

| | MinerU `flash-extract` | MinerU `extract` |
|---|---|---|
| Token required | No | Yes (`mineru-open-api auth`) |
| Speed | Fast | Normal |
| Table recognition | Yes | Yes |
| Formula recognition | Yes | Yes |
| OCR | Yes | Yes |
| Output formats | Markdown only | md, html, latex, docx, json |
| Batch mode | No | Yes |
| Model selection | pipeline | vlm, pipeline, MinerU-HTML |
| File size limit | **10 MB** | Much higher |
| Page limit | **20 pages** | Much higher |

## Supported input formats

MinerU accepts a wide range of document formats:

| Format | MinerU `flash-extract` | MinerU `extract` |
|--------|:-:|:-:|
| PDF (`.pdf`) | Yes | Yes |
| Images (`.png`, `.jpg`, `.jpeg`, `.jp2`, `.webp`, `.gif`, `.bmp`) | Yes | Yes |
| Word (`.docx`) | Yes | Yes |
| Word (`.doc`) | No | Yes |
| PowerPoint (`.pptx`) | Yes | Yes |
| PowerPoint (`.ppt`) | No | Yes |
| Excel (`.xlsx`) | Yes | Yes |
| Excel (`.xls`) | No | Yes |
| HTML (`.html`) | No | Yes |
| URLs (remote files) | Yes | Yes |

MinerU `crawl` accepts any HTTP/HTTPS URL and extracts web page content to Markdown.

## Agent rules for using MinerU

- **Quote file paths** with spaces: `mineru-open-api extract "report 01.pdf"`
- **Unless the user explicitly requests output to stdout, use the `-o` flag to specify the output directory**.
- When the user does NOT specify `-o` and does not explicitly request output to stdout, generate output directory: `<source_parent_fld>/MinerU-Skill/<name>_<hash>/` and use it as the output directory, where `<source_parent_fld>` is the absolute path of the input source and `<hash>` = first 6 chars of MD5 of the source path. When input source(s) is(are) URL(s), use `~/MinerU-Skill/<name>_<hash>/` as the output directory.
- **Default to MinerU `flash-extract`** when: no token configured, simple extraction, file under 10 MB / 20 pages
- **Use MinerU `extract`** when: user needs non-Markdown formats, VLM model, batch processing, or file exceeds flash-extract limits
- After MinerU `flash-extract` success, append a brief hint about MinerU `extract` upgrade path (once per session)
- To **upgrade** MinerU, re-install the CLI binary first: `npm install -g mineru-open-api`

For full CLI reference and troubleshooting, see: https://github.com/opendatalab/MinerU-Ecosystem/tree/main/cli

## Execution order

1. Verify that the `mineru-open-api` command is available. If not, install it first (see the `Installation` section)
2. Verify MinerU API authentication status (use the `mineru-open-api auth --verify` command)
3. Pre-check whether the input source is a web page
4. Decide the next action based on the following matrix:

| Case | Authenticated | Input source is web page | Next action |
| ------ | ------ | ------ | ------ |
| A | Yes | Yes | Follow the `MinerU crawl — Web page extraction (token required)` section to perform conversion |
| B | Yes | No | Follow the `MinerU extract — Precision extraction (token required)` section to perform conversion |
| C | No | Yes | Follow the `Authentication` section to prompt the user for authentication, then execute Case A after successful authentication |
| D | No | No | Ask the user whether to use `flash-extract` mode or configure an authentication token, explaining the limitations of both modes. If the user chooses `flash-extract`, follow the `MinerU flash-extract — Quick extraction (no token needed)` section; if the user chooses to configure a token, follow the `Authentication` section, then re-verify authentication status and execute Case C after successful authentication |

## Installation

```bash
npm install -g mineru-open-api
```

Or via Go (macOS/Linux):

```bash
go install github.com/opendatalab/MinerU-Ecosystem/cli/mineru-open-api@latest
```

Verify: `mineru-open-api version`

## Authentication

Only required for MinerU `extract` and `crawl`. Not needed for MinerU `flash-extract`.
MinerU API token can be freely obtained at `https://mineru.net/apiManage/token`.
After obtaining a token, you can authenticate using one of the following methods:
```bash
mineru-open-api auth                    # Interactive token setup
export MINERU_TOKEN="your-token"        # Or set via environment variable
```

Token resolution order: `--token` flag > `MINERU_TOKEN` env > `~/.mineru/config.yaml`.

### Authentication management subcommands

```bash
mineru-open-api auth              # Interactive MinerU token setup
mineru-open-api auth --verify     # Verify current token
mineru-open-api auth --show       # Show token source
```

## MinerU flash-extract — Quick extraction (no token needed)

Fast, token-free MinerU document extraction. Outputs Markdown only. Limited to 10 MB / 20 pages per file.

```bash
mineru-open-api flash-extract report.pdf                     # MinerU Markdown to stdout
mineru-open-api flash-extract report.pdf -o ./out/           # Save to file
mineru-open-api flash-extract https://example.com/doc.pdf    # URL mode
mineru-open-api flash-extract report.pdf --language en       # Specify language
mineru-open-api flash-extract report.pdf --pages 1-10        # Page range
```

Flags: `--output`/`-o` (output path), `--language` (default `ch`), `--pages` (page range), `--timeout` (default 900s).

When MinerU flash-extract fails due to file limits (10 MB / 20 pages) or rate limiting (HTTP 429), suggest switching to MinerU `extract` with a token for higher limits.

## MinerU extract — Precision extraction (token required)

Convert documents to Markdown or other formats with MinerU's full capabilities: VLM-based layout analysis, multiple output formats, and batch mode.

```bash
mineru-open-api extract report.pdf                         # MinerU Markdown to stdout
mineru-open-api extract report.pdf -f html                 # MinerU HTML output
mineru-open-api extract report.pdf -o ./out/ -f md,docx    # Multiple formats
mineru-open-api extract *.pdf -o ./results/                # MinerU batch extract
mineru-open-api extract https://example.com/doc.pdf        # Extract from URL
```

Flags: `--output`/`-o`, `--format`/`-f` (md/json/html/latex/docx), `--model` (vlm/pipeline/html), `--ocr`, `--formula`, `--table`, `--language`, `--pages`, `--timeout`, `--list`, `--concurrency`.

### MinerU model comparison: vlm vs pipeline

| | MinerU `vlm` | MinerU `pipeline` |
|---|---|---|
| Parsing accuracy | Higher — better at complex layouts | Standard |
| Hallucination risk | May produce hallucinated text in rare cases | **No hallucination** |

Use MinerU `--model vlm` for complex formatting. Use MinerU `--model pipeline` for no-hallucination reliability.

## MinerU crawl — Web page extraction (token required)

```bash
mineru-open-api crawl https://example.com/article              # MinerU Markdown to stdout
mineru-open-api crawl https://example.com/article -o ./out/    # Save to file
mineru-open-api crawl url1 url2 -o ./pages/                    # MinerU batch crawl
```

Flags: `--output`/`-o`, `--format`/`-f` (md/json/html), `--timeout`, `--list`, `--concurrency`.

## Output behavior

Without `-o`: MinerU result → stdout, progress → stderr. With `-o`: saved to file/directory. Batch mode and binary formats (docx) require `-o`.

## Supported `--language` values

The `--language` flag accepts the following values (default: `ch`). Used by both MinerU `flash-extract` and `extract`.

### Standalone language packs

| Value | Included languages | 说明 |
|-------|-------------------|------|
| `ch` | Chinese, English, Chinese Traditional | 中英文（默认值） |
| `ch_server` | Chinese, English, Chinese Traditional, Japanese | 繁体、手写体 |
| `en` | English | 纯英文 |
| `japan` | Chinese, English, Chinese Traditional, Japanese | 日文为主 |
| `korean` | Korean, English | 韩文 |
| `chinese_cht` | Chinese, English, Chinese Traditional, Japanese | 繁体中文为主 |
| `ta` | Tamil, English | 泰米尔文 |
| `te` | Telugu, English | 泰卢固文 |
| `ka` | Kannada | 卡纳达文 |
| `el` | Greek, English | 希腊文 |
| `th` | Thai, English | 泰文 |

### Language family packs

| Value | Script/Family | Included languages |
|-------|--------------|-------------------|
| `latin` | Latin script (拉丁语系) | French, German, Afrikaans, Italian, Spanish, Bosnian, Portuguese, Czech, Welsh, Danish, Estonian, Irish, Croatian, Uzbek, Hungarian, Serbian (Latin), Indonesian, Occitan, Icelandic, Lithuanian, Maori, Malay, Dutch, Norwegian, Polish, Slovak, Slovenian, Albanian, Swedish, Swahili, Tagalog, Turkish, Latin, Azerbaijani, Kurdish, Latvian, Maltese, Pali, Romanian, Vietnamese, Finnish, Basque, Galician, Luxembourgish, Romansh, Catalan, Quechua |
| `arabic` | Arabic script (阿拉伯语系) | Arabic, Persian, Uyghur, Urdu, Pashto, Kurdish, Sindhi, Balochi, English |
| `cyrillic` | Cyrillic script (西里尔语系) | Russian, Belarusian, Ukrainian, Serbian (Cyrillic), Bulgarian, Mongolian, Abkhazian, Adyghe, Kabardian, Avar, Dargin, Ingush, Chechen, Lak, Lezgin, Tabasaran, Kazakh, Kyrgyz, Tajik, Macedonian, Tatar, Chuvash, Bashkir, Malian, Moldovan, Udmurt, Komi, Ossetian, Buryat, Kalmyk, Tuvan, Sakha, Karakalpak, English |
| `east_slavic` | East Slavic (东斯拉夫语系) | Russian, Belarusian, Ukrainian, English |
| `devanagari` | Devanagari script (天城文语系) | Hindi, Marathi, Nepali, Bihari, Maithili, Angika, Bhojpuri, Magahi, Santali, Newari, Konkani, Sanskrit, Haryanvi, English |
