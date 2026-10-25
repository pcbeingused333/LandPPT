"""Faithful artwork layers with measured, editable source text and pictures.

Binding and typesetting are local operations. Complex artwork stays in the
text-cleared source layer instead of being approximated by a model's primitives.
"""

import base64
from collections import Counter
from io import BytesIO

from lxml import etree
from PIL import Image

from .pptx_import import ImportPage, _ORDINAL, pair_blocks
from .pptx_vision import draw_visual_plan


def assign_regions(candidates, shapes):
    """Find the smallest painted card surrounding several source text objects."""
    texts = [c for c in candidates if c["kind"] == "text"]
    regions = []
    for shape in shapes:
        x, y, width, height = shape["box"]
        if (
            shape["picture"]
            or not shape["visible"]
            or width < 120
            or height < 70
            or not 0.015 <= width * height / (1280 * 720) <= 0.45
        ):
            continue
        members = [
            t
            for t in texts
            if t["suggested"] != "title"
            and not _ORDINAL.fullmatch(t["text"].strip())
            and x <= t["box"][0] < x + width - 8
            and y <= t["box"][1] < y + height - 8
            and t["box"][0] + t["box"][2] <= x + width + 2
        ]
        if len(members) >= 2:
            regions.append((width * height, shape, members))
    for _, shape, members in sorted(regions, key=lambda item: item[0]):
        for text in members:
            text.setdefault("region", dict(id=shape["id"], box=shape["box"]))


def automatic_page(number, candidates):
    texts = [c for c in candidates if c["kind"] == "text"]
    if not texts:
        raise ValueError("没有可编辑文字，未把整页图片作为模板")
    title = next((c for c in texts if c["suggested"] == "title"), texts[0])
    bindings, groups = {}, {}
    remaining = []
    for candidate in candidates:
        key = candidate["id"]
        if candidate is title:
            bindings[key] = "title"
        elif candidate["kind"] == "image":
            # Tiny icons are artwork. Content photographs/diagrams remain
            # replaceable and are removed from the source artwork layer.
            x, y, width, height = candidate["box"]
            behind_text = any(
                x < t["box"][0] + t["box"][2] / 2 < x + width
                and y < t["box"][1] + t["box"][3] / 2 < y + height
                for t in texts
            )
            bindings[key] = (
                "image"
                if width * height > 1280 * 720 * 0.03 and not behind_text
                else "fixed"
            )
        elif _ORDINAL.fullmatch(candidate["text"].strip()):
            bindings[key] = "fixed"
        else:
            # Do not freeze short English labels or small body copy merely
            # because a typography heuristic called them decoration.
            remaining.append(candidate)
    cards = {}
    for c in remaining:
        if c.get("region"):
            cards.setdefault(c["region"]["id"], []).append(c)
    for card_id, members in cards.items():
        heading = min(
            members,
            key=lambda c: (round(c["box"][1] / 20), -c["font_size"], c["box"][0]),
        )
        for c in members:
            bindings[c["id"]] = "heading" if c is heading else "body"
            groups[c["id"]] = f"card-{card_id}"
    remaining = [c for c in remaining if not c.get("region")]
    for number_, (heading, body) in enumerate(pair_blocks(remaining)):
        group = f"point-{number_ + 1}"
        if heading:
            bindings[heading["id"]] = "heading"
            groups[heading["id"]] = group
        text = body["text"].strip()
        short = not heading and len(text) <= 16 and "\n" not in text
        bindings[body["id"]] = "heading" if short else "body"
        groups[body["id"]] = group
    title_text = title["text"]
    family = "cover" if number == 1 else "points"
    if any(word in title_text for word in ("总结", "结语", "谢谢", "Thank")):
        family = "summary"
    elif any(word in title_text for word in ("对比", "比较", " vs ")):
        family = "comparison"
    return ImportPage(slide=number, family=family, bindings=bindings, groups=groups)


