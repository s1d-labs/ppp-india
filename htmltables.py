"""A small, forgiving HTML table reader (stdlib only) for the corporations' list pages.

Government pages often leave <tr> and <td> open, nest tables inside cells, and put the headings in commented-out rows. This
reader keeps what a person sees: comments are skipped, every <tr> starts a new row, every <td>/<th> a new cell, and a table inside
a cell is kept as that cell's own table. Each cell gives its text (spaces collapsed), its links (href, link text) and its
nested tables.
"""
import re
from html import unescape
from html.parser import HTMLParser

_WS = re.compile(r"\s+")


def clean(s):
    return _WS.sub(" ", unescape(s or "").replace("\xa0", " ")).strip()


class Cell:
    __slots__ = ("parts", "links", "tables", "header", "attrs")

    def __init__(self, header=False, attrs=None):
        self.parts, self.links, self.tables, self.header, self.attrs = [], [], [], header, attrs or {}

    @property
    def text(self):
        return clean(" ".join(self.parts))

    def __repr__(self):
        return f"Cell({self.text!r})"


class Table:
    __slots__ = ("rows", "attrs", "before")

    def __init__(self, attrs=None, before=""):
        self.rows, self.attrs, self.before = [], attrs or {}, before

    def data_rows(self):
        """Rows with at least one non-header cell that has text or a link or a nested table."""
        return [r for r in self.rows if any(not c.header for c in r)
                and any(c.text or c.links or c.tables for c in r)]

    def header(self):
        return [c.text for r in self.rows for c in r if c.header]


class _Reader(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []            # top-level tables, in page order
        self.stack = []             # open tables (innermost last)
        self.cell_stack = []        # the cell each open table lives in (None for top level)
        self.link = None            # [href, [text parts]] while inside <a>
        self.skip = 0               # inside <script>/<style>
        self.recent = []            # text seen outside tables (for Table.before)

    def _cell(self):
        if not self.stack:
            return None
        t = self.stack[-1]
        if not t.rows or not t.rows[-1]:
            return None
        return t.rows[-1][-1]

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style"):
            self.skip += 1
        elif tag == "table":
            t = Table(a, before=clean(" ".join(self.recent[-40:])))
            parent = self._cell()
            if parent is not None:
                parent.tables.append(t)
            elif not self.stack:
                self.tables.append(t)
            else:                               # table directly in a table (no cell): treat as top level
                self.tables.append(t)
            self.stack.append(t)
            self.recent = []
        elif tag == "tr" and self.stack:
            self.stack[-1].rows.append([])
        elif tag in ("td", "th") and self.stack:
            t = self.stack[-1]
            if not t.rows:
                t.rows.append([])
            t.rows[-1].append(Cell(header=(tag == "th"), attrs=a))
        elif tag == "a":
            self.link = [a.get("href") or "", []]
        elif tag in ("br", "p", "li", "div") and self._cell() is not None:
            self._cell().parts.append(" ")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
        elif tag == "table" and self.stack:
            self.stack.pop()
        elif tag == "a" and self.link is not None:
            href, parts = self.link
            c = self._cell()
            if c is not None and href:
                c.links.append((href.strip(), clean(" ".join(parts))))
            self.link = None

    def handle_data(self, data):
        if self.skip:
            return
        c = self._cell()
        if c is not None:
            c.parts.append(data)
        elif data.strip():
            self.recent.append(data)
        if self.link is not None:
            self.link[1].append(data)


def tables(html):
    """Top-level tables of a page (nested tables are reachable through their cells)."""
    r = _Reader()
    r.feed(re.sub(r"<!--.*?-->", " ", html, flags=re.S))
    r.close()
    return r.tables


# ---- small helpers shared by the site parsers ----
import hashlib  # noqa: E402
from datetime import datetime  # noqa: E402

_DATE_FORMATS = ("%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y", "%d-%b-%Y", "%d-%B-%Y", "%a %b %d %H:%M:%S IST %Y", "%a %b %d %H:%M IST %Y")


def iso_date(s):
    """'25.11.2024', '29/07/2025', '24-Sep-2026', '26-OCT-2026', 'Wed Mar 09 13:30:00 IST 2016' -> '2024-11-25'; else None."""
    s = clean(s)
    m = re.search(r"\d{1,2}[./-](?:\d{1,2}|[A-Za-z]{3,9})[./-]\d{4}", s)
    cands = [m.group(0)] if m else []
    cands.append(s)
    for c in cands:
        for f in _DATE_FORMATS:
            try:
                return datetime.strptime(c.title() if "%b" in f or "%B" in f else c, f).date().isoformat()
            except ValueError:
                pass
    return None


def num(s):
    """'2,37,000.00' -> 237000.0, '5' -> 5.0, '' / '-' -> None."""
    s = clean(s).replace(",", "")
    m = re.fullmatch(r"-?\d+(?:\.\d+)?", s)
    return float(m.group(0)) if m else None


def rid(kind, *parts):
    """A stable record id: '<kind>:<sha1 of the normalised parts>[:20]'."""
    key = "|".join(clean(str(p)).lower() for p in parts)
    return f"{kind}:{hashlib.sha1(key.encode()).hexdigest()[:20]}"


def shard_of(key, shards):
    return int(hashlib.sha1(key.encode()).hexdigest(), 16) % shards


def code_in_parens(s):
    """'SAI PARENTERALS LTD (U0810)' -> ('SAI PARENTERALS LTD', 'U0810'); no code -> (s, None)."""
    s = clean(s)
    m = re.match(r"^(.*?)\s*\(([^()]*)\)\s*$", s)
    if m:
        return m.group(1).strip(), (m.group(2).strip() or None)
    return s, None


def page_name(page, arg):
    """Queue key and bucket name of a list page: 'blacklist', 'drugrc-t25048', 'equipmentrc-reagents-kits-consumables'."""
    return page if arg is None else f"{page}-{re.sub(r'[^a-z0-9]+', '-', str(arg).lower()).strip('-')}"
