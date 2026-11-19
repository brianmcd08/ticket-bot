"""Charts in Word files: read their data and draw them as pictures.

A chart in a .docx isn't a picture. It's chart XML (series, categories,
numbers) plus an embedded spreadsheet, and mammoth skips it entirely. So
before mammoth runs we:

  1. find each chart in word/document.xml and swap it for a text marker
     ([[docx-chart:N]]) at the same spot;
  2. parse the chart's XML into a Chart (title, categories, series);
  3. draw it with matplotlib in the chart's own colors: each series' (or
     pie slice's) color as set in Word, else the document theme's accent
     colors in Word's order, which is what Word itself shows by default.

docx_import then turns each marker into a picture in the article, so the
chart appears exactly where it was in the document.

Covered: column, bar, line, area, pie, doughnut, scatter, stacked and
100% stacked variants, 3-D variants (drawn flat) and bar+line combos.
Anything else (waterfall, sunburst, maps...) is counted as unsupported so
the writer is told. SmartArt is counted the same way.
"""

import io
import re
import zipfile
from dataclasses import dataclass, field
from typing import Optional
from xml.etree import ElementTree as ET

NS = {
    "c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
}
CHART_URI = "drawingml/2006/chart"
SMARTART_URI = "drawingml/2006/diagram"
CHARTEX_URI = "office/drawing/2014/chartex"  # newer chart types we can't draw
MARKER = "[[docx-chart:{}]]"
MARKER_RE = re.compile(r"\[\[docx-chart:(\d+)\]\]")

# Office's default theme accents, used if a file has no theme of its own.
OFFICE_ACCENTS = ["#4472C4", "#ED7D31", "#A5A5A5", "#FFC000", "#5B9BD5", "#70AD47"]
SCHEME_ALIASES = {"tx1": "dk1", "tx2": "dk2", "bg1": "lt1", "bg2": "lt2"}
TITLE_COLOR = "#404040"  # Word's default chart title gray

# chart XML element -> (kind, bar direction override)
GROUP_TAGS = {
    "barChart": "bar",
    "bar3DChart": "bar",
    "lineChart": "line",
    "line3DChart": "line",
    "areaChart": "area",
    "area3DChart": "area",
    "pieChart": "pie",
    "pie3DChart": "pie",
    "ofPieChart": "pie",
    "doughnutChart": "doughnut",
    "scatterChart": "scatter",
}


@dataclass
class Series:
    name: str
    values: list[Optional[float]]
    xs: Optional[list[Optional[float]]] = None  # scatter only
    color: str = OFFICE_ACCENTS[0]
    point_colors: dict[int, str] = field(default_factory=dict)  # pie slices set one by one


@dataclass
class ChartGroup:
    kind: str  # bar | line | area | pie | doughnut | scatter
    series: list[Series]
    horizontal: bool = False
    grouping: str = "clustered"  # clustered | stacked | percentStacked | standard


@dataclass
class Chart:
    accents: list[str] = field(default_factory=lambda: list(OFFICE_ACCENTS))
    title: str = ""
    categories: list[str] = field(default_factory=list)
    groups: list[ChartGroup] = field(default_factory=list)
    x_label: str = ""
    y_label: str = ""


@dataclass
class ExtractedCharts:
    docx: bytes  # the file with charts swapped for markers
    charts: list[Optional[Chart]]  # by marker number; None = couldn't read
    smartart: int = 0


# ---------- finding charts in the document ----------


def _target(rels_xml: str, rel_id: str) -> Optional[str]:
    match = re.search(rf'<Relationship\b[^>]*\bId="{re.escape(rel_id)}"[^>]*>', rels_xml)
    if not match:
        return None
    target = re.search(r'\bTarget="([^"]+)"', match.group(0))
    return target.group(1) if target else None


