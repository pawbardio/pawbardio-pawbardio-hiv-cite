# HIV/AIDS papers from OpenAlex — top 200 by citations

Pulled **2026-11-18 01:41 UTC** from the [OpenAlex Works API](https://docs.openalex.org/).

## Query

- Publication years: **2005–2026**
- Sort: `cited_by_count:desc`
- Concepts (OR): `C3013748606, C2780195530, C2777583353, C2910359755, C2778451633, C2910020833, C2992699665, C2910823671, C2908958731, C2909828532, C2909201284, C2779898580, C2779127605`
- Topics (OR): `T10112, T10082, T10526, T11860, T11655, T14334, T13761, T13586`
- Combined with a union of two requests (OpenAlex cannot OR across attributes).
- Topic side uses `primary_topic.id`. Concept side keeps a work only when an HIV/AIDS concept has score > 0 (the API's `concepts.id` filter otherwise returns leftover score-0 tags on unrelated high-cite papers).

## Coverage of the ranking pool

- Works matching the **concept** filter: **491,276**
- Works matching the **primary topic** filter: **344,584**
- Papers considered before the top-200 cut: **at least 491,276** and **at most 835,860** (union of the two API filters; exact unique count would require paging the full ~0.3–0.7M-work sets).
- Candidate records downloaded: **1,200** (78 dropped as score-0 HIV concept tags with no HIV/AIDS primary topic; 322 collapsed as DOI/title duplicates).
- Rows in the CSV: **200**

## Among the 200

- Open access (`is_oa=true`): **136** (68.0%)
- With an OA / full-text URL: **136** (68.0%)
- With a PMCID: **115** (57.5%)
- Open full text **or** PMCID: **136** (68.0%)
- Truncated abstract present: **135** (67.5%)
- Publication years in the list: **2005–2022**
- Citation counts: **983–7628** (median 1436)

## Rate-limit and coverage notes

- HTTP requests this run: **8**; 429 responses: **0**; retries: **0**.
- The client uses the OpenAlex polite pool (`mailto` + identifying User-Agent) and waits ~120 ms between requests. Without an API key, OpenAlex currently shares a small free daily budget per IP; this export is a handful of cheap `/works` calls and stays well under that.
- API notice: No API key, so this request shares one free daily budget ($0.10) with everyone on your network's IP address. The mailto parameter doesn't raise this limit. Get a free key with its own $1/day at https://openalex.org/settings/api and add api_key=YOUR_KEY to your requests. An AI agent can get one for its user in one call: POST https://api.openalex.org/api-keys with {"email": "<your user's email>"}; we email them a link, and the key works once they click it. Docs for agents: https://help.openalex.org/llms.txt
- OpenAlex concepts and topics are classifier tags, not a MeSH explosion. Papers about HIV that were never tagged will be missing; papers tagged HIV/AIDS that are only tangentially related can appear.
- Abstracts arrive as an inverted index and are reconstructed, then cut to 500 characters. Some works have no abstract in OpenAlex.
- `oa_url` is the OpenAlex open-access URL when present, otherwise the best OA PDF / landing page. Links can rot; PMCID is the more stable full-text handle when it exists.
- 2026 is the current/upcoming calendar year, so that slice is incomplete. Recent years (2023–2026) also rarely reach a top-200 citation cutoff; this export’s years stop at 2022.
- Citation counts are OpenAlex `cited_by_count` (cross-publisher), not Web of Science or Scopus, and they move as the graph updates.

## Top 10 (preview)

| # | Year | Cites | OA | PMCID | Title |
|---|------|------:|----|-------|-------|
| 1 | 2011 | 7628 | yes | PMC3200068 | Prevention of HIV-1 Infection with Early Antiretroviral Therapy |
| 2 | 2010 | 5608 | yes | PMC3079639 | Preexposure Chemoprophylaxis for HIV Prevention in Men Who Have Sex with Men |
| 3 | 2020 | 5499 | yes | PMC7121492 | A Trial of Lopinavir–Ritonavir in Adults Hospitalized with Severe Covid-19 |
| 4 | 2006 | 5450 | yes |  | Development of a simple noninvasive index to predict significant fibrosis in patients with HIV/HCV coinfection†‡ |
| 5 | 2006 | 3986 | no |  | Microbial translocation is a cause of systemic immune activation in chronic HIV infection |
| 6 | 2017 | 3902 | yes | PMC6945892 | Can Treatment Adherence Be Improved by Using Rubin's Four Tendencies Framework to Understand a Patient's Response to Expectations |
| 7 | 2007 | 3623 | yes | PMC7119119 | 2007 Guideline for Isolation Precautions: Preventing Transmission of Infectious Agents in Health Care Settings |
| 8 | 2012 | 3597 | yes | PMC3770474 | Antiretroviral Prophylaxis for HIV Prevention in Heterosexual Men and Women |
| 9 | 2006 | 3591 | no |  | Youth risk behavior surveillance--United States, 2005. |
| 10 | 2021 | 3547 | yes | PMC8344968 | Sexually Transmitted Infections Treatment Guidelines, 2021 |
