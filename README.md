# HIV/AIDS papers from OpenAlex

Reusable script that pulls the most-cited HIV/AIDS works from the
[OpenAlex](https://openalex.org) Works API, deduplicates them, and writes a
clean CSV plus a short coverage summary.

## What it fetches

- **Concepts or topics** whose name is HIV or AIDS (not a title keyword search)
- **Publication years** 2005–2026
- **Sort** `cited_by_count` descending
- **Top 200** after DOI / normalized-title dedupe (keeps the higher-citation version)

Each row has: title, year, citation count, DOI, OpenAlex ID, primary (first)
author(s), `is_oa`, OA / best full-text URL, PMCID, truncated abstract.

## Run

Python 3.10+, standard library only.

```bash
python3 openalex_hiv_aids.py
```

Outputs:

- `data/hiv_aids_top200.csv`
- `SUMMARY.md`

Useful flags:

```bash
python3 openalex_hiv_aids.py --n 200 --oversample 600 \
  --out-csv data/hiv_aids_top200.csv --out-md SUMMARY.md \
  --mailto you@example.com
```

`OPENALEX_MAILTO` and `OPENALEX_API_KEY` are also read from the environment.
The mailto address puts you in OpenAlex’s polite pool.

```bash
python3 -m unittest tests.test_openalex_hiv_aids tests.test_download_fulltexts
```

## Download full texts

Takes the first 30 rows in `data/hiv_aids_top200.csv` that are open access
or have a PMCID, and writes PDF/XML files into `fulltexts/`.

Priority: PMC PDF, then PMC XML (NCBI eutils), then `oa_url`. PMC website
PDFs are often blocked by a browser check; the XML fallback is the public
full-text copy. Delays 1–2 seconds between papers.

```bash
python3 download_fulltexts.py --n 30
python3 download_fulltexts.py --offset 30 --skip-existing
```

Writes `fulltexts/{year}_{first_author}_{short_title}.pdf` (or `.xml`) and
updates `download_log.csv`. `--skip-existing` leaves files already in
`fulltexts/` alone. `--offset 30` continues after the first batch.

## Free deterministic screens

```bash
python3 screen_fulltexts.py
```

Writes `free_screens.md`: retractions (OpenAlex `is_retracted`), placeholder /
chatbot language, long identical passages across papers with no shared
authors, and basic statistical impossibilities.

## How the filter is built

OpenAlex can OR values *inside* one attribute, but not *across* attributes.
The script therefore:

1. Queries works tagged with the HIV/AIDS **concepts**
2. Queries works whose **primary topic** is an HIV/AIDS topic
3. Drops concept hits whose HIV/AIDS concept score is 0 and whose primary
   topic is not HIV/AIDS (OpenAlex still indexes those leftover tags)
4. Unions the two ranked lists, dedupes, and cuts to 200

“Decision aids”, hearing aids, and similar off-topic “AIDS” hits are left out
of the topic/concept ID lists. Secondary (non-primary) HIV topic tags on
unrelated mega-cited papers are also left out.

## Rate limits

The client identifies itself, sends `mailto`, and waits ~120 ms between calls.
Without an API key, OpenAlex shares a small free daily budget per IP; this
export is a few `/works` pages and stays well under that. Cursor paging now
requires a key, so the unkeyed path uses `page=`. HTTP 429 is retried with
backoff.
