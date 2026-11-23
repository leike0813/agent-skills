"""Content accepted by both filing renderers, independent of the input format."""

from dataclasses import dataclass
import re


PATENT_TYPES = ("invention", "utility-model", "design")
HEADINGS = frozenset({"技术领域", "背景技术", "发明内容", "实用新型内容", "附图说明", "具体实施方式"})
FIGURE_LABEL = re.compile(r"图\s*[1-9][0-9]*")
DESIGN_VIEWS = "外观设计图片或照片"
DESIGN_BRIEF = "外观设计简要说明"
DESIGN_TITLE = "产品名称"
DESIGN_PURPOSE = "产品用途"
DESIGN_FEATURES = "设计要点"
DESIGN_REPRESENTATIVE = "最能表明设计要点的图片或照片"
DESIGN_BASE = "基本设计"
DESIGN_REQUIRED_FIELDS = (DESIGN_PURPOSE, DESIGN_FEATURES, DESIGN_REPRESENTATIVE)
DESIGN_FIELDS = (*DESIGN_REQUIRED_FIELDS, DESIGN_BASE)
DESIGN_GROUP = re.compile(r"^(设计|套件|组件)([0-9]+)(?=\D)")
EMU_PER_MM = 36000
MAX_FIGURE_EMU = 420 * EMU_PER_MM
INVALID_XML_CHAR = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")


class InvalidDocument(ValueError):
    pass


class UnsupportedDocument(ValueError):
    pass


@dataclass(frozen=True)
class Script:
    text: str
    position: str


@dataclass(frozen=True)
class Break:
    pass


@dataclass(frozen=True)
class Fraction:
    numerator: "Math"
    denominator: "Math"


@dataclass(frozen=True)
class Subscript:
    base: "Math"
    index: "Math"


type Math = tuple[str | Fraction | Subscript, ...]


def valid_math_text(text: str) -> bool:
    return re.fullmatch(r"[A-Za-z0-9Α-Ωα-ω +−=*/.,():\[\]<>-]+", text) is not None


@dataclass(frozen=True)
class Equation:
    expression: Math
    display: bool


@dataclass(frozen=True)
class Paragraph:
    parts: tuple[str | Script | Break | Equation, ...]
    location: str

    def has_text(self):
        return any(
            (part if isinstance(part, str) else part.text).strip()
            for part in self.parts
            if isinstance(part, (str, Script))
        )


@dataclass(frozen=True)
class Heading:
    text: str
    location: str


@dataclass(frozen=True)
class Table:
    """Column widths are relative weights in each writer."""

    rows: tuple[tuple[tuple[Paragraph, ...], ...], ...]
    widths: tuple[int, ...]
    location: str


@dataclass(frozen=True)
class Claim:
    number: int
    paragraph: Paragraph


@dataclass(frozen=True)
class Figure:
    label: str
    data: bytes
    format: str
    width_emu: int
    height_emu: int
    location: str


def view_name(text):
    return re.sub(r"^(设计|套件|组件)\s*([0-9]+)\s*", r"\1\2", text.strip())


