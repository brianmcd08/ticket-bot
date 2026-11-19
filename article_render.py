"""Turn an article's document tree into Discord messages.

docx_import turns a Word file into a JSON tree (TipTap/ProseMirror style).
This module converts that tree into the Markdown dialect Discord
understands and splits it into messages Discord will accept. Preview and
publish both call render_article, so the preview is exactly what's posted.

Pure functions only: no network, no AWS. Everything here is unit tested.

What Discord can show, and what we do with the rest:
  headings, bold, italic, underline, strikethrough, inline code, links,
  bullet and numbered lists, quotes, code blocks  -> Discord's own syntax
  tables            -> an aligned monospace block (Discord has no tables)
  pictures          -> a message of their own with the picture embedded
  horizontal rules  -> a thin line of box-drawing characters
  anything else (fonts, colors, alignment) is dropped when the Word file is
  read, since Discord can't show it.
"""

import re
from dataclasses import dataclass
from typing import Any, Iterable, Optional

LIMIT = 2000  # characters per Discord message
TABLE_CELL_MAX = 24  # wider cells are cut with an ellipsis
RULE = "─" * 20

Node = dict[str, Any]


@dataclass(frozen=True)
class Part:
    """One Discord message: text, or a picture (never both). image_url is an
    https URL or a "docx-image:<n>" reference to a picture from the file."""

    content: str = ""
    image_url: Optional[str] = None


# ---------- inline text ----------

_URL = re.compile(r"https?://\S+")
# Characters Discord would read as formatting. Backslash first, so the
# backslashes we add aren't themselves escaped.
_INLINE_SPECIAL = re.compile(r"([\\*_~`|<\[\]])")
_MENTION = re.compile(r"@(everyone|here)\b")
# Things that only mean something at the start of a line.
_LINE_START = re.compile(r"^(\s*)(#{1,3} |-# |> |>>> |[-*+] )")
_LINE_START_NUMBER = re.compile(r"^(\s*\d+)(\. )")


def escape_text(text: str) -> str:
    """Make plain text show up literally in Discord.

    Bare URLs are left alone: escaping an underscore inside one would break
    the link.
    """
    out = []
    pos = 0
    for match in _URL.finditer(text):
        out.append(_escape_plain(text[pos : match.start()]))
        out.append(match.group(0))
        pos = match.end()
    out.append(_escape_plain(text[pos:]))
    return "".join(out)


def _escape_plain(text: str) -> str:
    text = _INLINE_SPECIAL.sub(r"\\\1", text)
    return _MENTION.sub(r"\\@\1", text)


def _escape_line_starts(text: str) -> str:
    """'# Not a heading' typed in a paragraph must stay a paragraph."""
    def fix(line: str) -> str:
        line = _LINE_START.sub(r"\1\\\2", line)
        # A backslash before a digit isn't an escape; it goes before the dot.
        return _LINE_START_NUMBER.sub(r"\1\\\2", line)

    return "\n".join(fix(line) for line in text.split("\n"))


# Order matters: outermost first when wrapping.
_MARK_ORDER = ["bold", "italic", "underline", "strike"]
_MARK_WRAP = {"bold": "**", "italic": "*", "underline": "__", "strike": "~~"}


def _runs(nodes: Iterable[Node]) -> list[tuple[str, frozenset[str], Optional[str]]]:
    """Flatten inline nodes into (text, marks, link) runs, merging neighbours
    with identical formatting so we don't emit '**a****b**'."""
    runs: list[tuple[str, frozenset[str], Optional[str]]] = []
    for node in nodes:
        if node.get("type") == "hardBreak":
            text, marks, href = "\n", frozenset(), None
        elif node.get("type") == "text":
            text = node.get("text", "")
            names = set()
            href = None
            for mark in node.get("marks", []):
                kind = mark.get("type")
                if kind == "link":
                    href = (mark.get("attrs") or {}).get("href")
                elif kind in _MARK_WRAP or kind == "code":
                    names.add(kind)
            marks = frozenset(names)
        else:
            continue  # inline node we don't know (e.g. a stray image)
        if runs and runs[-1][1] == marks and runs[-1][2] == href and text != "\n" and runs[-1][0] != "\n":
            runs[-1] = (runs[-1][0] + text, marks, href)
        else:
            runs.append((text, marks, href))
    return runs


def _code_span(text: str) -> str:
    if "`" not in text:
        return f"`{text}`"
    # Double backticks with padding allow single backticks inside.
    return f"`` {text.replace('``', '` `')} ``"


def _wrap(text: str, marks: frozenset[str]) -> str:
    """Apply marks, keeping edge spaces outside: '**bold **' won't render."""
    if not text.strip():
        return text
    lead = text[: len(text) - len(text.lstrip())]
    trail = text[len(text.rstrip()) :]
    core = text.strip()
    if "code" in marks:
        inner = _code_span(core)
    else:
        inner = escape_text(core)
    for name in reversed(_MARK_ORDER):
        if name in marks:
            inner = f"{_MARK_WRAP[name]}{inner}{_MARK_WRAP[name]}"
    return f"{lead}{inner}{trail}"


