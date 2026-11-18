#!/usr/bin/env python3
"""
Fetch the most-cited HIV/AIDS papers from the OpenAlex Works API.

Filter
------
Works whose OpenAlex *concepts* or *topics* include HIV or AIDS, published
2005–2026, sorted by cited_by_count descending.

OpenAlex cannot OR two different filter attributes in one request, so this
script runs two queries (concepts, topics) and unions them. That is the
correct interpretation of "topic or concepts include HIV or AIDS".

Usage
-----
    python3 openalex_hiv_aids.py
    python3 openalex_hiv_aids.py --n 200 --out-csv data/hiv_aids_top200.csv

Set OPENALEX_MAILTO (or --mailto) to join the polite pool. An OpenAlex API
key is optional: pass --api-key or set OPENALEX_API_KEY if you have one.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

API_BASE = "https://api.openalex.org/works"
MAX_PER_PAGE = 200  # OpenAlex hard cap

# Join the polite pool by default so requests are attributed and rate-limited
# more generously than anonymous traffic. Override with OPENALEX_MAILTO.
DEFAULT_MAILTO = os.environ.get("OPENALEX_MAILTO", "pawbard2008@gmail.com")

# Human immunodeficiency virus (HIV) plus AIDS-named concepts that may not
# always carry the parent HIV tag. Child HIV concepts are usually redundant
# with C3013748606 but AIDS-named ones are included explicitly.
HIV_AIDS_CONCEPT_IDS = (
    "C3013748606",  # Human immunodeficiency virus (HIV)
    "C2780195530",  # HIV vaccine
    "C2777583353",  # HIV-1 protease
    "C2910359755",  # HIV Antigens
    "C2778451633",  # HIV drug resistance
    "C2910020833",  # HIV Long Terminal Repeat
    "C2992699665",  # Hiv test
    "C2910823671",  # HIV diagnosis
    "C2908958731",  # HIV screening
    "C2909828532",  # AIDS Vaccines
    "C2909201284",  # AIDS-Related Opportunistic Infections
    "C2779898580",  # Multicenter AIDS Cohort Study
    "C2779127605",  # AIDS-related complex
)

# Topics whose display name is about HIV or AIDS. "AIDS" string matches that
# are decision/hearing/navigation aids are intentionally excluded.
HIV_AIDS_TOPIC_IDS = (
    "T10112",  # HIV Research and Treatment
    "T10082",  # HIV/AIDS Research and Interventions
    "T10526",  # HIV/AIDS drug development and treatment
    "T11860",  # HIV, Drug Use, Sexual Risk
    "T11655",  # HIV-related health complications and treatments
    "T14334",  # HIV/AIDS Impact and Responses
    "T13761",  # HIV/AIDS oral health manifestations
    "T13586",  # HIV, TB, and STIs Epidemiology
)

YEAR_FROM = 2005
YEAR_TO = 2026
ABSTRACT_MAX_CHARS = 500

# Fields we actually write. Keeping `select` tight reduces payload size.
SELECT_FIELDS = ",".join(
    [
        "id",
        "doi",
        "title",
        "display_name",
        "publication_year",
        "cited_by_count",
        "authorships",
        "open_access",
        "ids",
        "abstract_inverted_index",
        "best_oa_location",
        "primary_location",
        "concepts",
        "topics",
        "primary_topic",
    ]
)

CSV_COLUMNS = [
    "title",
    "publication_year",
    "cited_by_count",
    "doi",
    "openalex_id",
    "primary_authors",
    "is_oa",
    "oa_url",
    "pmcid",
    "abstract",
]


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------


class OpenAlexError(RuntimeError):
    """Raised when OpenAlex returns an error body or we exhaust retries."""


@dataclass
class RateLimitNotes:
    """Lightweight log of throttling / coverage signals seen during a run."""

    retries: int = 0
    status_429: int = 0
    budget_notice: str = ""
    requests: int = 0


class OpenAlexClient:
    """Minimal OpenAlex Works client: polite User-Agent, cursor paging, backoff."""

    def __init__(
        self,
        mailto: str = DEFAULT_MAILTO,
        api_key: str | None = None,
        timeout: float = 60.0,
        min_interval: float = 0.12,
        max_retries: int = 5,
    ) -> None:
        self.mailto = mailto
        self.api_key = api_key or os.environ.get("OPENALEX_API_KEY")
        self.timeout = timeout
        # Polite-pool guidance is ~10 req/s; stay well under that.
        self.min_interval = min_interval
        self.max_retries = max_retries
        self._last_request_at = 0.0
        self.notes = RateLimitNotes()
        self.user_agent = (
            f"hiv-aids-openalex-export/1.0 (mailto:{mailto}; "
            "https://openalex.org)"
        )

    def _throttle(self) -> None:
        wait = self.min_interval - (time.monotonic() - self._last_request_at)
        if wait > 0:
            time.sleep(wait)

    def get(self, params: dict[str, Any]) -> dict[str, Any]:
        """GET /works with retries on 429 / 5xx."""
        query = dict(params)
        query["mailto"] = self.mailto
        if self.api_key:
            query["api_key"] = self.api_key

        url = f"{API_BASE}?{urllib.parse.urlencode(query, safe=':|,')}"
        request = urllib.request.Request(url, headers={"User-Agent": self.user_agent})

        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            self._throttle()
            self._last_request_at = time.monotonic()
            self.notes.requests += 1
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                notice = (payload.get("meta") or {}).get("notice") or ""
                if notice and not self.notes.budget_notice:
                    self.notes.budget_notice = notice
                return payload
            except urllib.error.HTTPError as exc:
                last_error = exc
                body = exc.read().decode("utf-8", errors="replace")
                if exc.code == 429:
                    self.notes.status_429 += 1
                    self.notes.retries += 1
                    retry_after = exc.headers.get("Retry-After")
                    sleep_s = float(retry_after) if retry_after else 2 ** (attempt + 1)
                    time.sleep(sleep_s)
                    continue
                if exc.code >= 500:
                    self.notes.retries += 1
                    time.sleep(2 ** attempt)
                    continue
                raise OpenAlexError(f"OpenAlex HTTP {exc.code}: {body[:500]}") from exc
            except urllib.error.URLError as exc:
                last_error = exc
                self.notes.retries += 1
                time.sleep(2 ** attempt)
        raise OpenAlexError(f"OpenAlex request failed after retries: {last_error}")

    def count_and_sample(
        self, work_filter: str, sort: str = "cited_by_count:desc"
    ) -> tuple[int, dict[str, Any]]:
        """Return (meta.count, first-page payload) for a filter."""
        payload = self.get(
            {
                "filter": work_filter,
                "sort": sort,
                "per-page": 1,
                "select": "id",
            }
        )
        return int((payload.get("meta") or {}).get("count") or 0), payload

    def iterate_works(
        self,
        work_filter: str,
        sort: str = "cited_by_count:desc",
        limit: int = 400,
        per_page: int = MAX_PER_PAGE,
    ) -> Iterable[dict[str, Any]]:
        """
        Yield up to `limit` works.

        Uses ordinary `page=` pagination so a free/unkeyed client can pass
        the first few pages. Cursor paging currently requires an API key
        ("API key required for cursor paging"), which we only send when one
        is configured.
        """
        remaining = limit
        page = 1
        use_cursor = bool(self.api_key)
        cursor: str | None = "*"
        while remaining > 0:
            page_size = min(per_page, remaining, MAX_PER_PAGE)
            params: dict[str, Any] = {
                "filter": work_filter,
                "sort": sort,
                "per-page": page_size,
                "select": SELECT_FIELDS,
            }
            if use_cursor:
                params["cursor"] = cursor
            else:
                params["page"] = page
            payload = self.get(params)
            results = payload.get("results") or []
            if not results:
                break
            for work in results:
                yield work
                remaining -= 1
                if remaining <= 0:
                    return
            if use_cursor:
                cursor = (payload.get("meta") or {}).get("next_cursor")
                if not cursor:
                    return
            else:
                page += 1


# ---------------------------------------------------------------------------
# Record extraction
# ---------------------------------------------------------------------------


def reconstruct_abstract(inverted: dict[str, list[int]] | None) -> str:
    """Rebuild a space-joined abstract from OpenAlex's inverted index."""
    if not inverted:
        return ""
    ranked: list[tuple[int, str]] = []
    for word, positions in inverted.items():
        for pos in positions:
            ranked.append((pos, word))
    ranked.sort(key=lambda item: item[0])
    return " ".join(word for _, word in ranked)


