# Copyright (c) 2026, NVIDIA CORPORATION.  All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Build the reviewed deck with an editable notebook-inspired editorial design."""
import json
import re
from pathlib import Path

from illustrations import draw_icon
from PIL import Image, ImageFont
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.oxml.xmlchemy import OxmlElement
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parent
PAPER = "F7F5EE"
INK = "20221F"
MUTED = "666A60"
RULE = "D8DACE"
FONT_BODY = "Carlito"
FONT_HEADING = "Lato"
FONT_CODE = "Cousine"
THEMES = {
    "Existing": ("2D6A63", "E2EBDD"),
    "Industry needs": ("A94F37", "F3E4D8"),
    "Proposed": ("435F83", "E2E9F1"),
    "Published evidence": ("795B3B", "ECE4D6"),
}
FONT_PATH = "/usr/share/fonts/truetype/crosextra/Carlito-Regular.ttf"


def rect(slide, x, y, w, h, fill=PAPER, stroke=None, rounded=False):
    kind = MSO_SHAPE.ROUNDED_RECTANGLE if rounded else MSO_SHAPE.RECTANGLE
    shape = slide.shapes.add_shape(kind, Inches(x), Inches(y), Inches(w), Inches(h))
    shape.fill.solid()
    shape.fill.fore_color.rgb = RGBColor.from_string(fill)
    if stroke:
        shape.line.color.rgb = RGBColor.from_string(stroke)
        shape.line.width = Pt(0.7)
    else:
        shape.line.fill.background()
    if rounded:
        shape.adjustments[0] = 0.10
    shape._element.spPr.append(OxmlElement("a:effectLst"))
    return shape


def line(slide, x1, y1, x2, y2, color=RULE, width=0.8):
    shape = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    shape.line.color.rgb = RGBColor.from_string(color)
    shape.line.width = Pt(width)
    shape._element.spPr.append(OxmlElement("a:effectLst"))
    return shape


def text(slide, value, x, y, w, h, size=20, color=INK, bold=False, font=FONT_BODY, emphasis=None):
    shape = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    frame = shape.text_frame
    frame.word_wrap = True
    frame.margin_left = frame.margin_right = Inches(0.015)
    frame.margin_top = frame.margin_bottom = 0
    shape._element.spPr.append(OxmlElement("a:effectLst"))
    for i, row in enumerate(value.split("\n")):
        p = frame.paragraphs[0] if i == 0 else frame.add_paragraph()
        p.space_after = Pt(0)
        p.space_before = Pt(0)
        p.line_spacing = 1.10
        p.font.name = font
        p.font.size = Pt(size)
        p.font.bold = bold
        p.font.color.rgb = RGBColor.from_string(color)
        if emphasis and ":" in row:
            prefix, rest = row.split(":", 1)
            first = p.add_run()
            first.text = prefix + ":"
            first.font.bold = True
            first.font.color.rgb = RGBColor.from_string(emphasis)
            p.add_run().text = rest
        else:
            p.text = row
    return shape


def line_count(value, width, size):
    """Estimate body wrapping with the same installed font used by the renderer."""
    font = ImageFont.truetype(FONT_PATH, round(size * 4))
    limit = width * 72 * 4
    count = 0
    for row in value.split("\n"):
        current = ""
        for word in row.split():
            candidate = (current + " " + word).strip()
            if current and font.getlength(candidate) > limit:
                count += 1
                current = word
            else:
                current = candidate
        count += 1
    return count


