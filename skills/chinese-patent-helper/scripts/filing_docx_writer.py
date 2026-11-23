"""Render approved application content into an editable DOCX."""

from copy import deepcopy
from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile, ZipInfo

from filing_ir import (
    DESIGN_BRIEF, DESIGN_TITLE, DESIGN_VIEWS, Break, DesignFiling, Equation, Filing,
    Fraction, Heading, InvalidDocument, Paragraph, Script, Table, UnsupportedDocument,
)


TEMPLATE = Path(__file__).resolve().parent.parent / "assets" / "WORD转XML编辑器五书模板文件.docx"

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
PIC = "http://schemas.openxmlformats.org/drawingml/2006/picture"
PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
IMAGE_REL = f"{R}/image"

BOOKS = ("说明书摘要", "权利要求书", "说明书")
FIGURE_BOOK = "说明书附图"
NO_INDENT = ("0", "0")
BODY_INDENT = ("200", "560")
VERTICAL = {"sub": "subscript", "sup": "superscript"}
IMAGE_TYPES = {"PNG": ("png", "image/png"), "JPEG": ("jpg", "image/jpeg")}
DEFAULT_TEXT_WIDTH = 8306
ZIP_DATE = (1980, 1, 1, 0, 0, 0)


def q(namespace, name):
    return f"{{{namespace}}}{name}"


def _lxml():
    try:
        from lxml import etree
    except ImportError as exc:
        raise UnsupportedDocument(f"DOCX 写出需要 lxml ({exc})") from exc
    return etree


def _template():
    try:
        data = TEMPLATE.read_bytes()
    except OSError as exc:
        raise InvalidDocument(f"缺少官方五书模板 {TEMPLATE} ({exc})") from exc
    try:
        with ZipFile(BytesIO(data)) as archive:
            infos = archive.infolist()
            members = {info.filename: archive.read(info.filename) for info in infos}
    except (BadZipFile, OSError, RuntimeError) as exc:
        raise InvalidDocument(f"官方五书模板无法读取 ({exc})") from exc
    return infos, members


def _sections(etree, body, rels, members):
    """Map each template section to its page setup and blank paragraph style."""
    targets = {rel.get("Id"): rel.get("Target") for rel in rels}
    groups = []
    blocks = []
    for child in list(body):
        if child.tag == q(W, "sectPr"):
            groups.append((blocks, child))
            blocks = []
            continue
        blocks.append(child)
        pPr = child.find(q(W, "pPr"))
        sectPr = pPr.find(q(W, "sectPr")) if pPr is not None else None
        if sectPr is not None:
            groups.append((blocks, sectPr))
            blocks = []
    sections = {}
    for blocks, sectPr in groups:
        name, header = _section_header(etree, sectPr, targets, members)
        if name in sections:
            raise InvalidDocument(f"模板出现重复分节 {name}")
        pPr, rPr = _base_style(blocks)
        sections[name] = {"sectPr": sectPr, "pPr": pPr, "rPr": rPr, "header": header}
    return sections


def _section_header(etree, sectPr, targets, members):
    reference = next(
        (node for node in sectPr.findall(q(W, "headerReference")) if node.get(q(W, "type")) == "default"),
        None,
    )
    if reference is None:
        raise InvalidDocument("模板分节缺少默认页眉")
    target = targets.get(reference.get(q(R, "id")))
    if target is None:
        raise InvalidDocument("模板分节页眉关系缺失")
    path = "word/" + target.lstrip("/")
    data = members.get(path)
    if data is None:
        raise InvalidDocument(f"模板页眉缺失 {path}")
    header = etree.fromstring(data)
    return "".join(node.text or "" for node in header.iter(q(W, "t"))).strip(), path


def _base_style(blocks):
    """Copy the section's blank paragraph formatting without decorative marks."""
    for block in blocks:
        if block.tag != q(W, "p"):
            continue
        pPr = block.find(q(W, "pPr"))
        if pPr is None:
            continue
        base_pPr = deepcopy(pPr)
        for child in list(base_pPr):
            if child.tag not in {q(W, "spacing"), q(W, "ind"), q(W, "jc")}:
                base_pPr.remove(child)
        base_rPr = None
        rPr = pPr.find(q(W, "rPr"))
        if rPr is not None:
            base_rPr = deepcopy(rPr)
            for child in list(base_rPr):
                if child.tag not in {q(W, "rFonts"), q(W, "sz"), q(W, "szCs")}:
                    base_rPr.remove(child)
        return base_pPr, base_rPr
    return None, None


