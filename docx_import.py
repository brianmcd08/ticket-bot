"""Read a Word (.docx) file into the document tree article_render understands.

mammoth turns the .docx into simple HTML (it understands Word's headings,
lists, tables and pictures); this module parses that HTML into the same
TipTap-style JSON tree the renderer was built for.

Pictures come out as bytes; the tree refers to them as "docx-image:<n>" so
the publisher can attach them as files where they appear.

Pure apart from mammoth: no Discord, no network. Fully unit tested.
"""

import io
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import PurePath
from typing import Any, Optional

import mammoth

IMAGE_REF = "docx-image:"
# Formats Discord shows inline. Word can also hold EMF/WMF drawings, which
# Discord can't display; those are skipped with a warning.
SHOWABLE = {"image/png": "png", "image/jpeg": "jpg", "image/gif": "gif", "image/webp": "webp"}

# Word styles mammoth doesn't map on its own.
STYLE_MAP = """
p[style-name='Title'] => h1.doc-title:fresh
p[style-name='Subtitle'] => h2:fresh
p[style-name='Quote'] => blockquote > p:fresh
p[style-name='Intense Quote'] => blockquote > p:fresh
u => u
"""

Node = dict[str, Any]


@dataclass
class Picture:
    data: bytes
    content_type: str

    @property
    def filename(self) -> str:
        return f"picture.{SHOWABLE.get(self.content_type, 'png')}"


@dataclass
class ImportedArticle:
    title: str
    doc: Node
    pictures: list[Picture] = field(default_factory=list)
    skipped_pictures: int = 0  # drawings Discord can't show


class UnreadableDocument(Exception):
    pass


# ---------- HTML -> a tiny element tree ----------


@dataclass
class El:
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    children: list["El | str"] = field(default_factory=list)


VOID = {"br", "img", "hr"}


class _TreeBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = El("root")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        el = El(tag, {k: v or "" for k, v in attrs})
        self.stack[-1].children.append(el)
        if tag not in VOID:
            self.stack.append(el)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(El(tag, {k: v or "" for k, v in attrs}))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def parse_html(html: str) -> El:
    builder = _TreeBuilder()
    builder.feed(html)
    builder.close()
    return builder.root


# ---------- element tree -> document tree ----------

MARKS = {
    "strong": "bold",
    "b": "bold",
    "em": "italic",
    "i": "italic",
    "u": "underline",
    "s": "strike",
    "del": "strike",
    "strike": "strike",
    "code": "code",
}
HEADINGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 3, "h5": 3, "h6": 3}
BLOCKS = {"p", "ul", "ol", "li", "table", "blockquote", "pre", "hr", *HEADINGS}


def _inline(el: El, marks: tuple[Node, ...] = ()) -> list[Node]:
    out: list[Node] = []
    for child in el.children:
        if isinstance(child, str):
            text = re.sub(r"\s+", " ", child)
            if text:
                node: Node = {"type": "text", "text": text}
                if marks:
                    node["marks"] = list(marks)
                out.append(node)
            continue
        if child.tag == "br":
            out.append({"type": "hardBreak"})
        elif child.tag == "img":
            out.append({"type": "image", "attrs": {"src": child.attrs.get("src", "")}})
        elif child.tag in MARKS:
            out.extend(_inline(child, marks + ({"type": MARKS[child.tag]},)))
        elif child.tag == "a" and child.attrs.get("href", "").startswith(("http://", "https://")):
            out.extend(_inline(child, marks + ({"type": "link", "attrs": {"href": child.attrs["href"]}},)))
        else:
            out.extend(_inline(child, marks))  # spans, bookmarks, unknown inline tags
    return out


def _paragraph(inline: list[Node]) -> Node:
    return {"type": "paragraph", "content": inline}


def _list_item(li: El) -> Node:
    content: list[Node] = []
    loose = El("p")
    for child in li.children:
        if isinstance(child, El) and child.tag in ("ul", "ol"):
            if loose.children:
                content.append(_paragraph(_inline(loose)))
                loose = El("p")
            content.append(_list(child))
        elif isinstance(child, El) and child.tag == "p":
            if loose.children:
                content.append(_paragraph(_inline(loose)))
                loose = El("p")
            content.append(_paragraph(_inline(child)))
        else:
            loose.children.append(child)
    if loose.children:
        content.append(_paragraph(_inline(loose)))
    return {"type": "listItem", "content": content}


def _list(el: El) -> Node:
    kind = "orderedList" if el.tag == "ol" else "bulletList"
    items = [_list_item(c) for c in el.children if isinstance(c, El) and c.tag == "li"]
    node: Node = {"type": kind, "content": items}
    if kind == "orderedList":
        node["attrs"] = {"start": 1}
    return node