def frame(slide, s, idx):
    accent, soft = THEMES[s["label"]]
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = RGBColor.from_string(PAPER)
    text(slide, "NVFLARE  /  AUDIT FIELD NOTES", 0.70, 0.39, 8, 0.28, 10, MUTED, True, FONT_HEADING)
    rect(slide, 10.12, 0.33, 2.5, 0.36, soft, rounded=True)
    section = "APPENDIX" if s.get("appendix") else s["label"].upper()
    text(slide, section, 10.28, 0.40, 2.15, 0.20, 9.5, accent, True, FONT_HEADING)
    line(slide, 0.7, 0.81, 12.63, 0.81)
    if s["id"] != 1:
        title_size = 34
        while title_size > 26:
            title_font = ImageFont.truetype("/usr/share/fonts/truetype/lato/Lato-Bold.ttf", round(title_size * 4))
            if title_font.getlength(s["title"]) / 4 <= 11.7 * 72:
                break
            title_size -= 0.5
        text(slide, s["title"], 0.7, 1.03, 11.93, 0.85, title_size, INK, True, FONT_HEADING)
        text(slide, s["takeaway"], 0.7, 2.15, 11.85, 0.65, 20, accent)
    line(slide, 0.7, 7.00, 12.63, 7.00)
    text(slide, f"{idx:02d}", 12.13, 7.10, 0.50, 0.25, 11, accent, True, FONT_HEADING)
    return accent, soft


def callout(slide, value, accent, soft, height=0.37, font_size=13):
    top = 6.88 - height
    rect(slide, 0.7, top, 11.93, height, soft, rounded=True)
    line(slide, 0.82, top + 0.07, 0.82, 6.81, accent, 2)
    text(slide, value, 0.98, top + 0.055, 11.4, height - 0.07, font_size, accent)


def render_table(slide, s, accent, soft):
    data = s["table"]
    bullets = s.get("bullets", [])
    if bullets:
        text(slide, "  •  ".join(bullets), 0.7, 2.91, 11.9, 0.56, 16, MUTED)
    y = {3: 3.58, 9: 3.38}.get(s["id"], 2.95)
    bottom = min(6.35, 6.88 - s.get("callout_height", 0.37) - 0.16) if "callout" in s else 6.6
    rows = [data["headers"]] + data["rows"]
    shape = slide.shapes.add_table(len(rows), len(rows[0]), Inches(0.7), Inches(y), Inches(11.93), Inches(bottom - y))
    table = shape.table
    widths = (
        data.get("column_widths")
        or {
            3: (2.65, 4.1, 5.18),
            6: (3.6, 4.0, 4.33),
            8: (3.0, 4.3, 4.63),
            9: (2.2, 4.45, 5.28),
        }[s["id"]]
    )
    for ci, width in enumerate(widths):
        table.columns[ci].width = Inches(width)
    if "header_height" in data:
        table.rows[0].height = Inches(data["header_height"])
        body_height = (bottom - y - data["header_height"]) / (len(rows) - 1)
        for row in list(table.rows)[1:]:
            row.height = Inches(body_height)
    for ri, row in enumerate(rows):
        for ci, value in enumerate(row):
            cell = table.cell(ri, ci)
            cell.fill.solid()
            fill = soft if ri == 0 else ("FDFCF8" if ri % 2 else "EEEFE7")
            if s["id"] == 8 and ri == len(rows) - 1:
                fill = "F4E1D3"
            cell.fill.fore_color.rgb = RGBColor.from_string(fill)
            cell.margin_left, cell.margin_right = Inches(0.15), Inches(0.13)
            cell.margin_top = cell.margin_bottom = Inches(data.get("cell_margin_y", 0.035))
            cell.text = str(value)
            for p in cell.text_frame.paragraphs:
                p.space_after = Pt(0)
                p.line_spacing = data.get("line_spacing", 1.08)
                p.font.name = FONT_BODY
                p.font.size = Pt(
                    15
                    if ri == 0
                    else data.get("font_size", 15.5 if s["id"] == 6 else 16 if s["id"] in (3, 8, 9) else 17)
                )
                p.font.bold = ri == 0 or ci == 0
                p.font.color.rgb = RGBColor.from_string(accent if ri == 0 else INK)


