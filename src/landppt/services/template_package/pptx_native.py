"""Build a visual plan from supported OOXML objects before asking a model to draw.

Unsupported paint/geometry raises a diagnostic, rather than silently producing a
successful but incomplete replica. The ordinary validation gate remains final.
"""

import colorsys
from io import BytesIO

from lxml import etree
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.oxml.ns import qn


def theme_xml(slide):
    master = slide.slide_layout.slide_master
    relation = next(
        (r for r in master.part.rels.values() if r.reltype.endswith("/theme")), None
    )
    if relation is None:
        raise ValueError("原稿缺少主题")
    return etree.fromstring(relation.target_part.blob)


def theme_palette(slide):
    master = slide.slide_layout.slide_master
    root = theme_xml(slide)
    palette = {}
    for scheme in root.iter(qn("a:clrScheme")):
        for node in scheme:
            if len(node):
                value = (
                    node[0].get("val")
                    if node[0].tag == qn("a:srgbClr")
                    else node[0].get("lastClr")
                )
                if value:
                    palette[etree.QName(node).localname] = "#" + value
    mapping = master._element.find(qn("p:clrMap"))
    for alias, target in (mapping.attrib.items() if mapping is not None else ()):
        if target in palette:
            palette[alias] = palette[target]
    return palette


def color_value(node, palette):
    if node is None:
        raise ValueError("原稿颜色缺失")
    kind = etree.QName(node).localname
    if kind == "schemeClr":
        value = palette.get(node.get("val"))
    elif kind == "srgbClr":
        value = "#" + node.get("val", "")
    elif kind == "sysClr":
        value = "#" + node.get("lastClr", "")
    else:
        value = None
    if not value or len(value) != 7:
        raise ValueError("原稿使用暂不支持的颜色定义")
    channels = list(bytes.fromhex(value[1:]))
    for transform in node:
        operation = etree.QName(transform).localname
        amount = float(transform.get("val", "100000")) / 100000
        if operation in {"lumMod", "lumOff"}:
            hue, lightness, saturation = colorsys.rgb_to_hls(
                *(c / 255 for c in channels)
            )
            lightness = (
                lightness * amount if operation == "lumMod" else lightness + amount
            )
            channels = [
                c * 255
                for c in colorsys.hls_to_rgb(hue, max(0, min(1, lightness)), saturation)
            ]
        elif operation == "shade":
            channels = [c * amount for c in channels]
        elif operation == "tint":
            channels = [c * amount + 255 * (1 - amount) for c in channels]
        elif operation == "alpha" and amount == 1:
            continue
        else:
            raise ValueError(f"原稿颜色变换 {operation} 需要视觉重建")
    return "#" + "".join(f"{max(0, min(255, round(c))):02X}" for c in channels)


def solid_paint(properties, palette, fallback=None):
    if properties is None:
        return fallback
    if properties.find(qn("a:noFill")) is not None:
        return "none"
    fill = properties.find(qn("a:solidFill"))
    if fill is not None and len(fill):
        return color_value(fill[0], palette)
    if any(
        properties.find(qn("a:" + kind)) is not None
        for kind in ("gradFill", "blipFill", "pattFill", "grpFill")
    ):
        raise ValueError("原稿含复杂填充，需要视觉重建")
    return fallback


