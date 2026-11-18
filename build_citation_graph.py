#!/usr/bin/env python3
"""
Build a single-file 3D citation graph from data/hiv_aids_top200.csv.

No citation-edge file ships with this repo, so links are a sparse
year-proximity stand-in (k nearest papers within a year window, with
log-citation distance as a weak co-citation proxy).

    python3 build_citation_graph.py
"""

from __future__ import annotations

import csv
import html
import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CSV_PATH = ROOT / "data" / "hiv_aids_top200.csv"
FLAGS_PATH = ROOT / "model_flags.md"
LOG_PATH = ROOT / "download_log.csv"
EDGES_PATH = ROOT / "data" / "citation_edges.csv"
OUT_PATHS = [
    ROOT / "citation_graph.html",
    ROOT / "graph" / "index.html",
]

YEAR_WINDOW = 4
K_NEIGHBORS = 3


def flagged_filenames(text: str) -> set[str]:
    """Filenames under ## Flags, before ## Nothing clear found."""
    flags_block = text.split("## Flags", 1)[-1]
    flags_block = flags_block.split("## Nothing clear found", 1)[0]
    return set(re.findall(r"### `([^`]+\.xml)`", flags_block))


def filename_to_title(log_path: Path) -> dict[str, str]:
    if not log_path.exists():
        return {}
    mapping: dict[str, str] = {}
    with log_path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            name = (row.get("filename") or "").strip()
            title = (row.get("title") or "").strip()
            if name and title:
                mapping[name] = title
    return mapping


def load_papers(csv_path: Path) -> list[dict]:
    papers: list[dict] = []
    with csv_path.open(newline="", encoding="utf-8") as fh:
        for i, row in enumerate(csv.DictReader(fh)):
            year = int(row["publication_year"])
            cites = int(row["cited_by_count"])
            papers.append(
                {
                    "id": row.get("openalex_id") or f"p{i}",
                    "title": row["title"].strip(),
                    "year": year,
                    "cites": cites,
                    "authors": (row.get("primary_authors") or "").strip(),
                    "doi": (row.get("doi") or "").strip(),
                }
            )
    return papers


def load_real_edges(path: Path, ids: set[str]) -> list[dict] | None:
    if not path.exists():
        return None
    links: list[dict] = []
    seen: set[frozenset[str]] = set()
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            src = (row.get("source") or row.get("from") or "").strip()
            tgt = (row.get("target") or row.get("to") or "").strip()
            if src not in ids or tgt not in ids or src == tgt:
                continue
            key = frozenset((src, tgt))
            if key in seen:
                continue
            seen.add(key)
            links.append({"source": src, "target": tgt})
    return links


def year_proximity_edges(papers: list[dict]) -> list[dict]:
    """Sparse undirected k-NN in (year, log-citations)."""
    n = len(papers)
    logs = [math.log10(max(p["cites"], 1)) for p in papers]
    pairs: set[frozenset[int]] = set()
    for i, a in enumerate(papers):
        scored: list[tuple[float, int]] = []
        for j, b in enumerate(papers):
            if i == j:
                continue
            dy = abs(a["year"] - b["year"])
            if dy > YEAR_WINDOW:
                continue
            dc = abs(logs[i] - logs[j])
            scored.append((dy + 0.35 * dc, j))
        scored.sort()
        for _, j in scored[:K_NEIGHBORS]:
            pairs.add(frozenset((i, j)))
    # Isolated years: still attach each paper to its nearest neighbor.
    for i, a in enumerate(papers):
        if any(i in pair for pair in pairs):
            continue
        nearest = min(
            (j for j in range(n) if j != i),
            key=lambda j: (
                abs(a["year"] - papers[j]["year"]),
                abs(logs[i] - logs[j]),
            ),
        )
        pairs.add(frozenset((i, nearest)))
    return [
        {"source": papers[i]["id"], "target": papers[j]["id"]}
        for i, j in (sorted(p) for p in pairs)
    ]