def render_code(slide, s, accent, soft):
    for j, bullet in enumerate(s.get("bullets", [])):
        text(slide, bullet, 0.88, 2.94 + j * 0.32, 11.7, 0.31, 16.5, INK, emphasis=accent)
        line(slide, 0.71, 3.06 + j * 0.32, 0.78, 3.06 + j * 0.32, accent, 1.5)
    rect(slide, 0.76, 4.31, 11.93, 2.34, "E5E5DA", rounded=True)
    rect(slide, 0.7, 4.25, 11.93, 2.34, "FDFCF9", RULE, rounded=True)
    labels = {4: "THE WRITER  /  PYTHON", 5: "AUDIT.LOG  /  CURRENT TEXT", 11: "ILLUSTRATIVE EVENT  /  JSON"}
    rect(slide, 0.71, 4.26, 11.91, 0.32, soft)
    text(slide, s.get("code_label") or labels[s["id"]], 0.92, 4.33, 10.5, 0.19, 9.5, accent, True, FONT_HEADING)
    size = 13 if s["id"] == 4 else 14.5
    shape = text(slide, s["code"], 0.94, 4.63, 11.36, 1.95, size, INK, font=FONT_CODE)
    # Keep code fully editable; tint comments and quoted strings without changing its text.
    for p in shape.text_frame.paragraphs:
        value = p.text
        p.clear()
        p.line_spacing = 1.0
        for token in re.split(r'("(?:[^"\\]|\\.)*"|#[^\n]*)', value):
            run = p.add_run()
            run.text = token
            run.font.color.rgb = RGBColor.from_string(
                MUTED if token.lstrip().startswith("#") else accent if token.startswith('"') else INK
            )


def render_cover(slide, s, accent, soft):
    # An asymmetric cover leaves the outline visible beside the central question.
    text(slide, s["title"], 0.7, 1.04, 8.1, 1.5, 40, INK, True, FONT_HEADING)
    text(slide, s["takeaway"], 0.7, 2.68, 7.75, 0.75, 20, accent)
    for j, bullet in enumerate(s["bullets"]):
        text(slide, bullet, 0.9, 3.70 + j * 0.66, 7.25, 0.69, 17.5)
        line(slide, 0.71, 3.82 + j * 0.66, 0.78, 3.82 + j * 0.66, accent, 1.6)
    draw_icon(slide, "document", 9.77, 1.23, 1.75, 1.75, accent=accent, paper=PAPER)
    items = [
        ("server", "01  Existing implementation"),
        ("link", "02  Proposed design"),
        ("hospital", "03  Appendix references"),
    ]
    for j, (kind, label) in enumerate(items):
        rect(slide, 8.85, 3.28 + j * 0.94, 3.77, 0.78, soft if j != 1 else "F3E4D8", rounded=True)
        draw_icon(slide, kind, 9.02, 3.40 + j * 0.94, 0.55, 0.55, accent=accent, paper=soft)
        text(slide, label, 9.82, 3.48 + j * 0.94, 2.6, 0.5, 16, INK, True)


