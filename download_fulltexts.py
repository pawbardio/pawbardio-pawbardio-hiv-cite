#!/usr/bin/env python3
"""
Download full text for the first N open-access HIV/AIDS papers.

Reads data/hiv_aids_top200.csv, keeps rows where is_oa is true or pmcid is
set, and downloads the first 30 of those into fulltexts/.

Priority per paper
------------------
1. PMC PDF (https://www.ncbi.nlm.nih.gov/pmc/articles/PMCXXXXX/pdf/)
   then PMC JATS XML via NCBI eutils (the public OA full-text API; the
   classic oa.fcgi package endpoint is gone).
2. Else the OpenAlex oa_url.
3. Skip and log if neither yields a PDF or XML full text.

Usage
-----
    python3 download_fulltexts.py
    python3 download_fulltexts.py --n 30 --csv data/hiv_aids_top200.csv

Filenames: {year}_{first_author}_{short_title}.pdf (or .xml)
"""

from __future__ import annotations

import argparse
import csv
import html as html_lib
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT_MAILTO = os.environ.get("OPENALEX_MAILTO", "pawbard2008@gmail.com")
DEFAULT_CSV = "data/hiv_aids_top200.csv"
DEFAULT_OUT_DIR = "fulltexts"
DEFAULT_LOG = "download_log.csv"
NCBI_EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
TIMEOUT = 30
MAX_BYTES = 80 * 1024 * 1024  # 80 MiB cap so a runaway response cannot fill the disk

LOG_COLUMNS = ["title", "doi", "pmcid", "url_used", "status", "filename"]


# ---------------------------------------------------------------------------
# CSV selection and filenames
# ---------------------------------------------------------------------------


def is_true(value: str | None) -> bool:
    return (value or "").strip().lower() in {"true", "1", "yes"}


def select_papers(rows: list[dict[str, str]], n: int) -> list[dict[str, str]]:
    """Preserve CSV order; keep is_oa or non-empty pmcid; cut to n."""
    picked: list[dict[str, str]] = []
    for row in rows:
        if is_true(row.get("is_oa")) or (row.get("pmcid") or "").strip():
            picked.append(row)
        if len(picked) >= n:
            break
    return picked


def _slug(text: str, max_words: int = 6, max_chars: int = 60) -> str:
    text = (text or "").replace("‐", "-").replace("–", "-").replace("—", "-")
    words = re.findall(r"[A-Za-z0-9]+", text)
    slug = "_".join(words[:max_words])
    return slug[:max_chars].strip("_") or "untitled"


def first_author_slug(authors: str) -> str:
    first = (authors or "unknown").split(";")[0].strip()
    if first.lower().startswith("the "):
        return _slug(first[4:], max_words=4, max_chars=40)
    parts = re.findall(r"[A-Za-z0-9]+", first.replace("‐", "-"))
    return (parts[-1] if parts else "unknown")[:40]


def make_basename(row: dict[str, str]) -> str:
    year = str(row.get("publication_year") or "0000")
    author = first_author_slug(row.get("primary_authors") or "")
    title = _slug(row.get("title") or "")
    return f"{year}_{author}_{title}"


def existing_file(directory: Path, basename: str) -> Path | None:
    """Return an already-downloaded PDF/XML for this basename, if any."""
    for path in sorted(directory.glob(f"{basename}.*")):
        if path.suffix.lower() in {".pdf", ".xml"} and path.is_file() and path.stat().st_size > 0:
            return path
    return None


def unique_path(directory: Path, basename: str, ext: str) -> Path:
    candidate = directory / f"{basename}{ext}"
    n = 2
    while candidate.exists():
        candidate = directory / f"{basename}_{n}{ext}"
        n += 1
    return candidate


# ---------------------------------------------------------------------------
# HTTP + payload sniffing
# ---------------------------------------------------------------------------


def classify_payload(data: bytes) -> str:
    """Return pdf, xml, html, captcha, empty, or unknown."""
    if not data:
        return "empty"
    if data.startswith(b"%PDF"):
        return "pdf"
    head = data[:4096].lstrip().lower()
    if b"recaptcha" in head or b"checking your browser" in head:
        return "captcha"
    if (
        head.startswith(b"<?xml")
        or head.startswith(b"<pmc-articleset")
        or head.startswith(b"<article")
        or head.startswith(b"<!doctype pmc")
    ):
        if b"<error>" in head or b"<efetchresult>" in head:
            return "error"
        return "xml"
    if head.startswith(b"<!doctype html") or head.startswith(b"<html"):
        return "html"
    return "unknown"


def xml_has_body(data: bytes) -> bool:
    """JATS full text has a <body>; front-matter-only records are not enough."""
    return bool(re.search(rb"<body(\s|>)", data[:200_000], re.I))


