"""Style replica: learn a deck's look, then draw every page family from it.

Source pages are not slots. Real decks put two-character labels, thirty points
or illustrated cards on single pages; binding those boxes caps success at what
each page happens to fit. Instead this reads the deck's palette, fonts, title
position, content area and card style, renders one clean artwork layer per
page role (edge decoration and full-page backgrounds only) and lays out the
eight package families on it with capacity-sized slots. No model is called.
"""

from __future__ import annotations

import colorsys
import re
import uuid
from collections import Counter
from io import BytesIO
from statistics import median

import fitz
from lxml import etree
from PIL import Image
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.oxml.ns import qn

from . import pptx_import
from .pptx_import import (
    IDENTITY,
    SVG,
    _analyze,
    _candidates,
    _emu_box,
    _fit,
    _frame_kind,
    _is_visible,
    extract_page,
    page_png,
    raster_asset,
    walk_shapes,
)
from .schemas import (
    ContentBlock,
    ItemRange,
    Metric,
    PackageTheme,
    PageComponent,
    PageContent,
    Slot,
    TemplatePackage,
    VisualBrief,
)
from .service import validate_package

FALLBACK_FONTS = "Arial,'Microsoft YaHei','Noto Sans CJK SC',sans-serif"
DEFAULT_STAGE = (80.0, 200.0, 1120.0, 460.0)
#: Spare stage height above a content group; slightly above center reads balanced.
OPTICAL = 0.42
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


# ---------------------------------------------------------------- colors


def _rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def _hex(rgb):
    return "#" + "".join(f"{max(0, min(255, round(v))):02X}" for v in rgb[:3])