def truncate(text: str, max_chars: int = ABSTRACT_MAX_CHARS) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def strip_title_markup(title: str) -> str:
    """OpenAlex titles sometimes contain italics tags; drop them for CSV/dedup."""
    return re.sub(r"</?i>", "", title or "").strip()


def normalize_title(title: str) -> str:
    cleaned = strip_title_markup(title).lower()
    cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def normalize_doi(doi: str | None) -> str:
    if not doi:
        return ""
    value = doi.strip().lower()
    value = re.sub(r"^https?://(dx\.)?doi\.org/", "", value)
    return value.strip()


def short_openalex_id(url_or_id: str | None) -> str:
    if not url_or_id:
        return ""
    return url_or_id.rstrip("/").split("/")[-1]


def extract_pmcid(work: dict[str, Any]) -> str:
    """Return a PMCxxxx identifier when OpenAlex has one."""
    ids = work.get("ids") or {}
    raw = ids.get("pmcid") or ""
    if not raw:
        return ""
    match = re.search(r"(PMC)?(\d+)", str(raw), re.IGNORECASE)
    if not match:
        return ""
    return f"PMC{match.group(2)}"


def primary_authors(work: dict[str, Any]) -> str:
    """First-position author names; fall back to the first authorship listed."""
    authorships = work.get("authorships") or []
    firsts = [
        (a.get("author") or {}).get("display_name")
        or a.get("raw_author_name")
        for a in authorships
        if a.get("author_position") == "first"
    ]
    names = [n for n in firsts if n]
    if not names and authorships:
        fallback = (authorships[0].get("author") or {}).get("display_name") or authorships[
            0
        ].get("raw_author_name")
        if fallback:
            names = [fallback]
    return "; ".join(names)


