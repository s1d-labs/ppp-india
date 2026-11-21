"""What this family scrapes: DEA's PPP portal www.pppinindia.gov.in (PPPAC approvals, VGF, concession agreements, the PPP
pipeline and the infrastructure project database), and the documents it links (Records of Discussion, signed agreements).

FAMILY equals the repo name (s1d-labs/ppp-india). After a change here, run the Setup workflow (Actions -> setup). seed_queue keeps
existing keys, so a new ROUND (the weekly setup sets ROUND=<ISO week>) fetches every list page again, and a new DOCS_ROUND (month)
downloads the documents again. The server's If-Modified-Since only matches an exact date (no 304 for older files), and a task
cannot read what it stored before, so a monthly document round is the cheap way to catch replaced files (the bucket is
content-addressed: an unchanged file costs bandwidth, not space).
The site answers GitHub's runners and the team box directly: no proxy. It refuses HEAD requests (403); GET only.
"""
import json
import os
from pathlib import Path

FAMILY = json.loads((Path(__file__).parent / "scrape.json").read_text())["family"]
ROUND = os.environ.get("ROUND") or "2026-W46"
DOCS_ROUND = os.environ.get("DOCS_ROUND") or "2026-11"
SITE = "https://www.pppinindia.gov.in/"

# list page -> (table rows, document links) on 2026-11-14. Rows give progress; pages with documents also get docs items.
PAGES = {
    # PPPAC (central projects appraisal) and its meetings
    "pppac_projects_list": (425, 151), "pppac_projects_summary": (95, 0), "pppac_meetings": (144, 154), "pppac": (6, 11),
    "consolidated": (998, 172),
    # VGF (Empowered Committee / Empowered Institution) and IIPDF
    "vgf_inprinciple_project_list": (253, 88), "vgf_final_project_list": (72, 66), "vgf_projects_summary": (104, 0),
    "vgf_projects_final_summary": (62, 0), "ec_meetings": (57, 63), "ei_meetings": (84, 84), "vgfguidelines": (12, 24),
    "iipdf_projects": (31, 25), "iipdf_projects_summary": (26, 0), "iipdf_meetings": (32, 32), "guidelines_for_iipdf": (6, 13),
    "sfc_projects": (0, 0), "state-projects": (0, 0), "reit_invit": (0, 0),
    # agreements and bidding documents
    "signed_concession_agreements": (220, 92), "draft_concession_agreements": (0, 2), "model_concession_agreement": (7, 7),
    "model_request_proposal": (8, 8), "model_request_qualification": (1, 1), "bidding-doc": (0, 1),
    "bidding_doc_detail": (0, 16), "bidding_doc_ahp": (0, 4), "tenders": (19, 24), "circulars_and_orders": (41, 42),
    "guidance_material_and_reference_doc": (0, 34), "contigent-liability-toolkit": (0, 2), "": (0, 29),
    # infrastructure project database (all 9,243 projects; the three mode pages show only their first 100)
    "all_infrastructure_projects": (9243, 0), "goverment_infrastructure_projects_ppp": (100, 0),
    "goverment_infrastructure_projects_traditional_procurement": (100, 0), "private_sector_infrastructure_projects": (100, 0),
    "goverment_infrastructure_projects": (100, 0), "authority_wise_summary_report": (100, 0),
    "sector_wise_summary_report": (28, 0), "state_wise_summary_report": (35, 0), "status_wise_summary_report": (5, 0),
    "year_wise_summary_report": (36, 0),
    # PPP pipeline: central ministries and states
    "ppp-projects-pipeline": (2, 0), "ppp-projects-pipeline-ministries": (8, 0), "ppp-projects-pipeline-states": (23, 0),
}
PIPELINE_DEPTS = ["mopower", "moca", "mopng", "dowrgr", "mopsw", "dpiit", "railways", "morth"]
PIPELINE_STATES = ["andaman and nicobar islands", "andhra_pradesh", "arunachal_pradesh", "assam", "chhattisgarh", "goa", "gujarat",
                   "haryana", "himachal_pradesh", "jammu and kashmir", "karnataka", "madhya_pradesh", "nagaland", "odisha",
                   "puducherry", "punjab", "rajasthan", "sikkim", "tamil_nadu", "telangana", "tripura", "uttar_pradesh", "west_bengal"]
PAGES.update({f"ppp-projects-pipeline-department?dept={d}": (30, 0) for d in PIPELINE_DEPTS})
PAGES.update({f"ppp-projects-pipeline-states-yearwise?state={s.replace(' ', '%20')}": (35, 0) for s in PIPELINE_STATES})
DOCS_PER_SHARD = 60