def _luminance(color):
    def channel(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(v) for v in _rgb(color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def readable(color, background, minimum=4.5):
    """Keep the source color when legible; otherwise the better of black/white."""
    if color and _HEX.match(color) and contrast(color, background) >= minimum:
        return color.upper()
    return max(("#FFFFFF", "#111111"), key=lambda c: contrast(c, background))


def _saturation(color):
    return colorsys.rgb_to_hsv(*(v / 255 for v in _rgb(color)))[1]


def _mix(a, b, share):
    return _hex([x * (1 - share) + y * share for x, y in zip(_rgb(a), _rgb(b))])


def _mode(values, default):
    values = [v for v in values if v]
    return Counter(values).most_common(1)[0][0] if values else default


def theme_accent(prs):
    """accent1 of the master's theme when it is an explicit sRGB value."""
    try:
        part = prs.slide_master.part.part_related_by(
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme"
        )
        root = etree.fromstring(part.blob)
    except (KeyError, etree.XMLSyntaxError):
        return None
    value = root.xpath(
        "string(.//a:clrScheme/a:accent1/a:srgbClr/@val)",
        namespaces={"a": "http://schemas.openxmlformats.org/drawingml/2006/main"},
    )
    return f"#{value.upper()}" if re.fullmatch(r"[0-9a-fA-F]{6}", value) else None


class _Sampler:
    """Read rendered pixels in 1280×720 canvas coordinates."""

    def __init__(self, prs, page):
        scale, self.dx, self.dy = _fit(prs)
        self.image = Image.open(BytesIO(page_png(page))).convert("RGB")
        self.ratio = self.image.width / (prs.slide_width * scale)

    def at(self, x, y):
        px = min(self.image.width - 1, max(0, round((x - self.dx) * self.ratio)))
        py = min(self.image.height - 1, max(0, round((y - self.dy) * self.ratio)))
        return _hex(self.image.getpixel((px, py)))

    def edge(self, x, y):
        """One device pixel inside a shape outline, past anti-aliasing."""
        return self.at(x + 1.5 / self.ratio, y)

    def region(self, box):
        """Dominant color over a grid; one pixel may land on a stray mark."""
        x, y, w, h = box
        return _mode(
            [
                self.at(x + w * (i + 0.5) / 8, y + h * (j + 0.5) / 4)
                for i in range(8)
                for j in range(4)
            ],
            "#FFFFFF",
        )


# ---------------------------------------------------------------- analysis


def _box_bottom(c):
    return c["box"][1] + c["box"][3]


def _content_slide(index, visible):
    return len(visible) < 3 or 0 < visible.index(index) < len(visible) - 1


def analyze_style(prs, doc, visible):
    """Deck-wide measurements from every visible page; nothing is per-page."""
    titles, subtitles, bodies, extents, cards, pages = [], [], [], [], [], {}
    palette = Counter()
    for index in visible:
        slide, page = prs.slides[index], doc[index]
        candidates, _ = _candidates(prs, slide, page)
        texts = [c for c in candidates if c["kind"] == "text"]
        palette.update(c["color"].upper() for c in texts)
        title = next((c for c in texts if c["suggested"] == "title"), None)
        subtitle = next((c for c in texts if c["suggested"] == "subtitle"), None)
        pages[index] = dict(title=title, subtitle=subtitle, shapes=0)
        if not _content_slide(index, visible) or title is None:
            continue
        titles.append(title)
        if subtitle:
            subtitles.append(subtitle)
        header = _box_bottom(subtitle or title)
        content = [
            c["box"]
            for c in texts
            if c is not title
            and c is not subtitle
            and c["box"][1] >= header - 4
            and _box_bottom(c) <= 720 * 0.92
        ]
        bodies.extend(
            c
            for c in texts
            if c is not title and c is not subtitle and c["suggested"] == "body"
        )
        data = extract_page(prs, slide, page)
        pages[index]["shapes"] = len(data["shapes"])
        for shape in data["shapes"]:
            x, y, w, h = shape["box"]
            share = w * h / (1280 * 720)
            if (
                shape["visible"]
                and 0.002 <= share <= 0.6
                and y >= header - 4
                and min(x, y, 1280 - x - w, 720 - y - h) > 8
            ):
                content.append(shape["box"])
        if content:
            extents.append(
                (
                    min(b[0] for b in content),
                    min(b[1] for b in content),
                    max(b[0] + b[2] for b in content),
                    max(b[1] + b[3] for b in content),
                    header,
                )
            )
        hosts = {c["region"]["id"]: c["region"]["box"] for c in texts if c.get("region")}
        if hosts:
            sampler = _Sampler(prs, page)
            for shape_id, box in hosts.items():
                cards.append(_card_style(slide, shape_id, box, sampler))
    measured = _summarize(visible, titles, subtitles, bodies, extents, cards, pages)
    measured["palette"] = palette
    return measured


def _card_style(slide, shape_id, box, sampler):
    x, y, w, h = box
    fill = _mode(
        [
            sampler.at(x + w * 0.04, y + h * 0.5),
            sampler.at(x + w * 0.96, y + h * 0.5),
            sampler.at(x + w * 0.5, y + h * 0.95),
            sampler.at(x + w * 0.3, y + h * 0.92),
        ],
        None,
    )
    stroke = sampler.edge(x, y + h / 2)
    radius = 0.0
    for shape, _, _ in walk_shapes(slide.shapes):
        if str(shape.shape_id) != str(shape_id):
            continue
        geometry = shape._element.find(".//" + qn("a:prstGeom"))
        preset = geometry.get("prst") if geometry is not None else "rect"
        if preset == "roundRect":
            guide = geometry.find(".//" + qn("a:gd"))
            adjust = 16667
            if guide is not None and guide.get("fmla", "").startswith("val "):
                adjust = int(guide.get("fmla")[4:] or adjust)
            radius = min(w, h) * adjust / 100000
        elif preset != "rect":
            radius = 12.0
    return dict(fill=fill, stroke=stroke, radius=min(32.0, radius))


def _summarize(visible, titles, subtitles, bodies, extents, cards, pages):
    cover_index = visible[0]
    content_pool = [i for i in visible if _content_slide(i, visible) and pages[i]["title"]]
    if titles:
        tx = median(t["box"][0] for t in titles)
        ty = median(t["box"][1] for t in titles)
        size = median(t["font_size"] for t in titles)
    else:
        tx, ty, size = 80.0, 60.0, 40.0
    size = min(48.0, max(30.0, size))
    # The page whose title sits where most titles sit carries the shared artwork.
    content_index = (
        min(
            content_pool,
            key=lambda i: (
                abs(pages[i]["title"]["box"][1] - ty)
                + abs(pages[i]["title"]["box"][0] - tx),
                pages[i]["shapes"],
            ),
        )
        if content_pool
        else cover_index
    )
    sub_size = None
    if subtitles and len(subtitles) * 2 >= max(1, len(titles)):
        sub_size = min(24.0, max(20.0, median(s["font_size"] for s in subtitles)))
    header_bottom = ty + size * 1.3 + (sub_size * 1.4 + 10 if sub_size else 0)
    if extents:
        left = median(e[0] for e in extents)
        top = median(e[1] for e in extents)
        right = median(e[2] for e in extents)
        bottom = median(e[3] for e in extents)
    else:
        left, top, right, bottom = (
            DEFAULT_STAGE[0],
            DEFAULT_STAGE[1],
            DEFAULT_STAGE[0] + DEFAULT_STAGE[2],
            DEFAULT_STAGE[1] + DEFAULT_STAGE[3],
        )
    left = min(160.0, max(48.0, min(left, tx)))
    right = max(1120.0, min(1232.0, right))
    top = min(300.0, max(top, header_bottom + 20))
    bottom = min(680.0, max(bottom, top + 340))
    title_colors = [t["color"] for t in titles] or [
        pages[cover_index]["title"]["color"] if pages[cover_index]["title"] else None
    ]
    weights = Counter()
    for c in bodies:
        weights[c["color"]] += len(c["text"])
    card_rows = [c for c in cards if c["fill"]]
    card = None
    if card_rows:
        fill = _mode([c["fill"] for c in card_rows], None)
        same = [c for c in card_rows if c["fill"] == fill]
        card = dict(
            fill=fill,
            stroke=_mode([c["stroke"] for c in same], fill),
            radius=median(c["radius"] for c in same),
        )
    return dict(
        cover=cover_index,
        content=content_index,
        title=dict(
            x=tx,
            y=ty,
            size=size,
            color=_mode(title_colors, None),
            font=_mode([t["font"] for t in titles], None),
        ),
        subtitle_size=sub_size,
        subtitle_color=_mode([s["color"] for s in subtitles], None),
        body_color=weights.most_common(1)[0][0] if weights else None,
        body_font=_mode([c["font"] for c in bodies], None),
        stage=(left, top, right - left, bottom - top),
        header=(tx, ty, right - tx, header_bottom - ty),
        card=card,
        cover_title=pages[cover_index]["title"],
        cover_subtitle=pages[cover_index]["subtitle"],
    )


def cover_geometry(measured):
    """Cover title box (x, y, width, size).

    A cover title in the header band sat above artwork that is now removed;
    the group then moves to the optical center instead of leaving it empty.
    """
    cover, sx = measured["cover_title"], measured["stage"][0]
    size = min(64.0, max(44.0, cover["font_size"] if cover else 56.0))
    cx = min(cover["box"][0] if cover else sx, 1280 - 760.0)
    cw = min(1280 - cx - 64, 960.0)
    group = size * 2.6 + 12 + 26 * 1.4 * 2
    cy = cover["box"][1] if cover and cover["box"][1] >= 200 else (720 - group) / 2 - 20
    return cx, min(cy, 720 - group - 72), cw, size


def _vivid(color):
    h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in _rgb(color)))
    return s >= 0.35 and v >= 0.45


