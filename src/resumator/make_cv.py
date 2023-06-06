"""
TODO see http://eosrei.net/articles/2015/11/latex-templates-python-and-jinja2-generate-pdfs
TODO conferences
TODO professional affiliations
"""

import json
import re
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from operator import itemgetter
from typing import Optional, Sequence, Literal

import click
import pystow
import requests
import yaml
from jinja2 import Environment, FileSystemLoader, Template
from pydantic import BaseModel, Field

MODULE = pystow.module("resumator")

HERE = Path(__file__).parent.resolve()
TEMPLATES_DIRECTORY = HERE.joinpath("templates")
assert TEMPLATES_DIRECTORY.is_dir()
ROOT = HERE.parent.parent.resolve()
DATA = ROOT.joinpath("_data")

environment = Environment(
    autoescape=False,
    loader=FileSystemLoader(TEMPLATES_DIRECTORY),
    trim_blocks=True,
    lstrip_blocks=True,
    variable_start_string="@@@",
    variable_end_string="@@@",
)
CV_TEMPLATE = environment.get_template("cv.tex.jinja2")
output = ROOT.joinpath("cv.tex")

#: Wikidata SPARQL endpoint. See https://www.wikidata.org/wiki/Wikidata:SPARQL_query_service#Interfacing
WIKIDATA_ENDPOINT = "https://query.wikidata.org/bigdata/namespace/wdq/sparql"
WIKIBASE_LINE = """SERVICE wikibase:label { bd:serviceParam wikibase:language "[AUTO_LANGUAGE],en". }"""

CHARLIE = "Q47475003"
CEURWS_RE = re.compile(r"^https?://ceur-ws\.org/Vol-(\d+)/paper-?(\d+)")
QID_RE = re.compile(r"^Q\d+$")
PREPRINT_NAMES = {"chemrxiv", "arxiv", "biorxiv", "medxriv"}


class Date(BaseModel):
    month: str
    year: int
    day: Optional[str] = None


class Organization(BaseModel):
    name: str
    url: str
    ror: Optional[str] = None
    wikidata: Optional[str] = None


class Location(BaseModel):
    city: str
    country: str
    organization: Organization
    institute: Optional[Organization] = None
    group: Optional[Organization] = None


class Role(BaseModel):
    name: str
    start: Date
    end: Date
    location: Location


class Mentee(BaseModel):
    name: str
    github: str
    orcid: Optional[str] = None
    linkedin: Optional[str] = None
    googlescholar: Optional[str] = None
    description: Optional[str] = None
    roles: list[Role] = Field(default_factory=list)


class Period(BaseModel):
    semester: str
    year: str


class CourseLocation(BaseModel):
    university: str
    department: str


class Course(BaseModel):
    name: str
    level: Literal["Bachelor's Degree", "Master's course"]
    type: Literal["Practical", "Seminar", "Lecture"]
    date: Optional[Date] = None
    start: Optional[Date] = None
    end: Optional[Date] = None
    period: Period
    location: CourseLocation
    description: Optional[str] = None
    role: Literal["Guest Lecturer", "Instructor", "Teaching Assistant"]
    code: Optional[str] = None


def render_query(template: str, qid: str, *, refresh: bool):
    path = MODULE.join(qid, name=f"{template}.json")
    if path.is_file() and not refresh:
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
    return environment.get_template(name)


def get_attributes(qid: str, *, refresh: bool) -> dict[str, str]:
    """Get attributes."""
    res = render_query("attrs", qid=qid, refresh=refresh)[0]
    res["nationality"] = res["nationalityLabel"]
    res["name"] = res["personLabel"]
    return res


def get_topics(qid: str, *, refresh: bool) -> dict[str, str]:
    """Get topics of research."""
    q = render_query("topics", qid=qid, refresh=refresh)
    return _undict(q, "topic", "topicLabel")


def get_languages(qid: str, *, refresh: bool) -> dict[str, str]:
    """Get languages spoken/written."""
    q = render_query("languages", qid=qid, refresh=refresh)
    return _undict(q, "language", "languageLabel")


def get_employers(qid: str, *, refresh: bool):
    records = render_query("employers", qid=qid, refresh=refresh)
    for record in records:
        _add_period(record)
    return records