def extract_charts(data: bytes) -> ExtractedCharts:
    """Swap every chart in the document for a numbered marker and read
    each chart's data. Files without charts come back unchanged."""
    with zipfile.ZipFile(io.BytesIO(data)) as zin:
        names = zin.namelist()
        if "word/document.xml" not in names:
            return ExtractedCharts(data, [])
        document = zin.read("word/document.xml").decode("utf-8")
        if CHART_URI not in document and CHARTEX_URI not in document and SMARTART_URI not in document:
            return ExtractedCharts(data, [])
        rels = zin.read("word/_rels/document.xml.rels").decode("utf-8") if "word/_rels/document.xml.rels" in names else ""

        charts: list[Optional[Chart]] = []
        smartart = 0
        theme_name = next((n for n in names if re.fullmatch(r"word/theme/theme\d*\.xml", n)), None)
        theme = theme_colors(zin.read(theme_name) if theme_name else None)

        def chart_for(block: str) -> Optional[Chart]:
            if CHARTEX_URI in block and CHART_URI not in block.split(CHARTEX_URI)[0]:
                return None  # a newer chart type (waterfall, sunburst...)
            start = block.find(CHART_URI)
            rel = re.search(r'r:id="([^"]+)"', block[start:])
            target = _target(rels, rel.group(1)) if rel else None
            if not target:
                return None
            path = "word/" + target.lstrip("/").removeprefix("word/") if not target.startswith("/") else target.lstrip("/")
            path = re.sub(r"[^/]+/\.\./", "", path)
            if path not in names:
                return None
            try:
                return parse_chart(zin.read(path), theme)
            except Exception:
                return None

        def swap(match: re.Match) -> str:
            nonlocal smartart
            block = match.group(0)
            if CHART_URI in block or CHARTEX_URI in block:
                charts.append(chart_for(block))
                return f'<w:t xml:space="preserve">{MARKER.format(len(charts) - 1)}</w:t>'
            if SMARTART_URI in block:
                smartart += 1
            return block

        # Newer charts come wrapped in AlternateContent with a text fallback
        # ("This chart isn't available..."); replace the whole wrapper.
        document = re.sub(r"<mc:AlternateContent\b.*?</mc:AlternateContent>", swap, document, flags=re.S)
        document = re.sub(r"<w:drawing\b.*?</w:drawing>", swap, document, flags=re.S)

        if not charts:
            return ExtractedCharts(data, [], smartart)
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                body = document.encode("utf-8") if item.filename == "word/document.xml" else zin.read(item.filename)
                zout.writestr(item, body)
        return ExtractedCharts(out.getvalue(), charts, smartart)


# ---------- colors ----------


def theme_colors(theme_xml: Optional[bytes]) -> dict[str, str]:
    """Named colors from the document theme: accent1..6, dk1, lt1, ..."""
    colors: dict[str, str] = {}
    if not theme_xml:
        return colors
    try:
        root = ET.fromstring(theme_xml)
    except ET.ParseError:
        return colors
    scheme = root.find(".//a:clrScheme", NS)
    if scheme is None:
        return colors
    for slot in scheme:
        name = slot.tag.split("}")[1]
        rgb = slot.find("a:srgbClr", NS)
        sys = slot.find("a:sysClr", NS)
        if rgb is not None:
            colors[name] = "#" + rgb.get("val", "000000")
        elif sys is not None:
            colors[name] = "#" + sys.get("lastClr", "000000")
    return colors