def best_fulltext_url(work: dict[str, Any]) -> str:
    """Prefer OpenAlex oa_url, then PDF, then landing page of the OA location."""
    oa = work.get("open_access") or {}
    if oa.get("oa_url"):
        return oa["oa_url"]
    for loc_key in ("best_oa_location", "primary_location"):
        loc = work.get(loc_key) or {}
        if loc.get("pdf_url"):
            return loc["pdf_url"]
        if loc.get("is_oa") and loc.get("landing_page_url"):
            return loc["landing_page_url"]
    return ""


def extract_record(work: dict[str, Any]) -> dict[str, Any]:
    title = strip_title_markup(work.get("display_name") or work.get("title") or "")
    doi = normalize_doi(work.get("doi") or (work.get("ids") or {}).get("doi"))
    oa = work.get("open_access") or {}
    abstract = truncate(reconstruct_abstract(work.get("abstract_inverted_index")))
    is_oa = bool(oa.get("is_oa"))
    return {
        "title": title,
        "publication_year": work.get("publication_year") or "",
        "cited_by_count": int(work.get("cited_by_count") or 0),
        "doi": doi,
        "openalex_id": short_openalex_id(work.get("id")),
        "primary_authors": primary_authors(work),
        "is_oa": is_oa,
        "oa_url": best_fulltext_url(work),
        "pmcid": extract_pmcid(work),
        "abstract": abstract,
        "has_abstract": bool(abstract),
    }


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


def _dedupe_key(record: dict[str, Any]) -> tuple[str, str]:
    doi = record.get("doi") or ""
    title = normalize_title(record.get("title") or "")
    return doi, title


def is_better(candidate: dict[str, Any], incumbent: dict[str, Any]) -> bool:
    """Prefer the higher citation count; break ties toward richer metadata."""
    cand_cites = candidate.get("cited_by_count") or 0
    inc_cites = incumbent.get("cited_by_count") or 0
    if cand_cites != inc_cites:
        return cand_cites > inc_cites
    cand_score = (
        int(bool(candidate.get("doi")))
        + int(bool(candidate.get("pmcid")))
        + int(bool(candidate.get("oa_url")))
        + int(bool(candidate.get("has_abstract")))
    )
    inc_score = (
        int(bool(incumbent.get("doi")))
        + int(bool(incumbent.get("pmcid")))
        + int(bool(incumbent.get("oa_url")))
        + int(bool(incumbent.get("has_abstract")))
    )
    return cand_score > inc_score