def native_visual_plan(prs, slide, component):
    from .pptx_import import _emu_box, _fit, _frame_kind, walk_shapes

    scale, dx, dy = _fit(prs)
    # The current plan contract uses a complete 16:9 canvas. Letterboxed pages
    # continue through the multimodal path instead of stretching their design.
    if abs(dx) > 1 or abs(dy) > 1:
        raise ValueError("非 16:9 原稿需要保留留白的视觉重建")
    palette = theme_palette(slide)
    background = "#FFFFFF"
    for owner in (slide, slide.slide_layout, slide.slide_layout.slide_master):
        bg = owner._element.find(qn("p:cSld")).find(qn("p:bg"))
        if bg is not None:
            properties = bg.find(qn("p:bgPr"))
            if properties is None:
                ref = bg.find(qn("p:bgRef"))
                styles = theme_xml(slide).find(".//" + qn("a:bgFillStyleLst"))
                index = int(ref.get("idx", "0")) - 1001 if ref is not None else -1
                if styles is None or not 0 <= index < len(styles) or not len(ref):
                    raise ValueError("原稿使用未知主题背景引用，需要视觉重建")
                fill = styles[index]
                if fill.tag != qn("a:solidFill") or not len(fill):
                    raise ValueError("主题背景为复杂填充，需要视觉重建")
                palette["phClr"] = color_value(ref[0], palette)
                background = color_value(fill[0], palette)
                break
            background = solid_paint(properties, palette, background)
            break
    decorations, images = [], []
    inherited = (
        (slide.slide_layout.slide_master, slide.slide_layout)
        if slide._element.get("showMasterSp", "1") != "0"
        else ()
    )
    objects = [
        item
        for owner in (*inherited, slide)
        for item in walk_shapes(owner.shapes)
        if owner is slide or not item[0].is_placeholder
    ]
    for shape, transform, turned in objects:
        if any(
            node.get(attribute) in {"1", "true"}
            for node in shape._element.xpath("./p:grpSpPr/a:xfrm|./p:spPr/a:xfrm")
            for attribute in ("flipH", "flipV")
        ):
            raise ValueError("翻转对象需要视觉重建")
        if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
            continue
        if (
            turned
            or _frame_kind(shape)
            or shape._element.xpath('.//a:xfrm[@flipH="1" or @flipV="1"]')
        ):
            raise ValueError(f"对象“{shape.name}”需要视觉重建")
        if shape._element.tag == qn("p:pic"):
            from PIL import Image
            from .pptx_import import raster_asset

            box = _emu_box(shape, transform)
            if (
                box is None
                or box[2] * box[3] / prs.slide_width / prs.slide_height > 0.03
            ):
                raise ValueError("大幅固定图片需要视觉重建，不能作为截图底图")
            if shape._element.xpath('.//a:prstGeom[@prst!="rect"]'):
                raise ValueError("异形图片需要视觉重建")
            try:
                with Image.open(BytesIO(shape.image.blob)) as image:
                    width, height = image.size
                    if width * height > 16_000_000:
                        raise ValueError("图标像素超过限制")
                    image = image.crop(
                        (
                            round(width * shape.crop_left),
                            round(height * shape.crop_top),
                            round(width * (1 - shape.crop_right)),
                            round(height * (1 - shape.crop_bottom)),
                        )
                    )
                    out = BytesIO()
                    image.convert("RGBA").save(out, format="PNG")
                asset = raster_asset(out.getvalue())
            except (OSError, ValueError) as exc:
                raise ValueError(f"图标“{shape.name}”需要视觉重建：{exc}") from exc
            images.append(
                (
                    asset,
                    [
                        dx + box[0] * scale,
                        dy + box[1] * scale,
                        box[2] * scale,
                        box[3] * scale,
                    ],
                )
            )
            continue
        properties = shape._element.find(qn("p:spPr"))
        style = shape._element.find(qn("p:style"))
        fill_ref = None if style is None else style.find(qn("a:fillRef"))
        inherited = None
        explicit_fill = properties is not None and any(
            properties.find(qn("a:" + paint)) is not None
            for paint in ("solidFill", "noFill", "gradFill", "blipFill", "pattFill")
        )
        if (
            not explicit_fill
            and fill_ref is not None
            and fill_ref.get("idx", "0") != "0"
            and len(fill_ref)
        ):
            if fill_ref.get("idx") != "1":
                raise ValueError("主题复杂填充需要视觉重建")
            styles = theme_xml(slide).find(".//" + qn("a:fillStyleLst"))
            if (
                styles is None
                or not len(styles)
                or styles[0].tag != qn("a:solidFill")
                or not len(styles[0])
            ):
                raise ValueError("主题填充不是纯色，需要视觉重建")
            palette["phClr"] = color_value(fill_ref[0], palette)
            inherited = color_value(styles[0][0], palette)
        fill = solid_paint(properties, palette, inherited or "none")
        line = None if properties is None else properties.find(qn("a:ln"))
        if line is None and style is not None:
            line_ref = style.find(qn("a:lnRef"))
            if line_ref is not None and line_ref.get("idx", "0") != "0":
                raise ValueError("继承的图形边框需要视觉重建")
        stroke = solid_paint(line, palette, "none")
        if fill == "none" and stroke == "none":
            continue
        effects = None if properties is None else properties.find(qn("a:effectLst"))
        if effects is not None:
            if len(effects):
                raise ValueError("原稿阴影或特效需要视觉重建")
        if style is not None:
            effect_ref = style.find(qn("a:effectRef"))
            if effect_ref is not None and effect_ref.get("idx", "0") != "0":
                raise ValueError("原稿主题阴影需要视觉重建")
        if properties is not None and any(
            properties.find(qn("a:" + tag)) is not None
            for tag in ("effectDag", "scene3d", "sp3d")
        ):
            raise ValueError("原稿三维或复合特效需要视觉重建")
        if properties is not None and properties.find(qn("a:custGeom")) is not None:
            raise ValueError(f"自定义图形“{shape.name}”需要视觉重建")
        geometry = None if properties is None else properties.find(qn("a:prstGeom"))
        kind = geometry.get("prst", "rect") if geometry is not None else "rect"
        if kind not in {"rect", "roundRect", "ellipse", "line"}:
            raise ValueError(f"图形 {kind} 需要视觉重建")
        emu = _emu_box(shape, transform)
        if emu is None:
            raise ValueError(f"对象“{shape.name}”缺少位置")
        x, y, width, height = (
            dx + emu[0] * scale,
            dy + emu[1] * scale,
            emu[2] * scale,
            emu[3] * scale,
        )
        # Negative/off-canvas geometry must be handled explicitly by the AI.
        if x < 0 or y < 0 or x + width > 1281 or y + height > 721:
            raise ValueError("原稿装饰超出画布，需要视觉重建")
        width, height = min(width, 1280 - x), min(height, 720 - y)
        if kind == "line" and width > 1 and height > 1:
            raise ValueError("斜线需要视觉重建")
        decorations.append(
            {
                "kind": "ellipse" if kind == "ellipse" else "rect",
                "x": x,
                "y": y,
                "width": max(1, width),
                "height": max(1, height),
                "fill": stroke if kind == "line" else fill,
                "stroke": "none" if kind == "line" else stroke,
                "stroke_width": (
                    max(0, float(line.get("w", "12700")) * scale)
                    if line is not None
                    else 0
                ),
                "radius": (
                    min(width, height) * shape.adjustments[0]
                    if kind == "roundRect"
                    else 0
                ),
            }
        )
    nodes = {
        n.get("id"): n
        for n in etree.fromstring(component.svg.encode()).iter()
        if n.get("id")
    }
    slots = []
    for slot in component.slots:
        node = nodes[slot.node_id]
        size = float(node.get("font-size", "18"))
        slots.append(
            {
                "node_id": slot.node_id,
                "x": float(node.get("x")),
                "y": float(node.get("y")) - (size if slot.kind == "text" else 0),
                "width": float(
                    node.get("data-box-w" if slot.kind == "text" else "width")
                ),
                "height": float(
                    node.get("data-box-h" if slot.kind == "text" else "height")
                ),
                "font_size": size,
                "color": node.get("fill", "#182F36"),
                "bold": node.get("font-weight") == "bold",
                "align": node.get("data-align", "left"),
                "valign": node.get("data-valign", "top"),
                "crop": node.get("data-crop", "rect"),
            }
        )
    return {
        "background": background,
        "decorations": decorations,
        "slots": slots,
    }, images


