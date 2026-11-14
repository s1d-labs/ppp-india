import gzip
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import family  # noqa: E402
import portal  # noqa: E402
from crawl import slug  # noqa: E402

PAGES = Path(__file__).parent / "pages"


def page(name):
    return gzip.decompress((PAGES / f"{name}.html.gz").read_bytes()).decode()


def test_pppac_list():
    rows = portal.rows(page("pppac_projects_list"), "pppac_projects_list")
    assert len(rows) == 425 and len({r for r, _ in rows}) == 425
    f = rows[1][1]["fields"]
    assert f["Meeting Number"] == "153rd PPPAC" and f["Total Project Cost (In Rs. Crore)"] == "104,179.34"
    assert rows[1][1]["docs"][0].startswith("https://www.pppinindia.gov.in/docs/document/pppac/Record%20of%20Discussion")


def test_row_id_ignores_serial_number():
    html = page("vgf_final_project_list")
    a = dict(portal.rows(html, "v"))
    b = dict(portal.rows(html.replace('<th scope="row">1</th>', '<th scope="row">99</th>', 1), "v"))
    assert a.keys() == b.keys()


def test_vgf_final():
    rows = portal.rows(page("vgf_final_project_list"), "vgf_final_project_list")
    f = rows[0][1]["fields"]
    assert len(rows) == 72 and f["VGF Released till date by DEA for CAPEX (In Rs. Crore)"] == "0.00"
    assert f["Implementing Authority"] == "Indian Institute of Management, Udaipur"


def test_signed_agreements_and_counts():
    html = page("signed_concession_agreements")
    rows = portal.rows(html, "s")
    assert len(rows) == 220 and rows[0][1]["fields"]["Concessionaire"] == "Pune It City Metro Rail Limited"
    assert portal.report_counts(page("goverment_infrastructure_projects_ppp"))["No. of Projects in this Report"] == "1824"
    assert len(portal.doc_links(html, "s")) == 92


def test_pipeline_ids_and_empty_page():
    rows = portal.rows(page("pipeline_gujarat"), "p")
    assert rows[0][1]["pipeline_id"] == 985 and rows[0][1]["fields"]["PPP Model"] == "HAM"
    assert portal.rows(page("sfc_projects"), "sfc") == []


def test_queue():
    items = family.portal_items()
    keys = [i["key"] for i in items]
    assert len(keys) == len(set(keys)) and all(len(k) <= 200 for k in keys)
    assert slug("ppp-projects-pipeline-states-yearwise?state=jammu%20and%20kashmir") == "ppp-projects-pipeline-states-yearwise-state-jammu-and-kashmir"


def test_old_project_pages():
    ppp = {(s, l): v for s, l, v in portal.old_project(page("old_project_ppp"))}
    assert ppp[("Project Concessionaire", "Name Of Concessionaire")] == "PNC Infratech Limited"
    assert ppp[("Project Authority", "Name Of Authority")] == "National Highways Authority of India (NHAI)"
    assert ppp[("Project Cost", "Project Cost (Revised) in Rs Crore")] == "3,691.00"
    trad = {(s, l): v for s, l, v in portal.old_project(page("old_project_trad"))}
    assert trad[("Project Cost", "Project Cost (as per Contract) in Rs Crore")] == "679.00"
    assert portal.old_project("<html>Temporarily Offline</html>") == []


def test_old_index_and_shards():
    from crawl import old_index
    from htmltables import shard_of
    idx = old_index()
    assert len(idx) == 1863 and sum(1 for k in idx if shard_of(k, family.OLD_SHARDS) == 0) > 20
