"""The family's `crawl` task: www.pppinindia.gov.in list pages and the documents they link (PPPAC, VGF, concession agreements,
pipeline, project database). Two kinds of queue items (family.py):

- page: fetch one list page, keep the raw page in the bucket (evidence), store one record per table row and one page record;
- docs: fetch one list page again and download the documents it links (one shard of them), monthly. A link that answers 404
  gets a `missing` record; a replaced file gets a new record (the id holds the file's sha256), so old versions stay.

Try one page without the hub: python crawl.py --local pppac_projects_list
"""
import gzip
import json
import os
import re
import sys
from urllib.parse import unquote

from scrape_hub_client import HubClient, LocalHub, stop_flag

import docs
import portal
from htmltables import rid, shard_of
from taskrun import get, now, pause, run, session, time_up

PROJECT = os.environ.get("SCRAPE_POOL_PROJECT", "")
SITE = os.environ.get("SITE", portal.SITE)


def slug(path):
    return re.sub(r"[^a-z0-9]+", "-", unquote(path).lower()).strip("-") or "home"


def fetch_page(hub, s, path):
    r = get(hub, s, SITE + path)
    if r is None or r.status_code != 200:
        return None, f"page answered {getattr(r, 'status_code', 'nothing')}"
    r.encoding = r.encoding if r.encoding and r.encoding.lower() != "iso-8859-1" else "utf-8"
    return r.text, None


def do_page(hub, s, item):
    p = item["payload"]
    path, rnd, name = p["path"], p.get("round", ""), slug(p["path"])
    html, err = fetch_page(hub, s, path)
    if err:
        return None, err
    rows = portal.rows(html, name, SITE)
    if p.get("expected", 0) > 1 and not rows:
        return None, "no table rows (layout changed?)"
    up = hub.upload_many([(f"pages/{rnd}/{name}.html.gz", gzip.compress(html.encode()), "application/gzip")])
    seen = now()
    for row_id, data in rows:
        hub.record(row_id, {**data, "url": SITE + path, "round": rnd, "seen_at": seen})
    links = portal.doc_links(html, name, SITE)
    hub.record(f"page:{name}:{rnd}", {"kind": "page", "page": name, "url": SITE + path, "round": rnd, "seen_at": seen,
                                      "rows": len(rows), "docs": len(links), "report_counts": portal.report_counts(html),
                                      "bucket_path": up[0]["path"] if up else None})
    return len(rows) + 1, None


def do_docs(hub, s, item):
    p = item["payload"]
    path, rnd, name = p["path"], p.get("round", ""), slug(p["path"])
    shard, shards = int(p.get("shard", 0)), int(p.get("shards", 1))
    html, err = fetch_page(hub, s, path)
    if err:
        return None, err
    links = portal.doc_links(html, name, SITE)
    mine = sorted(u for u in links if shard_of(u, shards) == shard)
    stored = errors = 0
    for url in mine:
        if time_up():
            return None, "time up before the shard finished"
        pause(hub, 0.5)
        r = get(hub, s, url)
        file = url.split("?")[0].rsplit("/", 1)[-1]
        if r is None:
            errors += 1
            hub.failure("doc-error", url, "no answer", page=name)
            continue
        hub.clear_failure("doc-error", url)
        if r.status_code != 200:
            hub.record(f"{rid('missing', url)}:{rnd}", {"kind": "missing", "url": url, "page": name, "file": file,
                                                       "status": r.status_code, "rows": links[url], "round": rnd, "checked_at": now()})
            hub.failure("doc-missing", url, f"HTTP {r.status_code}", page=name)
            stored += 1
            continue
        body = r.content
        info, txt = docs.inspect(body, r.headers.get("content-type", ""), file)
        files, fields = docs.uploads(info, body, txt, name)
        hub.upload_many(files)
        hub.record(f"{rid('doc', url)}:{info['sha256'][:12]}", {
            "kind": "doc", "url": url, "page": name, "file": file, "rows": links[url], "round": rnd, "fetched_at": now(),
            "last_modified": r.headers.get("last-modified"), "etag": r.headers.get("etag"),
            "content_type": r.headers.get("content-type"), **info, **fields})
        stored += 1
    if mine and errors > len(mine) // 2:
        return None, f"{errors} of {len(mine)} documents did not answer"
    return stored, None


HANDLERS = {"page": do_page, "docs": do_docs}


def local(path):
    hub = LocalHub()
    html, err = fetch_page(hub, session(), path)
    if err:
        sys.exit(err)
    rows = portal.rows(html, slug(path), SITE)
    for row_id, data in rows:
        print(json.dumps({"record_id": row_id, "data": data}, ensure_ascii=False))
    print(f"{len(rows)} rows, {len(portal.doc_links(html, slug(path), SITE))} document links, counters {hub.counts}", file=sys.stderr)


def main():
    stop_flag()
    hub = HubClient(PROJECT, job_index=int(os.environ.get("SCRAPE_JOB_INDEX", "0")), total_jobs=int(os.environ.get("SCRAPE_TOTAL_JOBS", "1")))
    run(hub, session(), HANDLERS, margin_min=10)


if __name__ == "__main__":
    if sys.argv[1:2] == ["--local"]:
        local(sys.argv[2] if len(sys.argv) > 2 else "pppac_projects_list")
    else:
        main()
