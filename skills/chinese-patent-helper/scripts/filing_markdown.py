"""Read the structured Markdown form of an approved filing document."""

from io import BytesIO
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

from filing_ir import (
    DESIGN_BRIEF, DESIGN_VIEWS, EMU_PER_MM, FIGURE_LABEL, HEADINGS, INVALID_XML_CHAR, MAX_FIGURE_EMU,
    Break, Claim, DesignFiling, Equation, Figure, Filing, Fraction, Heading, InvalidDocument, Paragraph, Script,
    Subscript, Table, UnsupportedDocument, valid_math_text,
)


SECTIONS = {"权利要求书", "说明书", "说明书摘要", "说明书附图"}
SCRIPT_TAGS = {"<sub>": "sub", "<sup>": "sup"}


def inline_markup(node, location):
    parts = []
    script = None
    for child in node.children:
        if child.type == "text":
            parts.append(Script(child.content, script) if script else child.content)
        elif child.type in {"softbreak", "hardbreak"} and script is None:
            parts.append(" " if child.type == "softbreak" else Break())
        elif child.type == "html_inline" and script is None and child.content in SCRIPT_TAGS:
            script = SCRIPT_TAGS[child.content]
        elif child.type == "html_inline" and script is not None and child.content == f"</{script}>":
            script = None
        else:
            raise UnsupportedDocument(f"{location} 不支持 Markdown 行内对象 {child.type}")
    if script is not None:
        raise InvalidDocument(f"{location} 上下标标记未闭合")
    return tuple(parts)


def heading_text(node, location):
    parts = inline_markup(node.children[0], location)
    if not all(isinstance(part, str) for part in parts):
        raise UnsupportedDocument(f"{location} 标题需为纯文本")
    return "".join(parts).strip()


def read_math(source, location):
    source = "".join(source.split())
    cursor = 0

    def take(token):
        nonlocal cursor
        if not source.startswith(token, cursor):
            return False
        cursor += len(token)
        return True

    def group(depth):
        if not take("{"):
            raise UnsupportedDocument(f"{location} 分式或下标参数需要花括号")
        result = expression(depth + 1)
        if not take("}"):
            raise InvalidDocument(f"{location} 公式花括号未闭合")
        return result

    def expression(depth=0):
        nonlocal cursor
        if depth > 40:
            raise UnsupportedDocument(f"{location} 公式嵌套层级过深")
        parts = []
        while cursor < len(source) and source[cursor] != "}":
            if take(r"\frac"):
                atom = (Fraction(group(depth), group(depth)),)
            elif source[cursor] == "{":
                atom = group(depth)
            else:
                value = source[cursor]
                if not valid_math_text(value):
                    raise UnsupportedDocument(f"{location} 不支持的公式记法 {source[cursor:cursor + 12]!r}")
                atom = (value,)
                cursor += 1
            if take("_"):
                atom = (Subscript(atom, group(depth)),)
            for item in atom:
                if isinstance(item, str) and parts and isinstance(parts[-1], str):
                    parts[-1] += item
                else:
                    parts.append(item)
        if not parts:
            raise InvalidDocument(f"{location} 公式或公式参数为空")
        return tuple(parts)

    result = expression()
    if cursor != len(source):
        raise InvalidDocument(f"{location} 公式有未匹配的花括号")
    return result


def read_table(node, lines, location):
    rows = []
    width = len(node.children[0].children[0].children)
    for group in node.children:
        for row in group.children:
            row_loc = f"{location} 表格第 {len(rows) + 1} 行"
            raw = lines[row.map[0]].strip()
            cells = re.split(r"(?<!\\)\|", raw)
            if raw.startswith("|"):
                cells.pop(0)
            if raw.endswith("|") and not cells[-1]:
                cells.pop()
            if len(cells) != width:
                raise UnsupportedDocument(f"{row_loc} 列数与表头不一致")
            rows.append(tuple(
                (Paragraph(inline_markup(cell.children[0], row_loc), row_loc),) for cell in row.children
            ))
    return Table(tuple(rows), (1,) * width, location)


