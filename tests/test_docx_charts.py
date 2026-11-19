"""Charts inside Word files: found, read, drawn in their own colors, placed."""

import io

import docx
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.opc.packuri import PackURI
from docx.opc.part import Part
from docx.oxml import parse_xml

from article_render import render_article
from docx_charts import OFFICE_ACCENTS, default_color, extract_charts, parse_chart, render_chart
from docx_import import import_docx

C = "http://schemas.openxmlformats.org/drawingml/2006/chart"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
CHART_CT = "application/vnd.openxmlformats-officedocument.drawingml.chart+xml"


def strs(values):
    pts = "".join(f'<c:pt idx="{i}"><c:v>{v}</c:v></c:pt>' for i, v in enumerate(values))
    return f'<c:strRef><c:f>x</c:f><c:strCache><c:ptCount val="{len(values)}"/>{pts}</c:strCache></c:strRef>'


def nums(values):
    pts = "".join(f'<c:pt idx="{i}"><c:v>{v}</c:v></c:pt>' for i, v in enumerate(values))
    return f'<c:numRef><c:f>x</c:f><c:numCache><c:ptCount val="{len(values)}"/>{pts}</c:numCache></c:numRef>'


def series(idx, name, values, categories, fill="", points=""):
    sp = f"<c:spPr><a:solidFill>{fill}</a:solidFill></c:spPr>" if fill else ""
    return (
        f'<c:ser><c:idx val="{idx}"/><c:order val="{idx}"/><c:tx>{strs([name])}</c:tx>{sp}{points}'
        f"<c:cat>{strs(categories)}</c:cat><c:val>{nums(values)}</c:val></c:ser>"
    )


def chart_xml(body, title="Yards by quarter"):
    title_xml = (
        f"<c:title><c:tx><c:rich><a:bodyPr/><a:p><a:r><a:t>{title}</a:t></a:r></a:p></c:rich></c:tx></c:title>"
        if title
        else ""
    )
    return (
        f'<c:chartSpace xmlns:c="{C}" xmlns:a="{A}" xmlns:r="{R}"><c:chart>{title_xml}'
        f"<c:plotArea>{body}</c:plotArea></c:chart></c:chartSpace>"
    ).encode()


QUARTERS = ["Q1", "Q2", "Q3", "Q4"]
COLUMNS = (
    '<c:barChart><c:barDir val="col"/><c:grouping val="clustered"/>'
    + series(0, "Pitt", [120, 95, 140, 88], QUARTERS)
    + series(1, "Opponent", [70, 110, 60, 90], QUARTERS)
    + "</c:barChart>"
)


def add_chart(document, xml: bytes, number: int):
    """Put a chart in the document the way Word does: a chart part, a
    relationship to it, and a drawing that points at it."""
    part = Part(PackURI(f"/word/charts/chart{number}.xml"), CHART_CT, xml, document.part.package)
    rel_id = document.part.relate_to(part, RT.CHART)
    drawing = (
        f'<w:r xmlns:w="{W}"><w:drawing><wp:inline xmlns:wp="{WP}">'
        f'<wp:extent cx="5486400" cy="3200400"/><wp:docPr id="{number}" name="Chart {number}"/>'
        f'<a:graphic xmlns:a="{A}"><a:graphicData uri="{C}">'
        f'<c:chart xmlns:c="{C}" xmlns:r="{R}" r:id="{rel_id}"/>'
        f"</a:graphicData></a:graphic></wp:inline></w:drawing></w:r>"
    )
    document.add_paragraph()._p.append(parse_xml(drawing))


def word_file_with_charts(*charts: bytes) -> bytes:
    document = docx.Document()
    document.add_paragraph("Stats Story", style="Title")
    document.add_paragraph("Before the chart.")
    for number, xml in enumerate(charts, start=1):
        add_chart(document, xml, number)
        document.add_paragraph(f"After chart {number}.")
    out = io.BytesIO()
    document.save(out)
    return out.getvalue()


# ---------- reading ----------


def test_column_chart_data_is_read():
    chart = parse_chart(chart_xml(COLUMNS))
    assert chart.title == "Yards by quarter"
    assert chart.categories == QUARTERS
    (group,) = chart.groups
    assert (group.kind, group.horizontal, group.grouping) == ("bar", False, "clustered")
    assert [(s.name, s.values) for s in group.series] == [
        ("Pitt", [120, 95, 140, 88]),
        ("Opponent", [70, 110, 60, 90]),
    ]


def test_colors_set_in_word_are_kept():
    body = (
        '<c:barChart><c:barDir val="bar"/><c:grouping val="stacked"/>'
        + series(0, "Run", [1, 2], ["A", "B"], fill='<a:srgbClr val="003594"/>')
        + series(1, "Pass", [3, 4], ["A", "B"], fill='<a:srgbClr val="FFB81C"/>')
        + "</c:barChart>"
    )
    chart = parse_chart(chart_xml(body))
    assert [s.color for s in chart.groups[0].series] == ["#003594", "#FFB81C"]
    assert chart.groups[0].horizontal and chart.groups[0].grouping == "stacked"