def extract_citation_pdf_url(html: bytes, base: str) -> str:
    """One-hop PDF discovery from a landing page."""
    text = html[:200_000].decode("utf-8", errors="replace")
    match = re.search(
        r'<meta[^>]+name=["\']citation_pdf_url["\'][^>]+content=["\']([^"\']+)["\']',
        text,
        re.I,
    )
    if not match:
        match = re.search(
            r'<link[^>]+type=["\']application/pdf["\'][^>]+href=["\']([^"\']+)["\']',
            text,
            re.I,
        )
    if not match:
        return ""
    return urllib.parse.urljoin(base, html_lib.unescape(match.group(1).strip()))


class Downloader:
    def __init__(self, mailto: str, delay_min: float, delay_max: float) -> None:
        self.mailto = mailto
        self.delay_min = delay_min
        self.delay_max = delay_max
        self.user_agent = (
            f"hiv-aids-fulltext-download/1.0 (mailto:{mailto}; research full-text fetch)"
        )
        self._last_request_at = 0.0

    def polite_pause(self, lo: float | None = None, hi: float | None = None) -> None:
        lo = self.delay_min if lo is None else lo
        hi = self.delay_max if hi is None else hi
        # Honour the remaining wait if we already slept via min_interval.
        wait = random.uniform(lo, hi)
        elapsed = time.monotonic() - self._last_request_at
        leftover = wait - elapsed
        if leftover > 0:
            time.sleep(leftover)

    def fetch(self, url: str, accept: str = "*/*") -> tuple[bytes, str, str]:
        """
        GET url. Returns (body, final_url, error).
        error is empty on HTTP success (even if the body is HTML/captcha).
        """
        self.polite_pause(0.35, 0.6)  # extra spacing between attempts
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": accept,
                "Accept-Language": "en",
            },
        )
        last_error = "request failed"
        for attempt in range(2):
            self._last_request_at = time.monotonic()
            try:
                with urllib.request.urlopen(request, timeout=TIMEOUT) as resp:
                    chunks: list[bytes] = []
                    total = 0
                    while True:
                        block = resp.read(64 * 1024)
                        if not block:
                            break
                        total += len(block)
                        if total > MAX_BYTES:
                            return b"", resp.geturl(), f"response larger than {MAX_BYTES} bytes"
                        chunks.append(block)
                    return b"".join(chunks), resp.geturl(), ""
            except urllib.error.HTTPError as exc:
                return b"", url, f"HTTP {exc.code}"
            except (urllib.error.URLError, TimeoutError) as exc:
                reason = getattr(exc, "reason", exc)
                last_error = f"URL error: {reason}"
                time.sleep(1.5 * (attempt + 1))
                continue
            except Exception as exc:  # noqa: BLE001 — download loop must not crash
                return b"", url, f"{type(exc).__name__}: {exc}"
        return b"", url, last_error

    def try_as_fulltext(
        self, url: str, accept: str = "*/*"
    ) -> tuple[bytes | None, str, str, str]:
        """
        Fetch and classify. Returns (data, kind, final_url, error).
        data is set only for usable pdf/xml.
        """
        data, final_url, error = self.fetch(url, accept=accept)
        if error:
            return None, "error", final_url, error
        kind = classify_payload(data)
        if kind == "pdf":
            return data, kind, final_url, ""
        if kind == "xml":
            if xml_has_body(data):
                return data, kind, final_url, ""
            return None, "xml", final_url, "XML had no <body> (not full text)"
        if kind == "html":
            pdf_url = extract_citation_pdf_url(data, final_url)
            if pdf_url and pdf_url != url:
                return self.try_as_fulltext(pdf_url, accept="application/pdf,*/*")
            return None, kind, final_url, "HTML landing page, no PDF link"
        if kind == "captcha":
            return None, kind, final_url, "blocked by reCAPTCHA / browser check"
        return None, kind, final_url, f"not a PDF or XML full text ({kind})"


def pmc_pdf_urls(pmcid: str) -> list[str]:
    pmcid = pmcid.strip()
    if not pmcid.upper().startswith("PMC"):
        pmcid = f"PMC{pmcid}"
    numeric = re.sub(r"^PMC", "", pmcid, flags=re.I)
    # New host first, then the URL the user named, then the numeric form.
    return [
        f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/pdf/",
        f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/pdf/",
        f"https://www.ncbi.nlm.nih.gov/pmc/articles/{numeric}/pdf/",
    ]


def pmc_xml_url(pmcid: str, mailto: str) -> str:
    numeric = re.sub(r"^PMC", "", pmcid.strip(), flags=re.I)
    query = urllib.parse.urlencode(
        {
            "db": "pmc",
            "id": numeric,
            "rettype": "xml",
            "retmode": "xml",
            "tool": "hiv_aids_fulltext",
            "email": mailto,
        }
    )
    return f"{NCBI_EUTILS}?{query}"