def _pPr(etree, base, *, indent=None, align=None):
    pPr = deepcopy(base) if base is not None else etree.Element(q(W, "pPr"))
    if indent is not None:
        node = pPr.find(q(W, "ind"))
        if node is None:
            node = etree.Element(q(W, "ind"))
            anchor = pPr.find(q(W, "jc"))
            if anchor is None:
                pPr.append(node)
            else:
                anchor.addprevious(node)
        node.set(q(W, "firstLineChars"), indent[0])
        node.set(q(W, "firstLine"), indent[1])
    if align is not None:
        node = pPr.find(q(W, "jc"))
        if node is None:
            node = etree.SubElement(pPr, q(W, "jc"))
        node.set(q(W, "val"), align)
    return pPr


def _rPr(etree, base, *, bold=False, vert=None):
    rPr = etree.Element(q(W, "rPr"))
    fonts = base.find(q(W, "rFonts")) if base is not None else None
    if fonts is not None:
        rPr.append(deepcopy(fonts))
    if bold:
        rPr.append(etree.Element(q(W, "b")))
    for name in ("sz", "szCs"):
        node = base.find(q(W, name)) if base is not None else None
        if node is not None:
            rPr.append(deepcopy(node))
    if vert is not None:
        node = etree.SubElement(rPr, q(W, "vertAlign"))
        node.set(q(W, "val"), vert)
    return rPr


def _run(etree, base, text=None, *, bold=False, vert=None):
    run = etree.Element(q(W, "r"))
    run.append(_rPr(etree, base, bold=bold, vert=vert))
    if text is not None:
        node = etree.SubElement(run, q(W, "t"))
        if text != text.strip():
            node.set(XML_SPACE, "preserve")
        node.text = text
    return run


def _math_items(etree, expression):
    """Build native OMML for one expression, keeping fractions and subscripts."""
    items = []
    for item in expression:
        if isinstance(item, str):
            run = etree.Element(q(M, "r"))
            props = etree.SubElement(run, q(W, "rPr"))
            fonts = etree.SubElement(props, q(W, "rFonts"))
            fonts.set(q(W, "ascii"), "Cambria Math")
            fonts.set(q(W, "hAnsi"), "Cambria Math")
            text = etree.SubElement(run, q(M, "t"))
            if item != item.strip():
                text.set(XML_SPACE, "preserve")
            text.text = item
            items.append(run)
        elif isinstance(item, Fraction):
            node = etree.Element(q(M, "f"))
            props = etree.SubElement(node, q(M, "fPr"))
            kind = etree.SubElement(props, q(M, "type"))
            kind.set(q(M, "val"), "bar")
            for tag, part in (("num", item.numerator), ("den", item.denominator)):
                child = etree.SubElement(node, q(M, tag))
                child.extend(_math_items(etree, part))
            items.append(node)
        else:
            node = etree.Element(q(M, "sSub"))
            for tag, part in (("e", item.base), ("sub", item.index)):
                child = etree.SubElement(node, q(M, tag))
                child.extend(_math_items(etree, part))
            items.append(node)
    return items


def _paragraph(etree, section, parts, *, indent=None, align=None, bold=False, prefix=None):
    node = etree.Element(q(W, "p"))
    node.append(_pPr(etree, section["pPr"], indent=indent, align=align))
    base = section["rPr"]
    if prefix is not None:
        node.append(_run(etree, base, prefix, bold=bold))
    for part in parts:
        if isinstance(part, str):
            if part:
                node.append(_run(etree, base, part, bold=bold))
        elif isinstance(part, Script):
            node.append(_run(etree, base, part.text, bold=bold, vert=VERTICAL[part.position]))
        elif isinstance(part, Break):
            run = _run(etree, base)
            etree.SubElement(run, q(W, "br"))
            node.append(run)
        else:
            oMath = etree.Element(q(M, "oMath"))
            oMath.extend(_math_items(etree, part.expression))
            if part.display:
                wrapper = etree.Element(q(M, "oMathPara"))
                wrapper.append(oMath)
                node.append(wrapper)
            else:
                node.append(oMath)
    return node


def _text_width(sectPr):
    size = sectPr.find(q(W, "pgSz"))
    margins = sectPr.find(q(W, "pgMar"))
    if size is None or margins is None:
        return DEFAULT_TEXT_WIDTH
    try:
        width = int(size.get(q(W, "w"))) - int(margins.get(q(W, "left"))) - int(margins.get(q(W, "right")))
    except (TypeError, ValueError):
        return DEFAULT_TEXT_WIDTH
    return max(1, width)


