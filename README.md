# ppp-india

This family scrapes the PPP portal of the Department of Economic Affairs (DEA): https://www.pppinindia.gov.in/.

## What it collects

- PPPAC project list, summaries, meetings and Records of Discussion (RoD).
- VGF in-principle and final approvals, Empowered Committee (EC) and Empowered Institution (EI) meetings, IIPDF projects.
- Signed and draft concession agreements, model agreements, RFQ and RFP documents, circulars and tenders.
- The PPP pipeline of central ministries and states.
- The infrastructure project database (9,243 projects on 14 Nov 2026).

## How it works

- One project: `ppp-india-portal`. One task: `crawl` (`crawl.py`).
- A `page` item fetches one list page. It stores one record for each table row, one page record and the raw page (bucket).
- A `docs` item downloads the documents that one list page links. Files go to the bucket under their sha256.
- Row ids hash the row content without the serial number. A changed row gets a new id. The old version stays.
- The Setup workflow runs every Monday. List pages refresh each week. Documents refresh each month.
- The site answers without a proxy. It refuses HEAD requests.

## Check

```
python -m pytest tests -q
python crawl.py --local vgf_final_project_list
scrape-check --items 2
```
