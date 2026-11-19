from article_render import (
    LIMIT,
    RULE,
    Part,
    escape_text,
    render_article,
    table_text,
    word_count,
)

# ---------- builders for TipTap JSON ----------


def t(text, *marks, href=None):
    node = {"type": "text", "text": text}
    m = [{"type": k} for k in marks]
    if href:
        m.append({"type": "link", "attrs": {"href": href}})
    if m:
        node["marks"] = m
    return node


def p(*inline):
    return {"type": "paragraph", "content": list(inline)}


def h(level, text):
    return {"type": "heading", "attrs": {"level": level}, "content": [t(text)]}


def li(*blocks):
    return {"type": "listItem", "content": list(blocks)}


def ul(*items):
    return {"type": "bulletList", "content": list(items)}


def ol(*items, start=1):
    return {"type": "orderedList", "attrs": {"start": start}, "content": list(items)}


def img(src):
    return {"type": "image", "attrs": {"src": src}}


def cell(text, header=False):
    return {"type": "tableHeader" if header else "tableCell", "content": [p(t(text))]}


def row(*cells):
    return {"type": "tableRow", "content": list(cells)}


def doc(*blocks):
    return {"type": "doc", "content": list(blocks)}


def one(document) -> str:
    parts = render_article(document)
    assert len(parts) == 1, parts
    return parts[0].content


# ---------- inline formatting ----------


def test_plain_paragraphs_are_separated_by_a_blank_line():
    assert one(doc(p(t("First.")), p(t("Second.")))) == "First.\n\nSecond."


def test_bold_italic_underline_strike():
    text = one(doc(p(t("a", "bold"), t(" "), t("b", "italic"), t(" "), t("c", "underline"), t(" "), t("d", "strike"))))
    assert text == "**a** *b* __c__ ~~d~~"


def test_combined_marks_nest():
    assert one(doc(p(t("both", "bold", "italic")))) == "***both***"


def test_spaces_stay_outside_markers():
    # Discord won't render '**bold **'.
    assert one(doc(p(t("Pitt "), t("wins ", "bold"), t("big")))) == "Pitt **wins** big"


def test_neighbouring_runs_with_the_same_marks_merge():
    assert one(doc(p(t("Pi", "bold"), t("tt", "bold")))) == "**Pitt**"


def test_link_with_text():
    assert one(doc(p(t("Box score", href="https://pittsburghpanthers.com/box")))) == (
        "[Box score](https://pittsburghpanthers.com/box)"
    )


def test_link_whose_text_is_the_url_stays_bare():
    url = "https://example.com/a_b"
    assert one(doc(p(t(url, href=url)))) == url


def test_link_url_parentheses_are_encoded():
    text = one(doc(p(t("wiki", href="https://en.wikipedia.org/wiki/Pitt_(disambiguation)"))))
    assert text == "[wiki](https://en.wikipedia.org/wiki/Pitt_%28disambiguation%29)"


def test_inline_code():
    assert one(doc(p(t("x = 1", "code")))) == "`x = 1`"


def test_hard_break_is_a_newline():
    assert one(doc(p(t("line one"), {"type": "hardBreak"}, t("line two")))) == "line one\nline two"


# ---------- escaping ----------


def test_markdown_characters_in_text_show_literally():
    assert escape_text("2*3 = 6_ish ~ok~ `x` |a|") == r"2\*3 = 6\_ish \~ok\~ \`x\` \|a\|"


def test_everyone_and_here_are_defused():
    assert escape_text("hey @everyone and @here") == r"hey \@everyone and \@here"


def test_angle_brackets_cant_form_mentions():
    assert escape_text("<@123>") == r"\<@123>"


def test_urls_are_not_escaped():
    assert escape_text("see https://x.com/some_page_here now") == (
        "see https://x.com/some_page_here now"
    )


def test_paragraph_starting_with_hash_is_not_a_heading():
    assert one(doc(p(t("# 1 ranked defense")))) == r"\# 1 ranked defense"


def test_paragraph_starting_with_number_dot_is_not_a_list():
    assert one(doc(p(t("1. Not a list")))) == r"1\. Not a list"


# ---------- blocks ----------


def test_heading_levels_map_to_discord_hashes():
    text = one(doc(h(1, "Big"), h(2, "Heading"), h(3, "Sub"), h(4, "Smaller")))
    assert text.split("\n\n") == ["# Big", "## Heading", "### Sub", "### Smaller"]


def test_bullet_list_with_nesting():
    document = doc(
        ul(
            li(p(t("Offense"))),
            li(p(t("Defense")), ul(li(p(t("Front seven"))), li(p(t("Secondary"))))),
        )
    )
    assert one(document) == "- Offense\n- Defense\n  - Front seven\n  - Secondary"


def test_numbered_list_respects_start():
    assert one(doc(ol(li(p(t("a"))), li(p(t("b"))), start=3))) == "3. a\n4. b"