def _table(etree, section, table, text_width):
    total = sum(table.widths)
    widths = [max(1, round(width / total * text_width)) for width in table.widths]
    node = etree.Element(q(W, "tbl"))
    props = etree.SubElement(node, q(W, "tblPr"))
    table_width = etree.SubElement(props, q(W, "tblW"))
    table_width.set(q(W, "w"), str(sum(widths)))
    table_width.set(q(W, "type"), "dxa")
    borders = etree.SubElement(props, q(W, "tblBorders"))
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        border = etree.SubElement(borders, q(W, edge))
        border.set(q(W, "val"), "single")
        border.set(q(W, "sz"), "4")
    layout = etree.SubElement(props, q(W, "tblLayout"))
    layout.set(q(W, "type"), "fixed")
    grid = etree.SubElement(node, q(W, "tblGrid"))
    for width in widths:
        column = etree.SubElement(grid, q(W, "gridCol"))
        column.set(q(W, "w"), str(width))
    for row in table.rows:
        if len(row) != len(widths):
            raise InvalidDocument(f"{table.location} 表格行列数与列宽不一致")
        row_node = etree.SubElement(node, q(W, "tr"))
        for index, cell in enumerate(row):
            cell_node = etree.SubElement(row_node, q(W, "tc"))
            cell_props = etree.SubElement(cell_node, q(W, "tcPr"))
            cell_width = etree.SubElement(cell_props, q(W, "tcW"))
            cell_width.set(q(W, "w"), str(widths[index]))
            cell_width.set(q(W, "type"), "dxa")
            for paragraph in cell or (Paragraph((), table.location),):
                cell_node.append(_paragraph(etree, section, paragraph.parts, indent=NO_INDENT, align="left"))
    return node


def _drawing(etree, figure, rel_id, index, filename):
    drawing = etree.Element(q(W, "drawing"))
    inline = etree.SubElement(drawing, q(WP, "inline"))
    for name in ("distT", "distB", "distL", "distR"):
        inline.set(name, "0")
    extent = etree.SubElement(inline, q(WP, "extent"))
    extent.set("cx", str(figure.width_emu))
    extent.set("cy", str(figure.height_emu))
    doc_properties = etree.SubElement(inline, q(WP, "docPr"))
    doc_properties.set("id", str(index))
    doc_properties.set("name", filename)
    graphic = etree.SubElement(inline, q(A, "graphic"))
    graphic_data = etree.SubElement(graphic, q(A, "graphicData"))
    graphic_data.set("uri", "http://schemas.openxmlformats.org/drawingml/2006/picture")
    picture = etree.SubElement(graphic_data, q(PIC, "pic"))
    non_visual = etree.SubElement(picture, q(PIC, "nvPicPr"))
    non_visual_props = etree.SubElement(non_visual, q(PIC, "cNvPr"))
    non_visual_props.set("id", str(index))
    non_visual_props.set("name", filename)
    etree.SubElement(non_visual, q(PIC, "cNvPicPr"))
    fill = etree.SubElement(picture, q(PIC, "blipFill"))
    blip = etree.SubElement(fill, q(A, "blip"))
    blip.set(q(R, "embed"), rel_id)
    stretch = etree.SubElement(fill, q(A, "stretch"))
    etree.SubElement(stretch, q(A, "fillRect"))
    shape = etree.SubElement(picture, q(PIC, "spPr"))
    geometry = etree.SubElement(shape, q(A, "prstGeom"))
    geometry.set("prst", "rect")
    etree.SubElement(geometry, q(A, "avLst"))
    return drawing


def _image_part(etree, rels, types, figure, index):
    extension, content_type = IMAGE_TYPES[figure.format]
    filename = f"figure{index}.{extension}"
    used = {rel.get("Id") for rel in rels}
    number = 1
    while f"rId{number}" in used:
        number += 1
    rel_id = f"rId{number}"
    relation = etree.SubElement(rels, q(PKG, "Relationship"))
    relation.set("Id", rel_id)
    relation.set("Type", IMAGE_REL)
    relation.set("Target", f"media/{filename}")
    defaults = types.findall(q(CT, "Default"))
    if not any(node.get("Extension", "").lower() == extension for node in defaults):
        default = etree.Element(q(CT, "Default"))
        default.set("Extension", extension)
        default.set("ContentType", content_type)
        types.insert(list(types).index(defaults[-1]) + 1 if defaults else 0, default)
    return rel_id, f"word/media/{filename}", filename


def _description_elements(etree, section, filing, text_width):
    elements = [
        _paragraph(etree, section, filing.title.parts, indent=NO_INDENT, align="center", bold=True)
    ]
    for block in filing.description:
        if isinstance(block, Heading):
            elements.append(
                _paragraph(etree, section, (block.text,), indent=NO_INDENT, align="left", bold=True)
            )
        elif isinstance(block, Table):
            elements.append(_table(etree, section, block, text_width))
            elements.append(_paragraph(etree, section, (), indent=NO_INDENT))
        else:
            elements.append(_paragraph(etree, section, block.parts, indent=BODY_INDENT, align="both"))
    return elements