def get_education(qid: str, *, refresh: bool):
    records = render_query("education", qid=qid, refresh=refresh)
    for record in records:
        _add_period(record)
    return records


def _add_period(record):
    start_year = record.get("start_date", "").split("-")[0]
    end_year = record.get("end_date", "").split("-")[0]
    if start_year and end_year:
        if start_year == end_year:
            text = start_year
        else:
            text = f"{start_year}-{end_year[2:]}"
    elif start_year and not end_year:
        text = f"{start_year}-"
    else:
        print("Missing start and end dates")
        return
    record["period"] = text


def get_software(qid: str, *, refresh: bool):
    """Get software."""
    return render_query("software", qid=qid, refresh=refresh)


def get_databases(qid: str, *, refresh: bool):
    """Get databases."""
    return render_query("databases", qid=qid, refresh=refresh)


def get_databases_contributions(qid: str, *, refresh: bool):
    """Get contributions to databases."""
    return render_query("database_contributions", qid=qid, refresh=refresh)


def get_reviews(qid: str, *, refresh: bool):
    """Get reviews."""
    r = render_query("reviews", qid=qid, refresh=refresh)
    return _process_papers(r)


def get_acknowledgements(qid: str, *, refresh: bool):
    """Get acknowledgements."""
    r = render_query("acknowledgements", qid=qid, refresh=refresh)
    return _process_papers(r)


def get_papers(qid: str, *, refresh: bool):
    """Get papers."""
    r = render_query("works", qid=qid, refresh=refresh)
    return _process_papers(r)


def get_events(qid: str, *, refresh: bool):
    """Get papers."""
    r = render_query("events", qid=qid, refresh=refresh)
    return r


def _undict(records: list[dict[str, str]], k: str, v: str) -> dict[str, str]:
    """Unpack a list of dictionaries each containing an entry for a key and value."""
    return {record[k]: record[v] for record in records}


def _process_papers(
    papers,
    remove_corrigenda: bool = True,
    remove_figshare: bool = True,
    remove_missing_venue: bool = True,
):
    if remove_missing_venue:
        papers = [p for p in papers if p.get("venue")]
    if remove_corrigenda:
        papers = [
            paper
            for paper in papers
            if not any(
                paper["workLabel"].lower().startswith(p)
                for p in [
                    "corrigendum",
                    "erratum",
                    "publisher correction",
                    "correction",
                ]
            )
        ]
    if remove_figshare:
        papers = [
            paper
            for paper in papers
            if "figshare." not in paper.get("doi", "").lower() and "figshare.com" not in paper.get("url", "").lower()
        ]
    for paper in papers:
        _clean_pmc(paper)
        _clean_ceurs(paper)
    papers = _deduplicate(papers)
    return sorted(papers, key=itemgetter("date"), reverse=True)


def _clean_pmc(paper: dict[str, any]) -> None:
    pmc = paper.get("pmc", "").strip()
    if pmc:
        pmc = pmc.lower().removeprefix("pmc")
        paper["pmc"] = f"PMC{pmc}"


def _clean_ceurs(paper: dict[str, any]) -> None:
    url = paper.get("url", "").strip()
    if url:
        match = CEURWS_RE.match(url)
        if match:
            volume, n = match.groups()
            paper["ceurws"] = f"{volume}:{n}"


def _deduplicate(papers: Sequence[dict[str, any]]) -> Sequence[dict[str, any]]:
    title_to_papers = defaultdict(list)
    for paper in papers:
        title = paper["workLabel"].rstrip().rstrip(":").rstrip(".").lower().replace("-", "").replace(" ", "").replace(",", "")
        title_to_papers[title].append(paper)
    return [_get_best(group) for group in title_to_papers.values()]