def merge_replica_groups(selected, groups):
    from .pptx_vision import merge_visual_groups

    # Within a source card, short badge text and paragraphs form one semantic
    # point. Reading order is preserved and no source word is discarded.
    selected = sorted(
        selected, key=lambda row: (round(row[0]["box"][1] / 16), row[0]["box"][0])
    )
    body_styles = {}
    for c, role in selected:
        if role != "body":
            continue
        key = groups.get(c["id"], c["id"])
        if key not in body_styles or len(c["text"]) > len(body_styles[key]["text"]):
            body_styles[key] = c
    merged = merge_visual_groups(selected, groups)
    points = {
        groups.get(c["id"], c["id"])
        for c, role in merged
        if role in {"heading", "body"}
    }
    if len(points) > 20:
        raise ValueError(
            f"当前页含 {len(points)} 个独立要点，超过可复用版式的 20 个上限；"
            "请先拆页，或分析页面后调整分组"
        )
    for candidate, role in merged:
        candidate["replica_label"] = True
        group = groups.get(candidate["id"], "")
        if not group.startswith("card-") or not candidate.get("region"):
            continue
        x, y, width, height = candidate["region"]["box"]
        heading = next(
            (c for c, r in merged if r == "heading" and groups.get(c["id"]) == group),
            None,
        )
        if role == "body" and heading:
            # Keep the icon and title, use the existing card interior for copy.
            top = heading["box"][1] + min(24, heading["font_size"]) * 1.4 + 8
            candidate["text"] = " · ".join(candidate["text"].splitlines())
            candidate["box"] = [x + 14, top, width - 28, max(18, y + height - 10 - top)]
            candidate["font_size"] = 18
            style = body_styles[group]
            for attribute in ("font", "color", "bold"):
                candidate[attribute] = style[attribute]
            candidate["valign"] = "top"
            candidate["align"] = "left"
            candidate["artwork_box"] = candidate["box"]
        elif role == "heading":
            candidate["font_size"] = min(24, candidate["font_size"])
            candidate["box"][2] = max(
                candidate["box"][2], x + width - 12 - candidate["box"][0]
            )
            candidate["box"][3] = max(28, candidate["font_size"] * 1.4)
    return merged


def clean_card_interiors(component, selected, background):
    """Clear orphaned badges/diagram marks behind newly grouped card copy.

    Only a demonstrably flat card interior is covered. Gradients/illustrations
    are never replaced with an invented flat color. Card edges and header icons
    stay in the original layer.
    """
    root = etree.fromstring(component.svg.encode())
    node = next(n for n in root if n.get("id") == "background")
    bx, by, bw, bh = [float(node.get(k)) for k in ("x", "y", "width", "height")]
    with Image.open(BytesIO(base64.b64decode(background.data))) as image:
        image = image.convert("RGB")
        for candidate, role in selected:
            if role != "body" or not candidate.get("artwork_box"):
                continue
            x, y, width, height = candidate["artwork_box"]
            crop = image.crop(
                (
                    round((x - bx) / bw * image.width),
                    round((y - by) / bh * image.height),
                    round((x + width - bx) / bw * image.width),
                    round((y + height - by) / bh * image.height),
                )
            ).resize((96, 96), Image.Resampling.NEAREST)
            count, color = max(crop.getcolors(96 * 96), key=lambda entry: entry[0])
            edges = Counter(
                crop.getpixel((x_, y_)) for x_ in (0, 95) for y_ in range(1, 95)
            )
            edge_color, edge_count = edges.most_common(1)[0]
            if edge_count >= 188 * 0.75:
                color = edge_color
            elif count < 96 * 96 * 0.6:
                raise ValueError(
                    "卡片内部包含复杂图案，无法无损调整正文；请改用 AI 重新设计"
                )
            cover = etree.Element(
                f"{{{etree.QName(root).namespace}}}rect",
                {
                    "x": str(x),
                    "y": str(y),
                    "width": str(width),
                    "height": str(height),
                    "fill": "#" + "".join(f"{v:02x}" for v in color),
                    "data-role": "background",
                },
            )
            root.insert(2, cover)
    return component.model_copy(
        update={"svg": etree.tostring(root, encoding="unicode")}
    )


def fit_replica(component):
    """Use final-renderer metrics without repainting the original artwork.

    Only the source slots are replaced. The measured result keeps all private
    assets, font families and reference metadata; no screenshot enters a slot.
    """
    root = etree.fromstring(component.svg.encode())
    originals = {n.get("id"): n for n in root.iter() if n.get("id")}
    slots = []
    for slot in component.slots:
        node = originals[slot.node_id]
        text = slot.kind == "text"
        size = float(node.get("font-size", "18"))
        slots.append(
            dict(
                node_id=slot.node_id,
                x=float(node.get("x")),
                y=float(node.get("y")) - (size if text else 0),
                width=float(node.get("data-box-w" if text else "width")),
                height=float(node.get("data-box-h" if text else "height")),
                font_size=size,
                color=node.get("fill", "#182F36"),
                bold=node.get("font-weight") == "bold",
                align=node.get("data-align", "left"),
                valign=node.get("data-valign", "top"),
                crop=node.get("data-crop", "rect"),
            )
        )
    fitted = draw_visual_plan(
        component, dict(background="#FFFFFF", decorations=[], slots=slots), strict=False
    )
    fitted_root = etree.fromstring(fitted.svg.encode())
    ids = {s.node_id for s in component.slots}
    for node in fitted_root:
        if node.get("id") not in ids:
            continue
        original = originals[node.get("id")]
        if original.get("font-family"):
            node.set("font-family", original.get("font-family"))
        original.getparent().replace(original, node)
    return component.model_copy(
        update={"svg": etree.tostring(root, encoding="unicode")}
    )