def _hex_to_rgb(color: str) -> tuple[float, float, float]:
    color = color.lstrip("#")
    return tuple(int(color[i : i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def _rgb_to_hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{round(max(0.0, min(1.0, c)) * 255):02X}" for c in rgb)


def _adjust(color: str, el: ET.Element) -> str:
    """Apply Word's color tweaks (lumMod/lumOff for lighter or darker
    shades of a theme color, tint, shade)."""
    import colorsys

    r, g, b = _hex_to_rgb(color)
    h, l, sat = colorsys.rgb_to_hls(r, g, b)
    for mod in el:
        name = mod.tag.split("}")[1]
        value = int(mod.get("val", "100000")) / 100000
        if name == "lumMod":
            l *= value
        elif name == "lumOff":
            l += value
        elif name == "tint":  # toward white
            r, g, b = colorsys.hls_to_rgb(h, l, sat)
            r, g, b = (c + (1 - c) * (1 - value) for c in (r, g, b))
            h, l, sat = colorsys.rgb_to_hls(r, g, b)
        elif name == "shade":  # toward black
            r, g, b = colorsys.hls_to_rgb(h, l, sat)
            r, g, b = (c * value for c in (r, g, b))
            h, l, sat = colorsys.rgb_to_hls(r, g, b)
    return _rgb_to_hex(colorsys.hls_to_rgb(h, max(0.0, min(1.0, l)), sat))


def _fill_color(sp_pr: Optional[ET.Element], theme: dict[str, str], line: bool = False) -> Optional[str]:
    """The solid color set on a series or data point, if any. Lines are
    colored by their outline (a:ln); bars, areas and slices by their fill."""
    if sp_pr is None:
        return None
    holder = sp_pr.find("a:ln", NS) if line else sp_pr
    if holder is None:
        return None
    fill = holder.find("a:solidFill", NS)
    if fill is None:
        return None
    rgb = fill.find("a:srgbClr", NS)
    if rgb is not None:
        return _adjust("#" + rgb.get("val", "000000"), rgb)
    scheme = fill.find("a:schemeClr", NS)
    if scheme is not None:
        name = scheme.get("val", "accent1")
        base = theme.get(SCHEME_ALIASES.get(name, name))
        return _adjust(base, scheme) if base else None
    sys = fill.find("a:sysClr", NS)
    if sys is not None:
        return _adjust("#" + sys.get("lastClr", "000000"), sys)
    return None


def default_color(accents: list[str], index: int) -> str:
    """Word's automatic colors: accent1..6, then the same six darker, then
    lighter, and so on."""
    base = accents[index % len(accents)]
    cycle = index // len(accents)
    if cycle == 0:
        return base
    import colorsys

    h, l, s = colorsys.rgb_to_hls(*_hex_to_rgb(base))
    l = l * 0.6 if cycle % 2 else l + (1 - l) * 0.4
    return _rgb_to_hex(colorsys.hls_to_rgb(h, l, s))


# ---------- reading a chart's data ----------


def _text(el: Optional[ET.Element]) -> str:
    if el is None:
        return ""
    return "".join(t.text or "" for t in el.iter(f"{{{NS['a']}}}t")).strip()


def _points(ref: Optional[ET.Element]) -> list[str]:
    """Cached values from a c:cat / c:val / c:tx reference, in order."""
    if ref is None:
        return []
    cache = None
    for tag in ("strCache", "numCache", "multiLvlStrCache"):
        cache = ref.find(f".//c:{tag}", NS)
        if cache is not None:
            break
    if cache is None:
        # Literal values typed straight into the chart.
        cache = ref.find(".//c:strLit", NS) or ref.find(".//c:numLit", NS)
        if cache is None:
            return []
    if cache.tag.endswith("multiLvlStrCache"):
        cache = cache.find("c:lvl", NS) or cache
    count_el = cache.find("c:ptCount", NS)
    count = int(count_el.get("val", "0")) if count_el is not None else 0
    values = {}
    for pt in cache.findall("c:pt", NS):
        v = pt.find("c:v", NS)
        values[int(pt.get("idx", "0"))] = v.text if v is not None and v.text is not None else ""
    count = max(count, max(values) + 1 if values else 0)
    return [values.get(i, "") for i in range(count)]


def _numbers(ref: Optional[ET.Element]) -> list[Optional[float]]:
    out: list[Optional[float]] = []
    for value in _points(ref):
        try:
            out.append(float(value))
        except ValueError:
            out.append(None)
    return out


def _val(el: Optional[ET.Element], default: str = "") -> str:
    return el.get("val", default) if el is not None else default


def parse_chart(xml: bytes, theme: Optional[dict[str, str]] = None) -> Chart:
    theme = theme or {}
    root = ET.fromstring(xml)
    chart_el = root.find("c:chart", NS)
    if chart_el is None:
        raise ValueError("no chart")
    plot = chart_el.find("c:plotArea", NS)
    if plot is None:
        raise ValueError("no plot area")

    chart = Chart()
    accents = [theme[f"accent{i}"] for i in range(1, 7) if f"accent{i}" in theme]
    if len(accents) == 6:
        chart.accents = accents
    categories: list[str] = []
    for child in plot:
        tag = child.tag.split("}")[1]
        kind = GROUP_TAGS.get(tag)
        if kind is None:
            continue
        group = ChartGroup(
            kind=kind,
            series=[],
            horizontal=_val(child.find("c:barDir", NS)) == "bar",
            grouping=_val(child.find("c:grouping", NS), "clustered" if kind == "bar" else "standard"),
        )
        for ser in child.findall("c:ser", NS):
            name = (_points(ser.find("c:tx", NS)) or [""])[0] or _text(ser.find("c:tx", NS))
            index = int(_val(ser.find("c:idx", NS), "0") or 0)
            sp_pr = ser.find("c:spPr", NS)
            color = (
                _fill_color(sp_pr, theme, line=kind in ("line", "scatter"))
                or (_fill_color(sp_pr, theme) if kind in ("line", "scatter") else None)
                or default_color(chart.accents, index)
            )
            if kind == "scatter":
                xs = _numbers(ser.find("c:xVal", NS))
                ys = _numbers(ser.find("c:yVal", NS))
                series = Series(name=name, values=ys, xs=xs, color=color)
            else:
                if not categories:
                    categories = _points(ser.find("c:cat", NS))
                series = Series(name=name, values=_numbers(ser.find("c:val", NS)), color=color)
            for point in ser.findall("c:dPt", NS):
                point_color = _fill_color(point.find("c:spPr", NS), theme)
                if point_color:
                    series.point_colors[int(_val(point.find("c:idx", NS), "0") or 0)] = point_color
            group.series.append(series)
        if group.series:
            chart.groups.append(group)
    if not chart.groups:
        raise ValueError("no chart type we can draw")

    series_count = sum(len(g.series) for g in chart.groups)
    longest = max(len(s.values) for g in chart.groups for s in g.series)
    chart.categories = categories or [str(i + 1) for i in range(longest)]

    title_el = chart_el.find("c:title", NS)
    chart.title = _text(title_el)
    if not chart.title and title_el is not None and series_count == 1:
        # Word shows the series name when the title is left automatic.
        chart.title = chart.groups[0].series[0].name
    if not chart.title and _val(chart_el.find("c:autoTitleDeleted", NS)) not in ("1", "true") and series_count == 1:
        chart.title = chart.groups[0].series[0].name

    cat_ax = plot.find("c:catAx", NS)
    if cat_ax is None:
        cat_ax = plot.find("c:dateAx", NS)
    val_axes = plot.findall("c:valAx", NS)
    if cat_ax is not None:
        chart.x_label = _text(cat_ax.find("c:title", NS))
        if val_axes:
            chart.y_label = _text(val_axes[0].find("c:title", NS))
    elif len(val_axes) >= 2:  # scatter: two value axes
        chart.x_label = _text(val_axes[0].find("c:title", NS))
        chart.y_label = _text(val_axes[1].find("c:title", NS))
    return chart


# ---------- drawing ----------


def _clean(values: list[Optional[float]], length: int) -> list[float]:
    return [(values[i] if i < len(values) and values[i] is not None else 0.0) for i in range(length)]  # type: ignore[misc]


def render_chart(chart: Chart) -> bytes:
    """The chart as a PNG, sized to read well in Discord."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=150)
    try:
        _draw(fig, ax, chart)
        out = io.BytesIO()
        fig.savefig(out, format="png", bbox_inches="tight", facecolor="white")
        return out.getvalue()
    finally:
        plt.close(fig)


def _draw(fig, ax, chart: Chart) -> None:
    n = len(chart.categories)
    positions = list(range(n))
    labelled = 0

    pie = next((g for g in chart.groups if g.kind in ("pie", "doughnut")), None)
    if pie is not None:
        series = pie.series[0]
        values = _clean(series.values, n)
        # Each slice: its own color if set in Word, else the accent sequence.
        keep = [
            (c, v, series.point_colors.get(i) or default_color(chart.accents, i))
            for i, (c, v) in enumerate(zip(chart.categories, values))
            if v > 0
        ]
        wedge = {"width": 0.45, "edgecolor": "white"} if pie.kind == "doughnut" else {"edgecolor": "white"}
        wedges_text = ax.pie(
            [v for _, v, _ in keep],
            labels=[c for c, _, _ in keep],
            colors=[col for _, _, col in keep] or None,
            autopct="%1.0f%%",
            startangle=90,
            counterclock=False,
            wedgeprops=wedge,
            textprops={"fontsize": 10},
        )
        # Percentages sit on the slices: white on dark colors, black on light.
        # matplotlib 3.11+ returns a PieContainer whose .texts are
        # [labels, percentages]; older versions return a 3-tuple.
        percents = None
        if isinstance(wedges_text, tuple) and len(wedges_text) == 3:
            percents = wedges_text[2]
        else:
            groups = getattr(wedges_text, "texts", None)
            if groups and len(groups) >= 2:
                percents = groups[-1]
        if percents:
            for text, (_, _, col) in zip(percents, keep):
                r, g, b = _hex_to_rgb(col)
                text.set_color("white" if 0.299 * r + 0.587 * g + 0.114 * b < 0.55 else "black")
        ax.axis("equal")
    else:
        bar_groups = [g for g in chart.groups if g.kind == "bar"]
        bar_count = sum(len(g.series) for g in bar_groups if g.grouping == "clustered")
        bar_index = 0
        for group in chart.groups:
            stacked = group.grouping in ("stacked", "percentStacked")
            totals = [0.0] * n
            if group.grouping == "percentStacked":
                for s in group.series:
                    for i, v in enumerate(_clean(s.values, n)):
                        totals[i] += abs(v)
            base = [0.0] * n
            for s in group.series:
                values = _clean(s.values, n)
                if group.grouping == "percentStacked":
                    values = [v / t * 100 if t else 0.0 for v, t in zip(values, totals)]
                c = s.color
                label = s.name or None
                labelled += 1 if label else 0
                if group.kind == "bar":
                    if stacked:
                        width = 0.6
                        offsets = positions
                    else:
                        width = 0.8 / max(bar_count, 1)
                        offsets = [p - 0.4 + width * (bar_index + 0.5) for p in positions]
                        bar_index += 1
                    if group.horizontal:
                        ax.barh(offsets, values, height=width, left=base if stacked else None, color=c, label=label)
                    else:
                        ax.bar(offsets, values, width=width, bottom=base if stacked else None, color=c, label=label)
                elif group.kind == "line":
                    ax.plot(positions, values, color=c, marker="o", linewidth=2.5, label=label)
                elif group.kind == "area":
                    top = [b + v for b, v in zip(base, values)] if stacked else values
                    ax.fill_between(positions, base if stacked else [0.0] * n, top, color=c, alpha=0.75, label=label)
                elif group.kind == "scatter":
                    xs = s.xs if s.xs and any(x is not None for x in s.xs) else list(range(1, len(values) + 1))
                    pairs = [(x, y) for x, y in zip(xs, s.values) if x is not None and y is not None]
                    ax.scatter([x for x, _ in pairs], [y for _, y in pairs], color=c, s=40, label=label)
                if stacked:
                    base = [b + v for b, v in zip(base, values)]

        if not any(g.kind == "scatter" for g in chart.groups):
            horizontal = all(g.kind == "bar" and g.horizontal for g in chart.groups)
            if horizontal:
                ax.set_yticks(positions, chart.categories)
                ax.invert_yaxis()  # first category on top, as in Word
            else:
                rotate = n > 6 or max((len(c) for c in chart.categories), default=0) > 10
                ax.set_xticks(positions, chart.categories, rotation=30 if rotate else 0, ha="right" if rotate else "center")
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        ax.grid(axis="x" if all(g.horizontal for g in chart.groups if g.kind == "bar") and bar_groups else "y", alpha=0.3)
        ax.set_axisbelow(True)
        if chart.x_label:
            ax.set_xlabel(chart.x_label)
        if chart.y_label:
            ax.set_ylabel(chart.y_label)
        if labelled > 1:
            ax.legend(frameon=False)

    if chart.title:
        ax.set_title(chart.title, fontsize=14, color=TITLE_COLOR)
    fig.tight_layout()