def _rows(el: El) -> list[El]:
    rows = []
    for child in el.children:
        if isinstance(child, El):
            if child.tag == "tr":
                rows.append(child)
            elif child.tag in ("thead", "tbody", "tfoot"):
                rows.extend(_rows(child))
    return rows


def _table(el: El) -> Node:
    rows = []
    for r, tr in enumerate(_rows(el)):
        cells = []
        for cell in tr.children:
            if not isinstance(cell, El) or cell.tag not in ("td", "th"):
                continue
            # Articles' tables almost always start with a heading row, and
            # Word rarely marks it as one, so the first row is the header.
            kind = "tableHeader" if r == 0 or cell.tag == "th" else "tableCell"
            cells.append({"type": kind, "content": _blocks(cell)})
        rows.append({"type": "tableRow", "content": cells})
    return {"type": "table", "content": rows}


def _blocks(el: El) -> list[Node]:
    out: list[Node] = []
    loose = El("p")  # inline content sitting directly in a block container

    def flush():
        nonlocal loose
        inline = _inline(loose)
        if any(n.get("type") != "text" or n["text"].strip() for n in inline):
            out.append(_paragraph(inline))
        loose = El("p")

    for child in el.children:
        if isinstance(child, str) or child.tag not in BLOCKS:
            loose.children.append(child)
            continue
        flush()
        tag = child.tag
        if tag == "p":
            out.append(_paragraph(_inline(child)))
        elif tag in HEADINGS:
            out.append({"type": "heading", "attrs": {"level": HEADINGS[tag]}, "content": _inline(child)})
        elif tag in ("ul", "ol"):
            out.append(_list(child))
        elif tag == "table":
            out.append(_table(child))
        elif tag == "blockquote":
            out.append({"type": "blockquote", "content": _blocks(child)})
        elif tag == "pre":
            text = "".join(c if isinstance(c, str) else "" for c in child.children)
            out.append({"type": "codeBlock", "content": [{"type": "text", "text": text}]})
        elif tag == "hr":
            out.append({"type": "horizontalRule"})
        elif tag == "li":
            out.append(_list(El("ul", children=[child])))
    flush()
    return out


def _text_of(node: Node) -> str:
    if node.get("type") == "text":
        return node.get("text", "")
    return "".join(_text_of(c) for c in node.get("content", []))


def title_from_filename(filename: str) -> str:
    name = PurePath(filename).name
    stem = name[: -len(".docx")] if name.lower().endswith(".docx") else PurePath(name).stem
    return " ".join(re.sub(r"[_\-]+", " ", stem).split()) or "Untitled article"


def html_to_article(html: str, filename: str) -> tuple[str, Node]:
    """Pick the title and build the document tree.

    Title: a paragraph in Word's Title style; otherwise a heading that opens
    the document; otherwise the file name. Whichever is used is taken out of
    the body so it isn't shown twice.
    """
    root = parse_html(html)
    title = ""
    for i, child in enumerate(root.children):
        if isinstance(child, El) and child.tag == "h1" and "doc-title" in child.attrs.get("class", ""):
            title = _text_of({"content": _inline(child)})
            del root.children[i]
            break
    blocks = _blocks(root)
    if not title.strip() and blocks and blocks[0].get("type") == "heading":
        title = _text_of(blocks.pop(0))
    title = " ".join(title.split()) or title_from_filename(filename)
    return title, {"type": "doc", "content": blocks}


def import_docx(data: bytes, filename: str) -> ImportedArticle:
    pictures: list[Picture] = []
    skipped = 0

    def keep_picture(image) -> dict:
        nonlocal skipped
        content_type = (image.content_type or "").lower()
        if content_type not in SHOWABLE:
            skipped += 1
            return {"src": ""}  # dropped by the renderer
        with image.open() as stream:
            pictures.append(Picture(stream.read(), content_type))
        return {"src": f"{IMAGE_REF}{len(pictures) - 1}"}

    try:
        result = mammoth.convert_to_html(
            io.BytesIO(data),
            style_map=STYLE_MAP,
            convert_image=mammoth.images.img_element(keep_picture),
        )
    except Exception as error:  # a corrupt file, or not really a .docx
        raise UnreadableDocument(str(error)) from error
    title, doc = html_to_article(result.value, filename)
    return ImportedArticle(title=title, doc=doc, pictures=pictures, skipped_pictures=skipped)


def picture_index(src: Optional[str]) -> Optional[int]:
    if src and src.startswith(IMAGE_REF):
        try:
            return int(src[len(IMAGE_REF) :])
        except ValueError:
            return None
    return None
