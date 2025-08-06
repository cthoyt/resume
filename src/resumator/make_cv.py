"""
TODO see http://eosrei.net/articles/2015/11/latex-templates-python-and-jinja2-generate-pdfs
TODO conferences
TODO professional affiliations
"""

import datetime
import json
import re
from collections import defaultdict
from functools import lru_cache
from operator import itemgetter
from pathlib import Path
from typing import Literal, Optional, Sequence, Counter

import wikidata_client
import click
import pystow
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
PUBS_TEMPLATE = environment.get_template("cv_pubs.tex.jinja2")
FUNDINGS_TEMPLATE = environment.get_template("cv_fundings.tex.jinja2")
CV_OUTPUT_PATH = ROOT.joinpath("cv.tex")
PUBS_OUTPUT_PATH = ROOT.joinpath("publications.tex")
FUNDING_OUTPUT_PATH = ROOT.joinpath("funding.tex")

#: Wikidata SPARQL endpoint. See https://www.wikidata.org/wiki/Wikidata:SPARQL_query_service#Interfacing
WIKIDATA_ENDPOINT = "https://query.wikidata.org/bigdata/namespace/wdq/sparql"
WIKIBASE_LINE = """SERVICE wikibase:label { bd:serviceParam wikibase:language "[AUTO_LANGUAGE],en". }"""

CHARLIE = "Q47475003"
CEURWS_RE = re.compile(r"^https?://ceur-ws\.org/Vol-(\d+)/paper-?(\d+)")
QID_RE = re.compile(r"^Q\d+$")
PREPRINT_NAMES = {"chemrxiv", "arxiv", "biorxiv", "medxriv"}
SKIP_PAPERS = {
    "Q125455971": "this is a duplicate of Q72584451",
}


class Date(BaseModel):
    month: str
    year: int
    day: Optional[int] = None


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
    year: str | int


class CourseLocation(BaseModel):
    university: str
    department: str


class Course(BaseModel):
    name: str
    level: Literal["Bachelor's Degree", "Master's course", "N/A"]
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
    rv = wikidata_client.query(sparql, endpoint=WIKIDATA_LEGACY_ENDPOINT)
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

    mastodon: str | None = res.pop("mastodon", None)
    if mastodon is not None:
        user, _, host = mastodon.partition("@")
        res["mastodon"] = {"user": user, "host": host}
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
            if "figshare." not in paper.get("doi", "").lower()
            and "figshare.com" not in paper.get("url", "").lower()
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
        title = (
            paper["workLabel"]
            .rstrip()
            .rstrip(":")
            .rstrip(".")
            .lower()
            .replace("-", "")
            .replace(" ", "")
            .replace(",", "")
            .replace("z", "s")
        )
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