# document links that the first round missed (HTML entities / backslashes in the href, fixed 15 Nov 2026): fetched once
DOC_FIXES = {
    "ec_meetings": [
        "https://www.pppinindia.gov.in/docs/document/vgf/RoD%20of%20the%20125th%20%20PPPAC%20&%2048th%20EC%20meeting.pdf"
    ],
    "pppac_meetings": [
        "https://www.pppinindia.gov.in/docs/document/pppac/OM%20dated%2029th%20November,2023%20RoD%20of%20meeting%20of%20112th%20PPPAC%20and%2043rd%20EC%20for%20considering%20the%20proposal%20'Development%20of%20Outer%20Harbour%20container%20Terminal%20project%20including%20dredging%20and%20construction%20of%20Breakwater'%20at%20VOC%20Port,%20Tut.pdf",
        "https://www.pppinindia.gov.in/docs/document/pppac/RoD%20of%20the%20125th%20%20PPPAC%20&%2048th%20EC%20meeting.pdf"
    ],
    "guidance_material_and_reference_doc": [
        "https://www.pppinindia.gov.in/report/Guidance%20Note%20for%20IT%20PPP%20Projects%20by%20Ministry%20of%20Electronics%20&%20Information%20Technology%20(2017).pdf_1685172518.pdf",
        "https://www.pppinindia.gov.in/report/Guidance%20Note%20for%20IT%20PPP%20Projects%20by%20Ministry%20of%20Electronics%20&%20Information%20Technology%20(2017).pdf_1686045046.pdf",
        "https://www.pppinindia.gov.in/report/Report%20of%20the%20Committee%20on%20Revisiting%20&%20Revitalizing%20the%20Public%20Private%20Partnership%20Model%20of%20Infrastructure%20(Kelkar%20Committee%20Report).pdf_1685171086.pdf"
    ],
    "guidelines_for_iipdf": [
        "https://www.pppinindia.gov.in/assets/doc/iipdf/Book_IIPDF%20Schemes%20(05.11).pdf"
    ],
    "": [
        "https://www.pppinindia.gov.in/report/Infrastructure%20Newsletter%20Apr%20&%20May'23_v3_1697453314.pdf",
        "https://www.pppinindia.gov.in/report/Infrastructure%20Newsletter%20Aug%20&%20Sep%20'23_v4_1697453790.pdf",
        "https://www.pppinindia.gov.in/report/Infrastructure%20Newsletter%20Dec'22%20&%20Jan'23_v2_1697452789.pdf",
        "https://www.pppinindia.gov.in/report/Infrastructure%20Newsletter%20Dec'23%20&%20Jan'24_Final_1709560431.pdf",
        "https://www.pppinindia.gov.in/report/Infrastructure%20Newsletter%20Feb%20&%20Mar%202024_1720500514.pdf",
        "https://www.pppinindia.gov.in/report/Infrastructure%20Newsletter%20Feb%20&%20Mar'23-Final_1697453095.pdf",
        "https://www.pppinindia.gov.in/report/Infrastructure%20Newsletter%20Jun%20&%20Jul%20'23_v4_1697453548.pdf",
        "https://www.pppinindia.gov.in/report/Infrastructure%20Newsletter%20Oct%20&%20Nov'23_v2_1703829312.pdf"
    ]
}


def portal_items():
    items = [{"key": f"{ROUND}/page/{path or 'home'}", "payload": {"kind": "page", "path": path, "round": ROUND, "expected": n + 1}}
             for path, (n, _) in PAGES.items()]
    for path, (_, d) in PAGES.items():
        shards = max(1, -(-d // DOCS_PER_SHARD))
        items += [{"key": f"{DOCS_ROUND}/docs/{path or 'home'}/{k}-of-{shards}",
                   "payload": {"kind": "docs", "path": path, "shard": k, "shards": shards, "round": DOCS_ROUND,
                               "expected": max(1, d // shards)}}
                  for k in range(shards) if d]
    items += [{"key": f"2026-11/docs-fix/{path or 'home'}", "payload": {"kind": "docs", "path": path, "urls": urls, "round": "2026-11",
                                                                     "expected": len(urls)}} for path, urls in DOC_FIXES.items()]
    return items


PROJECTS = [
    {
        "name": f"{FAMILY}-portal",
        "title": "PPP India portal (DEA): PPPAC, VGF, concession agreements, pipeline, project database, and their documents",
        "task": "crawl", "target": "www.pppinindia.gov.in", "env": {"SITE": SITE}, "probe": f"{FAMILY}:www.pppinindia.gov.in",
        "unit_label": "page", "record_label": "row", "threads": 1, "delay_ms": 500, "max_workers": 2,
        "items": portal_items(),
    },
]

WBDOC_SHARDS = 22         # 764 archived documents
OLD_SHARDS = 47          # 1,863 archived old project pages, about 40 per item

PROJECTS.append({
    "name": f"{FAMILY}-wayback",
    "title": "PPP India old project database (2016-2023) from the Wayback Machine: concessionaires, contract and revised costs",
    "task": "crawl", "target": "web.archive.org", "env": {}, "probe": f"{FAMILY}:web.archive.org",
    "unit_label": "shard", "record_label": "project", "threads": 1, "delay_ms": 1500, "max_workers": 2,
    "items": [{"key": f"old/{k}-of-{OLD_SHARDS}", "payload": {"kind": "old", "shard": k, "shards": OLD_SHARDS, "expected": 40}}
              for k in range(OLD_SHARDS)]
             # archived documents: 535 no longer linked, 229 versions of changed agreements / RoDs (wayback/docs.json.gz)
             + [{"key": f"wbdoc/{k}-of-{WBDOC_SHARDS}", "payload": {"kind": "wbdoc", "shard": k, "shards": WBDOC_SHARDS, "expected": 35}}
                for k in range(WBDOC_SHARDS)],
})

PROBES = [{"name": f"{FAMILY}:www.pppinindia.gov.in", "url": SITE + "model_request_qualification",
           "expect": "public private partnership"},
          {"name": f"{FAMILY}:web.archive.org", "url": "https://web.archive.org/", "expect": "Wayback Machine"}]
