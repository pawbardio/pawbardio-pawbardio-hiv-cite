"""Tests for OA/PMC row selection, filename slugs, and payload sniffing."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from download_fulltexts import (
    classify_payload,
    extract_citation_pdf_url,
    first_author_slug,
    make_basename,
    select_papers,
    unique_path,
    xml_has_body,
)


class SelectTests(unittest.TestCase):
    def test_keeps_oa_or_pmcid_in_order(self) -> None:
        rows = [
            {"title": "paywalled", "is_oa": "false", "pmcid": ""},
            {"title": "oa", "is_oa": "true", "pmcid": ""},
            {"title": "pmc only", "is_oa": "false", "pmcid": "PMC1"},
            {"title": "both", "is_oa": "true", "pmcid": "PMC2"},
        ]
        picked = select_papers(rows, n=2)
        self.assertEqual([r["title"] for r in picked], ["oa", "pmc only"])


class FilenameTests(unittest.TestCase):
    def test_author_and_title_slug(self) -> None:
        self.assertEqual(first_author_slug("Myron S. Cohen"), "Cohen")
        self.assertEqual(
            first_author_slug("The INSIGHT START Study Group"),
            "INSIGHT_START_Study_Group",
        )
        row = {
            "publication_year": "2011",
            "primary_authors": "Myron S. Cohen",
            "title": "Prevention of HIV-1 Infection with Early Antiretroviral Therapy",
        }
        self.assertEqual(
            make_basename(row),
            "2011_Cohen_Prevention_of_HIV_1_Infection_with",
        )

    def test_unique_path_increments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            first = unique_path(directory, "2011_Cohen_Prevention", ".xml")
            first.write_text("a")
            second = unique_path(directory, "2011_Cohen_Prevention", ".xml")
            self.assertEqual(first.name, "2011_Cohen_Prevention.xml")
            self.assertEqual(second.name, "2011_Cohen_Prevention_2.xml")


class PayloadTests(unittest.TestCase):
    def test_classify(self) -> None:
        self.assertEqual(classify_payload(b"%PDF-1.4\n"), "pdf")
        self.assertEqual(
            classify_payload(b'<?xml version="1.0"?><article><body>x</body></article>'),
            "xml",
        )
        self.assertEqual(
            classify_payload(b"<!doctype html><title>Checking your browser - reCAPTCHA</title>"),
            "captcha",
        )
        self.assertEqual(classify_payload(b"<html><body>hi</body></html>"), "html")

    def test_xml_body_and_pdf_meta(self) -> None:
        self.assertTrue(xml_has_body(b"<article><body><p>x</p></body></article>"))
        self.assertFalse(xml_has_body(b"<article><front></front></article>"))
        html = b'<html><meta name="citation_pdf_url" content="/a/b.pdf"></html>'
        self.assertEqual(
            extract_citation_pdf_url(html, "https://example.org/paper"),
            "https://example.org/a/b.pdf",
        )


if __name__ == "__main__":
    unittest.main()