def read_figure(node, directory, location, *, design=False):
    parts = node.children[0].children if node.type == "paragraph" else ()
    if len(parts) != 1 or parts[0].type != "image":
        raise UnsupportedDocument(f"{location} 附图必须是单独成段的 Markdown 图片")
    image = parts[0]
    label = image.content.strip()
    if design and not label:
        raise InvalidDocument(f"{location} 图片替代文字需为完整视图名")
    if not design and not FIGURE_LABEL.fullmatch(label):
        raise UnsupportedDocument(f"{location} 图片替代文字需为图号，例如图1")
    spec = re.fullmatch(r"width-mm=([0-9]+(?:\.[0-9]+)?)", image.attrs.get("title", ""))
    if spec is None:
        raise UnsupportedDocument(f"{location} 图片标题需指定 width-mm")
    width = float(spec[1])
    if not 0 < width <= MAX_FIGURE_EMU / EMU_PER_MM:
        raise UnsupportedDocument(f"{location} 附图显示宽度超出支持范围")

    src = image.attrs["src"]
    try:
        uri = urlsplit(src)
    except ValueError as exc:
        raise InvalidDocument(f"{location} 附图路径无效 {src!r}") from exc
    local = unquote(uri.path)
    file = Path(local)
    if (
        uri.scheme or uri.netloc or uri.query or uri.fragment or not local
        or file.is_absolute() or file.drive or "\\" in local or "\0" in local
    ):
        raise UnsupportedDocument(f"{location} 附图应引用源稿目录下的相对路径 {src!r}")
    try:
        path = (directory / file).resolve()
        if not path.is_relative_to(directory):
            raise UnsupportedDocument(f"{location} 附图路径超出源稿目录 {src!r}")
        data = path.read_bytes()
    except (OSError, RuntimeError) as exc:
        raise InvalidDocument(f"{location} 无法读取附图 {src!r} ({exc})") from exc
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:
        raise UnsupportedDocument(f"{location} 附图读取需要 Pillow ({exc})") from exc
    try:
        with Image.open(BytesIO(data)) as raster:
            kind = raster.format
            if kind not in {"PNG", "JPEG"} or getattr(raster, "is_animated", False):
                raise UnsupportedDocument(f"{location} 附图需为单帧 PNG 或 JPEG")
            if design:
                raster.load()
            pixels_w, pixels_h = ImageOps.exif_transpose(raster).size
    except (OSError, Image.DecompressionBombError) as exc:
        raise InvalidDocument(f"{location} 附图无法解码 {src!r} ({exc})") from exc
    return Figure(label, data, kind, round(width * EMU_PER_MM), round(width * EMU_PER_MM * pixels_h / pixels_w), location)


def read_design(blocks, directory):
    title_location = f"产品名称 第 {blocks[0].map[0] + 1} 行"
    title = heading_text(blocks[0], title_location)
    books = {}
    section = None
    for node in blocks[1:]:
        location = f"{section or 'Markdown'} 第 {node.map[0] + 1} 行"
        if node.tag == "h2":
            section = heading_text(node, location)
            if section not in (DESIGN_VIEWS, DESIGN_BRIEF) or section in books:
                raise UnsupportedDocument(f"{location} 分册未知或重复 {section!r}")
            books[section] = []
        elif section == DESIGN_VIEWS:
            books[section].append(read_figure(node, directory, location, design=True))
        elif section == DESIGN_BRIEF and node.type == "paragraph":
            books[section].append(Paragraph(inline_markup(node.children[0], location), location))
        else:
            raise UnsupportedDocument(f"{location} 外观稿需在分册标题下编排独立图片或简要说明纯文本段落")
    return DesignFiling(title, tuple(books.get(DESIGN_BRIEF, ())), tuple(books.get(DESIGN_VIEWS, ())))