def pick_accent(prs, measured):
    """A color the deck actually uses for emphasis, not the theme default.

    Generated decks rarely set theme colors; Office's accent1 then appears in
    no page. Prefer a vivid title color, then the most used vivid text color.
    """
    title = measured["title"]["color"]
    if title and _vivid(title):
        return title.upper()
    vivid = [(n, c) for c, n in measured["palette"].items() if _vivid(c)]
    if vivid:
        return max(vivid)[1]
    if measured["card"] and _vivid(measured["card"]["stroke"]):
        return measured["card"]["stroke"]
    return theme_accent(prs) or "#B7462D"


def build_tokens(prs, measured, cover_art, content_art):
    """Colors are checked against the cleaned artwork they will sit on."""
    background = content_art.region(measured["stage"])
    card = measured["card"]
    surface = card["fill"] if card else background
    accent = pick_accent(prs, measured)
    foreground = readable(measured["body_color"], surface)
    if card and contrast(card["fill"], background) < 1.08 and card["stroke"] == card["fill"]:
        # An invisible card would read as floating text; give it an outline.
        card = {**card, "stroke": _mix(card["fill"], foreground, 0.18)}
    header = content_art.region(measured["header"])
    muted = measured["subtitle_color"] or _mix(foreground, surface, 0.35)
    if contrast(muted, header) < 3:
        muted = _mix(readable(None, header), header, 0.3)
    cx, cy, cw, size = cover_geometry(measured)
    cover = cover_art.region((cx, cy, cw, size * 2.6 + 12 + 26 * 2.8))
    cover_title = (measured["cover_title"] or {}).get("color") or measured["title"]["color"]
    cover_muted = measured["subtitle_color"] or muted
    return dict(
        background=background,
        surface=surface,
        foreground=foreground,
        heading=readable(foreground, surface),
        title=readable(measured["title"]["color"], header, 3),
        cover_title=readable(cover_title, cover, 3),
        cover_muted=readable(cover_muted, cover, 3),
        cover_accent=readable(accent, cover, 2.2),
        accent=readable(accent, surface, 2.2),
        accent_on_bg=readable(accent, background, 2.2),
        muted=muted,
        title_font=f"{measured['title']['font']},{FALLBACK_FONTS}"
        if measured["title"]["font"]
        else FALLBACK_FONTS,
        body_font=f"{measured['body_font']},{FALLBACK_FONTS}"
        if measured["body_font"]
        else FALLBACK_FONTS,
        card=card,
    )


