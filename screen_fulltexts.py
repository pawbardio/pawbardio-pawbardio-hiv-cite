#!/usr/bin/env python3
"""
Deterministic integrity screens for JATS XML full texts.

Checks
------
1. Retraction flag via OpenAlex `is_retracted` (DOI lookup). If the API is
   unreachable, the report says no retraction list was available.
2. Placeholder / TODO / chatbot-residue language.
3. Long identical word runs shared by papers that have no authors in common.
4. Basic statistical impossibilities (p-values, correlations, n-of-m
   percentages, inverted CIs, "% of" over 100).

Usage
-----
    python3 screen_fulltexts.py
    python3 screen_fulltexts.py --xml-dir fulltexts --out free_screens.md
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

DEFAULT_MAILTO = os.environ.get("OPENALEX_MAILTO", "pawbard2008@gmail.com")
SHINGLE_WORDS = 40  # "long" identical passage
OPENALEX_WORKS = "https://api.openalex.org/works"

# Strip these JATS blocks before screening body text.
DROP_BLOCKS = (
    r"<ref-list\b[\s\S]*?</ref-list>",
    r"<ack\b[\s\S]*?</ack>",
    r"<fn-group\b[\s\S]*?</fn-group>",
    r"<funding-group\b[\s\S]*?</funding-group>",
    r"<license\b[\s\S]*?</license>",
    r"<permissions\b[\s\S]*?</permissions>",
    r"<notes\b[\s\S]*?</notes>",
    r"<boxed-text\b[\s\S]*?</boxed-text>",
    r"<!--[\s\S]*?-->",
)

BOILERPLATE = re.compile(
    r"creative commons|open access article|distributed under the terms|"
    r"creativecommons|competing interest|conflict of interest|"
    r"all rights reserved|copyright \d{4}|authors declare|"
    r"informed consent was obtained|ethics committee approved|"
    r"role of the funding source|funders of the study had no role|"
    r"corresponding author had full access|"
    r"final responsibility for the decision",
    re.I,
)

# Chatbot residue and editorial placeholders — not ordinary scientific prose.
LANGUAGE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("todo", re.compile(r"\bTODO\b")),
    ("fixme", re.compile(r"\bFIXME\b")),
    ("tbd", re.compile(r"\bTBD\b")),
    ("lorem", re.compile(r"lorem ipsum", re.I)),
    ("placeholder", re.compile(r"\[(?:insert|placeholder|your text|citation needed)[^\]]*\]", re.I)),
    ("chatbot", re.compile(r"as an ai(?: language model)?|as a large language model", re.I)),
    ("chatgpt", re.compile(r"\b(?:chatgpt|gpt-3|gpt-4|claude\.ai)\b", re.I)),
    ("assistant", re.compile(r"\bI(?:'m| am) (?:an AI|a language model|an assistant)\b", re.I)),
    ("cannot_help", re.compile(r"\bI cannot (?:assist|provide|help with)\b", re.I)),
]


@dataclass
class Paper:
    filename: str
    doi: str
    authors: set[str]
    text: str  # whitespace-normalized prose
    words: list[str]


@dataclass
class Flag:
    filename: str
    check: str
    detail: str
    extra: str = ""  # second filename for pairs


@dataclass
class ScreenResult:
    papers: list[Paper]
    retractions: list[Flag] = field(default_factory=list)
    language: list[Flag] = field(default_factory=list)
    stats: list[Flag] = field(default_factory=list)
    reuse: list[Flag] = field(default_factory=list)
    retraction_source: str = ""
    screened_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    )


# ---------------------------------------------------------------------------
# XML → Paper
# ---------------------------------------------------------------------------


def strip_tags(blob: str) -> str:
    blob = re.sub(r"<[^>]+>", " ", blob)
    blob = html.unescape(blob)
    return re.sub(r"\s+", " ", blob).strip()


def first_article(xml: str) -> str:
    match = re.search(r"<article\b[\s\S]*?</article>", xml, re.I)
    return match.group(0) if match else xml


def drop_blocks(xml: str) -> str:
    out = xml
    for pattern in DROP_BLOCKS:
        out = re.sub(pattern, " ", out, flags=re.I)
    return out


def extract_doi(front: str) -> str:
    match = re.search(
        r'<article-id[^>]*pub-id-type="doi"[^>]*>\s*([^<\s]+)', front, re.I
    )
    if not match:
        return ""
    doi = match.group(1).strip().lower()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi)
    return doi


def extract_authors(front: str) -> set[str]:
    """Normalized author keys: lastname + first initial, plus collab slugs."""
    names: set[str] = set()
    for contrib in re.finditer(r"<contrib\b[\s\S]*?</contrib>", front, re.I):
        block = contrib.group(0)
        surname = re.search(r"<surname>([^<]+)", block, re.I)
        given = re.search(r"<given-names>([^<]+)", block, re.I)
        if surname:
            last = re.sub(r"[^a-z0-9]+", "", surname.group(1).lower())
            initial = ""
            if given:
                letters = re.findall(r"[a-z]", given.group(1).lower())
                initial = letters[0] if letters else ""
            if last:
                names.add(f"{last}|{initial}")
        for collab in re.findall(r"<collab>([^<]+)", block, re.I):
            slug = re.sub(r"[^a-z0-9]+", "", collab.lower())
            if slug:
                names.add(f"collab|{slug[:40]}")
    return names


def extract_prose(article: str) -> str:
    """Abstract + body, with refs/acks/licenses removed."""
    cleaned = drop_blocks(article)
    parts: list[str] = []
    for tag in ("abstract", "body"):
        match = re.search(rf"<{tag}\b[\s\S]*?</{tag}>", cleaned, re.I)
        if match:
            parts.append(strip_tags(match.group(0)))
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+(?:'[a-z]+)?", text.lower())


def load_paper(path: Path) -> Paper:
    xml = path.read_text(encoding="utf-8", errors="replace")
    article = first_article(xml)
    front_m = re.search(r"<front>[\s\S]*?</front>", article, re.I)
    front = front_m.group(0) if front_m else article[:20_000]
    text = extract_prose(article)
    return Paper(
        filename=path.name,
        doi=extract_doi(front),
        authors=extract_authors(front),
        text=text,
        words=tokenize(text),
    )


# ---------------------------------------------------------------------------
# Language
# ---------------------------------------------------------------------------


def screen_language(paper: Paper) -> list[Flag]:
    flags: list[Flag] = []
    hay = paper.text
    for label, pattern in LANGUAGE_PATTERNS:
        hit = pattern.search(hay)
        if hit:
            start = max(0, hit.start() - 40)
            snippet = hay[start : hit.end() + 40].strip()
            flags.append(
                Flag(paper.filename, "language", f"{label}: …{snippet}…")
            )
    return flags


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


def _decimals(num_s: str) -> int:
    if "." in num_s:
        return len(num_s.split(".", 1)[1])
    return 0


def percent_matches(x: int, y: int, reported: float, reported_raw: str) -> bool:
    """True if reported % is a plausible rounding of 100*x/y."""
    if y == 0:
        return reported == 0
    exact = 100.0 * x / y
    dec = _decimals(reported_raw)
    rounded = round(exact, dec)
    # Integer percents: allow ±1 pp for n-of-m rounding (1/3 → 33%).
    tol = 1.0 if dec == 0 else 0.5 * 10 ** (-dec) + 1e-9
    return abs(rounded - reported) <= tol or abs(exact - reported) <= max(tol, 0.6)


def screen_stats(paper: Paper) -> list[Flag]:
    flags: list[Flag] = []
    text = paper.text

    for match in re.finditer(
        r"\bp(?:-?\s*value)?\s*(?:=|<|>|≤|≥|<=|>=)\s*"
        r"([+-]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?)\s*(%?)",
        text,
        re.I,
    ):
        raw, pct = match.group(1), match.group(2)
        try:
            value = float(raw)
        except ValueError:
            continue
        if pct:
            # "p = 5%" is a percent, not a probability; skip.
            continue
        rest = text[match.end() : match.end() + 16]
        # "P = 2.8 × 10 −35" and "p=10 −103" are scientific notation, not p>1.
        if re.match(r"\s*[×xX]\s*10", rest) or re.match(r"\s*10\s*[−^-]", rest):
            continue
        if re.match(r"\s*[−-]\d", rest):
            continue
        # "p = 6 rigid body parameters" is not a p-value.
        if value > 1 and re.match(r"[A-Za-z]", rest.lstrip()):
            continue
        if value < 0 or value > 1:
            flags.append(
                Flag(
                    paper.filename,
                    "stats",
                    f"p-value outside [0, 1]: {match.group(0)}",
                )
            )

    for match in re.finditer(
        r"\b(?:r|rho|ρ|R)\s*=\s*([+-]?(?:\d+(?:\.\d+)?|\.\d+))",
        text,
    ):
        try:
            value = float(match.group(1))
        except ValueError:
            continue
        if abs(value) > 1:
            flags.append(
                Flag(
                    paper.filename,
                    "stats",
                    f"correlation outside [-1, 1]: {match.group(0)}",
                )
            )

    for match in re.finditer(
        r"(\d{1,6})\s*(of|/)\s*(\d{1,6})\s*\(\s*(\d{1,3}(?:\.\d+)?)\s*%\s*\)",
        text,
        re.I,
    ):
        x, conj, y, z_raw = match.group(1), match.group(2), match.group(3), match.group(4)
        xi, yi, z = int(x), int(y), float(z_raw)
        # "1/3 (32.4%)" is a fraction, not an n-of-m count.
        if conj == "/" and yi < 10:
            continue
        if yi == 0 or not percent_matches(xi, yi, z, z_raw):
            flags.append(
                Flag(
                    paper.filename,
                    "stats",
                    f"n-of-m percent mismatch: {match.group(0)} "
                    f"(expected ~{100.0 * xi / yi:.1f}% )"
                    if yi
                    else f"n-of-m percent mismatch: {match.group(0)} (denominator 0)",
                )
            )

    for match in re.finditer(
        r"(\d{3,}(?:\.\d+)?)\s*%\s+of\b",
        text,
        re.I,
    ):
        value = float(match.group(1))
        if value > 100:
            ctx = text[max(0, match.start() - 25) : match.end() + 20]
            if not re.search(r"increase|decrease|change|rise|higher|more than", ctx, re.I):
                flags.append(
                    Flag(
                        paper.filename,
                        "stats",
                        f"percentage over 100 as a share: {match.group(0)}",
                    )
                )

    # Numbers may use thousands commas (1,070) or mid-dot decimals (1·68).
    ci_num = r"[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:[.,·]\d+)?"
    for match in re.finditer(
        rf"95\s*%\s*CI[:\s=]*[\[(]?\s*"
        rf"({ci_num})\s*(?:to|–|—|-)\s*"
        rf"({ci_num})",
        text,
        re.I,
    ):
        def _ci_float(s: str) -> float:
            s = s.replace(",", "").replace("·", ".")
            return float(s)

        lo, hi = _ci_float(match.group(1)), _ci_float(match.group(2))
        if lo > hi:
            flags.append(
                Flag(
                    paper.filename,
                    "stats",
                    f"inverted 95% CI: {match.group(0)}",
                )
            )

    return flags


# ---------------------------------------------------------------------------
# Text reuse
# ---------------------------------------------------------------------------


def authors_disjoint(a: Paper, b: Paper) -> bool:
    if not a.authors or not b.authors:
        return False
    return a.authors.isdisjoint(b.authors)


def extend_match(a: list[str], i: int, b: list[str], j: int, width: int) -> str:
    """Grow a shared shingle to the longest identical run around it."""
    left = 0
    while i - left - 1 >= 0 and j - left - 1 >= 0 and a[i - left - 1] == b[j - left - 1]:
        left += 1
    right = width
    while i + right < len(a) and j + right < len(b) and a[i + right] == b[j + right]:
        right += 1
    return " ".join(a[i - left : i + right])


def screen_reuse(papers: list[Paper], width: int = SHINGLE_WORDS) -> list[Flag]:
    index: dict[tuple[str, ...], list[tuple[int, int]]] = defaultdict(list)
    for p_i, paper in enumerate(papers):
        words = paper.words
        if len(words) < width:
            continue
        seen_here: set[tuple[str, ...]] = set()
        for i in range(0, len(words) - width + 1):
            shingle = tuple(words[i : i + width])
            if shingle in seen_here:
                continue
            seen_here.add(shingle)
            index[shingle].append((p_i, i))

    pair_best: dict[tuple[int, int], str] = {}
    for shingle, locations in index.items():
        if len(locations) < 2:
            continue
        passage = " ".join(shingle)
        if BOILERPLATE.search(passage):
            continue
        for (i, pos_i), (j, pos_j) in combinations(locations, 2):
            if i == j:
                continue
            a, b = papers[i], papers[j]
            if not authors_disjoint(a, b):
                continue
            span = extend_match(a.words, pos_i, b.words, pos_j, width)
            if BOILERPLATE.search(span):
                continue
            key = (min(i, j), max(i, j))
            if len(span) > len(pair_best.get(key, "")):
                pair_best[key] = span

    flags: list[Flag] = []
    for (i, j), span in sorted(pair_best.items(), key=lambda kv: kv[0]):
        nwords = len(span.split())
        snippet = span if len(span) <= 220 else span[:217] + "…"
        flags.append(
            Flag(
                papers[i].filename,
                "reuse",
                f"{nwords} identical words: “{snippet}”",
                extra=papers[j].filename,
            )
        )
    return flags


# ---------------------------------------------------------------------------
# Retractions
# ---------------------------------------------------------------------------


def normalize_doi(doi: str) -> str:
    doi = (doi or "").strip().lower()
    return re.sub(r"^https?://(dx\.)?doi\.org/", "", doi)


def fetch_openalex_retractions(dois: list[str], mailto: str) -> tuple[set[str], str]:
    """Return (retracted DOIs, coverage note)."""
    unique = [d for d in sorted(set(dois)) if d]
    if not unique:
        return set(), "No DOIs found in XML; retraction lookup skipped."
    retracted: set[str] = set()
    found = 0
    try:
        for start in range(0, len(unique), 50):
            chunk = unique[start : start + 50]
            filt = "doi:" + "|".join(chunk)
            query = urllib.parse.urlencode(
                {
                    "filter": filt,
                    "select": "doi,is_retracted",
                    "per-page": 50,
                    "mailto": mailto,
                }
            )
            url = f"{OPENALEX_WORKS}?{query}"
            request = urllib.request.Request(
                url,
                headers={"User-Agent": f"hiv-aids-screens/1.0 (mailto:{mailto})"},
            )
            with urllib.request.urlopen(request, timeout=45) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            for work in payload.get("results") or []:
                doi = normalize_doi(work.get("doi") or "")
                found += 1
                if work.get("is_retracted"):
                    retracted.add(doi)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return set(), (
            f"OpenAlex retraction lookup failed ({exc}). "
            "No local retraction list is bundled; retractions treated as unavailable."
        )
    missing = len(unique) - found
    note = (
        f"OpenAlex `is_retracted` for {found}/{len(unique)} DOIs "
        f"(mailto polite pool). OpenRetractions.com was not reachable."
    )
    if missing:
        note += f" {missing} DOI(s) had no OpenAlex work record."
    return retracted, note


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def write_report(path: str, result: ScreenResult) -> None:
    triggered = sorted(
        {
            f.filename
            for group in (result.retractions, result.language, result.stats, result.reuse)
            for f in group
        }
        | {f.extra for f in result.reuse if f.extra}
    )
    lines = [
        "# Free deterministic screens",
        "",
        f"Ran **{result.screened_at}** on every `.xml` file in `fulltexts/`.",
        "",
        "| Check | Count |",
        "|---|---:|",
        f"| papers screened | {len(result.papers)} |",
        f"| retractions | {len(result.retractions)} |",
        f"| text-reuse pairs | {len(result.reuse)} |",
        f"| language flags | {len(result.language)} |",
        f"| statistical flags | {len(result.stats)} |",
        "",
        f"Retraction source: {result.retraction_source}",
        "",
        "## Retractions",
        "",
    ]
    if result.retractions:
        for flag in result.retractions:
            lines.append(f"- `{flag.filename}` — {flag.detail}")
    else:
        lines.append("None flagged.")
    lines += ["", "## Language flags", ""]
    if result.language:
        for flag in result.language:
            lines.append(f"- `{flag.filename}` — {flag.detail}")
    else:
        lines.append("None flagged.")
    lines += ["", "## Statistical flags", ""]
    if result.stats:
        for flag in result.stats:
            lines.append(f"- `{flag.filename}` — {flag.detail}")
    else:
        lines.append("None flagged.")
    lines += [
        "",
        f"## Text-reuse pairs (no shared authors, ≥{SHINGLE_WORDS} consecutive words)",
        "",
    ]
    if result.reuse:
        for flag in result.reuse:
            lines.append(f"- `{flag.filename}` ↔ `{flag.extra}` — {flag.detail}")
    else:
        lines.append("None flagged.")
    lines += ["", "## Files that triggered anything", ""]
    if triggered:
        for name in triggered:
            lines.append(f"- `{name}`")
    else:
        lines.append("None.")
    lines.append("")
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def run(xml_dir: str, out_path: str, mailto: str) -> ScreenResult:
    paths = sorted(Path(xml_dir).glob("*.xml"))
    print(f"Loading {len(paths)} XML files…", file=sys.stderr)
    papers = [load_paper(p) for p in paths]
    dois = [p.doi for p in papers if p.doi]
    retracted, source = fetch_openalex_retractions(dois, mailto)
    retractions = [
        Flag(p.filename, "retraction", f"OpenAlex is_retracted=true for {p.doi}")
        for p in papers
        if p.doi and p.doi in retracted
    ]
    language: list[Flag] = []
    stats: list[Flag] = []
    for paper in papers:
        language.extend(screen_language(paper))
        stats.extend(screen_stats(paper))
    print("Scanning for identical passages…", file=sys.stderr)
    reuse = screen_reuse(papers)
    result = ScreenResult(
        papers=papers,
        retractions=retractions,
        language=language,
        stats=stats,
        reuse=reuse,
        retraction_source=source,
    )
    write_report(out_path, result)
    print(
        f"screened={len(papers)} retractions={len(retractions)} "
        f"reuse_pairs={len(reuse)} language={len(language)} stats={len(stats)}\n"
        f"Wrote {out_path}",
        file=sys.stderr,
    )
    return result


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("Usage", 1)[0].strip())
    parser.add_argument("--xml-dir", default="fulltexts")
    parser.add_argument("--out", default="free_screens.md")
    parser.add_argument("--mailto", default=DEFAULT_MAILTO)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    run(args.xml_dir, args.out, args.mailto)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