def deduplicate(records: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """
    Collapse records that share a DOI or a normalized title.

    DOI matches win even when titles differ (preprint vs VoR). Title matches
    catch works that never received a DOI. When a cluster collides, keep the
    higher cited_by_count version.
    """
    by_doi: dict[str, dict[str, Any]] = {}
    by_title: dict[str, dict[str, Any]] = {}
    dropped = 0

    def keep(record: dict[str, Any]) -> None:
        doi, title = _dedupe_key(record)
        if doi:
            by_doi[doi] = record
        if title:
            by_title[title] = record

    def drop_old(old: dict[str, Any]) -> None:
        old_doi, old_title = _dedupe_key(old)
        if old_doi and by_doi.get(old_doi) is old:
            by_doi.pop(old_doi, None)
        if old_title and by_title.get(old_title) is old:
            by_title.pop(old_title, None)

    for record in records:
        doi, title = _dedupe_key(record)
        incumbent = None
        if doi and doi in by_doi:
            incumbent = by_doi[doi]
        elif title and title in by_title:
            incumbent = by_title[title]

        if incumbent is None:
            keep(record)
            continue

        dropped += 1
        if is_better(record, incumbent):
            drop_old(incumbent)
            keep(record)

    # Unique by object identity — a record may sit in both maps.
    unique: dict[int, dict[str, Any]] = {}
    for record in list(by_doi.values()) + list(by_title.values()):
        unique[id(record)] = record
    ordered = sorted(
        unique.values(),
        key=lambda r: (-(r.get("cited_by_count") or 0), r.get("title") or ""),
    )
    return ordered, dropped


# ---------------------------------------------------------------------------
# Fetch + report
# ---------------------------------------------------------------------------


def concept_filter() -> str:
    ids = "|".join(HIV_AIDS_CONCEPT_IDS)
    return f"publication_year:{YEAR_FROM}-{YEAR_TO},concepts.id:{ids}"


def topic_filter() -> str:
    """Primary topic, not every secondary tag.

    OpenAlex also stores additional `topics`, but those are noisy on
    mega-cited guidelines (metabolic syndrome, generic TB reports, etc.).
    'The topic includes HIV or AIDS' is interpreted as primary_topic.
    """
    ids = "|".join(HIV_AIDS_TOPIC_IDS)
    return f"publication_year:{YEAR_FROM}-{YEAR_TO},primary_topic.id:{ids}"


def hiv_concept_score(work: dict[str, Any]) -> float:
    """Highest OpenAlex score among our HIV/AIDS concept IDs (0 if untagged)."""
    wanted = set(HIV_AIDS_CONCEPT_IDS)
    score = 0.0
    for concept in work.get("concepts") or []:
        if short_openalex_id(concept.get("id")) in wanted:
            score = max(score, float(concept.get("score") or 0))
    return score


def has_hiv_aids_primary_topic(work: dict[str, Any]) -> bool:
    primary = work.get("primary_topic") or {}
    return short_openalex_id(primary.get("id")) in set(HIV_AIDS_TOPIC_IDS)


def is_hiv_aids_work(work: dict[str, Any]) -> bool:
    """True when the work actually includes an HIV/AIDS topic or concept.

    `concepts.id` matches even when the HIV concept score is 0 (a leftover
    tag OpenAlex still indexes). Those are not treated as 'concepts include
    HIV or AIDS'.
    """
    return has_hiv_aids_primary_topic(work) or hiv_concept_score(work) > 0


@dataclass
class FetchResult:
    records: list[dict[str, Any]]
    concept_count: int
    topic_count: int
    fetched_raw: int
    dropped_weak_tags: int
    duplicates_dropped: int
    notes: RateLimitNotes
    pulled_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    )


