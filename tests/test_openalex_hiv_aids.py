"""Unit tests for abstract reconstruction, PMCID parsing, and DOI/title dedupe."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openalex_hiv_aids import (
    best_fulltext_url,
    deduplicate,
    extract_pmcid,
    extract_record,
    is_hiv_aids_work,
    normalize_doi,
    normalize_title,
    primary_authors,
    reconstruct_abstract,
    truncate,
)


class AbstractTests(unittest.TestCase):
    def test_reconstruct_and_truncate(self) -> None:
        inverted = {"HIV": [0, 3], "treatment": [1], "reduces": [2]}
        self.assertEqual(reconstruct_abstract(inverted), "HIV treatment reduces HIV")
        self.assertEqual(truncate("abcdefghij", 8), "abcdefg…")
        self.assertEqual(reconstruct_abstract(None), "")


class NormalizeTests(unittest.TestCase):
    def test_doi_and_title(self) -> None:
        self.assertEqual(
            normalize_doi("https://doi.org/10.1056/NEJMoa1105243"),
            "10.1056/nejmoa1105243",
        )
        self.assertEqual(
            normalize_title("Prevention of <i>HIV-1</i> Infection!"),
            "prevention of hiv 1 infection",
        )


class ExtractTests(unittest.TestCase):
    def test_pmcid_authors_and_oa_url(self) -> None:
        work = {
            "id": "https://openalex.org/W123",
            "display_name": "A trial of <i>HIV</i> therapy",
            "publication_year": 2011,
            "cited_by_count": 10,
            "doi": "https://doi.org/10.1/xyz",
            "ids": {"pmcid": "https://www.ncbi.nlm.nih.gov/pmc/articles/3200068"},
            "open_access": {"is_oa": True, "oa_url": ""},
            "best_oa_location": {
                "is_oa": True,
                "pdf_url": "https://example.org/paper.pdf",
                "landing_page_url": "https://example.org/paper",
            },
            "authorships": [
                {
                    "author_position": "first",
                    "author": {"display_name": "Ada Lovelace"},
                },
                {
                    "author_position": "first",
                    "author": {"display_name": "Alan Turing"},
                },
            ],
            "abstract_inverted_index": {"Hello": [0], "world": [1]},
        }
        record = extract_record(work)
        self.assertEqual(record["pmcid"], "PMC3200068")
        self.assertEqual(record["primary_authors"], "Ada Lovelace; Alan Turing")
        self.assertEqual(record["title"], "A trial of HIV therapy")
        self.assertEqual(record["oa_url"], "https://example.org/paper.pdf")
        self.assertEqual(record["abstract"], "Hello world")
        self.assertEqual(extract_pmcid({"ids": {"pmcid": "PMC99"}}), "PMC99")
        self.assertEqual(
            best_fulltext_url({"open_access": {"oa_url": "https://oa.example/a"}}),
            "https://oa.example/a",
        )


class TagFilterTests(unittest.TestCase):
    def test_drops_zero_score_concept_without_hiv_topic(self) -> None:
        work = {
            "concepts": [
                {
                    "id": "https://openalex.org/C3013748606",
                    "display_name": "Human immunodeficiency virus (HIV)",
                    "score": 0,
                }
            ],
            "primary_topic": {
                "id": "https://openalex.org/T10272",
                "display_name": "Mental Health Treatment and Access",
            },
        }
        self.assertFalse(is_hiv_aids_work(work))

    def test_keeps_scored_concept_or_primary_topic(self) -> None:
        scored = {
            "concepts": [
                {
                    "id": "https://openalex.org/C3013748606",
                    "score": 0.38,
                }
            ],
            "primary_topic": {"id": "https://openalex.org/T10041"},
        }
        primary = {
            "concepts": [],
            "primary_topic": {
                "id": "https://openalex.org/T10082",
                "display_name": "HIV/AIDS Research and Interventions",
            },
        }
        self.assertTrue(is_hiv_aids_work(scored))
        self.assertTrue(is_hiv_aids_work(primary))


class DedupeTests(unittest.TestCase):
    def test_prefers_higher_citations_on_doi_or_title(self) -> None:
        a = {
            "title": "Same Paper",
            "doi": "10.1/abc",
            "cited_by_count": 10,
            "openalex_id": "W1",
            "pmcid": "",
            "oa_url": "",
            "has_abstract": False,
        }
        b = {
            "title": "Same Paper",
            "doi": "10.1/abc",
            "cited_by_count": 50,
            "openalex_id": "W2",
            "pmcid": "PMC1",
            "oa_url": "https://x",
            "has_abstract": True,
        }
        # Title-only duplicate of a lower-cited preprint.
        c = {
            "title": "Same Paper",
            "doi": "",
            "cited_by_count": 4,
            "openalex_id": "W3",
            "pmcid": "",
            "oa_url": "",
            "has_abstract": False,
        }
        unique, dropped = deduplicate([a, c, b])
        self.assertEqual(dropped, 2)
        self.assertEqual(len(unique), 1)
        self.assertEqual(unique[0]["openalex_id"], "W2")
        self.assertEqual(unique[0]["cited_by_count"], 50)

    def test_distinct_titles_without_doi_stay_separate(self) -> None:
        unique, dropped = deduplicate(
            [
                {"title": "Alpha", "doi": "", "cited_by_count": 3},
                {"title": "Beta", "doi": "", "cited_by_count": 9},
            ]
        )
        self.assertEqual(dropped, 0)
        self.assertEqual([r["title"] for r in unique], ["Beta", "Alpha"])


if __name__ == "__main__":
    unittest.main()