# ---------------------------------------------------------------- artwork


def _overlaps(a, b):
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


def _strip_slide(prs, slide, stage, header):
    """Keep page backgrounds and edge decoration; content-area objects go."""
    scale, dx, dy = _fit(prs)
    sx, sy, sw, sh = stage
    for shape in list(slide.shapes):
        emu = _emu_box(shape, IDENTITY)
        element = shape._element
        if emu is None or _frame_kind(shape):
            element.getparent().remove(element)
            continue
        x, y = dx + emu[0] * scale, dy + emu[1] * scale
        w, h = emu[2] * scale, emu[3] * scale
        share = w * h / (1280 * 720)
        group = shape.shape_type == MSO_SHAPE_TYPE.GROUP
        texts = [
            s
            for s, _, _ in walk_shapes([shape])
            if getattr(s, "has_text_frame", False) and s.text_frame.text.strip()
        ]
        paints = group or _is_visible(element)
        inside_w = max(0.0, min(x + w, sx + sw) - max(x, sx))
        inside_h = max(0.0, min(y + h, sy + sh) - max(y, sy))
        in_stage = inside_w * inside_h / max(1.0, w * h)
        edge = min(x, y, 1280 - x - w, 720 - y - h) <= 8
        keep = paints and (
            share >= 0.6
            or (edge and (min(w, h) <= 40 or in_stage <= 0.15))
            or (
                y + h <= sy - 4
                and not texts
                and share <= 0.05
                and not _overlaps((x, y, w, h), header)
            )
        )
        if not keep:
            element.getparent().remove(element)
            continue
        for item in texts:
            for paragraph in item.text_frame.paragraphs:
                paragraph.clear()


def render_artwork(normalized, roles, stage, header):
    """One render for all roles, in role order; source pages stay untouched."""
    prs = Presentation(BytesIO(normalized))
    ids = prs.slides._sldIdLst
    nodes = list(ids)
    for node in nodes:
        ids.remove(node)
    for index in roles:
        ids.append(nodes[index])
    for slide in prs.slides:
        slide._element.set("show", "1")
        _strip_slide(prs, slide, stage, header)
        for container in (slide, slide.slide_layout, slide.slide_layout.slide_master):
            for field in list(container._element.xpath(".//a:fld")):
                if field.get("type", "").startswith(("slidenum", "datetime")):
                    field.getparent().remove(field)
    output = BytesIO()
    prs.save(output)
    pdf, _ = pptx_import.render_pdf(output.getvalue())
    return fitz.open(stream=pdf, filetype="pdf")


# ---------------------------------------------------------------- layouts


