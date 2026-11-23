"""Read a supported CNIPA template DOCX into the filing document model."""

from io import BytesIO
from itertools import chain
import posixpath
import re
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

from filing_ir import (
    DESIGN_BRIEF, DESIGN_TITLE, DESIGN_VIEWS, FIGURE_LABEL, Break, Claim, DesignFiling,
    Equation, Figure, Filing, Fraction, HEADINGS, Heading,
    InvalidDocument, Paragraph, Script, Subscript, Table, UnsupportedDocument, valid_math_text,
)


REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "r": REL,
    "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
}
SECTIONS = {"权利要求书", "说明书", "说明书摘要", "说明书附图", "摘要附图"}
CLAIM_NUMBER = re.compile(r"^\s*([1-9][0-9]*)[.．、]\s*")


def qname(name):
    prefix, local = name.split(":")
    return f"{{{NS[prefix]}}}{local}"


def plain(parts):
    if all(isinstance(part, str) for part in parts):
        return "".join(parts)
    return None


def read_math(node):
    tag = node.tag.removeprefix(f"{{{NS['m']}}}")
    if tag in {"oMathPara", "oMath", "num", "den", "e", "sub"}:
        children = list(node)
        if tag == "oMathPara":
            children = [child for child in children if child.tag != qname("m:oMathParaPr")]
            if [child.tag for child in children] != [qname("m:oMath")]:
                raise UnsupportedDocument("公式段落必须包含一个原生公式")
        result = tuple(part for child in children for part in read_math(child))
        if any(not isinstance(part, str) or part.strip() for part in result):
            return result
    elif tag == "r":
        children = [child for child in node if child.tag != qname("w:rPr")]
        if children and all(child.tag == qname("m:t") for child in children):
            value = "".join(child.text or "" for child in children)
            if valid_math_text(value):
                return (value,)
            raise UnsupportedDocument(f"公式包含超出支持范围的符号 {value!r}")
    elif tag == "f":
        children = list(node)
        if children and children[0].tag == qname("m:fPr"):
            properties = children.pop(0)
            kind = properties.find("m:type", NS)
            if kind is not None and kind.get(qname("m:val")) != "bar":
                raise UnsupportedDocument("公式分式不是水平分数线样式")
            if any(child.tag not in {qname("m:type"), qname("m:ctrlPr")} for child in properties):
                raise UnsupportedDocument("公式分式含有未支持的属性")
        if [child.tag for child in children] == [qname("m:num"), qname("m:den")]:
            return (Fraction(*map(read_math, children)),)
    elif tag == "sSub":
        children = list(node)
        if children and children[0].tag == qname("m:sSubPr"):
            properties = children.pop(0)
            if any(child.tag != qname("m:ctrlPr") for child in properties):
                raise UnsupportedDocument("公式下标含有未支持的属性")
        if [child.tag for child in children] == [qname("m:e"), qname("m:sub")]:
            return (Subscript(*map(read_math, children)),)
    raise UnsupportedDocument(f"公式结构超出支持范围 {tag}")


