"""Parliament questions and answers on PPP and VGF (Lok Sabha and Rajya Sabha), with the answer PDFs.

python fetch.py [OUT_DIR] [--no-pdf] [--kw "keyword" ...]

Standard library only. Writes OUT_DIR/index.csv (one row per question) and OUT_DIR/pdf/<house>-<id>.pdf. A second run skips
files that it already has. One request every 2 seconds.
"""
import csv
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

KEYWORDS = ["viability gap", "VGF", "public private partnership", "PPPAC", "concession agreement", "IIPDF",
            "infrastructure project development fund", "national monetisation pipeline", "toll operate transfer"]
LOK_SABHAS = range(13, 19)
LS_API = "https://sansad.in/api_ls/question/qetFilteredQuestionsAns"
RS_API = "https://integration.rajyasabha.digital/rsdebate/api/question/search-questions"
DELAY = 2.0
UA = {"User-Agent": "Mozilla/5.0 (research; PPP question index)"}
GAPS = []                                            # search pages that did not load: the index is incomplete
FIELDS = ["house", "id", "term", "qno", "qtype", "date", "ministry", "subject", "keywords", "url", "file", "bytes", "sha256"]


def get(url, tries=3):
    for i in range(tries):
        time.sleep(DELAY)
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):                 # the file is not there: trying again does not help
                print(f"  {e.code}: {url}", file=sys.stderr)
                return None
            print(f"  retry {i + 1}: {e}", file=sys.stderr)
            time.sleep(10 * (i + 1))
        except Exception as e:                       # noqa: BLE001 - network errors of any kind: wait and try again
            print(f"  retry {i + 1}: {e}", file=sys.stderr)
            time.sleep(10 * (i + 1))
    return None


def ls_rows(kw):
    for ls in LOK_SABHAS:
        page = 1
        while True:
            q = urllib.parse.urlencode({"loksabhaNo": ls, "pageNo": page, "pageSize": 100, "locale": "en", "keyWord": kw})
            body = get(f"{LS_API}?{q}")
            if body is None:
                GAPS.append(f"LS{ls} '{kw}' page {page}")
                break
            d = json.loads(body)[0]
            for x in d["listOfQuestions"]:
                yield {"house": "LS", "id": f"{ls}-{x['type'][:1]}{x['quesNo']}-{x['date']}", "term": f"LS{ls} session {x.get('sessionNo')}",
                       "qno": x["quesNo"], "qtype": x["type"].strip(), "date": x["date"], "ministry": x["ministry"],
                       "subject": x["subjects"].strip(), "url": (x.get("questionsFilePath") or "").strip()}
            if page * 100 >= d["totalRecordSize"]:
                break
            page += 1


def rs_rows(kw):
    page = 0
    while True:
        q = urllib.parse.urlencode({"sessionFrom": 1, "sessionTo": 400, "searchParam": kw, "searchOn": "fullText",
                                    "matchesOn": "exactMatch", "page": page, "size": 100})
        body = get(f"{RS_API}?{q}")
        if body is None:
            GAPS.append(f"RS '{kw}' page {page}")
            break
        d = json.loads(body)
        for x in d.get("records") or []:
            f, name = x.get("files") or "", x.get("eng_file_name") or ""
            key, stem = f.split("?")[0].rsplit("/", 1)[-1], name.removesuffix(".pdf")
            url = f if ".rajyasabha.digital" in f else ""
            if url and stem.startswith(key) and stem != key:      # newer answers: `files` holds a shortened key
                url = f.split("?")[0].rsplit("/", 1)[0] + "/" + stem
            yield {"house": "RS", "id": str(x["qslno"]), "term": f"RS session {x['ses_no']}", "qno": x["qno"], "qtype": x["qtype"].strip(),
                   "date": x["ans_date"], "ministry": x["min_name"], "subject": x["qtitle"].strip(), "url": url}
        if page + 1 >= d["_metadata"]["totalPages"]:
            break
        page += 1


def main():
    args = sys.argv[1:]
    out = args[0] if args and not args[0].startswith("--") else "out"
    kws = [args[i + 1] for i, a in enumerate(args) if a == "--kw"] or KEYWORDS
    os.makedirs(os.path.join(out, "pdf"), exist_ok=True)
    rows = {}
    for kw in kws:
        for house, fn in (("LS", ls_rows), ("RS", rs_rows)):
            n = 0
            for r in fn(kw):
                key = (r["house"], r["id"])
                rows.setdefault(key, {**r, "keywords": []})["keywords"].append(kw)
                n += 1
            print(f"{house} '{kw}': {n}", file=sys.stderr)
    for r in rows.values():
        r["keywords"] = "; ".join(sorted(set(r["keywords"])))
        if not r["url"] or "--no-pdf" in args:
            continue
        htm = r["url"].split("?")[0].endswith(".htm")            # 15th and 16th Lok Sabha answers are HTML pages
        r["file"] = f"pdf/{r['house']}-{r['id'].replace('.', '')}.{'htm' if htm else 'pdf'}"
        path = os.path.join(out, r["file"])
        if not os.path.exists(path):
            body = get(r["url"])
            if body is None or not (htm or body[:5] == b"%PDF-"):
                print(f"  no PDF: {r['url']}", file=sys.stderr)
                r["file"] = ""
                continue
            open(path, "wb").write(body)
        data = open(path, "rb").read()
        r["bytes"], r["sha256"] = len(data), hashlib.sha256(data).hexdigest()
    with open(os.path.join(out, "index.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(rows.values(), key=lambda r: (r["house"], r["date"][6:], r["date"][3:5], r["date"][:2])))   # dates are DD.MM.YYYY
    print(f"{len(rows)} questions, {sum(1 for r in rows.values() if r.get('file'))} PDFs in {out}", file=sys.stderr)
    if GAPS:
        sys.exit(f"index incomplete, these search pages did not load (run again): {'; '.join(GAPS)}")


if __name__ == "__main__":
    main()