def _figure_elements(etree, section, figures, rels, types, media):
    elements = []
    for index, figure in enumerate(figures, 1):
        rel_id, path, filename = _image_part(etree, rels, types, figure, index)
        media[path] = figure.data
        picture = etree.Element(q(W, "p"))
        picture.append(_pPr(etree, section["pPr"], indent=NO_INDENT, align="center"))
        run = etree.SubElement(picture, q(W, "r"))
        run.append(_rPr(etree, section["rPr"]))
        run.append(_drawing(etree, figure, rel_id, index, filename))
        elements.append(picture)
        elements.append(_paragraph(etree, section, (figure.label,), indent=NO_INDENT, align="center"))
    return elements


def _technical_books(etree, sections, filing, rels, types, media):
    for name in BOOKS:
        if name not in sections:
            raise InvalidDocument(f"模板缺少{name}分节")
    if filing.figures and FIGURE_BOOK not in sections:
        raise InvalidDocument("模板缺少说明书附图分节")

    books = {
        "说明书摘要": [
            _paragraph(etree, sections["说明书摘要"], paragraph.parts, indent=NO_INDENT, align="both")
            for paragraph in filing.abstract
        ],
        "权利要求书": [
            _paragraph(
                etree, sections["权利要求书"], claim.paragraph.parts,
                indent=NO_INDENT, align="both", prefix=f"{claim.number}. ",
            )
            for claim in filing.claims
        ],
        "说明书": _description_elements(
            etree, sections["说明书"], filing, _text_width(sections["说明书"]["sectPr"])
        ),
    }
    if filing.figures:
        books[FIGURE_BOOK] = _figure_elements(
            etree, sections[FIGURE_BOOK], filing.figures, rels, types, media
        )
    return books


def _design_books(etree, sections, filing, rels, types, media, members):
    for source, name in (("说明书附图", DESIGN_VIEWS), ("说明书摘要", DESIGN_BRIEF)):
        section = sections[source]
        sections[name] = section
        path = section["header"]
        header = etree.fromstring(members[path])
        runs = list(header.iter(q(W, "t")))
        runs[0].text = name
        for run in runs[1:]:
            run.text = ""
        members[path] = etree.tostring(header, xml_declaration=True, encoding="UTF-8", standalone=True)
    pictures = _figure_elements(etree, sections[DESIGN_VIEWS], filing.views, rels, types, media)
    for picture in pictures[2::2]:
        picture.find(q(W, "pPr")).insert(0, etree.Element(q(W, "pageBreakBefore")))
    brief = sections[DESIGN_BRIEF]
    return {
        DESIGN_VIEWS: pictures,
        DESIGN_BRIEF: [
            _paragraph(etree, brief, (f"{DESIGN_TITLE}：{filing.title}",), indent=NO_INDENT),
            *(_paragraph(etree, brief, paragraph.parts, indent=NO_INDENT) for paragraph in filing.brief),
        ],
    }


def render_docx(filing: Filing | DesignFiling) -> bytes:
    etree = _lxml()
    infos, members = _template()
    document = etree.fromstring(members["word/document.xml"])
    rels = etree.fromstring(members["word/_rels/document.xml.rels"])
    types = etree.fromstring(members["[Content_Types].xml"])
    body = document.find(q(W, "body"))
    if body is None:
        raise InvalidDocument("模板缺少正文")
    sections = _sections(etree, body, rels, members)
    media = {}
    if isinstance(filing, DesignFiling):
        books = _design_books(etree, sections, filing, rels, types, media, members)
    else:
        books = _technical_books(etree, sections, filing, rels, types, media)

    for child in list(body):
        body.remove(child)
    for position, (name, elements) in enumerate(books.items()):
        if not elements:
            raise InvalidDocument(f"{name} 没有内容")
        for element in elements:
            body.append(element)
        sectPr = sections[name]["sectPr"]
        if position == len(books) - 1:
            body.append(sectPr)
        else:
            last = elements[-1]
            pPr = last.find(q(W, "pPr")) if last.tag == q(W, "p") else None
            if pPr is None:
                raise InvalidDocument(f"{name} 分节缺少段落")
            pPr.append(sectPr)

    replaced = {
        "word/document.xml": etree.tostring(document, xml_declaration=True, encoding="UTF-8", standalone=True)
    }
    if media:
        replaced["word/_rels/document.xml.rels"] = etree.tostring(
            rels, xml_declaration=True, encoding="UTF-8", standalone=True
        )
        replaced["[Content_Types].xml"] = etree.tostring(
            types, xml_declaration=True, encoding="UTF-8", standalone=True
        )
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for info in infos:
            archive.writestr(info, replaced.get(info.filename, members[info.filename]))
        for path, data in media.items():
            info = ZipInfo(path, ZIP_DATE)
            info.compress_type = ZIP_DEFLATED
            archive.writestr(info, data)
    return output.getvalue()