def render_gaps(slide, s, accent):
    icons = ("shield", "document", "warning", "archive")
    fills = ("E2EBDD", "F3E4D8", "E2E9F1", "ECE4D6")
    for j, bullet in enumerate(s["bullets"]):
        x, y = 0.7 + (j % 2) * 6.10, 2.98 + (j // 2) * 1.74
        rect(slide, x, y, 5.83, 1.60, fills[j], rounded=True)
        text(slide, f"0{j + 1}", x + 0.2, y + 0.16, 0.5, 0.25, 12, accent, True, FONT_HEADING)
        draw_icon(slide, icons[j], x + 5.12, y + 0.08, 0.38, 0.38, accent=accent, paper=fills[j])
        text(slide, bullet, x + 0.2, y + 0.50, 5.4, 1.04, 18.5, emphasis=accent)


def render_case(slide, s, accent, soft):
    kind = s["case_kind"]
    draw_icon(slide, kind, 0.9, 3.14, 2.5, 2.5, accent=accent, paper=PAPER)
    for j, label in enumerate(s["case_labels"]):
        rect(slide, 1.02, 5.60 + j * 0.36, 2.2, 0.28, soft, rounded=True)
        text(slide, label, 1.15, 5.64 + j * 0.36, 1.95, 0.20, 11, accent, True)
    for j, bullet in enumerate(s["bullets"]):
        y = 2.98 + j * 0.80
        text(slide, bullet, 3.80, y, 8.7, 0.72, 19.5, emphasis=accent)
        if j < len(s["bullets"]) - 1:
            line(slide, 3.8, y + 0.73, 12.62, y + 0.73)


def render_flow(slide, s, accent, soft):
    y = 2.98
    for bullet in s["bullets"]:
        height = max(0.48, line_count(bullet, 5.7, 18) * 18 * 1.1 / 72 + 0.06)
        text(slide, bullet, 0.9, y, 5.65, height, 18, emphasis=accent)
        line(slide, 0.71, y + 0.12, 0.78, y + 0.12, accent, 1.6)
        y += height + 0.16
    labels = s["flow"]
    for j, label in enumerate(labels):
        y = 2.99 + j * 0.72
        rect(slide, 7.05, y, 5.57, 0.59, soft if j % 2 == 0 else "FDFCF9", RULE, rounded=True)
        text(slide, label, 7.25, y + 0.15, 5.14, 0.40, 17, accent, True)
        if s.get("flow_arrows", True) and j < len(labels) - 1:
            line(slide, 9.83, y + 0.60, 9.83, y + 0.69, accent, 1.2)
            line(slide, 9.79, y + 0.65, 9.83, y + 0.69, accent, 1.2)
            line(slide, 9.87, y + 0.65, 9.83, y + 0.69, accent, 1.2)


def render_exhibit(slide, s, accent, soft):
    image_path = ROOT / s["image"]
    left, top, right, bottom = s.get("image_crop", [0, 0, 0, 0])
    with Image.open(image_path) as source:
        source_w, source_h = source.size
    visible_w, visible_h = source_w * (1 - left - right), source_h * (1 - top - bottom)
    scale = min(8.32 / visible_w, 3.43 / visible_h)
    w, h = visible_w * scale, visible_h * scale
    x, y = 0.87 + (8.32 - w) / 2, 3.09 + (3.43 - h) / 2
    rect(slide, 0.7, 2.94, 8.66, 3.75, "FFFFFF", RULE, rounded=True)
    picture = slide.shapes.add_picture(str(image_path), Inches(x), Inches(y), width=Inches(w), height=Inches(h))
    picture.crop_left, picture.crop_top, picture.crop_right, picture.crop_bottom = left, top, right, bottom
    text(slide, "READ THE EVIDENCE", 9.78, 3.02, 2.8, 0.25, 10, accent, True, FONT_HEADING)
    y = 3.52
    for bullet in s["bullets"]:
        height = max(0.62, line_count(bullet, 2.7, 17.5) * 17.5 * 1.1 / 72 + 0.06)
        text(slide, bullet, 9.80, y, 2.72, height, 17.5)
        line(slide, 9.60, y + 0.12, 9.68, y + 0.12, accent, 1.4)
        y += height + 0.20
    text(slide, s.get("image_caption", ""), 0.75, 6.76, 11.8, 0.19, 10, MUTED)


def render_content(slide, s, idx):
    accent, soft = frame(slide, s, idx)
    if s["id"] == 1:
        render_cover(slide, s, accent, soft)
    elif "image" in s:
        render_exhibit(slide, s, accent, soft)
    elif s["id"] == 7:
        render_gaps(slide, s, accent)
    elif "case_kind" in s:
        render_case(slide, s, accent, soft)
    elif "table" in s:
        render_table(slide, s, accent, soft)
    elif "code" in s:
        render_code(slide, s, accent, soft)
    elif "flow" in s:
        render_flow(slide, s, accent, soft)
    if "callout" in s:
        callout(slide, s["callout"], accent, soft, s.get("callout_height", 0.37), s.get("callout_font_size", 13))
    # Explicitly clear theme effects; some renderers inherit a shadow even when
    # an empty local effect list is present.
    for shape in slide.shapes:
        for effect in shape._element.xpath(".//a:effectRef"):
            effect.set("idx", "0")


def build():
    content = []
    for name in (
        "current",
        "industry",
        "healthcare-standards",
        "finance-standards",
        "finance-vendors",
        "proposed",
        "implementation",
    ):
        content.extend(json.loads((ROOT / f"{name}.json").read_text()))
    for name in ("evidence",):
        content.extend(json.loads((ROOT / f"appendix-{name}.json").read_text()))
    content.sort(key=lambda s: s["id"])
    main = [s for s in content if not s.get("appendix")]
    appendix = [s for s in content if s.get("appendix")]
    assert [s["id"] for s in main + appendix] == list(range(1, len(content) + 1)), "Slide IDs must be consecutive"
    deck = Presentation()
    deck.slide_width, deck.slide_height = Inches(13.333), Inches(7.5)
    deck.core_properties.title = "NVFlare audit logging: current implementation, industry practice, proposed design"
    deck.core_properties.subject = "Focused engineering presentation; approximately 25 minutes plus discussion"
    deck.core_properties.author = "NVFlare engineering"
    manuscript = [
        "# NVFlare audit logging — speaker manuscript",
        "",
        "Current implementation → common record meanings → proposed design → appendix: industry references/examples.",
        "",
    ]
    for idx, s in enumerate(main + appendix, 1):
        if s.get("appendix") and idx == len(main) + 1:
            manuscript.extend(["# Appendix — industry standards and examples", ""])
        slide = deck.slides.add_slide(deck.slide_layouts[6])
        render_content(slide, s, idx)
        bullets = s.get("bullets", [])
        sources = s.get("sources", [])
        checked = s.get("source_checked", "2026-11-03")
        dated_sources = [f"{s.get('source_checks', {}).get(u, checked)} — {u}" for u in sources]
        note = f"Slide {idx} | {s['title']}\n\n{s['notes']}\n\nSources (review dates):\n" + "\n".join(dated_sources)
        slide.notes_slide.notes_text_frame.text = note
        manuscript.extend(
            [f"## {idx}. {s['title']} [{s['label']}]", "", s["takeaway"], "", *[f"- {b}" for b in bullets], ""]
        )
        if "image" in s:
            manuscript.extend([f"![Source view]({s['image']})", "", s.get("image_caption", ""), ""])
        if "code" in s:
            manuscript.extend(["```text", s["code"], "```", ""])
        if "flow" in s:
            separator = " → " if s.get("flow_arrows", True) else "\n\n"
            manuscript.extend([separator.join(s["flow"]), ""])
        if "table" in s:
            t = s["table"]
            manuscript.extend(
                ["| " + " | ".join(t["headers"]) + " |", "| " + " | ".join(["---"] * len(t["headers"])) + " |"]
            )
            manuscript.extend("| " + " | ".join(map(str, row)) + " |" for row in t["rows"])
        if "callout" in s:
            manuscript.extend(["", s["callout"], ""])
        manuscript.extend(["", "**Speaker notes**", "", s["notes"], "", *[f"- {u}" for u in dated_sources], ""])
    out = ROOT / "output"
    out.mkdir(exist_ok=True)
    deck.save(out / "nvflare-audit-logging.pptx")
    (ROOT / "speaker-notes.md").write_text("\n".join(manuscript))
    (out / "slides.json").write_text(json.dumps(main + appendix, indent=2))
    print(f"Built {len(main)} main + {len(appendix)} appendix slides")


if __name__ == "__main__":
    build()