def reconstruct_native(prs, slide, component):
    from .pptx_vision import draw_visual_plan

    plan, images = native_visual_plan(prs, slide, component)
    result = draw_visual_plan(component, plan)
    root = etree.fromstring(result.svg.encode())
    original = {
        n.get("id"): n
        for n in etree.fromstring(component.svg.encode()).iter()
        if n.get("id")
    }
    for node in root.iter():
        source = original.get(node.get("id"))
        if (
            source is not None
            and node.tag.endswith("}text")
            and source.get("font-family")
        ):
            node.set("font-family", source.get("font-family"))
    # Only explicitly retained small source icons enter the fixed layer. Full
    # source pages and large content photographs always take the visual path.
    first_slot = next(
        (n for n in root if n.get("id") in {s.node_id for s in component.slots}), None
    )
    insertion = list(root).index(first_slot) if first_slot is not None else len(root)
    for asset, (x, y, width, height) in images:
        node = etree.Element(
            "{http://www.w3.org/2000/svg}image",
            {
                "x": str(x),
                "y": str(y),
                "width": str(width),
                "height": str(height),
                "data-asset": asset.id,
                "data-role": "background",
                "preserveAspectRatio": "none",
            },
        )
        root.insert(insertion, node)
        insertion += 1
    return result.model_copy(
        update={"svg": etree.tostring(root, encoding="unicode")}
    ), tuple(asset for asset, _ in images)