def graph_payload(papers: list[dict], flagged_titles: set[str], links: list[dict], placeholder: bool) -> dict:
    flagged_lower = {t.casefold() for t in flagged_titles}
    nodes = []
    for p in papers:
        nodes.append(
            {
                **p,
                "title": html.escape(p["title"], quote=False),
                "authors": html.escape(p["authors"], quote=False),
                "flagged": p["title"].casefold() in flagged_lower,
            }
        )
    return {
        "placeholder": placeholder,
        "nodes": nodes,
        "links": links,
    }


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>HIV/AIDS citation field</title>
  <style>
    :root {
      --bg: #07080b;
      --ink: #d7dbe3;
      --mute: #7c8494;
      --line: #1c212c;
      --red: #e23d3d;
    }
    html, body { margin: 0; height: 100%; background: var(--bg); color: var(--ink);
      font: 13px/1.4 "IBM Plex Sans", "Segoe UI", sans-serif; overflow: hidden; }
    #graph { position: absolute; inset: 0; }
    .hud {
      position: absolute; z-index: 2; pointer-events: none;
      text-shadow: 0 1px 8px #000;
    }
    .hud h1 {
      margin: 0 0 6px; font: 600 13px/1.3 "IBM Plex Sans", sans-serif;
      letter-spacing: 0.04em; text-transform: uppercase; color: #e8ecf2;
    }
    .hud p { margin: 0 0 4px; color: var(--mute); max-width: 28rem; }
    .topleft { top: 22px; left: 24px; }
    .bottomleft { bottom: 22px; left: 24px; color: var(--mute); }
    .topright { top: 22px; right: 24px; text-align: right; }
    .legend-row { display: flex; align-items: center; justify-content: flex-end; gap: 8px; margin: 3px 0; color: var(--mute); }
    .swatch { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
    .swatch.red { background: var(--red); box-shadow: 0 0 8px #e23d3d88; }
    .swatch.year { background: linear-gradient(90deg, #4a7ea8, #c9a46a); width: 28px; height: 6px; border-radius: 1px; }
    .years {
      position: absolute; left: 18px; top: 50%; transform: translateY(-50%);
      z-index: 2; pointer-events: none; color: #4e5666; font-size: 11px;
      letter-spacing: 0.08em; text-align: right; width: 36px;
    }
    .years span { display: block; margin: 22px 0; }
    .graph-tooltip {
      font: 12px/1.45 "IBM Plex Sans", "Segoe UI", sans-serif !important;
      background: #0e1218ee !important; color: #e8ecf2 !important;
      border: 1px solid #2a3140 !important; padding: 8px 10px !important;
      border-radius: 2px !important; max-width: 22rem;
    }
  </style>
</head>
<body>
  <div id="graph"></div>
  <div class="hud topleft">
    <h1>HIV / AIDS · citation field</h1>
    <p>200 papers, OpenAlex cited-by rank, 2005–2026. Height is year. Volume is citations.</p>
    <p id="link-note"></p>
  </div>
  <div class="hud topright">
    <div class="legend-row"><span class="swatch red"></span> flagged in model audit</div>
    <div class="legend-row"><span class="swatch year"></span> earlier → later</div>
    <div class="legend-row">click a node · neighbors hold</div>
  </div>
  <div class="years" id="year-scale"></div>
  <div class="hud bottomleft">drag to orbit · scroll to zoom · click empty space to clear</div>

  <script src="https://unpkg.com/3d-force-graph@1.73.3/dist/3d-force-graph.min.js"></script>
  <script>
    const DATA = __DATA__;
    const graphEl = document.getElementById("graph");
    const years = DATA.nodes.map(n => n.year);
    const yMin = Math.min(...years);
    const yMax = Math.max(...years);
    const cites = DATA.nodes.map(n => n.cites);
    const cMin = Math.log10(Math.max(Math.min(...cites), 1));
    const cMax = Math.log10(Math.max(...cites, 1));
    const Y_SPAN = 420;

    document.getElementById("link-note").textContent = DATA.placeholder
      ? "Lines are year-proximity stand-ins. No citation-edge file was present."
      : "Lines are recorded citations.";

    const scale = document.getElementById("year-scale");
    for (const y of [yMax, Math.round((yMin + yMax) / 2), yMin]) {
      const s = document.createElement("span");
      s.textContent = y;
      scale.appendChild(s);
    }

    DATA.nodes.forEach(n => {
      n.fy = ((n.year - yMin) / Math.max(yMax - yMin, 1) - 0.5) * Y_SPAN;
    });

    let focus = null;
    const neighborOf = new Map();
    DATA.nodes.forEach(n => neighborOf.set(n.id, new Set([n.id])));
    DATA.links.forEach(l => {
      neighborOf.get(l.source).add(l.target);
      neighborOf.get(l.target).add(l.source);
    });

    function yearTint(year) {
      const t = (year - yMin) / Math.max(yMax - yMin, 1);
      const r = Math.round(74 + t * 127);
      const g = Math.round(126 - t * 22);
      const b = Math.round(168 - t * 62);
      return [r, g, b];
    }
    function brightness(cites) {
      const t = (Math.log10(Math.max(cites, 1)) - cMin) / Math.max(cMax - cMin, 1e-6);
      return 0.38 + 0.62 * t;
    }
    function mix(rgb, b, dim) {
      const k = b * dim;
      return `rgb(${Math.round(rgb[0]*k)}, ${Math.round(rgb[1]*k)}, ${Math.round(rgb[2]*k)})`;
    }
    function inFocus(id) {
      if (!focus) return true;
      return neighborOf.get(focus).has(id);
    }
    function nid(end) {
      return typeof end === "object" ? end.id : end;
    }
    function nodeColor(n) {
      const dim = inFocus(n.id) ? 1 : 0.16;
      if (n.flagged) return mix([226, 61, 61], brightness(n.cites), dim);
      return mix(yearTint(n.year), brightness(n.cites), dim);
    }
    function linkColor(l) {
      const s = nid(l.source), t = nid(l.target);
      const on = !focus || (inFocus(s) && inFocus(t) && (s === focus || t === focus));
      return on ? "rgba(196,204,216,0.55)" : "rgba(80,90,108,0.08)";
    }
    function linkWidth(l) {
      const s = nid(l.source), t = nid(l.target);
      const on = focus && (s === focus || t === focus);
      return on ? 0.9 : 0.25;
    }

    const Graph = ForceGraph3D()(graphEl)
      .graphData(DATA)
      .backgroundColor("#07080b")
      .showNavInfo(false)
      .nodeId("id")
      .nodeVal(n => Math.pow(n.cites, 0.55))
      .nodeRelSize(2.4)
      .nodeResolution(12)
      .nodeOpacity(0.95)
      .nodeColor(nodeColor)
      .nodeLabel(n => {
        const flag = n.flagged ? "<div style='color:#e23d3d;margin-top:4px'>flagged · model audit</div>" : "";
        const by = n.authors ? `<div style="color:#8b93a3">${n.authors}</div>` : "";
        return `<div class="t"><strong>${n.title}</strong></div>
                ${by}
                <div style="color:#b7bec9;margin-top:4px">${n.year} · ${n.cites.toLocaleString()} citations</div>
                ${flag}`;
      })
      .linkColor(linkColor)
      .linkOpacity(1)
      .linkWidth(linkWidth)
      .linkDirectionalParticles(0)
      .warmupTicks(60)
      .cooldownTicks(140)
      .enableNodeDrag(false)
      .onNodeClick(node => {
        focus = (focus === node.id) ? null : node.id;
        Graph.nodeColor(nodeColor).linkColor(linkColor).linkWidth(linkWidth);
      })
      .onBackgroundClick(() => {
        focus = null;
        Graph.nodeColor(nodeColor).linkColor(linkColor).linkWidth(linkWidth);
      });

    Graph.d3Force("charge").strength(-85);
    Graph.d3Force("link").distance(38).strength(0.35);
    Graph.cameraPosition({ x: 0, y: 40, z: 680 }, { x: 0, y: 0, z: 0 }, 800);
  </script>
</body>
</html>
"""


def build() -> dict:
    papers = load_papers(CSV_PATH)
    flags_md = FLAGS_PATH.read_text(encoding="utf-8") if FLAGS_PATH.exists() else ""
    titles = {
        filename_to_title(LOG_PATH).get(name, "")
        for name in flagged_filenames(flags_md)
    }
    titles.discard("")
    ids = {p["id"] for p in papers}
    real = load_real_edges(EDGES_PATH, ids)
    if real:
        links, placeholder = real, False
    else:
        links, placeholder = year_proximity_edges(papers), True
    payload = graph_payload(papers, titles, links, placeholder)
    html = HTML_TEMPLATE.replace("__DATA__", json.dumps(payload, ensure_ascii=False))
    for path in OUT_PATHS:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html, encoding="utf-8")
    return {
        "papers": len(papers),
        "links": len(links),
        "flagged": sum(1 for n in payload["nodes"] if n["flagged"]),
        "placeholder": placeholder,
        "outputs": [str(p.relative_to(ROOT)) for p in OUT_PATHS],
    }


if __name__ == "__main__":
    info = build()
    print(
        f"{info['papers']} nodes, {info['links']} links, "
        f"{info['flagged']} flagged, placeholder={info['placeholder']}"
    )
    print("wrote", ", ".join(info["outputs"]))