@click.command()
@click.option("--qid", default=CHARLIE)
@click.option("--refresh", is_flag=True)
def main(qid: str, refresh: bool):
    if not QID_RE.fullmatch(qid):
        raise ValueError(f"Invalid wikidata identifier: {qid}")

    ctdata = Path.home().joinpath("dev", "cthoyt.github.io", "_data")

    data = get_attributes(qid, refresh=refresh)
    topics = get_topics(qid, refresh=refresh)
    databases_contributions = get_databases_contributions(qid, refresh=refresh)
    languages = get_languages(qid, refresh=refresh)
    reviews = get_reviews(qid, refresh=refresh)
    acknowledgements = get_acknowledgements(qid, refresh=refresh)
    employers = get_employers(qid, refresh=refresh)
    remotes = {"Q49121", "Q94505592"}
    for e in employers:
        if e["employer"] in remotes:
            e["remote"] = True

    degrees = get_education(qid, refresh=refresh)

    papers_dd = defaultdict(list)
    papers = get_papers(qid, refresh=refresh)
    firsts = {
        "Q120200936",
        "Q118774152",
        "Q115317009",
        "Q111337218",
        "Q109583780",
        "Q96909013",
        "Q63709723",
        "Q96909013",
        "Q61473695",
        "Q64911025",
        "Q60302045",
        "Q55315340",
        "Q42695788",
        "Q63709723",
        "Q123462831",  # o3 preprint
        "Q126325456",  # o3 peer reviewed
        "Q130365052",  # PNNL vaccinology review preprint
        "Q134057794",  # PNNL vaccinology review post-print
        "Q134057813", # SeMRA preprint
    }
    seniors_or_last = {
        "Q118774035",
        "Q126325520",  # ptwt
    }
    for paper in papers:
        if paper["work"] == "Q107296731":
            continue  # look for my future blog post on what I consider borderline misconduct from Jochen Garke on this
        if paper["work"] in SKIP_PAPERS:
            continue
        if paper["work"] in firsts or paper.get("first"):
            paper["first"] = True
        if paper["work"] in seniors_or_last or paper.get("last"):
            paper["senior"] = True
        papers_dd[paper.get("date", "").split("-")[0]].append(paper)

    in_preparation_path = ctdata.joinpath("in_preparation.yml")
    in_preparation_papers = yaml.safe_load(in_preparation_path.read_text())
    today_year = str(datetime.date.today().year)
    for in_preparation_paper in in_preparation_papers:
        in_preparation_paper["date"] = today_year
        in_preparation_paper["workLabel"] = in_preparation_paper["name"]
        in_prep_venue = in_preparation_paper.get("venue")
        if in_prep_venue:
            in_preparation_paper["venueLabel"] = f"in preparation for {in_prep_venue}"
        else:
            in_preparation_paper["venueLabel"] = "in preparation"
        papers_dd[today_year].append(in_preparation_paper)

    mentees_path = ctdata.joinpath("mentees.yml")
    courses_path = ctdata.joinpath("courses.yml")
    software_path = ctdata.joinpath("software.yml")

    mentees = defaultdict(list)
    for mentee in yaml.safe_load(mentees_path.read_text()):
        try:
            m = Mentee.model_validate(mentee)
        except ValueError as e:
            print(mentee["name"])
            print(e)
        else:
            for role in m.roles:
                mentees[role.location.organization.name].append(m)

    courses = defaultdict(list)
    course_stats = Counter()
    for course in yaml.safe_load(courses_path.read_text()):
        try:
            c = Course.model_validate(course)
        except ValueError as e:
            print(course["name"])
            print(e)
        else:
            courses[c.location.university].append(c)
            course_stats[c.type.lower()] += 1

    events = get_events(qid, refresh=refresh)

    service = yaml.safe_load(
        open("/Users/cthoyt/dev/cthoyt.github.io/_data/service.yml")
    )
    reviewers = yaml.safe_load(
        open("/Users/cthoyt/dev/cthoyt.github.io/_data/reviewer.yml")
    )
    organizations = yaml.safe_load(
        open("/Users/cthoyt/dev/cthoyt.github.io/_data/organizations.yml")
    )
    fundings = yaml.safe_load(
        open("/Users/cthoyt/dev/cthoyt.github.io/_data/funding.yml")
    )
    databases = yaml.safe_load(ctdata.joinpath("databases.yml").read_text())

    software = yaml.safe_load(software_path.read_text())
    # for record in software:
    #     core = any(
    #         role in {"creator", "advisor"}
    #         for role in record["roles"]
    #     )

    invited = []
    submitted = []
    for event in yaml.safe_load(ctdata.joinpath("events.yml").read_text()):
        for key, flag in [("talk", False), ("poster", True)]:
            if (talk := event.get(key)) is not None:
                record = {
                    **talk,
                    "venue": event["name"],
                    "poster": flag,
                }
                if "date" not in talk:
                    if "date" in event:
                        record["date"] = event["date"]
                    else:
                        record["date"] = event["end"]  # just assume last day
                if talk.get("invited"):
                    invited.append(record)
                else:
                    submitted.append(record)

    peer_review_count = 0
    preprint_count = 0
    in_progress_count = 0
    for year, papers in papers_dd.items():
        for paper in papers:
            venue = paper.get("venueLabel")
            if venue is None:  # in preparation
                in_progress_count += 1
            elif venue.lower() in {"arxiv", "medrxiv", "chemrxiv", "biorxiv", "osf preprints"}:
                preprint_count += 1
            elif venue.startswith("in preparation"):
                in_progress_count += 1
            else:
                peer_review_count += 1

    paper_stats = {
        "peer_reviewed": peer_review_count,
        "preprints": preprint_count,
        "in_progress": in_progress_count,
    }

    tex = CV_TEMPLATE.render(
        qid=qid,
        topics=topics,
        software=software,
        invited=invited,
        submitted=submitted,
        databases=databases,
        databases_contributions=databases_contributions,
        conference_committees=[s for s in service if s["type"] == "conference"],
        other_service=[s for s in service if s["type"] != "conference"],
        reviewers=reviewers,
        fundings=fundings,
        organizations=organizations,
        # languages=languages,
        # reviews=reviews,
        # acknowledgements=acknowledgements,
        papers_dd=papers_dd,
        papers_stats=paper_stats,
        employers=employers,
        degrees=degrees,
        mentees=mentees,
        courses=courses,
        course_stats=course_stats,
        events=events,
        **data,
    )
    CV_OUTPUT_PATH.write_text(tex)

    pub_tex = PUBS_TEMPLATE.render(
        qid=qid,
        invited=invited,
        submitted=submitted,
        papers_dd=papers_dd,
        papers_stats=paper_stats,
        **data,
    )
    PUBS_OUTPUT_PATH.write_text(pub_tex)

    funding_tex = FUNDINGS_TEMPLATE.render(
        qid=qid,
        fundings=fundings,
        **data,
    )
    FUNDING_OUTPUT_PATH.write_text(funding_tex)


if __name__ == "__main__":
    main()
