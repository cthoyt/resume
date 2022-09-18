from collections import defaultdict
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, Template
import requests
from functools import lru_cache
import pystow
import json

MODULE = pystow.module("resumator")

HERE = Path(__file__).parent.resolve()
ROOT = HERE.parent.resolve()
DATA = ROOT.joinpath("_data")

environment = Environment(
    autoescape=True,
    loader=FileSystemLoader(HERE),
    trim_blocks=True,
    lstrip_blocks=True,
    variable_start_string="@@@",
    variable_end_string="@@@",
)
CV_TEMPLATE = environment.get_template("cv.tex.jinja2")
output = HERE.joinpath("cv.tex")

#: Wikidata SPARQL endpoint. See https://www.wikidata.org/wiki/Wikidata:SPARQL_query_service#Interfacing
WIKIDATA_ENDPOINT = "https://query.wikidata.org/bigdata/namespace/wdq/sparql"
WIKIBASE_LINE = """SERVICE wikibase:label { bd:serviceParam wikibase:language "[AUTO_LANGUAGE],en". }"""

CHARLIE = "Q47475003"


def render_query(template: str, qid: str):
    path = MODULE.join(qid, name=f"{template}.txt")
    if path.is_file():
        return json.loads(path.read_text())

    sparql = render(f"{template}.rq", qid=qid)
    print("querying with SPARQL:\n", sparql)
    rv = query_wikidata(sparql)
    path.write_text(json.dumps(rv, indent=2, sort_keys=True))
    print("writing to", path)
    return rv


def render(template: str, *args, qid: str, **kwargs) -> str:
    return _get_template(template).render(*args, qid=qid, **kwargs)


@lru_cache(None)
def _get_template(name: str) -> Template:
    return environment.get_template(f"templates/{name}")


def get_attributes(qid: str) -> dict[str, str]:
    """Get attributes."""
    res = render_query("attrs", qid=qid)[0]
    res["nationality"] = res["nationalityLabel"]
    res["name"] = res["personLabel"]
    return res


def get_topics(qid: str) -> dict[str, str]:
    """Get topics of research."""
    q = render_query("topics", qid=qid)
    return _undict(q, "topic", "topicLabel")


def get_languages(qid: str) -> dict[str, str]:
    """Get languages spoken/written."""
    q = render_query("languages", qid=qid)
    return _undict(q, "language", "languageLabel")


def get_software(qid: str):
    """Get software."""
    return render_query("software", qid=qid)


def get_reviews(qid: str):
    """Get reviews."""
    r = render_query("reviews", qid=qid)
    return _sort_papers(r)


def get_acknowledgements(qid: str):
    """Get acknowledgements."""
    r = render_query("acknowledgements", qid=qid)
    return _sort_papers(r)


def get_papers(qid: str):
    """Get papers."""
    r = render_query("works", qid=qid)
    return _sort_papers(r)


def _undict(rows: list[dict[str, str]], k: str, v: str) -> dict[str, str]:
    return {
        row[k]: row[v]
        for row in rows
    }


def _sort_papers(
    papers, remove_updates: bool = True, remove_figshare: bool = True,
    remove_missing_venue: bool = True,
):
    if remove_missing_venue:
        papers = [
            p
            for p in papers
            if p.get('venue')
        ]
    if remove_updates:
        papers = [
            paper
            for paper in papers
            if not any(
                paper["workLabel"].lower().startswith(p)
                for p in ["corrigendum", "erratum", "publisher correction", "correction"]
            )
        ]
    if remove_figshare:
        papers = [
            paper
            for paper in papers
            if "figshare." not in paper.get("doi", "").lower()
        ]
    papers = _deduplicate(papers)
    return sorted(papers, key=lambda s: s["date"], reverse=True)


def _deduplicate(papers):
    dd = defaultdict(list)
    for paper in papers:
        title = paper.get("workLabel", "").rstrip().rstrip(":").rstrip(".").lower()
        dd[title].append(paper)
    return [
        _get_best(p)
        for p in dd.values()
    ]


def _get_best(papers):
    if len(papers) == 0:
        raise ValueError("missing papers")
    if len(papers) == 1:
        return papers[0]
    if len(papers) > 2:
        raise ValueError("too many papers?")

    if "pubmed" in papers[0] or "pmc" in papers[0]:
        return papers[0]
    if "pubmed" in papers[1] or "pmc" in papers[1]:
        return papers[1]

    first_venue = papers[0].get("venueLabel")
    if "biorxiv" in first_venue or "arxiv" in first_venue:
        return papers[0]
    return papers[1]


def query_wikidata(sparql: str) -> list[dict[str, any]]:
    """Query Wikidata's sparql service."""
    results = query_wikidata_raw(sparql)
    rows = []
    for bindings in results:
        for key in bindings:
            bindings[key]["value"] = bindings[key]["value"].removeprefix("http://www.wikidata.org/entity/")
        rows.append({key: value["value"] for key, value in bindings.items()})
    return rows


def query_wikidata_raw(sparql: str) -> list[dict[str, any]]:
    """Query Wikidata's sparql service.

    :param sparql: A SPARQL query string
    :return: A list of bindings
    """
    res = requests.get(WIKIDATA_ENDPOINT, params={"query": sparql, "format": "json"})
    res.raise_for_status()
    res_json = res.json()
    return res_json["results"]["bindings"]


def main(qid: str = CHARLIE):
    data = get_attributes(qid)
    topics = get_topics(qid)
    software = get_software(qid)
    languages = get_languages(qid)
    reviews = get_reviews(qid)
    acknowledgements = get_acknowledgements(qid)

    papers_dd = defaultdict(list)
    papers = get_papers(qid)
    for paper in papers:
        papers_dd[paper.get("date", "").split("-")[0]].append(paper)

    tex = CV_TEMPLATE.render(
        qid=qid,
        topics=topics,
        software=software,
        languages=languages,
        reviews=reviews,
        acknowledgements=acknowledgements,
        papers_dd=papers_dd,
        **data,
    )
    output.write_text(tex)


if __name__ == '__main__':
    main()