class _Layout:
    def __init__(self, tokens, header, background_id, fit):
        self.t = tokens
        self.header = header
        self.root = etree.Element(f"{{{SVG}}}svg", nsmap={None: SVG}, viewBox="0 0 1280 720")
        etree.SubElement(
            self.root,
            f"{{{SVG}}}rect",
            x="0",
            y="0",
            width="1280",
            height="720",
            fill=tokens["background"],
        )
        scale, dx, dy = fit
        self.node(
            "image",
            id="background",
            x=dx,
            y=dy,
            width=1280 - 2 * dx,
            height=720 - 2 * dy,
            **{"data-asset": background_id, "data-role": "background"},
        )
        self.slots = []

    def node(self, tag, **attributes):
        return etree.SubElement(
            self.root,
            f"{{{SVG}}}{tag}",
            {k: str(round(v, 1) if isinstance(v, float) else v) for k, v in attributes.items()},
        )

    def text(self, field, x, y, w, h, size, *, color=None, bold=False, font=None,
             align="left", valign="top", required=None, max_chars=240):
        node_id = f"slot-{len(self.slots)}"
        if required is None:
            required = field == "title" or field.startswith("metrics[")
        self.slots.append(
            Slot(node_id=node_id, field=field, required=required, max_chars=max_chars)
        )
        self.node(
            "text",
            id=node_id,
            x=x,
            y=y + size,
            fill=color or self.t["foreground"],
            **{
                "font-size": size,
                "font-family": font or self.t["body_font"],
                "font-weight": "bold" if bold else "normal",
                "data-box-w": w,
                "data-box-h": h,
                "data-align": align,
                "data-valign": valign,
                "text-anchor": "start",
            },
        )

    def label(self, value, x, y, size, color):
        node = self.node(
            "text",
            x=x,
            y=y + size,
            fill=color,
            **{"font-size": size, "font-family": self.t["title_font"], "font-weight": "bold"},
        )
        node.text = value

    def card(self, x, y, w, h, *, accent=False):
        card = self.t["card"]
        if card is None:
            # Decks without cards: an accent rule marks each group instead.
            self.node("rect", x=x, y=y, width=min(56.0, w), height=4, fill=self.t["accent_on_bg"])
            return
        self.node(
            "rect",
            x=x,
            y=y,
            width=w,
            height=h,
            rx=card["radius"],
            fill=card["fill"],
            stroke=self.t["accent"] if accent else card["stroke"],
            **{"stroke-width": 2 if accent else 1},
        )

    def title_block(self):
        h = self.header
        self.text(
            "title",
            h["x"],
            h["y"],
            h["w"],
            h["size"] * 1.3,
            h["size"],
            color=self.t["title"],
            bold=True,
            font=self.t["title_font"],
            max_chars=60,
        )
        if h["sub"]:
            self.text(
                "subtitle",
                h["x"],
                h["y"] + h["size"] * 1.3 + 8,
                h["w"],
                h["sub"] * 1.4,
                h["sub"],
                color=self.t["muted"],
                max_chars=80,
            )

    def point(self, index, x, y, w, h, *, heading=26, body=20, pad=24, chars=90,
              accent=False):
        self.card(x, y, w, h, accent=accent)
        inner = w - 2 * pad if self.t["card"] else w
        left = x + pad if self.t["card"] else x
        top = y + pad if self.t["card"] else y + 20
        self.text(
            f"blocks[{index}].heading",
            left,
            top,
            inner,
            heading * 1.4,
            heading,
            color=self.t["accent"] if accent else self.t["heading"],
            bold=True,
            max_chars=24,
        )
        body_top = top + heading * 1.4 + 12
        self.text(
            f"blocks[{index}].body",
            left,
            body_top,
            inner,
            max(body * 1.4, y + h - (pad if self.t["card"] else 0) - body_top),
            body,
            max_chars=chars,
        )


    def component(self, component_id, family, description, example, *, source,
                  reference, blocks=0, metrics=0, images=0):
        return PageComponent(
            id=component_id,
            family=family,
            description=description,
            svg=etree.tostring(self.root, encoding="unicode"),
            slots=tuple(self.slots),
            blocks=ItemRange(minimum=blocks, maximum=blocks),
            metrics=ItemRange(minimum=metrics, maximum=metrics),
            images=ItemRange(minimum=images, maximum=images),
            examples=(example,),
            reference_asset=reference,
            source_slide=source,
        )