def fetch_top(
    client: OpenAlexClient,
    n: int = 200,
    oversample: int = 400,
) -> FetchResult:
    """
    Pull `oversample` works from each query, union, dedupe, keep top `n`.

    Oversampling is required because (a) OpenAlex cannot OR concepts vs topics
    in one filter, and (b) preprint/VoR duplicates shrink the unique set.
    Any work in the true union top-n must appear in at least one of the two
    oversampled lists.
    """
    print("Counting concept-tagged HIV/AIDS works…", file=sys.stderr)
    concept_count, _ = client.count_and_sample(concept_filter())
    print(f"  concepts filter: {concept_count:,}", file=sys.stderr)

    print("Counting topic-tagged HIV/AIDS works…", file=sys.stderr)
    topic_count, _ = client.count_and_sample(topic_filter())
    print(f"  topics filter:   {topic_count:,}", file=sys.stderr)

    raw: list[dict[str, Any]] = []
    print(f"Fetching up to {oversample} concept-tagged works…", file=sys.stderr)
    raw.extend(client.iterate_works(concept_filter(), limit=oversample))
    print(f"Fetching up to {oversample} primary-topic-tagged works…", file=sys.stderr)
    raw.extend(client.iterate_works(topic_filter(), limit=oversample))

    kept_works = [work for work in raw if is_hiv_aids_work(work)]
    dropped_weak = len(raw) - len(kept_works)
    print(
        f"  kept {len(kept_works)} / {len(raw)} after dropping score-0 concept tags "
        f"without an HIV/AIDS primary topic",
        file=sys.stderr,
    )

    extracted = [extract_record(work) for work in kept_works]
    unique, dropped = deduplicate(extracted)
    if len(unique) < n:
        print(
            f"Warning: only {len(unique)} unique works after filters; "
            "raise --oversample if you need a full top-N.",
            file=sys.stderr,
        )
    top = unique[:n]
    return FetchResult(
        records=top,
        concept_count=concept_count,
        topic_count=topic_count,
        fetched_raw=len(raw),
        dropped_weak_tags=dropped_weak,
        duplicates_dropped=dropped,
        notes=client.notes,
    )


