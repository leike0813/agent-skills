"""Render the filing model as the CNIPA technical document package."""

from collections import Counter
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

from filing_ir import (
    DESIGN_REPRESENTATIVE, DESIGN_TITLE, EMU_PER_MM, Break, DesignFiling, Equation,
    Fraction, Heading, InvalidDocument, Script, Table, UnsupportedDocument, view_name,
)


def prolog(root):
    doctype = f'<!DOCTYPE {root} SYSTEM "/dtdandxsl/{root}-20080416.dtd"[]>\r\n' if root != "authorization" else ""
    return (
        '\ufeff<?xml version="1.0" encoding="UTF-8"?>\r\n'
        + doctype
        + '<?xml-stylesheet type="text/xsl" href="/dtdandxsl/showxml.xsl"?>\r\n'
    ).encode("utf-8")


DPI = 300
SRGB_PROFILE = Path(__file__).resolve().parent.parent / "assets" / "sRGB-v4.icc"


def math_tex(expression):
    parts = []
    for node in expression:
        if isinstance(node, str):
            parts.append(node)
        elif isinstance(node, Fraction):
            parts.append(r"\frac{%s}{%s}" % (math_tex(node.numerator), math_tex(node.denominator)))
        else:
            parts.append("{%s}_{%s}" % (math_tex(node.base), math_tex(node.index)))
    return "".join(parts)


class XmlBook:
    def __init__(self, archive, code, tag, *, root_tag="cn-application-body"):
        self.archive = archive
        self.code = code
        self.root = ET.Element(root_tag)
        self.body = self.root
        if tag is not None:
            self.root.attrib.update(lang="zh", country="CN")
            self.body = ET.SubElement(self.root, tag)
        self.counts = Counter()
        self.images = {}

    def number(self, kind, prefix):
        self.counts[kind] += 1
        index = self.counts[kind]
        return {"id": f"{prefix}{index:04}", "num": f"{index:04}"}

    def jpeg(self, index, image, profile=None):
        filename = f"{self.code}_{index}.jpg"
        output = BytesIO()
        image.save(output, "JPEG", dpi=(DPI, DPI), quality=95, subsampling=0, icc_profile=profile)
        self.images[filename] = output.getvalue()
        return filename

    def image(self, parent, index, image, millimetres, *, inline):
        filename = self.jpeg(index, image)
        width, height = (str(max(1, int(value))) for value in millimetres)
        ET.SubElement(
            parent, "img", id=f"{'if' if inline else 'idf'}{index:04}", file=filename,
            wi=width, he=height, top="0", left="0", orientation="portrait",
            inline="yes" if inline else "no", **{"img-content": "drawing", "img-format": "jpg"},
        )

    def equation(self, parent, equation, location):
        try:
            from matplotlib.font_manager import FontProperties
            from matplotlib.mathtext import math_to_image
            from PIL import Image, ImageOps
        except ImportError as exc:
            raise UnsupportedDocument(f"{location} 公式转换需要 Matplotlib 和 Pillow ({exc})") from exc
        output = BytesIO()
        try:
            math_to_image(
                "$" + math_tex(equation.expression) + "$", output,
                prop=FontProperties(size=12), dpi=DPI, format="png",
            )
        except ValueError as exc:
            raise UnsupportedDocument(f"{location} 无法渲染原生公式 ({exc})") from exc
        with Image.open(output) as rendered:
            maths = ET.SubElement(parent, "maths", self.number("maths", "math"))
            image = ImageOps.expand(rendered.convert("RGB"), border=round(DPI / 25.4), fill="white")
            size = [pixels / DPI * 25.4 for pixels in image.size]
            self.image(maths, self.counts["maths"], image, size, inline=False)

    def inline(self, element, paragraph):
        for part in paragraph.parts:
            if isinstance(part, str):
                if len(element):
                    element[-1].tail = (element[-1].tail or "") + part
                else:
                    element.text = (element.text or "") + part
            elif isinstance(part, Script):
                ET.SubElement(element, part.position).text = part.text
            elif isinstance(part, Break):
                ET.SubElement(element, "br")
            elif isinstance(part, Equation):
                self.equation(element, part, paragraph.location)

    def paragraph(self, *, italic="1"):
        return ET.SubElement(self.body, "p", self.number("p", "p"), Italic=italic)

    def table(self, block):
        tables = ET.SubElement(self.paragraph(), "tables", self.number("table", "tabl"))
        tgroup = ET.SubElement(ET.SubElement(tables, "table"), "tgroup", cols=str(len(block.widths)))
        total = sum(block.widths)
        for column, width in enumerate(block.widths, 1):
            ET.SubElement(tgroup, "colspec", colname=f"c{column:03}", colwidth=f"{width / total:.1%}")
        tbody = ET.SubElement(tgroup, "tbody")
        for row in block.rows:
            out_row = ET.SubElement(tbody, "row")
            for cell in row:
                entry = ET.SubElement(out_row, "entry", morerows="1")
                for paragraph in cell:
                    self.inline(entry, paragraph)
                    ET.SubElement(entry, "br")

    @staticmethod
    def design_cmyk(source, figure):
        location = f"{figure.location}（{figure.label}）"
        profile = source.info.get("icc_profile")
        if not profile:
            raise UnsupportedDocument(f"{location} CMYK 图样缺少源 ICC 配置，请提供经确认的 sRGB 副本")
        try:
            from PIL import ImageCms
        except ImportError as exc:
            raise UnsupportedDocument(f"{location} 缺少 Pillow 色彩管理组件，请提供经确认的 sRGB 副本") from exc
        try:
            target = ImageCms.getOpenProfile(str(SRGB_PROFILE))
            return ImageCms.profileToProfile(source, BytesIO(profile), target, outputMode="RGB")
        except (ImageCms.PyCMSError, ImportError, OSError, ValueError) as exc:
            raise UnsupportedDocument(f"{location} ICC 色彩转换失败，请提供经确认的 sRGB 副本（{exc}）") from exc

    @staticmethod
    def raster(figure, *, design=False):
        try:
            from PIL import Image, ImageOps
        except ImportError as exc:
            raise UnsupportedDocument(f"{figure.location} 位图转换需要 Pillow ({exc})") from exc
        size = (figure.width_emu / EMU_PER_MM, figure.height_emu / EMU_PER_MM)
        with Image.open(BytesIO(figure.data)) as source:
            source = ImageOps.exif_transpose(source)
            if design and source.mode == "CMYK":
                source = XmlBook.design_cmyk(source, figure)
            profile = source.info.get("icc_profile") if design and source.mode in ("RGB", "RGBA", "P") else None
            if design:
                if abs(size[0] * source.height / source.width - size[1]) > 0.1:
                    raise InvalidDocument(f"{figure.location} 外观图片显示比例与原图不一致")
                pixels_w = max(1, round(size[0] / 25.4 * DPI))
                pixels = (pixels_w, max(1, round(pixels_w * source.height / source.width)))
            else:
                pixels = tuple(max(1, round(mm / 25.4 * DPI)) for mm in size)
            raster = source.convert("RGBA").resize(pixels, Image.Resampling.LANCZOS)
        white = Image.new("RGB", pixels, "white")
        white.paste(raster, mask=raster.getchannel("A"))
        return white, size, profile

    def figure(self, figure):
        white, size, _ = self.raster(figure)
        element = ET.SubElement(self.body, "figure", self.number("figure", "f"), **{"figure-labels": figure.label})
        self.image(element, self.counts["figure"], white, size, inline=True)

    def write(self):
        self.archive.writestr(f"{self.code}/{self.code}.xml", prolog(self.root.tag) + ET.tostring(self.root, encoding="utf-8"))
        for filename, data in sorted(self.images.items()):
            self.archive.writestr(f"{self.code}/{filename}", data)