def _safe_url(url: str) -> str:
    return url.replace(" ", "%20").replace("(", "%28").replace(")", "%29")


def render_inline(nodes: Iterable[Node]) -> str:
    out = []
    for text, marks, href in _runs(nodes):
        if text == "\n":
            out.append("\n")
            continue
        piece = _wrap(text, marks)
        if href and re.match(r"https?://", href):
            if text.strip() == href:
                piece = href  # a pasted URL: show it as-is
            else:
                piece = f"[{piece.strip()}]({_safe_url(href)})"
                lead = text[: len(text) - len(text.lstrip())]
                trail = text[len(text.rstrip()) :]
                piece = f"{lead}{piece}{trail}"
        out.append(piece)
    return "".join(out)


def plain_text(node: Node) -> str:
    """Just the words, for table cells (formatting can't show in a code block)."""
    if node.get("type") == "text":
        return node.get("text", "")
    if node.get("type") == "hardBreak":
        return " "
    return " ".join(
        t for t in (plain_text(child) for child in node.get("content", [])) if t
    )


# ---------- blocks ----------


@dataclass(frozen=True)
class Block:
    """A rendered top-level block, before packing into messages."""

    text: str = ""
    kind: str = "text"  # text | heading | fenced | quote | list | image
    image_url: Optional[str] = None


def _heading(node: Node) -> str:
    level = int((node.get("attrs") or {}).get("level", 2))
    hashes = "#" * max(1, min(level, 3))
    text = render_inline(node.get("content", [])).replace("\n", " ").strip()
    return f"{hashes} {text}" if text else ""


def _paragraph(node: Node) -> str:
    # Leading/trailing spaces mean nothing in Discord; drop them.
    return _escape_line_starts(render_inline(node.get("content", [])).strip())


def _list(node: Node, depth: int = 0) -> str:
    ordered = node.get("type") == "orderedList"
    start = int((node.get("attrs") or {}).get("start", 1) or 1)
    lines = []
    for i, item in enumerate(node.get("content", [])):
        marker = f"{start + i}. " if ordered else "- "
        indent = "  " * depth
        first = True
        for child in item.get("content", []):
            kind = child.get("type")
            if kind in ("bulletList", "orderedList"):
                lines.append(_list(child, depth + 1))
                continue
            text = _paragraph(child) if kind == "paragraph" else _block_text(child)
            if not text:
                continue
            text_lines = text.split("\n")
            if first:
                lines.append(f"{indent}{marker}{text_lines[0]}")
                rest = text_lines[1:]
                first = False
            else:
                rest = text_lines
            pad = indent + " " * len(marker)
            lines.extend(f"{pad}{line}" for line in rest)
        if first:  # an empty item
            lines.append(f"{indent}{marker}".rstrip())
    return "\n".join(lines)


def _quote(node: Node) -> str:
    inner = "\n\n".join(t for t in (_block_text(c) for c in node.get("content", [])) if t)
    return "\n".join(f"> {line}" if line else ">" for line in inner.split("\n"))


def _fence(body: str, lang: str = "") -> str:
    body = body.replace("```", "`\u200b``")  # can't close the block early
    return f"```{lang}\n{body}\n```"


def _code_block(node: Node) -> str:
    lang = (node.get("attrs") or {}).get("language") or ""
    return _fence(plain_text_preserving(node), lang)


def plain_text_preserving(node: Node) -> str:
    """Text with its own line breaks kept (for code blocks)."""
    return "".join(
        c.get("text", "") if c.get("type") == "text" else "\n"
        for c in node.get("content", [])
    )


def _cell(text: str) -> str:
    text = " ".join(text.split())
    if len(text) > TABLE_CELL_MAX:
        text = text[: TABLE_CELL_MAX - 1] + "…"
    return text


def table_text(node: Node) -> str:
    """Rows of cells, columns padded to line up, a rule under a header row."""
    rows: list[list[str]] = []
    header = False
    for i, row in enumerate(node.get("content", [])):
        cells = row.get("content", [])
        if i == 0 and cells and all(c.get("type") == "tableHeader" for c in cells):
            header = True
        rows.append([_cell(plain_text(c)) for c in cells])
    if not rows:
        return ""
    columns = max(len(r) for r in rows)
    for r in rows:
        r.extend([""] * (columns - len(r)))
    widths = [max(len(r[c]) for r in rows) for c in range(columns)]

    def line(cells: list[str]) -> str:
        return "  ".join(cell.ljust(widths[c]) for c, cell in enumerate(cells)).rstrip()

    lines = [line(rows[0])]
    if header:
        lines.append("  ".join("─" * w for w in widths))
    lines.extend(line(r) for r in rows[1:])
    return "\n".join(lines)