def point_height(width, chars, *, heading=26, body=20, pad=24):
    """Card height that the body budget fills, so cards never stretch hollow."""
    per_line = max(1, int((width - 2 * pad) // body))
    lines = -(-chars // per_line)
    return 2 * pad + heading * 1.4 + 12 + lines * body * 1.4 + body * 0.3


_HEADINGS = ("明确目标", "验证效果", "持续改进", "沉淀经验", "扩大范围")
_BODY = "以实际需求为起点，明确责任与验收标准，结合反馈调整下一步行动。"


def _blocks(count, kind="point"):
    return tuple(
        ContentBlock(id=f"b{i + 1}", kind=kind, heading=_HEADINGS[i % 5], body=_BODY)
        for i in range(count)
    )


def capacity_examples(component):
    """Keep the preview copy and exercise short and near-capacity replacements."""
    from ..slide.package_generation.capacity import slot_limits

    budgets = slot_limits(component)
    examples = [component.examples[0]]
    for label, longer in (("short", False), ("long", True)):
        payload = component.examples[0].model_dump(mode="json")
        payload["slide_id"] = label
        for slot in component.slots:
            if slot.kind != "text":
                continue
            length = min(80 if longer else 4, max(1, int(budgets[slot.field] * 0.65)))
            sample = ("示例内容" * 21)[:length]
            match = re.fullmatch(r"(blocks|metrics)\[(\d+)\]\.(\w+)", slot.field)
            if match:
                payload[match[1]][int(match[2])][match[3]] = sample
            else:
                payload[slot.field] = sample
        examples.append(PageContent.model_validate(payload))
    return component.model_copy(update={"examples": tuple(examples)})


def _columns(stage, count, gap=24):
    x, _, w, _ = stage
    width = (w - gap * (count - 1)) / count
    return [x + i * (width + gap) for i in range(count)], width


def build_layouts(tokens, measured, fit, assets):
    """Ten capacity-sized components; each is validated on its own later."""
    stage = measured["stage"]
    sx, sy, sw, sh = stage
    t = measured["title"]
    header = dict(
        x=t["x"],
        y=t["y"],
        w=sx + sw - t["x"],
        size=t["size"],
        sub=measured["subtitle_size"],
    )
    cards = tokens["card"] is not None
    layouts = []

    def content(name, family, description, example, draw, **ranges):
        page = _Layout(tokens, header, assets["content_bg"], fit)
        page.title_block()
        draw(page)
        layouts.append(
            page.component(
                name,
                family,
                description,
                example,
                source=measured["content"] + 1,
                reference=assets["content_ref"],
                **ranges,
            )
        )

    cx, cy, cw, size = cover_geometry(measured)
    for family, description, title, subtitle, scale in (
        ("cover", "演示开场", "让每一次表达都有清晰的方向", "从内容出发，以结构组织观点", 1.0),
        ("section", "章节分隔", "从想法走向行动", "第二章 · 建立可验证的实践路径", 0.85),
    ):
        page = _Layout(tokens, header, assets["cover_bg"], fit)
        font = round(size * scale)
        page.node("rect", x=cx, y=cy - 28, width=64, height=6, fill=tokens["cover_accent"])
        page.text("title", cx, cy, cw, font * 2.6, font, color=tokens["cover_title"],
                  bold=True, font=tokens["title_font"], max_chars=40)
        page.text("subtitle", cx, cy + font * 2.6 + 12, cw, 26 * 1.4 * 2, 26,
                  color=tokens["cover_muted"], max_chars=60)
        layouts.append(
            page.component(
                family,
                family,
                description,
                PageContent(slide_id=family, title=title, subtitle=subtitle),
                source=measured["cover"] + 1,
                reference=assets["cover_ref"],
            )
        )

    def row(page, count, chars, *, gap=24, accent=None, heading=26, body=20, pad=24,
            offset=0.0):
        xs, width = _columns(stage, count, gap)
        h = min(sh - offset, point_height(width, chars, heading=heading, body=body, pad=pad))
        top = sy + offset + (sh - offset - h) * OPTICAL
        for i, x in enumerate(xs):
            page.point(i, x, top, width, h, heading=heading, body=body, pad=pad,
                       chars=chars, accent=i == accent)
        return xs, top

    content("points_3", "points", "三个并列观点，各有说明",
            PageContent(slide_id="points_3", title="把目标转化为可执行的步骤", blocks=_blocks(3)),
            lambda page: row(page, 3, 90, accent=0), blocks=3)

    def points4(page):
        xs, width = _columns(stage, 2)
        h = min((sh - 24) / 2, point_height(width, 80, pad=20))
        top = sy + (sh - 2 * h - 24) * OPTICAL
        for i in range(4):
            page.point(i, xs[i % 2], top + (i // 2) * (h + 24), width, h, pad=20, chars=80)

    content("points_4", "points", "四个并列观点，两行两列",
            PageContent(slide_id="points_4", title="四个方面共同支撑目标", blocks=_blocks(4)),
            points4, blocks=4)

    content("comparison_2", "comparison", "两个方案、状态或立场的对比",
            PageContent(slide_id="comparison_2", title="用一致的标准比较不同路径",
                        relation="comparison", blocks=_blocks(2, "comparison")),
            lambda page: row(page, 2, 120, gap=40, accent=1), blocks=2)

    for count, chars in ((3, 80), (4, 60), (5, 44)):
        def process(page, count=count, chars=chars):
            marker = 22.0
            body = 20 if count < 5 else 18
            xs, top = row(page, count, chars, heading=24, body=body, pad=18,
                          offset=marker * 2 + 20)
            line_y = top - 20 - marker
            page.node("line", x1=xs[0] + marker, y1=line_y, x2=xs[-1] + marker, y2=line_y,
                      stroke=tokens["accent_on_bg"], **{"stroke-width": 2})
            for i, x in enumerate(xs):
                page.node("circle", cx=x + marker, cy=line_y, r=marker,
                          fill=tokens["accent_on_bg"])
                page.label(str(i + 1), x + marker - 7, line_y - 13, 22,
                           readable(None, tokens["accent_on_bg"]))

        content(f"process_{count}", "process", f"{count}个按顺序推进的阶段",
                PageContent(slide_id=f"process_{count}", title="分阶段推进，让结果可以验证",
                            relation="sequence", blocks=_blocks(count, "step")),
                process, blocks=count)

    def image(page):
        width = sw * 0.42
        h = min(sh, 360.0)
        top = sy + (sh - h) * OPTICAL
        page.point(0, sx, top, width, h, chars=140)
        page.slots.append(Slot(node_id="visual", field="visual_briefs[0].id", kind="image"))
        page.node("image", id="visual", x=sx + width + 32, y=top, width=sw - width - 32,
                  height=h, **{"data-crop": "rounded"})

    content("image_1", "image", "一幅配图与一段解释，图片为必需素材",
            PageContent(slide_id="image_1", title="让配图为观点提供具体语境",
                        blocks=_blocks(1, "paragraph"),
                        visual_briefs=(VisualBrief(id="visual1", brief="团队围绕白板讨论实施路径"),)),
            image, blocks=1, images=1)

    def metrics(page):
        xs, width = _columns(stage, 3)
        pad = 28 if cards else 0
        h = 2 * pad + 84 + 8 + 34 + 16 + 22 * 1.4 * 2
        y = sy + (sh - h) * OPTICAL
        for i, x in enumerate(xs):
            page.card(x, y, width, h, accent=i == 0)
            page.text(f"metrics[{i}].value", x + pad, y + pad, width - 2 * pad, 84, 64,
                      color=tokens["accent"], bold=True, font=tokens["title_font"], max_chars=8)
            page.text(f"metrics[{i}].unit", x + pad, y + pad + 92, width - 2 * pad, 34, 22,
                      color=tokens["muted"], required=False, max_chars=10)
            page.text(f"metrics[{i}].label", x + pad, y + pad + 142, width - 2 * pad,
                      22 * 1.4 * 2, 22, max_chars=30)

    content("metrics_3", "metrics", "三个有来源的关键指标",
            PageContent(slide_id="metrics_3", title="用数据回答关键问题",
                        subtitle="演示数据，仅用于版式预览" if measured["subtitle_size"] else "",
                        relation="evidence", source_refs=("demo",),
                        metrics=tuple(
                            Metric(id=f"m{i + 1}", label=label, value=value, unit=unit,
                                   source_refs=("demo",))
                            for i, (label, value, unit) in enumerate(
                                (("示例项目数", "12", "项"), ("示例验证项", "36", "项"),
                                 ("示例完成率", "90", "%")))
                        )),
            metrics, metrics=3)

    def summary(page):
        gap, pad = 20, (24 if cards else 0)
        h = min((sh - gap * 2) / 3, 112.0)
        y0 = sy + (sh - (h * 3 + gap * 2)) * OPTICAL
        for i in range(3):
            y = y0 + i * (h + gap)
            page.card(sx, y, sw, h, accent=i == 0)
            page.label(f"0{i + 1}", sx + pad, y + (h - 36) / 2, 36, tokens["accent"])
            page.text(f"blocks[{i}].heading", sx + pad + 72, y + (h - 34) / 2, sw * 0.28, 34,
                      24, color=tokens["heading"], bold=True, max_chars=16)
            body_x = sx + pad + 72 + sw * 0.28 + 24
            page.text(f"blocks[{i}].body", body_x, y + (h - 56) / 2, sx + sw - pad - body_x,
                      56, 20, max_chars=70)

    content("summary_3", "summary", "三项结论与行动建议",
            PageContent(slide_id="summary_3", title="让结论推动下一步行动", relation="summary",
                        blocks=_blocks(3, "action")),
            summary, blocks=3)
    return layouts


# ---------------------------------------------------------------- entry


def style_replicate_pptx(data, name, progress=None):
    """Two renders (source, artwork), deterministic layouts, per-layout validation."""
    normalized, prs, doc, _ = _analyze(data, progress)
    warnings, failures = [], []
    try:
        visible = [i for i, s in enumerate(prs.slides) if s._element.get("show") != "0"]
        if not visible:
            raise ValueError("原稿没有可见页面")
        if progress:
            progress("style", f"正在从 {len(visible)} 页提取配色、字体、标题位置与卡片样式")
        measured = analyze_style(prs, doc, visible)
        if measured["card"] is None:
            warnings.append("原稿未识别到可复用的卡片样式，版式改用强调色分隔线组织内容")
        if abs(prs.slide_width / prs.slide_height - 16 / 9) > 0.01:
            warnings.append("原稿不是 16:9，将等比居中放入 1280×720 画布并留白")
        roles = [measured["cover"]]
        if measured["content"] != measured["cover"]:
            roles.append(measured["content"])
        if progress:
            progress("background", "正在渲染去除内容后的原稿装饰层")
        assets = {}
        with render_artwork(normalized, roles, measured["stage"], measured["header"]) as art:
            if len(art) != len(roles):
                raise ValueError("装饰层页数不匹配，已停止")
            backgrounds = [raster_asset(page_png(page)) for page in art]
            tokens = build_tokens(
                prs, measured, _Sampler(prs, art[0]), _Sampler(prs, art[len(art) - 1])
            )
            leftover = {
                line.strip()
                for page in art
                for line in page.get_text().splitlines()
                if line.strip()
            }
        if leftover:
            warnings.append(
                "装饰层保留了母版中的固定文字：" + "、".join(sorted(leftover)[:5])
                + "。如不需要，请在原稿母版中删除后重新导入"
            )
        references = [raster_asset(page_png(doc[i])) for i in roles]
        for asset in (*backgrounds, *references):
            assets[asset.id] = asset
        ids = dict(
            cover_bg=backgrounds[0].id,
            content_bg=backgrounds[-1].id,
            cover_ref=references[0].id,
            content_ref=references[-1].id,
        )
        components = []
        for layout in build_layouts(tokens, measured, _fit(prs), ids):
            if progress:
                progress("validate", f"正在校验版式 {layout.id}")
            try:
                checked = capacity_examples(layout)
                validate_package(
                    TemplatePackage(
                        contract_version=2,
                        package_id="style-check",
                        version=1,
                        name=name,
                        components=(checked,),
                        assets=tuple(assets.values()),
                    )
                )
                components.append(checked)
            except ValueError as exc:
                failures.append({"layout": layout.id, "error": str(exc)})
        if not components:
            raise ValueError(
                "没有版式通过校验：" + "；".join(f"{f['layout']}：{f['error']}" for f in failures)
            )
        used = {c.reference_asset for c in components} | {
            n.get("data-asset")
            for c in components
            for n in etree.fromstring(c.svg.encode()).iter()
            if n.get("data-asset")
        }
        package = TemplatePackage(
            contract_version=2,
            package_id="pptx_" + uuid.uuid4().hex,
            version=1,
            name=name,
            description="从本地 PPTX 风格复刻；原稿配色、字体与装饰 + 程序生成的八类版式",
            theme=PackageTheme(
                background=tokens["background"],
                foreground=readable(tokens["foreground"], tokens["background"]),
                accent=tokens["accent_on_bg"],
                muted=tokens["muted"],
            ),
            components=tuple(components),
            assets=tuple(a for key, a in assets.items() if key in used),
        )
        return package, {
            "failures": failures,
            "warnings": warnings,
            "partial": bool(failures),
            "methods": [{"layout": c.id, "method": "style"} for c in components],
            "style": {
                "stage": [round(v) for v in measured["stage"]],
                "source_pages": [i + 1 for i in roles],
                "card": tokens["card"],
                "colors": {
                    k: tokens[k] for k in ("background", "foreground", "title", "accent", "muted")
                },
            },
        }
    finally:
        doc.close()