def _design_books(filing, archive):
    representative = view_name(filing.fields()[DESIGN_REPRESENTATIVE])
    drawings = XmlBook(archive, "130001", None, root_tag="authorization")
    for index, view in enumerate(filing.views, 1):
        raster, _, profile = drawings.raster(view, design=True)
        image = ET.SubElement(drawings.body, "image")
        ET.SubElement(image, "physical-name").text = drawings.jpeg(index, raster, profile)
        ET.SubElement(image, "logical-name").text = view.label
        ET.SubElement(image, "fengpi-flag").text = "1" if view_name(view.label) == representative else "0"
    drawings.write()

    brief = XmlBook(archive, "130002", "cn-brief", root_tag="cn-design-application-body")
    brief.paragraph(italic="0").text = f"{DESIGN_TITLE}：{filing.title}"
    names = {view_name(view.label): view.label for view in filing.views}
    for paragraph in filing.brief:
        value = "".join(paragraph.parts)
        field, separator, reference = value.replace(":", "：", 1).partition("：")
        if separator and field.strip() == DESIGN_REPRESENTATIVE:
            value = f"{field}：{names[view_name(reference)]}"
        brief.paragraph(italic="0").text = value
    brief.write()


def _technical_books(filing, archive):
    claims = XmlBook(archive, "100001", "cn-claims")
    for item in filing.claims:
        claim = ET.SubElement(claims.body, "claim", id=f"cl{item.number:03}", num=str(item.number))
        claims.inline(ET.SubElement(claim, "claim-text"), item.paragraph)
    claims.write()

    description = XmlBook(archive, "100002", "description")
    description.inline(ET.SubElement(description.body, "invention-title"), filing.title)
    for block in filing.description:
        if isinstance(block, Heading):
            attrs = description.number("heading", "h")
            ET.SubElement(description.body, "heading", id=attrs["id"], level="2").text = block.text
        elif isinstance(block, Table):
            description.table(block)
        else:
            description.inline(description.paragraph(), block)
    description.write()

    if filing.figures:
        drawings = XmlBook(archive, "100003", "cn-drawings")
        for figure in filing.figures:
            drawings.figure(figure)
        drawings.write()

    abstract = XmlBook(archive, "100004", "cn-abstract")
    for paragraph in filing.abstract:
        abstract.inline(abstract.paragraph(), paragraph)
    abstract.write()


def render_zip(filing):
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        if isinstance(filing, DesignFiling):
            _design_books(filing, archive)
        else:
            _technical_books(filing, archive)
    return output.getvalue()