def write_csv(path: str, records: list[dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=CSV_COLUMNS,
            extrasaction="ignore",
            quoting=csv.QUOTE_MINIMAL,
        )
        writer.writeheader()
        for row in records:
            out = {key: row.get(key, "") for key in CSV_COLUMNS}
            out["is_oa"] = "true" if row.get("is_oa") else "false"
            writer.writerow(out)


def _pct(part: int, whole: int) -> str:
    if whole == 0:
        return "0%"
    return f"{part / whole:.1%}"


def write_summary(path: str, result: FetchResult, n: int) -> None:
    rows = result.records
    oa = sum(1 for r in rows if r.get("is_oa"))
    oa_url = sum(1 for r in rows if r.get("oa_url"))
    pmcid = sum(1 for r in rows if r.get("pmcid"))
    oa_or_pmc = sum(1 for r in rows if r.get("oa_url") or r.get("pmcid"))
    abstracts = sum(1 for r in rows if r.get("abstract"))
    years = [r["publication_year"] for r in rows if r.get("publication_year")]
    cites = [r["cited_by_count"] for r in rows]
    considered_floor = max(result.concept_count, result.topic_count)
    considered_ceil = result.concept_count + result.topic_count

    lines = [
        "# HIV/AIDS papers from OpenAlex — top 200 by citations",
        "",
        f"Pulled **{result.pulled_at}** from the [OpenAlex Works API](https://docs.openalex.org/).",
        "",
        "## Query",
        "",
        f"- Publication years: **{YEAR_FROM}–{YEAR_TO}**",
        f"- Sort: `cited_by_count:desc`",
        f"- Concepts (OR): `{', '.join(HIV_AIDS_CONCEPT_IDS)}`",
        f"- Topics (OR): `{', '.join(HIV_AIDS_TOPIC_IDS)}`",
            "- Combined with a union of two requests (OpenAlex cannot OR across attributes).",
            "- Topic side uses `primary_topic.id`. Concept side keeps a work only when an "
            "HIV/AIDS concept has score > 0 (the API's `concepts.id` filter otherwise "
            "returns leftover score-0 tags on unrelated high-cite papers).",
        "",
        "## Coverage of the ranking pool",
        "",
        f"- Works matching the **concept** filter: **{result.concept_count:,}**",
        f"- Works matching the **primary topic** filter: **{result.topic_count:,}**",
        f"- Papers considered before the top-{n} cut: **at least {considered_floor:,}** "
        f"and **at most {considered_ceil:,}** (union of the two API filters; exact unique "
        "count would require paging the full ~0.3–0.7M-work sets).",
        f"- Candidate records downloaded: **{result.fetched_raw:,}** "
        f"({result.dropped_weak_tags} dropped as score-0 HIV concept tags with no HIV/AIDS "
        f"primary topic; {result.duplicates_dropped} collapsed as DOI/title duplicates).",
        f"- Rows in the CSV: **{len(rows)}**",
        "",
        "## Among the 200",
        "",
        f"- Open access (`is_oa=true`): **{oa}** ({_pct(oa, len(rows))})",
        f"- With an OA / full-text URL: **{oa_url}** ({_pct(oa_url, len(rows))})",
        f"- With a PMCID: **{pmcid}** ({_pct(pmcid, len(rows))})",
        f"- Open full text **or** PMCID: **{oa_or_pmc}** ({_pct(oa_or_pmc, len(rows))})",
        f"- Truncated abstract present: **{abstracts}** ({_pct(abstracts, len(rows))})",
        f"- Publication years in the list: **{min(years) if years else '—'}–{max(years) if years else '—'}**",
        f"- Citation counts: **{min(cites) if cites else '—'}–{max(cites) if cites else '—'}** "
        f"(median {sorted(cites)[len(cites)//2] if cites else '—'})",
        "",
        "## Rate-limit and coverage notes",
        "",
        f"- HTTP requests this run: **{result.notes.requests}**; "
        f"429 responses: **{result.notes.status_429}**; retries: **{result.notes.retries}**.",
        "- The client uses the OpenAlex polite pool (`mailto` + identifying User-Agent) "
        "and waits ~120 ms between requests. Without an API key, OpenAlex currently "
        "shares a small free daily budget per IP; this export is a handful of cheap "
        "`/works` calls and stays well under that.",
    ]
    if result.notes.budget_notice:
        lines.append(f"- API notice: {result.notes.budget_notice}")
    lines.extend(
        [
            "- OpenAlex concepts and topics are classifier tags, not a MeSH explosion. "
            "Papers about HIV that were never tagged will be missing; papers tagged "
            "HIV/AIDS that are only tangentially related can appear.",
            "- Abstracts arrive as an inverted index and are reconstructed, then cut "
            f"to {ABSTRACT_MAX_CHARS} characters. Some works have no abstract in OpenAlex.",
            "- `oa_url` is the OpenAlex open-access URL when present, otherwise the "
            "best OA PDF / landing page. Links can rot; PMCID is the more stable "
            "full-text handle when it exists.",
            f"- {YEAR_TO} is the current/upcoming calendar year, so that slice is incomplete. "
            "Recent years (2023–2026) also rarely reach a top-200 citation cutoff; this export’s "
            "years stop at 2022.",
            "- Citation counts are OpenAlex `cited_by_count` (cross-publisher), not "
            "Web of Science or Scopus, and they move as the graph updates.",
            "",
            "## Top 10 (preview)",
            "",
            "| # | Year | Cites | OA | PMCID | Title |",
            "|---|------|------:|----|-------|-------|",
        ]
    )
    for i, row in enumerate(rows[:10], start=1):
        title = (row.get("title") or "").replace("|", "/")
        pmc = row.get("pmcid") or ""
        oa_flag = "yes" if row.get("is_oa") else "no"
        lines.append(
            f"| {i} | {row.get('publication_year')} | {row.get('cited_by_count')} | "
            f"{oa_flag} | {pmc} | {title} |"
        )
    lines.append("")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("Usage", 1)[0].strip())
    parser.add_argument("--n", type=int, default=200, help="Rows to keep after dedupe")
    parser.add_argument(
        "--oversample",
        type=int,
        default=600,
        help="Works to pull from each of the two filters before the union",
    )
    parser.add_argument("--out-csv", default="data/hiv_aids_top200.csv")
    parser.add_argument("--out-md", default="SUMMARY.md")
    parser.add_argument("--mailto", default=DEFAULT_MAILTO)
    parser.add_argument("--api-key", default=os.environ.get("OPENALEX_API_KEY"))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    client = OpenAlexClient(mailto=args.mailto, api_key=args.api_key)
    result = fetch_top(client, n=args.n, oversample=args.oversample)
    write_csv(args.out_csv, result.records)
    write_summary(args.out_md, result, n=args.n)
    oa_url = sum(1 for r in result.records if r.get("oa_url"))
    pmcid = sum(1 for r in result.records if r.get("pmcid"))
    print(
        f"Wrote {len(result.records)} rows to {args.out_csv} and {args.out_md}\n"
        f"Concept-tagged: {result.concept_count:,} | topic-tagged: {result.topic_count:,}\n"
        f"With OA URL: {oa_url} | with PMCID: {pmcid}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
