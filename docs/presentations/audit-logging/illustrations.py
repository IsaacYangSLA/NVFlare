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

"""Editable ink-style illustrations for the audit presentation.

All artwork consists of native PowerPoint shapes, connectors and freeforms.
Coordinates accepted by ``draw_icon`` are in inches. No fonts or image assets
are required, and the illustrations contain no hidden or visible text.
"""

from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.oxml.xmlchemy import OxmlElement
from pptx.util import Inches, Pt


def _tint(color, paper, amount=0.14):
    """Blend an accent into the page color for a restrained illustration wash."""
    a = RGBColor.from_string(color)
    b = RGBColor.from_string(paper)
    return "".join(f"{round(x * amount + y * (1 - amount)):02X}" for x, y in zip(a, b))


class _Drawing:
    def __init__(self, slide, x, y, size, ink, accent, paper):
        self.slide = slide
        self.x, self.y, self.size = x, y, size
        self.ink, self.accent, self.paper = ink, accent, paper
        self.wash = _tint(accent, paper)
        self.weight = max(1.0, min(2.4, size * 1.35))

    def shape(self, kind, x, y, w, h, fill=None, stroke=None, weight=None):
        shape = self.slide.shapes.add_shape(
            kind,
            Inches(self.x + x * self.size),
            Inches(self.y + y * self.size),
            Inches(w * self.size),
            Inches(h * self.size),
        )
        if fill:
            shape.fill.solid()
            shape.fill.fore_color.rgb = RGBColor.from_string(fill)
        else:
            shape.fill.background()
        if stroke:
            shape.line.color.rgb = RGBColor.from_string(stroke)
            shape.line.width = Pt(weight or self.weight)
        else:
            shape.line.fill.background()
        shape._element.spPr.append(OxmlElement("a:effectLst"))
        if kind == MSO_SHAPE.ROUNDED_RECTANGLE:
            shape.adjustments[0] = 0.12
        return shape

    def line(self, x1, y1, x2, y2, color=None, weight=None):
        shape = self.slide.shapes.add_connector(
            MSO_CONNECTOR.STRAIGHT,
            Inches(self.x + x1 * self.size),
            Inches(self.y + y1 * self.size),
            Inches(self.x + x2 * self.size),
            Inches(self.y + y2 * self.size),
        )
        shape.line.color.rgb = RGBColor.from_string(color or self.ink)
        shape.line.width = Pt(weight or self.weight)
        shape._element.spPr.append(OxmlElement("a:effectLst"))
        return shape

    def polygon(self, points, fill=None, stroke=None):
        coords = [(round(x * 1000), round(y * 1000)) for x, y in points]
        builder = self.slide.shapes.build_freeform(*coords[0], scale=Inches(self.size) / 1000)
        builder.add_line_segments(coords[1:], close=True)
        shape = builder.convert_to_shape(Inches(self.x), Inches(self.y))
        if fill:
            shape.fill.solid()
            shape.fill.fore_color.rgb = RGBColor.from_string(fill)
        else:
            shape.fill.background()
        if stroke:
            shape.line.color.rgb = RGBColor.from_string(stroke)
            shape.line.width = Pt(self.weight)
        else:
            shape.line.fill.background()
        shape._element.spPr.append(OxmlElement("a:effectLst"))
        return shape

    def circle(self, cx, cy, radius, fill=None, stroke=None):
        return self.shape(MSO_SHAPE.OVAL, cx - radius, cy - radius, radius * 2, radius * 2, fill, stroke)

    def box(self, x, y, w, h, fill=None, stroke=None, rounded=False):
        kind = MSO_SHAPE.ROUNDED_RECTANGLE if rounded else MSO_SHAPE.RECTANGLE
        return self.shape(kind, x, y, w, h, fill, stroke)

    def tick(self, x, y, size=0.2):
        self.line(x, y + size * 0.45, x + size * 0.35, y + size * 0.8, self.accent, self.weight * 1.5)
        self.line(x + size * 0.35, y + size * 0.8, x + size, y, self.accent, self.weight * 1.5)

    def halo(self):
        self.circle(0.52, 0.52, 0.4, self.wash)
        self.circle(0.88, 0.2, 0.024, self.accent)
        self.line(0.12, 0.21, 0.18, 0.15, self.accent)
        self.line(0.12, 0.15, 0.18, 0.21, self.accent)