class DocxReader:
    def __init__(self, archive):
        self.archive = archive
        self.location = "DOCX"
        self.relationships = {}
        self.character_styles = None
        relationships = self.xml("word/_rels/document.xml.rels")
        if relationships.tag != f"{{{PKG}}}Relationships":
            raise InvalidDocument("无法识别 DOCX 主文档的关系文件")
        for relationship in relationships:
            key = relationship.get("Id")
            if not key or key in self.relationships:
                raise InvalidDocument("DOCX 主文档的关系 ID 缺失或重复")
            self.relationships[key] = relationship

    def read(self, path):
        try:
            return self.archive.read(path)
        except (KeyError, OSError, BadZipFile, RuntimeError, NotImplementedError) as exc:
            raise InvalidDocument(f"{self.location} 无法读取包内资源 {path}") from exc

    def xml(self, path):
        try:
            return ET.fromstring(self.read(path))
        except ET.ParseError as exc:
            raise InvalidDocument(f"{self.location} XML 损坏 {path} ({exc})") from exc

    def target(self, key, kind):
        relationship = self.relationships.get(key)
        if relationship is None or relationship.get("Type") != f"{REL}/{kind}":
            raise InvalidDocument(f"{self.location} 缺少有效的 {kind} 关系 {key}")
        target = relationship.get("Target", "")
        uri = urlsplit(target)
        if relationship.get("TargetMode", "Internal") != "Internal" or uri.scheme or uri.netloc:
            raise UnsupportedDocument(f"{self.location} 使用了外部 {kind} 关系 {key}")
        path = unquote(uri.path)
        if not path or "\\" in path or "\0" in path or uri.query or uri.fragment:
            raise InvalidDocument(f"{self.location} 包内资源路径无效 {target}")
        path = posixpath.normpath(path.lstrip("/") if path.startswith("/") else f"word/{path}")
        if path == ".." or path.startswith("../"):
            raise InvalidDocument(f"{self.location} 资源路径超出 DOCX {target}")
        return path

    def sections(self, names=SECTIONS):
        body = self.xml("word/document.xml").find("w:body", NS)
        if body is None:
            raise InvalidDocument("DOCX 缺少主文档正文")
        blocks = []
        for index, node in enumerate(body, 1):
            if node.tag == qname("w:sectPr"):
                section = node
            else:
                blocks.append((index, node))
                section = node.find("w:pPr/w:sectPr", NS)
            if section is None:
                continue
            self.location = f"正文块 {index} 的分节"
            header_ref = section.find("w:headerReference[@w:type='default']", NS)
            if header_ref is None:
                raise UnsupportedDocument(f"{self.location} 缺少模板默认页眉")
            header = self.xml(self.target(header_ref.get(qname("r:id")), "header"))
            name = "".join(node.text or "" for node in header.iter(qname("w:t"))).strip()
            if name not in names:
                raise UnsupportedDocument(f"{self.location} 无法识别页眉 {name!r}")
            yield name, blocks
            blocks = []
        if blocks:
            raise InvalidDocument("DOCX 结尾缺少正文分节属性")

    def style_chain(self, reference):
        if reference is None:
            return
        if self.character_styles is None:
            keys = [key for key, rel in self.relationships.items() if rel.get("Type") == f"{REL}/styles"]
            if len(keys) != 1:
                raise InvalidDocument(f"{self.location} 字符样式表关系缺失或重复")
            root = self.xml(self.target(keys[0], "styles"))
            styles = {}
            for style in root.findall("w:style[@w:type='character']", NS):
                key = style.get(qname("w:styleId"))
                if not key or key in styles:
                    raise InvalidDocument(f"{self.location} 字符样式编号缺失或重复 {key!r}")
                styles[key] = style
            self.character_styles = styles
        seen = set()
        while reference is not None:
            key = reference.get(qname("w:val"))
            if key not in self.character_styles or key in seen:
                raise InvalidDocument(f"{self.location} 字符样式缺失或循环引用 {key!r}")
            seen.add(key)
            style = self.character_styles[key]
            yield style.find("w:rPr", NS)
            reference = style.find("w:basedOn", NS)

    def run_script(self, properties):
        if properties is None:
            return None
        alignment = None
        reference = properties.find("w:rStyle", NS)
        for layer in chain((properties,), self.style_chain(reference)):
            if layer is None:
                continue
            if any(layer.find(f"w:{tag}", NS) is not None for tag in (
                "rPrChange", "vanish", "webHidden", "position", "strike", "dstrike",
            )):
                raise UnsupportedDocument(f"{self.location} 含有隐藏、偏移、删除线或修订文字")
            value = layer.find("w:vertAlign", NS)
            if value is not None and alignment is None:
                alignment = value.get(qname("w:val"))
                if alignment not in {"subscript", "superscript", "baseline"}:
                    raise InvalidDocument(f"{self.location} 上下标属性无效")
        return {"subscript": "sub", "superscript": "sup"}.get(alignment)

    def paragraph(self, paragraph, *, maths=False, drawing=False):
        parts = []
        for node in paragraph:
            if node.tag == qname("w:pPr"):
                if node.find("w:numPr", NS) is not None:
                    raise UnsupportedDocument(f"{self.location} 使用了 Word 自动编号")
                if node.find("w:pPrChange", NS) is not None:
                    raise UnsupportedDocument(f"{self.location} 含有未处理的段落修订")
            elif node.tag == qname("w:r"):
                script = self.run_script(node.find("w:rPr", NS))
                for child in node:
                    if child.tag == qname("w:rPr"):
                        continue
                    if child.tag in {qname("w:t"), qname("w:tab"), qname("w:noBreakHyphen")}:
                        value = {qname("w:tab"): "\t", qname("w:noBreakHyphen"): "‑"}.get(
                            child.tag, child.text or ""
                        )
                        if script:
                            parts.append(Script(value, script))
                        else:
                            parts.append(value)
                    elif child.tag == qname("w:cr") or (
                        child.tag == qname("w:br") and child.get(qname("w:type"), "textWrapping") == "textWrapping"
                    ):
                        parts.append(Break())
                    elif child.tag == qname("w:lastRenderedPageBreak"):
                        continue
                    elif child.tag == qname("w:drawing") and drawing:
                        parts.append(child)
                    else:
                        raise UnsupportedDocument(f"{self.location} 不支持 {child.tag.rsplit('}', 1)[-1]} 对象")
            elif node.tag in {qname("m:oMath"), qname("m:oMathPara")} and maths:
                try:
                    parts.append(Equation(read_math(node), node.tag == qname("m:oMathPara")))
                except UnsupportedDocument as exc:
                    raise UnsupportedDocument(f"{self.location} {exc}") from exc
            elif node.tag not in {qname("w:bookmarkStart"), qname("w:bookmarkEnd"), qname("w:proofErr")}:
                raise UnsupportedDocument(f"{self.location} 不支持 {node.tag.rsplit('}', 1)[-1]} 对象")
        return parts

    def table(self, table):
        if any(table.find(f".//w:{tag}", NS) is not None for tag in (
            "gridSpan", "vMerge", "hMerge", "gridBefore", "gridAfter", "tblpPr", "tblPrChange",
            "trPrChange", "tcPrChange", "cellIns", "cellDel", "cellMerge",
        )):
            raise UnsupportedDocument(f"{self.location} 表格包含合并、省略、浮动或有修订的单元格")
        if any(node.tag not in {qname("w:tblPr"), qname("w:tblGrid"), qname("w:tr")} for node in table):
            raise UnsupportedDocument(f"{self.location} 表格含有未支持的结构")
        rows = table.findall("w:tr", NS)
        grid = table.findall("w:tblGrid/w:gridCol", NS)
        if not rows or not grid:
            raise InvalidDocument(f"{self.location} 表格缺少行或列")
        widths = [int(col.get(qname("w:w"), "0")) for col in grid]
        if any(width <= 0 for width in widths):
            raise UnsupportedDocument(f"{self.location} 表格列宽不明确")
        location = self.location
        result = []
        for row_number, row in enumerate(rows, 1):
            cells = [node for node in row if node.tag not in {qname("w:trPr"), qname("w:tblPrEx")}]
            if len(cells) != len(grid) or any(cell.tag != qname("w:tc") for cell in cells):
                raise UnsupportedDocument(f"{self.location} 表格不是普通矩形行列")
            result_row = []
            for column_number, cell in enumerate(cells, 1):
                self.location = f"{location} 表格第 {row_number} 行第 {column_number} 列"
                paragraphs = []
                for node in cell:
                    if node.tag == qname("w:tcPr"):
                        continue
                    if node.tag != qname("w:p"):
                        raise UnsupportedDocument(f"{self.location} 表格含有未支持的单元格对象")
                    paragraphs.append(Paragraph(tuple(self.paragraph(node)), self.location))
                result_row.append(tuple(paragraphs))
            result.append(tuple(result_row))
        self.location = location
        return Table(tuple(result), tuple(widths), location)

    def figure(self, node, label):
        path = "wp:inline/a:graphic/a:graphicData/pic:pic"
        picture = node.find(path, NS)
        if len(node) != 1 or picture is None or len(node.findall(path, NS)) != 1:
            raise UnsupportedDocument(f"{self.location} 附图需要单个嵌入位图，浮动图形和绘图对象需另行转换")
        fill = picture.find("pic:blipFill", NS)
        blip = fill.find("a:blip", NS) if fill is not None else None
        if blip is not None and blip.get(qname("r:link")):
            raise UnsupportedDocument(f"{self.location} 附图链接到外部图件")
        if blip is None or not blip.get(qname("r:embed")):
            raise InvalidDocument(f"{self.location} 位图缺少嵌入关系")
        properties = picture.find("pic:spPr", NS)
        transform = properties.find("a:xfrm", NS) if properties is not None else None
        geometry = properties.find("a:prstGeom", NS) if properties is not None else None
        crop = fill.find("a:srcRect", NS)
        stretch = fill.find("a:stretch/a:fillRect", NS)
        if (
            (transform is not None and any(value not in {"0", "false"} for value in transform.attrib.values()))
            or (crop is not None and any(value != "0" for value in crop.attrib.values()))
            or (stretch is None or any(value != "0" for value in stretch.attrib.values()))
            or geometry is None or geometry.get("prst") != "rect"
            or any(child.tag not in {qname("a:xfrm"), qname("a:prstGeom")} for child in properties)
            or len(blip)
        ):
            raise UnsupportedDocument(f"{self.location} 附图包含裁切、旋转或其他未支持的图形处理")
        extent = node.find("wp:inline/wp:extent", NS)
        if extent is None:
            raise InvalidDocument(f"{self.location} 位图缺少显示尺寸")
        width, height = (int(extent.get(axis, "0")) for axis in ("cx", "cy"))
        data = self.read(self.target(blip.get(qname("r:embed")), "image"))
        try:
            from PIL import Image
        except ImportError as exc:
            raise UnsupportedDocument(f"{self.location} 位图转换需要 Pillow ({exc})") from exc
        try:
            with Image.open(BytesIO(data)) as source:
                if source.format not in {"PNG", "JPEG"}:
                    raise UnsupportedDocument(f"{self.location} 位图格式超出支持范围 {source.format}")
                if getattr(source, "is_animated", False):
                    raise UnsupportedDocument(f"{self.location} 位图包含多帧内容")
                image_format = source.format
                source.load()
        except (OSError, Image.DecompressionBombError) as exc:
            raise InvalidDocument(f"{self.location} 无法读取 PNG 或 JPEG 位图 ({exc})") from exc
        return Figure(label, data, image_format, width, height, self.location)

    def book(self, name, blocks):
        content = []
        pending_figure = None
        with_figures = name in ("说明书附图", DESIGN_VIEWS)
        for index, node in blocks:
            self.location = f"{name}正文块 {index}"
            if node.tag == qname("w:tbl") and name == "说明书" and len(content):
                content.append(self.table(node))
                continue
            if node.tag != qname("w:p"):
                raise UnsupportedDocument(f"{self.location} 不是受支持的段落或普通说明书表格")
            parts = self.paragraph(
                node, maths=name == "说明书" and bool(content), drawing=with_figures,
            )
            text = plain(parts)
            if text is not None and not text.strip():
                continue
            if name == "权利要求书":
                prefix_end = next((i for i, part in enumerate(parts) if not isinstance(part, str)), len(parts))
                prefix = "".join(parts[:prefix_end])
                match = CLAIM_NUMBER.match(prefix)
                if match is None:
                    raise UnsupportedDocument(f"{self.location} 需要顺序编号且每项单独成段的权利要求")
                paragraph = Paragraph((prefix[match.end():], *parts[prefix_end:]), self.location)
                content.append(Claim(int(match[1]), paragraph))
            elif name == "说明书" and content and text is not None and text.strip() in HEADINGS:
                content.append(Heading(text.strip(), self.location))
            elif with_figures:
                objects = [part for part in parts if not isinstance(part, str)]
                if pending_figure is None and len(objects) == 1 and isinstance(objects[0], ET.Element) and all(
                    not part.strip() for part in parts if isinstance(part, str)
                ):
                    pending_figure = (objects[0], self.location)
                elif pending_figure is not None and text is not None and (
                    name == DESIGN_VIEWS or FIGURE_LABEL.fullmatch(text.strip())
                ):
                    drawing, self.location = pending_figure
                    content.append(self.figure(drawing, text.strip()))
                    pending_figure = None
                else:
                    raise UnsupportedDocument(f"{self.location} 需要独立的嵌入图片段及紧随其后的图号或视图名")
            else:
                content.append(Paragraph(tuple(parts), self.location))
        if pending_figure is not None:
            raise UnsupportedDocument(f"{pending_figure[1]} 图片缺少图号或视图名")
        return tuple(content)

    def read_design(self):
        books = {}
        for name, blocks in self.sections((DESIGN_VIEWS, DESIGN_BRIEF)):
            if name in books:
                raise UnsupportedDocument(f"{name} 出现在多个 DOCX 节")
            books[name] = self.book(name, blocks)
        if not books.get(DESIGN_BRIEF):
            raise InvalidDocument(f"DOCX 缺少必要分册 {DESIGN_BRIEF}")
        first, *brief = books[DESIGN_BRIEF]
        text = plain(first.parts)
        title = re.fullmatch(rf"{DESIGN_TITLE}[：:]\s*(.+)", text.strip()) if text else None
        if not title:
            raise InvalidDocument(f"{first.location} 首段需为「{DESIGN_TITLE}：…」")
        return DesignFiling(title[1].strip(), tuple(brief), books.get(DESIGN_VIEWS, ()))

    def read_filing(self):
        books = {}
        for name, blocks in self.sections():
            if name == "摘要附图":
                for index, node in blocks:
                    self.location = f"摘要附图正文块 {index}"
                    if node.tag != qname("w:p"):
                        raise UnsupportedDocument(f"{self.location} 需要在请求书中指定现有说明书附图")
                    text = plain(self.paragraph(node))
                    if text is None or text.strip():
                        raise UnsupportedDocument(f"{self.location} 需要在请求书中指定现有说明书附图")
                continue
            content = self.book(name, blocks)
            if not content:
                continue
            if name in books:
                raise UnsupportedDocument(f"{name} 出现在多个非空 DOCX 节")
            books[name] = content
        for name in ("权利要求书", "说明书", "说明书摘要"):
            if name not in books:
                raise InvalidDocument(f"DOCX 缺少必要分册 {name}")
        title, *description = books["说明书"]
        return Filing(title, books["权利要求书"], tuple(description), books["说明书摘要"], books.get("说明书附图", ()))


def read_docx(path, patent_type="invention"):
    with ZipFile(path) as archive:
        reader = DocxReader(archive)
        try:
            if patent_type == "design":
                return reader.read_design()
            return reader.read_filing()
        except (InvalidDocument, UnsupportedDocument):
            raise
        except (ValueError, OSError) as exc:
            raise InvalidDocument(f"{reader.location} ({exc})") from exc