def test_unchanged_colors_follow_the_theme_like_word():
    chart = parse_chart(chart_xml(COLUMNS))
    assert [s.color for s in chart.groups[0].series] == OFFICE_ACCENTS[:2]

    theme = {f"accent{i}": c for i, c in enumerate(["#111111", "#222222", "#333333", "#444444", "#555555", "#666666"], 1)}
    themed = parse_chart(chart_xml(COLUMNS), theme)
    assert [s.color for s in themed.groups[0].series] == ["#111111", "#222222"]


def test_theme_color_with_word_shading_is_applied():
    theme = {f"accent{i}": "#4472C4" for i in range(1, 7)}
    fill = '<a:schemeClr val="accent1"><a:lumMod val="50000"/></a:schemeClr>'
    body = '<c:barChart><c:barDir val="col"/>' + series(0, "S", [1], ["A"], fill=fill) + "</c:barChart>"
    color = parse_chart(chart_xml(body), theme).groups[0].series[0].color
    assert color != "#4472C4" and color.startswith("#")  # a darker shade


def test_pie_slices_keep_their_own_colors():
    points = '<c:dPt><c:idx val="1"/><c:spPr><a:solidFill><a:srgbClr val="FF0000"/></a:solidFill></c:spPr></c:dPt>'
    body = "<c:pieChart>" + series(0, "Share", [50, 30, 20], ["Run", "Pass", "Other"], points=points) + "</c:pieChart>"
    chart = parse_chart(chart_xml(body))
    assert chart.groups[0].kind == "pie"
    assert chart.groups[0].series[0].point_colors == {1: "#FF0000"}


def test_untitled_single_series_uses_series_name():
    body = '<c:lineChart><c:grouping val="standard"/>' + series(0, "Attendance", [1, 2], ["A", "B"]) + "</c:lineChart>"
    assert parse_chart(chart_xml(body, title="")).title == "Attendance"


def test_word_cycles_colors_after_six_series():
    assert default_color(OFFICE_ACCENTS, 0) == OFFICE_ACCENTS[0]
    assert default_color(OFFICE_ACCENTS, 6) not in OFFICE_ACCENTS  # a darker accent1


# ---------- drawing ----------


def test_every_kind_draws_a_png():
    kinds = [
        COLUMNS,
        '<c:barChart><c:barDir val="bar"/><c:grouping val="percentStacked"/>'
        + series(0, "A", [1, 2], ["x", "y"]) + series(1, "B", [3, 1], ["x", "y"]) + "</c:barChart>",
        '<c:lineChart><c:grouping val="standard"/>' + series(0, "L", [3, 1, 2], ["a", "b", "c"]) + "</c:lineChart>",
        '<c:areaChart><c:grouping val="stacked"/>' + series(0, "A", [1, 2], ["a", "b"]) + series(1, "B", [2, 2], ["a", "b"]) + "</c:areaChart>",
        "<c:pieChart>" + series(0, "P", [50, 50], ["a", "b"]) + "</c:pieChart>",
        "<c:doughnutChart>" + series(0, "D", [1, 3], ["a", "b"]) + "</c:doughnutChart>",
        COLUMNS.replace("</c:barChart>", "</c:barChart><c:lineChart><c:grouping val=\"standard\"/>"
                        + series(2, "Avg", [90, 90, 90, 90], QUARTERS) + "</c:lineChart>"),
    ]
    for body in kinds:
        png = render_chart(parse_chart(chart_xml(body)))
        assert png.startswith(b"\x89PNG")


# ---------- in a real Word file ----------


def test_chart_in_a_word_file_becomes_a_picture_in_place():
    article = import_docx(word_file_with_charts(chart_xml(COLUMNS)), "stats.docx")
    parts = render_article(article.doc)
    assert [p.content or p.image_url for p in parts] == [
        "Before the chart.",
        "docx-image:0",
        "After chart 1.",
    ]
    assert article.pictures[0].data.startswith(b"\x89PNG")
    assert (article.charts_drawn, article.unsupported_charts) == (1, 0)


def test_two_charts_and_a_broken_one():
    broken = b"<not-a-chart/>"
    article = import_docx(word_file_with_charts(chart_xml(COLUMNS), broken, chart_xml(COLUMNS)), "s.docx")
    parts = [p.content or p.image_url for p in render_article(article.doc)]
    assert parts == ["Before the chart.", "docx-image:0", "After chart 1.\n\nAfter chart 2.", "docx-image:1", "After chart 3."]
    assert (article.charts_drawn, article.unsupported_charts) == (2, 1)


def test_files_without_charts_are_untouched():
    document = docx.Document()
    document.add_paragraph("Plain.")
    out = io.BytesIO()
    document.save(out)
    data = out.getvalue()
    assert extract_charts(data).docx == data