def _document(d):
    d.polygon([(0.27, 0.13), (0.62, 0.13), (0.78, 0.29), (0.78, 0.87), (0.27, 0.87)], d.paper, d.ink)
    d.polygon([(0.62, 0.13), (0.62, 0.29), (0.78, 0.29)], d.wash, d.ink)
    d.line(0.36, 0.36, 0.64, 0.36, d.accent, d.weight * 1.8)
    for y, end in ((0.48, 0.68), (0.59, 0.63), (0.7, 0.67)):
        d.circle(0.36, y, 0.012, d.accent)
        d.line(0.42, y, end, y)
    d.line(0.37, 0.79, 0.54, 0.79, d.accent)


def _server(d):
    for y in (0.19, 0.39, 0.59):
        d.box(0.22, y, 0.58, 0.15, d.paper, d.ink, rounded=True)
        d.circle(0.3, y + 0.075, 0.019, d.accent)
        d.line(0.41, y + 0.075, 0.69, y + 0.075)
    d.line(0.5, 0.75, 0.5, 0.86)
    d.line(0.26, 0.86, 0.75, 0.86)
    for x in (0.26, 0.5, 0.75):
        d.circle(x, 0.86, 0.025, d.paper, d.ink)


def _hospital(d):
    d.box(0.16, 0.43, 0.22, 0.42, d.paper, d.ink)
    d.box(0.65, 0.43, 0.22, 0.42, d.paper, d.ink)
    d.box(0.34, 0.18, 0.35, 0.67, d.paper, d.ink)
    d.shape(MSO_SHAPE.MATH_PLUS, 0.425, 0.25, 0.18, 0.18, d.accent)
    d.box(0.445, 0.63, 0.14, 0.22, d.wash, d.ink)
    for x in (0.22, 0.73):
        for y in (0.52, 0.68):
            d.box(x, y, 0.065, 0.065, d.wash, d.ink)
    for x in (0.41, 0.56):
        d.box(x, 0.5, 0.065, 0.065, d.wash, d.ink)
    d.line(0.12, 0.85, 0.91, 0.85)


def _pharma(d):
    d.polygon(
        [(0.4, 0.14), (0.63, 0.14), (0.63, 0.42), (0.84, 0.79), (0.8, 0.87), (0.23, 0.87), (0.19, 0.79), (0.4, 0.42)],
        d.paper,
        d.ink,
    )
    d.polygon([(0.33, 0.61), (0.7, 0.61), (0.8, 0.8), (0.23, 0.8)], d.wash)
    d.line(0.33, 0.61, 0.7, 0.61, d.accent)
    d.line(0.36, 0.14, 0.67, 0.14)
    for x, y, r in ((0.44, 0.73, 0.022), (0.59, 0.7, 0.031), (0.51, 0.52, 0.025)):
        d.circle(x, y, r, None, d.accent)
    for y in (0.27, 0.35):
        d.line(0.54, y, 0.63, y)


def _finance(d):
    d.polygon([(0.13, 0.33), (0.51, 0.12), (0.89, 0.33)], d.paper, d.ink)
    d.circle(0.51, 0.25, 0.035, d.accent)
    d.box(0.17, 0.35, 0.68, 0.065, d.wash, d.ink)
    for x in (0.24, 0.47, 0.7):
        d.box(x, 0.42, 0.08, 0.32, d.paper, d.ink)
        d.line(x - 0.025, 0.45, x + 0.105, 0.45)
        d.line(x - 0.025, 0.74, x + 0.105, 0.74)
    d.box(0.17, 0.76, 0.68, 0.06, d.wash, d.ink)
    d.line(0.11, 0.87, 0.91, 0.87)


def _shield(d):
    d.polygon(
        [(0.51, 0.13), (0.8, 0.25), (0.77, 0.61), (0.68, 0.76), (0.51, 0.89), (0.34, 0.76), (0.25, 0.61), (0.22, 0.25)],
        d.paper,
        d.ink,
    )
    d.polygon(
        [(0.51, 0.23), (0.7, 0.31), (0.68, 0.57), (0.61, 0.7), (0.51, 0.78), (0.41, 0.7), (0.34, 0.57), (0.32, 0.31)],
        d.wash,
    )
    d.tick(0.36, 0.41, 0.3)
    d.line(0.8, 0.7, 0.89, 0.77, d.accent)
    d.line(0.81, 0.82, 0.85, 0.86, d.accent)


