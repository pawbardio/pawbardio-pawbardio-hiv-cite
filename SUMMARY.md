# Screening summary

Rolled up from `free_screens.md` (all 92 XML full texts) and `model_flags.md` (25 most-cited complete XMLs). No new model reads.

## Free deterministic screens (`free_screens.md`)

Ran 2026-11-18 03:01 UTC on every `.xml` in `fulltexts/`.

| Check | Count |
|---|---:|
| papers screened | 92 |
| retractions | 0 |
| text-reuse pairs | 0 |
| language flags | 0 |
| statistical flags | 1 |

Retractions used OpenAlex `is_retracted` for 91/91 DOIs. OpenRetractions.com was not reachable.

**Statistical flag**

- `2014_Grant_Uptake_of_pre_exposure_prophylaxis_sexual.xml` — n-of-m percent mismatch: 1125/1603 (76%) (expected ~70.2%).

That is the only file that triggered a free-screen flag.

## Model audit (`model_flags.md`)

One pass each on the 25 most-cited complete JATS XMLs in `fulltexts/`, ranked by OpenAlex `cited_by_count`. Papers were treated as data. The audit looked only for numerical inconsistencies, statistical reporting problems, claims not supported by the paper’s own data or methods, and citations that appear to misstate the cited work. Guideline-length papers were read from structured extracts; trial papers from the same extracts in full.

**Token cost.** The host does not expose per-call token usage. Approximate input: ~853,000 characters of extracted text (~213,000 tokens at 4 characters/token). Combined XML of the 25 files is ~11.2 million characters; four guideline XMLs exceed 1 million characters each and were not re-read as raw XML.

**Result.** 8 flags in 6 papers. Nothing clear in the other 19.

### Flags

**`2020_Cao_A_Trial_of_Lopinavir_Ritonavir_in.xml` (3)**

1. Same ITT primary-endpoint hazard ratio reported three ways: abstract 1.24 (0.90–1.72); results 1.31 (0.95–1.85); Table 3 1.31 (0.95–1.80).
2. Day-28 detectable RNA in the lopinavir–ritonavir arm is 60.3% in results and 40.7% (then “approximately … 40%”) in the discussion, with no reconciliation.
3. Glucocorticoid use stated as 33.0% vs 35.7%; Table 2 is 32/99 (32.3%) vs 35/100 (35.0%).

**`2011_Cohen_Prevention_of_HIV_1_Infection_with.xml` (1)**

- “Of all treated participants, 66% initiated a second-line regimen” after 50 virologic failures among 1,070 treated (~5%). The paper does not give a numerator that makes 66% of all treated participants.

**`2005_Auvert_Randomized_Controlled_Intervention_Trial_of_Male.xml` (1)**

- Rate-ratio CIs labeled with percent signs: RR 0.40 (95% CI: 0.24%–0.68%), and a cited meta-analysis RR 0.42 (95% CI: 0.34%–0.54%). Those bounds are ratios, not percentages.

**`2012_Baeten_Antiretroviral_Prophylaxis_for_HIV_Prevention_in.xml` (1)**

- 17 + 13 = 30 post-randomization infections on the active arms, then a plasma-tenofovir analysis of 29 subjects, with no stated reason for the omitted one.

**`2017_Rajasingham_Global_burden_of_disease_of_HIV.xml` (1)**

- 181,100 cryptococcal deaths claimed as 15% of AIDS-related deaths. 181,100 / 1.4 million = 12.9%; 181,100 / 1.1 million = 16.5%. Neither of the paper’s own AIDS-death figures yields 15%.

**`2015_Murray_Circulating_microRNAs_in_Sera_Correlate_with.xml` (2)**

1. Table 4 miR-150 case IQR `4.48 (4.48, 3.35)` has an upper bound below the median.
2. Supporting caption names miR-245 among nadir-CD4 correlates; results name miR-145.

### Nothing clear (19 papers)

`2010_Grant_Preexposure_Chemoprophylaxis_for_HIV_Prevention_in.xml`, `2017_Kirk_Can_Treatment_Adherence_Be_Improved_by.xml`, `2007_Siegel_2007_Guideline_for_Isolation_Precautions_Preventing.xml`, `2021_Workowski_Sexually_Transmitted_Infections_Treatment_Guidelines_2021.xml`, `2009_Pappas_Clinical_Practice_Guidelines_for_the_Management.xml`, `2022_Coleman_Standards_of_Care_for_the_Health.xml`, `2015_INSIGHT_START_Study_Group_Initiation_of_Antiretroviral_Therapy_in_Early.xml`, `2010_Perfect_Clinical_Practice_Guidelines_for_the_Management.xml`, `2010_Karim_Effectiveness_and_Safety_of_Tenofovir_Gel.xml`, `2013_Deeks_The_end_of_AIDS_HIV_infection.xml`, `2012_Kuybeda_A_collaborative_framework_for_3D_alignment.xml`, `2015_McCormack_Pre_exposure_prophylaxis_to_prevent_the.xml`, `2011_Workowski_Sexually_Transmitted_Diseases_Treatment_Guidelines_2010.xml`, `2015_Hughto_Transgender_stigma_and_health_A_critical.xml`, `2012_Haynes_Immune_Correlates_Analysis_of_an_HIV.xml`, `2008_Buchbinder_Efficacy_assessment_of_a_cell_mediated.xml`, `2009_Chomont_HIV_reservoir_size_and_persistence_are.xml`, `2019_Rowley_Chlamydia_gonorrhoea_trichomoniasis_and_syphilis_global.xml`, `2016_Cohen_Antiretroviral_Therapy_for_the_Prevention_of.xml`.

Guideline extracts were truncated relative to the raw XML. Citation-by-citation checking of guideline reference lists was not done. Empty `[]` / `(REF)` markers in XMLs are leftover stripped cross-references, not chatbot language.

## Combined count

| Source | Papers | Flags |
|---|---:|---:|
| Free screens (92 XML) | 92 | 1 statistical (Grant 2014 uptake paper; not in the model-audit 25) |
| Model audit (top 25 complete XML) | 25 | 8 in 6 papers |
| Overlap of those two sets | — | none |