def _block_text(node: Node) -> str:
    kind = node.get("type")
    if kind == "paragraph":
        return _paragraph(node)
    if kind == "heading":
        return _heading(node)
    if kind in ("bulletList", "orderedList"):
        return _list(node)
    if kind == "blockquote":
        return _quote(node)
    if kind == "codeBlock":
        return _code_block(node)
    if kind == "table":
        return _fence(table_text(node))
    if kind == "horizontalRule":
        return RULE
    # Unknown block: keep its words rather than lose them.
    return escape_text(plain_text(node))


def _usable_picture(src: str) -> bool:
    """A picture we can post: one hosted online (https) or one taken out of
    a Word file ("docx-image:<n>", attached as a file when posting). Pasted
    data: URLs and file:// paths are skipped."""
    return src.startswith(("https://", "docx-image:"))


def _blocks(doc: Node) -> list[Block]:
    blocks = []
    for node in doc.get("content", []):
        kind = node.get("type")
        if kind == "image":
            src = (node.get("attrs") or {}).get("src") or ""
            if _usable_picture(src):
                blocks.append(Block(kind="image", image_url=src))
            continue
        text = _block_text(node)
        # Pictures inside a paragraph (Word puts each picture in one) come
        # after its text, even when the paragraph has no text at all.
        inline_pictures = [
            Block(kind="image", image_url=(child.get("attrs") or {}).get("src"))
            for child in node.get("content", []) or []
            if child.get("type") == "image"
            and _usable_picture((child.get("attrs") or {}).get("src") or "")
        ]
        if not text.strip():
            blocks.extend(inline_pictures)
            continue
        if kind == "heading":
            block_kind = "heading"
        elif kind in ("codeBlock", "table"):
            block_kind = "fenced"
        elif kind == "blockquote":
            block_kind = "quote"
        elif kind in ("bulletList", "orderedList"):
            block_kind = "list"
        else:
            block_kind = "text"
        blocks.append(Block(text=text, kind=block_kind))
        blocks.extend(inline_pictures)
    return blocks


# ---------- splitting into messages ----------


def _split_words(line: str, budget: int) -> list[str]:
    """Split one over-long line at sentence ends, then spaces, then anywhere."""
    pieces: list[str] = []
    rest = line
    while len(rest) > budget:
        window = rest[:budget]
        cut = max(window.rfind(". "), window.rfind("! "), window.rfind("? "))
        if cut > budget // 2:
            cut += 1  # keep the punctuation
        else:
            cut = window.rfind(" ")
            if cut <= 0:
                cut = budget
        pieces.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip()
    if rest:
        pieces.append(rest)
    return pieces


def _split_lines(text: str, budget: int) -> list[str]:
    """Group lines into pieces no longer than budget."""
    pieces: list[str] = []
    current = ""
    for line in text.split("\n"):
        for chunk in _split_words(line, budget) if len(line) > budget else [line]:
            candidate = f"{current}\n{chunk}" if current else chunk
            if len(candidate) <= budget:
                current = candidate
            else:
                if current:
                    pieces.append(current)
                current = chunk
    if current:
        pieces.append(current)
    return pieces


def split_block(block: Block, limit: int = LIMIT) -> list[str]:
    """Split a block that doesn't fit in one message."""
    if block.kind == "fenced":
        first, _, rest = block.text.partition("\n")
        body = rest.rsplit("\n```", 1)[0]
        overhead = len(first) + len("\n\n```")
        return [f"{first}\n{piece}\n```" for piece in _split_lines(body, limit - overhead)]
    if block.kind == "quote":
        # Each line keeps its own "> ", so any split stays a quote.
        return _split_lines(block.text, limit)
    return _split_lines(block.text, limit)


def pack(blocks: list[Block], limit: int = LIMIT) -> list[Part]:
    """Fill messages with whole blocks, starting a new message for pictures
    and for headings that would otherwise be stranded at a message's end."""
    parts: list[Part] = []
    current = ""
    sep = "\n\n"

    def flush():
        nonlocal current
        if current.strip():
            parts.append(Part(content=current))
        current = ""

    for i, block in enumerate(blocks):
        if block.kind == "image":
            flush()
            parts.append(Part(image_url=block.image_url))
            continue
        joined = f"{current}{sep}{block.text}" if current else block.text
        if block.kind == "heading" and current and i + 1 < len(blocks):
            follower = blocks[i + 1]
            if follower.kind != "image" and len(joined) + len(sep) + len(follower.text) > limit:
                flush()  # keep the heading with the text under it
                joined = block.text
        if len(joined) <= limit:
            current = joined
            continue
        flush()
        if len(block.text) <= limit:
            current = block.text
        else:
            pieces = split_block(block, limit)
            parts.extend(Part(content=p) for p in pieces[:-1])
            current = pieces[-1]
    flush()
    return parts


def render_article(doc: Node, limit: int = LIMIT) -> list[Part]:
    """The whole article as Discord messages, in order."""
    return pack(_blocks(doc), limit)


def word_count(doc: Node) -> int:
    return len(plain_text(doc).split())