def _get_best(papers: Sequence[dict[str, any]]) -> dict[str, any]:
    if len(papers) == 0:
        raise ValueError("missing papers")
    if len(papers) == 1:
        return papers[0]
    if len(papers) > 2:
        # TODO deal with multiple URLs
        return papers[0]

    if "biorxiv" in papers[0] and papers[0].get("doi", "").endswith(
        papers[0]["biorxiv"]
    ):
        return papers[1]
    elif "biorxiv" in papers[1] and papers[1].get("doi", "").endswith(
        papers[1]["biorxiv"]
    ):
        return papers[0]

    if "pubmed" in papers[0] or "pmc" in papers[0]:
        return papers[0]
    if "pubmed" in papers[1] or "pmc" in papers[1]:
        return papers[1]

    if "arxiv" in papers[0] and "doi" in papers[1]:
        return papers[1]
    elif "arxiv" in papers[1] and "doi" in papers[0]:
        return papers[0]

    if papers[0].get("venueLabel", "").lower() in PREPRINT_NAMES:
        return papers[1]
    if papers[1].get("venueLabel", "").lower() in PREPRINT_NAMES:
        return papers[0]

    return max(papers, key=lambda paper: paper.get("date", ""))


def query_wikidata(sparql: str) -> list[dict[str, any]]:
    """Query Wikidata's sparql service."""
    results = query_wikidata_raw(sparql)
    rows = []
    for bindings in results:
        for key in bindings:
            bindings[key]["value"] = bindings[key]["value"].removeprefix(
                "http://www.wikidata.org/entity/"
            )
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


@click.command()
@click.option("--qid", default=CHARLIE)
@click.option("--refresh", is_flag=True)
def main(qid: str, refresh: bool):
    if not QID_RE.fullmatch(qid):
        raise ValueError(f"Invalid wikidata identifier: {qid}")
    data = get_attributes(qid, refresh=refresh)
    topics = get_topics(qid, refresh=refresh)
    software = get_software(qid, refresh=refresh)
    databases = get_databases(qid, refresh=refresh)
    databases_contributions = get_databases_contributions(qid, refresh=refresh)
    languages = get_languages(qid, refresh=refresh)
    reviews = get_reviews(qid, refresh=refresh)
    acknowledgements = get_acknowledgements(qid, refresh=refresh)
    employers = get_employers(qid, refresh=refresh)
    degrees = get_education(qid, refresh=refresh)

    papers_dd = defaultdict(list)
    papers = get_papers(qid, refresh=refresh)
    for paper in papers:
        papers_dd[paper.get("date", "").split("-")[0]].append(paper)

    ctdata = Path.home().joinpath("dev", "cthoyt.github.io", "_data")
    mentees_path = ctdata.joinpath("mentees.yml")
    courses_path = ctdata.joinpath("courses.yml")

    mentees = []
    for mentee in yaml.safe_load(mentees_path.read_text()):
        try:
            m = Mentee.parse_obj(mentee)
        except ValueError as e:
            print(mentee["name"])
            print(e)
        else:
            mentees.append(m)

    courses = []
    for course in yaml.safe_load(courses_path.read_text()):
        try:
            c = Course.parse_obj(course)
        except ValueError as e:
            print(course["name"])
            print(e)
        else:
            courses.append(c)

    events = get_events(qid, refresh=refresh)

    presentations = yaml.safe_load(open("/Users/cthoyt/dev/cthoyt.github.io/_data/presentations.yml"))
    conference_committees = yaml.safe_load(open("/Users/cthoyt/dev/cthoyt.github.io/_data/service.yml"))
    reviewers = yaml.safe_load(open("/Users/cthoyt/dev/cthoyt.github.io/_data/reviewer.yml"))
    organizations = yaml.safe_load(open("/Users/cthoyt/dev/cthoyt.github.io/_data/organizations.yml"))
    fundings = yaml.safe_load(open("/Users/cthoyt/dev/cthoyt.github.io/_data/funding.yml"))

    tex = CV_TEMPLATE.render(
        qid=qid,
        topics=topics,
        software=software,
        presentations=presentations,
        databases=databases,
        databases_contributions=databases_contributions,
        conference_committees=conference_committees,
        reviewers=reviewers,
        fundings=fundings,
        organizations=organizations,
        # languages=languages,
        # reviews=reviews,
        # acknowledgements=acknowledgements,
        papers_dd=papers_dd,
        employers=employers,
        degrees=degrees,
        mentees=mentees,
        courses=courses,
        events=events,
        **data,
    )
    output.write_text(tex)


if __name__ == "__main__":
    main()
