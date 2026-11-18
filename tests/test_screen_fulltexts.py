"""Unit tests for language, stats, reuse, and XML extraction screens."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from screen_fulltexts import (
    Paper,
    authors_disjoint,
    extract_authors,
    extract_doi,
    percent_matches,
    screen_language,
    screen_reuse,
    screen_stats,
    tokenize,
)


def paper(name: str, text: str, authors: set[str] | None = None, doi: str = "") -> Paper:
    return Paper(
        filename=name,
        doi=doi,
        authors=authors or {name},
        text=text,
        words=tokenize(text),
    )


class ExtractTests(unittest.TestCase):
    def test_doi_and_authors(self) -> None:
        front = """
        <front><article-meta>
        <article-id pub-id-type="doi">10.1371/journal.pmed.0020298</article-id>
        <contrib contrib-type="author"><name>
        <surname>Auvert</surname><given-names>Bertran</given-names>
        </name></contrib>
        <contrib contrib-type="author"><collab>ANRS Study Group</collab></contrib>
        </article-meta></front>
        """
        self.assertEqual(extract_doi(front), "10.1371/journal.pmed.0020298")
        names = extract_authors(front)
        self.assertIn("auvert|b", names)
        self.assertTrue(any(n.startswith("collab|") for n in names))


class LanguageTests(unittest.TestCase):
    def test_todo_and_chatbot(self) -> None:
        hits = screen_language(paper("a.xml", "Methods TODO were not completed."))
        self.assertTrue(any(f.detail.startswith("todo") for f in hits))
        clean = screen_language(paper("b.xml", "Patients were followed for 48 weeks."))
        self.assertEqual(clean, [])
        bot = screen_language(
            paper("c.xml", "As an AI language model I cannot diagnose HIV.")
        )
        self.assertTrue(any("chatbot" in f.detail for f in bot))


class StatsTests(unittest.TestCase):
    def test_percent_rounding(self) -> None:
        self.assertTrue(percent_matches(1, 3, 33, "33"))
        self.assertFalse(percent_matches(1, 3, 50, "50"))

    def test_impossible_p_and_n_of_m(self) -> None:
        bad_p = screen_stats(paper("p.xml", "The association was significant (p = 1.4)."))
        self.assertTrue(any("p-value" in f.detail for f in bad_p))
        ok_p = screen_stats(paper("p2.xml", "The test was significant (p = 0.01)."))
        self.assertEqual(ok_p, [])
        mismatch = screen_stats(paper("n.xml", "Response in 15 of 30 (80%) patients."))
        self.assertTrue(any("n-of-m" in f.detail for f in mismatch))
        match = screen_stats(paper("n2.xml", "Response in 15 of 30 (50%) patients."))
        self.assertEqual(match, [])
        ci = screen_stats(paper("ci.xml", "OR 1.2 (95% CI 2.5-1.1) was reported."))
        self.assertTrue(any("inverted" in f.detail for f in ci))
        sci = screen_stats(paper("sci.xml", "GWAS hit (P = 2.8 × 10 −35) and p=10 −103."))
        self.assertEqual(sci, [])
        param = screen_stats(paper("par.xml", "translations corresponding to p = 6 rigid body parameters."))
        self.assertEqual(param, [])
        third = screen_stats(paper("fr.xml", "roughly 1/3 (32.4%) of proviruses were defective."))
        self.assertEqual(third, [])
        thousands = screen_stats(
            paper("th.xml", "DALYs per year [95%CI 410 to 1,070] nationally.")
        )
        self.assertEqual(thousands, [])


class ReuseTests(unittest.TestCase):
    def test_shared_run_without_shared_authors(self) -> None:
        passage = " ".join([f"word{i}" for i in range(50)])
        a = paper("a.xml", f"Intro {passage} end", authors={"smith|j"})
        b = paper("b.xml", f"Other {passage} tail", authors={"lee|a"})
        flags = screen_reuse([a, b], width=40)
        self.assertEqual(len(flags), 1)
        self.assertEqual({flags[0].filename, flags[0].extra}, {"a.xml", "b.xml"})
        boiler = (
            "role of the funding source the funders of the study had no role in "
            "study design data collection data analysis data interpretation or "
            "writing of the report the corresponding author had full access to "
            "all the data in the study and had final responsibility for the decision"
        )
        b1 = paper("c.xml", boiler, authors={"aa|a"})
        b2 = paper("d.xml", boiler, authors={"bb|b"})
        self.assertEqual(screen_reuse([b1, b2], width=40), [])

    def test_same_authors_not_flagged(self) -> None:
        passage = " ".join([f"word{i}" for i in range(50)])
        a = paper("a.xml", passage, authors={"smith|j"})
        b = paper("b.xml", passage, authors={"smith|j", "lee|a"})
        self.assertFalse(authors_disjoint(a, b))
        self.assertEqual(screen_reuse([a, b], width=40), [])


if __name__ == "__main__":
    unittest.main()