def _link(d):
    a = d.shape(MSO_SHAPE.ROUNDED_RECTANGLE, 0.18, 0.25, 0.43, 0.24, d.paper, d.ink)
    a.rotation = 325
    b = d.shape(MSO_SHAPE.ROUNDED_RECTANGLE, 0.43, 0.49, 0.43, 0.24, d.paper, d.ink)
    b.rotation = 325
    d.line(0.41, 0.61, 0.64, 0.44, d.accent, d.weight * 2)
    d.circle(0.3, 0.7, 0.025, d.accent)
    d.line(0.16, 0.68, 0.22, 0.65, d.accent)
    d.line(0.74, 0.27, 0.81, 0.22, d.accent)
    d.circle(0.76, 0.79, 0.025, d.accent)


def _archive(d):
    d.box(0.2, 0.31, 0.61, 0.52, d.paper, d.ink)
    d.box(0.16, 0.23, 0.69, 0.14, d.wash, d.ink)
    d.box(0.35, 0.47, 0.3, 0.12, d.paper, d.ink)
    d.line(0.42, 0.53, 0.58, 0.53, d.accent)
    d.line(0.28, 0.73, 0.45, 0.73)
    d.line(0.28, 0.77, 0.4, 0.77)
    d.line(0.25, 0.18, 0.55, 0.18)
    d.line(0.29, 0.13, 0.59, 0.13)


def _warning(d):
    d.polygon([(0.5, 0.16), (0.88, 0.82), (0.13, 0.82)], d.paper, d.ink)
    d.box(0.475, 0.38, 0.05, 0.23, d.accent)
    d.circle(0.5, 0.71, 0.027, d.accent)
    d.line(0.18, 0.44, 0.11, 0.42, d.accent)
    d.line(0.22, 0.3, 0.16, 0.25, d.accent)
    d.line(0.8, 0.34, 0.85, 0.28, d.accent)


def _clock(d):
    d.circle(0.51, 0.51, 0.32, d.paper, d.ink)
    for x1, y1, x2, y2 in (
        (0.51, 0.23, 0.51, 0.29),
        (0.51, 0.73, 0.51, 0.79),
        (0.23, 0.51, 0.29, 0.51),
        (0.73, 0.51, 0.79, 0.51),
    ):
        d.line(x1, y1, x2, y2)
    d.line(0.51, 0.51, 0.51, 0.34)
    d.line(0.51, 0.51, 0.65, 0.59, d.accent, d.weight * 1.5)
    d.circle(0.51, 0.51, 0.025, d.accent)
    d.line(0.24, 0.17, 0.17, 0.22, d.accent)


def _process(d):
    d.line(0.32, 0.33, 0.69, 0.33)
    d.line(0.69, 0.33, 0.69, 0.69)
    d.line(0.69, 0.69, 0.32, 0.69)
    for x, y in ((0.17, 0.2), (0.56, 0.2), (0.56, 0.56), (0.17, 0.56)):
        d.box(x, y, 0.25, 0.25, d.paper, d.ink, rounded=True)
        d.circle(x + 0.125, y + 0.125, 0.035, d.accent)
    d.line(0.45, 0.29, 0.5, 0.33, d.accent)
    d.line(0.5, 0.33, 0.45, 0.37, d.accent)


def _checklist(d):
    d.box(0.24, 0.15, 0.55, 0.72, d.paper, d.ink, rounded=True)
    d.box(0.39, 0.11, 0.25, 0.1, d.wash, d.ink, rounded=True)
    for y in (0.33, 0.52, 0.71):
        d.box(0.32, y, 0.1, 0.1, d.paper, d.ink)
        d.tick(0.33, y - 0.005, 0.095)
        d.line(0.48, y + 0.05, 0.7, y + 0.05)


_ICONS = {
    "document": _document,
    "server": _server,
    "hospital": _hospital,
    "pharma": _pharma,
    "finance": _finance,
    "shield": _shield,
    "link": _link,
    "archive": _archive,
    "warning": _warning,
    "clock": _clock,
    "process": _process,
    "checklist": _checklist,
}


def draw_icon(slide, kind, x, y, w, h, ink="20221F", accent="2D6A63", paper="F7F5EE"):
    """Draw an editable illustration centered in the requested inch-based box.

    Supported kinds are document, server, hospital, pharma, finance, shield,
    link, archive, warning, clock, process and checklist. Returns the tuple of
    added native shapes so callers can inspect their bounds or group them.
    """
    if kind not in _ICONS:
        raise ValueError(f"Unknown illustration kind: {kind}")
    if w <= 0 or h <= 0:
        raise ValueError("Illustration width and height must be positive")
    size = min(w, h)
    d = _Drawing(slide, x + (w - size) / 2, y + (h - size) / 2, size, ink, accent, paper)
    before = len(slide.shapes)
    d.halo()
    _ICONS[kind](d)
    return tuple(slide.shapes[i] for i in range(before, len(slide.shapes)))
