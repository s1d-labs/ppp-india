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
import time
from urllib.parse import unquote

from scrape_hub_client import HubClient, LocalHub, stop_flag

import docs
import portal
from htmltables import rid, shard_of
from taskrun import STOP, get, now, pause, run, session, time_up

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


def old_index():
    """{project id: [capture timestamp, original url]} of the old portal's archived view-project pages (wayback/index.json.gz,
    built from the Wayback CDX on 2026-11-14: 1,863 ids, latest capture of each)."""
    return json.loads(gzip.decompress(open(os.path.join(os.path.dirname(__file__), "wayback", "index.json.gz"), "rb").read()))


def do_old(hub, s, item):
    p = item["payload"]
    index = old_index()
    mine = [str(x) for x in p["pids"]] if p.get("pids") else \
        sorted((pid for pid in index if shard_of(pid, int(p["shards"])) == int(p["shard"])), key=int)   # pids: a retry item
    stored = errors = 0
    for pid in mine:
        if time_up():
            return None, "time up before the shard finished"
        ts, original = index[pid]
        url = f"https://web.archive.org/web/{ts}id_/{original}"
        fields = []
        for wait in (0, 60):                       # the archive answers 429 or a "Temporarily Offline" page when busy
            time.sleep(wait)
            r = get(hub, s, url)
            pause(hub, 1.5)
            pdf = r is not None and r.status_code == 200 and r.content[:5] == b"%PDF-"
            fields = portal.old_project(r.text) if r is not None and r.status_code == 200 and not pdf else []
            if fields or pdf or STOP.is_set():
                break
        if pdf:                                    # some captures are the old site's "project details" PDF export
            info, txt = docs.inspect(r.content, "application/pdf", f"{pid}.pdf")
            files, extra = docs.uploads(info, r.content, txt, "wayback")
            hub.upload_many(files)
            hub.record(f"old:{pid}", {"kind": "old_project_pdf", "old_id": int(pid), "captured": ts, "wayback_url": url,
                                      "text": txt[:20000], **info, **extra, "fetched_at": now()})
            hub.clear_failure("wayback", pid)
            stored += 1
            continue
        if not fields:
            errors += 1
            hub.failure("wayback", pid, f"no project fields (HTTP {getattr(r, 'status_code', None)})", url=url)
            continue
        up = hub.upload_many([(f"wayback/{pid}-{ts}.html.gz", gzip.compress(r.content), "application/gzip")])
        flat = {}
        for section, label, value in fields:
            flat[label if label not in flat else f"{section}: {label}"] = value
        mode = re.search(r"_ppp=([^&]*)", original, re.I)
        hub.record(f"old:{pid}", {"kind": "old_project", "old_id": int(pid), "captured": ts, "wayback_url": url,
                                  "mode": unquote(mode.group(1).replace("+", " ")) if mode else None, "fields": flat,
                                  "pairs": fields, "bucket_path": up[0]["path"] if up else None, "fetched_at": now()})
        stored += 1
    if mine and errors > len(mine) // 2:
        return None, f"{errors} of {len(mine)} archived pages did not load"
    return stored, None


def do_wbdoc(hub, s, item):
    """Archived copies of portal documents (wayback/docs.json.gz: [timestamp, url, cdx digest, why]): files the current site no
    longer links ("gone"), and every archived version of agreements and RoDs that changed under the same name ("version")."""
    p = item["payload"]
    caps = json.loads(gzip.decompress(open(os.path.join(os.path.dirname(__file__), "wayback", "docs.json.gz"), "rb").read()))
    mine = [c for c in caps if shard_of(c[2], int(p["shards"])) == int(p["shard"])]
    stored = errors = 0
    for ts, original, digest, why in mine:
        if time_up():
            return None, "time up before the shard finished"
        url = f"https://web.archive.org/web/{ts}id_/{original}"
        for wait in (0, 60):
            time.sleep(wait)
            r = get(hub, s, url)
            pause(hub, 1.5)
            if (r is not None and r.status_code == 200 and r.content[:5] == b"%PDF-") or STOP.is_set():
                break
        if r is None or r.status_code != 200 or r.content[:5] != b"%PDF-":
            errors += 1
            hub.failure("wbdoc", digest, f"no PDF (HTTP {getattr(r, 'status_code', None)})", url=url)
            continue
        file = unquote(original.split("?")[0].rsplit("/", 1)[-1])
        info, txt = docs.inspect(r.content, "application/pdf", file)
        files, extra = docs.uploads(info, r.content, txt, "wayback-docs")
        hub.upload_many(files)
        hub.record(f"wbdoc:{digest}", {"kind": "wbdoc", "why": why, "captured": ts, "original": original, "file": file,
                                       "wayback_url": url, **info, **extra, "fetched_at": now()})
        hub.clear_failure("wbdoc", digest)
        stored += 1
    if mine and errors > len(mine) // 2:
        return None, f"{errors} of {len(mine)} archived documents did not load"
    return stored, None


HANDLERS = {"page": do_page, "docs": do_docs, "old": do_old, "wbdoc": do_wbdoc}


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
