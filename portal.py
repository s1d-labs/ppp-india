"""Pure parsing of www.pppinindia.gov.in pages (DEA's PPP portal). Every list page is a server-rendered HTML table, so one
generic reader covers them all: one record per table row, with the column headings as keys, the links of each cell, and the
document links of the row. Test it on saved pages (tests/pages/).

Row ids hash the row's content (without the serial number, which shifts when a new row is added at the top). So a row whose
cost, date or document changes on the site gets a new id, and the old version stays in the hub with an older `round`: the
history of changed and removed rows comes for free.
"""
import re
from urllib.parse import quote, urljoin

from htmltables import clean, rid, tables

SITE = "https://www.pppinindia.gov.in/"
DOC = re.compile(r"\.(pdf|xlsx?|docx?|zip|pptx?|csv|rar)$", re.I)
SKIP_COL = re.compile(r"^(s\.?\s*no|sr\.?\s*no|sl\.?\s*no|action|queries|download pdf|view)\.?$", re.I)
REPORT_COUNT = re.compile(r"<li[^>]*>\s*([^<:]{3,60}):\s*<span>\s*([\d,.]+)\s*</span>", re.I)
PIPELINE_ID = re.compile(r'class="[^"]*ask-question[^"]*"\s+data-id="(\d+)"')


def absolute(href, base=SITE):
    """A link as an absolute URL with spaces and other unsafe characters quoted ('#' and javascript: give None)."""
    href = (href or "").strip()
    if not href or href.startswith(("#", "javascript:", "mailto:")):
        return None
    return quote(urljoin(base, href), safe=":/?&=%#,;+()~'@!$*")


def heading(table):
    """The column headings: the first row whose cells are all <th>."""
    for r in table.rows:
        if r and all(c.header for c in r):
            return [c.text for c in r]
    return []


def rows(html, page, base=SITE):
    """[(record_id, data)] for every table row on the page."""
    out, seen = [], {}
    ids = PIPELINE_ID.findall(html)
    for ti, t in enumerate(tables(html)):
        hdr = heading(t)
        data_rows = t.data_rows()
        if len(data_rows) == 1 and len([c for c in data_rows[0] if c.text]) == 1 and "not available" in data_rows[0][0].text.lower():
            continue                                    # "Currently SFC Projects are not available"
        for ri, r in enumerate(data_rows):
            fields, links, docs = {}, {}, []
            for i, c in enumerate(r):
                name = hdr[i] if i < len(hdr) and hdr[i] else f"col{i}"
                fields[name] = c.text
                hrefs = [u for u in (absolute(h, base) for h, _ in c.links) if u]
                if hrefs:
                    links[name] = hrefs
                    docs += [u for u in hrefs if DOC.search(u.split("?")[0])]
            key = [v for k, v in fields.items() if not SKIP_COL.match(k)] + sorted(docs)
            n = seen[tuple(key)] = seen.get(tuple(key), 0) + 1    # identical rows: keep each one
            data = {"kind": "row", "page": page, "table": ti, "row": ri, "headings": hdr, "fields": fields}
            if links:
                data["links"] = links
            if docs:
                data["docs"] = sorted(set(docs))
            if ids and len(ids) == len(data_rows):
                data["pipeline_id"] = int(ids[ri])     # the portal's own pipeline project id (Ask / View buttons)
            out.append((rid("row", page, ti, n, *key), data))
    return out


def report_counts(html):
    """{'No. of Projects in this Report': '1824', ...}: the totals some pages print above their table."""
    return {clean(k): clean(v) for k, v in REPORT_COUNT.findall(html)}


def doc_links(html, page, base=SITE):
    """{url: [row record ids]} for every document link on the page (links outside tables get an empty list)."""
    out = {}
    for row_id, data in rows(html, page, base):
        for u in data.get("docs", []):
            out.setdefault(u, []).append(row_id)
    for h in re.findall(r'href="([^"]+)"', html):
        u = absolute(h, base)
        if u and u.startswith(SITE) and DOC.search(u.split("?")[0]):
            out.setdefault(u, [])
    return out
