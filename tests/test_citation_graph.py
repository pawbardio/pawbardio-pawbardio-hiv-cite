"""Flag parsing and placeholder edges for the 3D citation graph."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from build_citation_graph import (
    flagged_filenames,
    graph_payload,
    year_proximity_edges,
)


FLAGS_SAMPLE = """
## Flags

### `2020_Cao_A_Trial_of_Lopinavir_Ritonavir_in.xml`

**Reason.** mismatch

### `2011_Cohen_Prevention_of_HIV_1_Infection_with.xml`

**Reason.** mismatch

## Nothing clear found

### `2010_Grant_Preexposure_Chemoprophylaxis_for_HIV_Prevention_in.xml`
"""


class FlagParseTests(unittest.TestCase):
    def test_stops_before_nothing_clear(self) -> None:
        names = flagged_filenames(FLAGS_SAMPLE)
        self.assertEqual(
            names,
            {
                "2020_Cao_A_Trial_of_Lopinavir_Ritonavir_in.xml",
                "2011_Cohen_Prevention_of_HIV_1_Infection_with.xml",
            },
        )


class EdgeTests(unittest.TestCase):
    def test_knn_is_undirected_and_sparse(self) -> None:
        papers = [
            {"id": f"p{i}", "title": f"T{i}", "year": 2005 + i, "cites": 1000 - i * 10}
            for i in range(12)
        ]
        links = year_proximity_edges(papers)
        keys = {frozenset((l["source"], l["target"])) for l in links}
        self.assertEqual(len(keys), len(links))
        self.assertLess(len(links), 12 * 3)
        self.assertGreaterEqual(len(links), 11)

    def test_flag_on_matching_title(self) -> None:
        papers = [
            {"id": "a", "title": "Alpha", "year": 2011, "cites": 10, "authors": "", "doi": ""},
            {"id": "b", "title": "Beta", "year": 2012, "cites": 20, "authors": "", "doi": ""},
        ]
        payload = graph_payload(papers, {"Alpha"}, [], True)
        flags = {n["id"]: n["flagged"] for n in payload["nodes"]}
        self.assertTrue(flags["a"])
        self.assertFalse(flags["b"])


if __name__ == "__main__":
    unittest.main()