def download_one(
    downloader: Downloader, row: dict[str, str]
) -> tuple[bytes | None, str, str, str]:
    """
    Walk the priority list. Returns (data, ext_with_dot, url_used, error).
    """
    pmcid = (row.get("pmcid") or "").strip()
    oa_url = (row.get("oa_url") or "").strip()
    last_url = ""
    last_error = "no download URL"

    if pmcid:
        for url in pmc_pdf_urls(pmcid):
            last_url = url
            data, kind, final_url, error = downloader.try_as_fulltext(
                url, accept="application/pdf,*/*"
            )
            last_url = final_url or url
            if data and kind == "pdf":
                return data, ".pdf", last_url, ""
            last_error = error or kind
            # PMC's web PDFs are often behind a reCAPTCHA interstitial from
            # datacenter IPs; extra PDF URLs will fail the same way.
            if kind == "captcha":
                break

        xml_url = pmc_xml_url(pmcid, downloader.mailto)
        last_url = xml_url
        data, kind, final_url, error = downloader.try_as_fulltext(
            xml_url, accept="application/xml,text/xml,*/*"
        )
        last_url = final_url or xml_url
        if data and kind == "xml":
            return data, ".xml", last_url, ""
        last_error = error or kind

    if oa_url:
        last_url = oa_url
        data, kind, final_url, error = downloader.try_as_fulltext(oa_url)
        last_url = final_url or oa_url
        if data and kind in {"pdf", "xml"}:
            return data, f".{kind}", last_url, ""
        last_error = error or kind

    return None, "", last_url, last_error or "neither PMC nor oa_url worked"


def write_file(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_bytes(data)
    tmp.replace(path)


def run(
    csv_path: str,
    out_dir: str,
    log_path: str,
    n: int,
    mailto: str,
    delay_min: float,
    delay_max: float,
    skip_existing: bool = False,
) -> int:
    with open(csv_path, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    papers = select_papers(rows, n)
    if not papers:
        print(f"No OA/PMC rows in {csv_path}", file=sys.stderr)
        return 1

    dest = Path(out_dir)
    dest.mkdir(parents=True, exist_ok=True)
    downloader = Downloader(mailto=mailto, delay_min=delay_min, delay_max=delay_max)

    log_rows: list[dict[str, str]] = []
    succeeded = 0
    failed = 0

    print(f"Downloading {len(papers)} papers into {dest}/ …", file=sys.stderr)
    for i, row in enumerate(papers, start=1):
        title = row.get("title") or ""
        print(f"[{i}/{len(papers)}] {title[:80]}", file=sys.stderr)
        already = existing_file(dest, make_basename(row)) if skip_existing else None
        if already:
            succeeded += 1
            print(f"    skip existing {already.name}", file=sys.stderr)
            pmcid = (row.get("pmcid") or "").strip()
            reused_url = (
                pmc_xml_url(pmcid, mailto)
                if pmcid
                else (row.get("oa_url") or "")
            )
            log_rows.append(
                {
                    "title": title,
                    "doi": row.get("doi") or "",
                    "pmcid": pmcid,
                    "url_used": reused_url,
                    "status": "success",
                    "filename": already.name,
                }
            )
            if i < len(papers):
                downloader.polite_pause()
            continue
        data, ext, url_used, error = download_one(downloader, row)
        filename = ""
        status = "fail"
        if data:
            path = unique_path(dest, make_basename(row), ext)
            try:
                write_file(path, data)
                filename = path.name
                status = "success"
                succeeded += 1
                print(f"    saved {filename}  ({len(data):,} bytes)", file=sys.stderr)
            except OSError as exc:
                error = f"could not write file: {exc}"
                failed += 1
                print(f"    FAIL write: {exc}", file=sys.stderr)
        else:
            failed += 1
            print(f"    FAIL {error}", file=sys.stderr)
        log_rows.append(
            {
                "title": title,
                "doi": row.get("doi") or "",
                "pmcid": row.get("pmcid") or "",
                "url_used": url_used,
                "status": status if status == "success" else "fail",
                "filename": filename,
            }
        )
        # Polite delay between papers (1–2 s by default), even after a skip.
        if i < len(papers):
            downloader.polite_pause()

    with open(log_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=LOG_COLUMNS)
        writer.writeheader()
        writer.writerows(log_rows)

    print(
        f"\nDone. succeeded={succeeded}  failed={failed}  "
        f"total={len(papers)}\nLog: {log_path}",
        file=sys.stderr,
    )
    return 0 if succeeded else 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("Usage", 1)[0].strip())
    parser.add_argument("--csv", default=DEFAULT_CSV)
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    parser.add_argument("--log", default=DEFAULT_LOG)
    parser.add_argument("--n", type=int, default=30)
    parser.add_argument("--mailto", default=DEFAULT_MAILTO)
    parser.add_argument("--delay-min", type=float, default=1.0)
    parser.add_argument("--delay-max", type=float, default=2.0)
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Do not re-download papers that already have a file in --out-dir",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.delay_max < args.delay_min:
        args.delay_max = args.delay_min
    return run(
        csv_path=args.csv,
        out_dir=args.out_dir,
        log_path=args.log,
        n=args.n,
        mailto=args.mailto,
        delay_min=args.delay_min,
        delay_max=args.delay_max,
        skip_existing=args.skip_existing,
    )


if __name__ == "__main__":
    raise SystemExit(main())