def read_markdown(path, patent_type="invention"):
    try:
        from markdown_it import MarkdownIt
        from markdown_it.tree import SyntaxTreeNode
    except ImportError as exc:
        raise UnsupportedDocument(f"Markdown 读取需要 markdown-it-py ({exc})") from exc

    source = path.read_text(encoding="utf-8-sig")
    bad = INVALID_XML_CHAR.search(source)
    if bad is not None:
        line = source.count("\n", 0, bad.start()) + 1
        raise InvalidDocument(f"Markdown 第 {line} 行含有 XML 无法表示的字符")
    lines = source.split("\n")
    env = {}
    parser = MarkdownIt("commonmark", {"html": True}).enable("table")
    blocks = SyntaxTreeNode(parser.parse(source, env)).children
    if env.get("references"):
        reference = next(iter(env["references"].values()))
        raise UnsupportedDocument(f"Markdown 第 {reference['map'][0] + 1} 行需使用直接引用的附图路径")
    if not blocks or blocks[0].tag != "h1":
        raise InvalidDocument("Markdown 首个内容块需为写明申请名称的一级标题")
    directory = path.parent.resolve()
    if patent_type == "design":
        return read_design(blocks, directory)
    title_loc = f"申请名称 第 {blocks[0].map[0] + 1} 行"
    title = Paragraph(inline_markup(blocks[0].children[0], title_loc), title_loc)
    books = {}
    section = None
    for node in blocks[1:]:
        location = f"{section or 'Markdown'} 第 {node.map[0] + 1} 行"
        if node.tag == "h2":
            section = heading_text(node, location)
            if section not in SECTIONS or section in books:
                raise UnsupportedDocument(f"{location} 分册未知或重复 {section!r}")
            books[section] = []
            continue
        if section is None:
            raise UnsupportedDocument(f"{location} 正文应位于分册标题下")
        blocks_in_book = books[section]
        if section == "权利要求书":
            if node.type != "ordered_list" or blocks_in_book:
                raise UnsupportedDocument(f"{location} 权利要求应使用一个有序列表")
            for claim in node.children:
                claim_loc = f"权利要求书 第 {claim.map[0] + 1} 行"
                if len(claim.children) != 1 or claim.children[0].type != "paragraph" or claim.markup != ".":
                    raise UnsupportedDocument(f"{claim_loc} 每项权利要求需用数字加点单独编号成段")
                if not re.fullmatch("[1-9][0-9]*", claim.info):
                    raise InvalidDocument(f"{claim_loc} 权项编号无效")
                parts = inline_markup(claim.children[0].children[0], claim_loc)
                blocks_in_book.append(Claim(int(claim.info), Paragraph(parts, claim_loc)))
        elif section == "说明书附图":
            blocks_in_book.append(read_figure(node, directory, location))
        elif node.type == "paragraph":
            parts = inline_markup(node.children[0], location)
            if section == "说明书" and all(isinstance(part, str) for part in parts) and "".join(parts).strip() in HEADINGS:
                raise UnsupportedDocument(f"{location} 说明书章节需使用三级标题")
            blocks_in_book.append(Paragraph(parts, location))
        elif section == "说明书" and node.tag == "h3":
            text = heading_text(node, location)
            if text not in HEADINGS:
                raise UnsupportedDocument(f"{location} 不支持的说明书章节 {text!r}")
            blocks_in_book.append(Heading(text, location))
        elif section == "说明书" and node.type == "table":
            blocks_in_book.append(read_table(node, lines, location))
        elif section == "说明书" and node.type == "fence" and node.info.strip() == "math":
            closer = lines[node.map[1] - 1].strip()
            if node.map[1] <= node.map[0] + 1 or not closer.startswith(node.markup) or set(closer) != {node.markup[0]}:
                raise InvalidDocument(f"{location} math 围栏未闭合")
            blocks_in_book.append(Paragraph((Equation(read_math(node.content, location), True),), location))
        else:
            raise UnsupportedDocument(f"{location} 不支持 Markdown 内容 {node.type}")
    return Filing(
        title,
        tuple(books.get("权利要求书", ())),
        tuple(books.get("说明书", ())),
        tuple(books.get("说明书摘要", ())),
        tuple(books.get("说明书附图", ())),
    )