def test_list_item_with_two_paragraphs_indents_the_second():
    assert one(doc(ul(li(p(t("first")), p(t("second")))))) == "- first\n  second"


def test_quote_prefixes_every_line():
    quote = {"type": "blockquote", "content": [p(t("We'll be ready.")), p(t("— Coach"))]}
    assert one(doc(quote)) == "> We'll be ready.\n>\n> — Coach"


def test_code_block_is_fenced_and_cant_be_broken_out_of():
    code = {"type": "codeBlock", "content": [t("print(1)\n```\nprint(2)")]}
    text = one(doc(code))
    assert text.startswith("```\nprint(1)\n")
    assert text.endswith("\n```")
    assert text.count("```") == 2  # the inner one is defused


def test_horizontal_rule():
    assert one(doc(p(t("a")), {"type": "horizontalRule"}, p(t("b")))) == f"a\n\n{RULE}\n\nb"


def test_empty_paragraphs_are_dropped():
    assert one(doc(p(t("a")), p(), p(t("b")))) == "a\n\nb"


# ---------- tables ----------


def test_table_lines_up_with_a_rule_under_the_header():
    table = {
        "type": "table",
        "content": [
            row(cell("Player", True), cell("Yds", True)),
            row(cell("Desmond Reid"), cell("142")),
            row(cell("Eli Holstein"), cell("88")),
        ],
    }
    assert table_text(table) == (
        "Player        Yds\n"
        "────────────  ───\n"
        "Desmond Reid  142\n"
        "Eli Holstein  88"
    )
    assert one(doc(table)).startswith("```\nPlayer")


def test_table_without_header_has_no_rule_and_pads_short_rows():
    table = {"type": "table", "content": [row(cell("a"), cell("b")), row(cell("c"))]}
    assert table_text(table) == "a  b\nc"


def test_long_table_cells_are_cut():
    table = {"type": "table", "content": [row(cell("x" * 40))]}
    assert table_text(table) == "x" * 23 + "…"


# ---------- pictures ----------


def test_pictures_get_their_own_message_in_place():
    parts = render_article(doc(p(t("Before")), img("https://cdn.example/a.png"), p(t("After"))))
    assert parts == [
        Part(content="Before"),
        Part(image_url="https://cdn.example/a.png"),
        Part(content="After"),
    ]


def test_pictures_that_never_uploaded_are_skipped():
    parts = render_article(doc(img("data:image/png;base64,xyz"), img("file:///C:/me.png"), p(t("x"))))
    assert parts == [Part(content="x")]


def test_inline_picture_inside_a_paragraph_follows_its_text():
    para = p(t("Look:"), img("https://cdn.example/b.png"))
    assert render_article(doc(para)) == [
        Part(content="Look:"),
        Part(image_url="https://cdn.example/b.png"),
    ]


# ---------- splitting ----------


def para_of(n, word="word"):
    return p(t(" ".join([word] * n)))


def test_short_article_is_one_message():
    assert len(render_article(doc(para_of(50)))) == 1


def test_every_message_fits_discords_limit():
    parts = render_article(doc(*[para_of(120) for _ in range(10)]))
    assert len(parts) > 1
    assert all(len(part.content) <= LIMIT for part in parts)


def test_paragraphs_are_not_cut_when_they_fit_whole():
    blocks = [para_of(150, w) for w in ("alpha", "bravo", "charlie", "delta")]
    for part in render_article(doc(*blocks)):
        for chunk in part.content.split("\n\n"):
            assert len(set(chunk.split())) == 1  # each paragraph intact


def test_one_huge_paragraph_splits_at_sentences():
    sentence = "Pitt ran the ball well in the second half. "
    parts = render_article(doc(p(t(sentence * 100))))
    assert len(parts) > 1
    assert all(len(x.content) <= LIMIT for x in parts)
    assert all(x.content.endswith(".") for x in parts)


def test_heading_is_not_stranded_at_the_end_of_a_message():
    filler = para_of(300)  # ~1500 chars
    document = doc(filler, h(2, "Second half"), para_of(100))
    parts = render_article(document)
    assert parts[0].content == one(doc(filler))
    assert parts[1].content.startswith("## Second half")


def test_long_table_splits_into_fenced_pieces():
    rows = [row(cell("Player", True), cell("Yds", True))] + [
        row(cell(f"Player number {i}"), cell(str(i))) for i in range(150)
    ]
    parts = render_article(doc({"type": "table", "content": rows}))
    assert len(parts) > 1
    for part in parts:
        assert len(part.content) <= LIMIT
        assert part.content.startswith("```\n") and part.content.endswith("\n```")


def test_long_quote_stays_quoted_after_splitting():
    quote = {"type": "blockquote", "content": [p(t(f"Line {i} " * 10)) for i in range(60)]}
    parts = render_article(doc(quote))
    assert len(parts) > 1
    for part in parts:
        assert all(line.startswith(">") for line in part.content.split("\n"))


def test_word_count():
    assert word_count(doc(h(2, "Title here"), p(t("one two three")))) == 5