@dataclass(frozen=True)
class DesignFiling:
    title: str
    brief: tuple[Paragraph, ...]
    views: tuple[Figure, ...]

    def fields(self):
        fields = {}
        for paragraph in self.brief:
            if not all(isinstance(part, str) for part in paragraph.parts):
                raise UnsupportedDocument(f"{paragraph.location} 外观设计简要说明需用纯文本段落")
            text = "".join(paragraph.parts).strip()
            if not text or INVALID_XML_CHAR.search(text):
                raise InvalidDocument(f"{paragraph.location} 简要说明段落为空或含 XML 无法表示的字符")
            match = re.fullmatch(r"([^：:]+)[：:]\s*(.*)", text)
            if match and match[1].strip() in (*DESIGN_FIELDS, DESIGN_TITLE):
                name, value = (part.strip() for part in match.groups())
                if name == DESIGN_TITLE or name in fields or not value:
                    raise InvalidDocument(f"{paragraph.location} 简要说明字段冲突、重复或为空 {name}")
                fields[name] = value
        return fields

    def validate(self):
        if not self.title.strip() or INVALID_XML_CHAR.search(self.title):
            raise InvalidDocument("外观设计产品名称为空或含 XML 无法表示的字符")
        fields = self.fields()
        for field in DESIGN_REQUIRED_FIELDS:
            if field not in fields:
                raise InvalidDocument(f"{DESIGN_BRIEF} 缺少 {field}")
        if not self.views:
            raise InvalidDocument(f"缺少必要分册 {DESIGN_VIEWS}")
        names = set()
        groups = {}
        for view in self.views:
            name = view_name(view.label)
            if not name or INVALID_XML_CHAR.search(name) or name in names:
                raise InvalidDocument(f"{view.location} 外观视图名无效或重复 {view.label!r}")
            if not (0 < view.width_emu <= 150 * EMU_PER_MM and 0 < view.height_emu <= 220 * EMU_PER_MM):
                raise UnsupportedDocument(f"{view.location} 外观视图尺寸须在 150 × 220 mm 内")
            names.add(name)
            group = DESIGN_GROUP.match(name)
            if group:
                if group[2].startswith("0"):
                    raise InvalidDocument(f"{view.location} 视图分组编号需使用从 1 开始的阿拉伯数字")
                groups.setdefault(group[1], set()).add(int(group[2]))
        if view_name(fields[DESIGN_REPRESENTATIVE]) not in names:
            raise InvalidDocument(f"{DESIGN_BRIEF} 指定的代表图未出现在图片或照片分册")
        for kind, numbers in groups.items():
            if min(numbers) != 1 or max(numbers) != len(numbers):
                raise InvalidDocument(f"{DESIGN_VIEWS} 的{kind}编号须从 1 连续")
        designs = groups.get("设计", set())
        suites = groups.get("套件", set())
        basic = fields.get(DESIGN_BASE)
        if designs and suites:
            raise InvalidDocument("相似设计和成套产品须分别处理")
        if designs:
            if not 2 <= len(designs) <= 10:
                raise InvalidDocument("相似设计须包含 2 至 10 项")
            if basic is None or view_name(basic) not in {f"设计{number}" for number in designs}:
                raise InvalidDocument(f"{DESIGN_BRIEF} 的基本设计须引用一项已有设计")
        elif basic is not None:
            raise InvalidDocument(f"{DESIGN_BRIEF} 的基本设计缺少对应设计视图")
        if suites and len(suites) < 2:
            raise InvalidDocument("成套产品须包含至少两件产品")


@dataclass(frozen=True)
class Filing:
    title: Paragraph
    claims: tuple[Claim, ...]
    description: tuple[Paragraph | Heading | Table, ...]
    abstract: tuple[Paragraph, ...]
    figures: tuple[Figure, ...]

    def validate(self, patent_type="invention"):
        for name, present in (
            ("权利要求书", bool(self.claims)),
            ("说明书", self.title.has_text() and any(isinstance(block, (Paragraph, Table)) for block in self.description)),
            ("说明书摘要", any(paragraph.has_text() for paragraph in self.abstract)),
        ):
            if not present:
                raise InvalidDocument(f"缺少必要分册或正文 {name}")
        for index, claim in enumerate(self.claims, 1):
            if claim.number != index:
                raise UnsupportedDocument(f"{claim.paragraph.location} 权利要求应从 1 开始顺序编号")
            if not claim.paragraph.has_text():
                raise InvalidDocument(f"{claim.paragraph.location} 权利要求正文为空")
        if patent_type == "utility-model" and not self.figures:
            raise InvalidDocument("实用新型缺少必要的说明书附图")
        for index, figure in enumerate(self.figures, 1):
            label = "".join(figure.label.split())
            if label != f"图{index}":
                raise InvalidDocument(f"{figure.location} 说明书附图实际为{label}，应为图{index}")
            if not all(0 < size <= MAX_FIGURE_EMU for size in (figure.width_emu, figure.height_emu)):
                raise UnsupportedDocument(f"{figure.location} 附图显示尺寸超出支持范围")
        paragraphs = [self.title, *self.abstract, *(claim.paragraph for claim in self.claims)]
        for block in self.description:
            if isinstance(block, Paragraph):
                paragraphs.append(block)
            elif isinstance(block, Table):
                paragraphs.extend(paragraph for row in block.rows for cell in row for paragraph in cell)
        for paragraph in paragraphs:
            for part in paragraph.parts:
                text = part if isinstance(part, str) else part.text if isinstance(part, Script) else ""
                if INVALID_XML_CHAR.search(text):
                    raise InvalidDocument(f"{paragraph.location} 正文含有 XML 无法表示的字符")
