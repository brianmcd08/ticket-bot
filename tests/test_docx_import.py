import io
import struct
import zlib

import docx
import pytest
from docx.shared import Inches

from article_render import Part, render_article
from docx_import import (
    UnreadableDocument,
    html_to_article,
    import_docx,
    picture_index,
    title_from_filename,
)


def tiny_png() -> bytes:
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    header = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00"))
        + chunk(b"IEND", b"")
    )


def word_file(build) -> bytes:
    document = docx.Document()
    build(document)
    out = io.BytesIO()
    document.save(out)
    return out.getvalue()


def rendered(data: bytes, filename="article.docx"):
    article = import_docx(data, filename)
    return article, render_article(article.doc)


# ---------- real Word files ----------


def test_title_style_becomes_the_title_and_leaves_the_body():
    def build(d):
        d.add_paragraph("Pitt Rolls Past FSU", style="Title")
        d.add_paragraph("What a night.")

    article, parts = rendered(word_file(build))
    assert article.title == "Pitt Rolls Past FSU"
    assert parts == [Part(content="What a night.")]


def test_formatting_headings_and_lists_come_through():
    def build(d):
        d.add_paragraph("Recap", style="Title")
        d.add_heading("First half", level=1)
        p = d.add_paragraph("Pitt ")
        p.add_run("dominated").bold = True
        p.add_run(" and ")
        p.add_run("scored").italic = True
        p.add_run(" ")
        p.add_run("often").underline = True
        d.add_heading("Key plays", level=2)
        d.add_paragraph("The pick-six", style="List Bullet")
        d.add_paragraph("The goal-line stand", style="List Bullet")
        d.add_paragraph("Kickoff", style="List Number")
        d.add_paragraph("Halftime", style="List Number")
        d.add_paragraph("We'll be ready.", style="Quote")

    _, parts = rendered(word_file(build))
    assert len(parts) == 1
    assert parts[0].content.split("\n\n") == [
        "# First half",
        "Pitt **dominated** and *scored* __often__",
        "## Key plays",
        "- The pick-six\n- The goal-line stand",
        "1. Kickoff\n2. Halftime",
        "> We'll be ready.",
    ]


def test_table_becomes_a_lined_up_block_with_a_header():
    def build(d):
        d.add_paragraph("Stats", style="Title")
        table = d.add_table(rows=3, cols=2)
        for r, (a, b) in enumerate([("Player", "Yds"), ("Desmond Reid", "142"), ("Eli Holstein", "88")]):
            table.cell(r, 0).text = a
            table.cell(r, 1).text = b

    _, parts = rendered(word_file(build))
    assert parts[0].content == (
        "```\n"
        "Player        Yds\n"
        "────────────  ───\n"
        "Desmond Reid  142\n"
        "Eli Holstein  88\n"
        "```"
    )


def test_pictures_are_kept_in_place(tmp_path):
    png = tmp_path / "p.png"
    png.write_bytes(tiny_png())

    def build(d):
        d.add_paragraph("Photos", style="Title")
        d.add_paragraph("Before the picture.")
        d.add_picture(str(png), width=Inches(1))
        d.add_paragraph("After the picture.")

    article, parts = rendered(word_file(build))
    assert [p.content or p.image_url for p in parts] == [
        "Before the picture.",
        "docx-image:0",
        "After the picture.",
    ]
    assert article.pictures[0].data == tiny_png()
    assert article.pictures[0].filename == "picture.png"


def test_no_title_style_uses_an_opening_heading():
    def build(d):
        d.add_heading("Signing Day Winners", level=1)
        d.add_paragraph("Body.")

    article, parts = rendered(word_file(build))
    assert article.title == "Signing Day Winners"
    assert parts == [Part(content="Body.")]


def test_no_title_at_all_uses_the_file_name():
    article, _ = rendered(word_file(lambda d: d.add_paragraph("Just text.")), "spring_game-recap.docx")
    assert article.title == "spring game recap"


def test_not_a_word_file_is_reported():
    with pytest.raises(UnreadableDocument):
        import_docx(b"this is not a docx", "x.docx")


# ---------- HTML details mammoth can produce ----------


def test_nested_lists():
    _, doc = html_to_article("<ul><li>Offense<ul><li>Run game</li></ul></li><li>Defense</li></ul>", "a.docx")
    assert render_article(doc)[0].content == "- Offense\n  - Run game\n- Defense"


def test_links_keep_their_address():
    _, doc = html_to_article('<p>See the <a href="https://pittsburghpanthers.com">schedule</a>.</p>', "a.docx")
    assert render_article(doc)[0].content == "See the [schedule](https://pittsburghpanthers.com)."


def test_internal_word_links_are_dropped_but_text_kept():
    _, doc = html_to_article('<p><a href="#_Toc123">Section two</a></p>', "a.docx")
    assert render_article(doc)[0].content == "Section two"


def test_line_breaks_and_strikethrough():
    _, doc = html_to_article("<p>one<br />two <s>old</s></p>", "a.docx")
    assert render_article(doc)[0].content == "one\ntwo ~~old~~"


def test_empty_paragraphs_vanish():
    _, doc = html_to_article("<p>a</p><p></p><p> </p><p>b</p>", "a.docx")
    assert render_article(doc)[0].content == "a\n\nb"


def test_picture_index():
    assert picture_index("docx-image:3") == 3
    assert picture_index("https://x/y.png") is None
    assert picture_index(None) is None


def test_title_from_filename():
    assert title_from_filename("My_Big-Story.docx") == "My Big Story"
    assert title_from_filename(".docx") == "Untitled article"
