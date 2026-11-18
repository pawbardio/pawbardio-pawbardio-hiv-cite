# Verified flags

Spot-check of the flags in `model_flags.md` against the corresponding sentences in `fulltexts/*.xml`. No new full-paper reads. The audit counted “8 flags in 6 papers”; the file has 9 reason blocks (Murray has two).

## 1. `2020_Cao_A_Trial_of_Lopinavir_Ritonavir_in.xml` — ITT hazard ratio

Quote: “Treatment with lopinavir–ritonavir was not associated with a difference from standard care in the time to clinical improvement (hazard ratio for clinical improvement, 1.24; 95% confidence interval [CI], 0.90 to 1.72).” Results: “hazard ratio for clinical improvement, 1.31; 95% confidence interval [CI], 0.95 to 1.85; P=0.09.” Table 3: “1.31 (0.95 to 1.80).”
The same ITT primary endpoint is printed three ways. Modified ITT is a fourth figure (HR 1.39; 1.00 to 1.91) and does not explain the abstract.
**confirmed inconsistency**

## 2. `2020_Cao_A_Trial_of_Lopinavir_Ritonavir_in.xml` — day-28 RNA

Quote: “The percentage of patients with detectable viral RNA for SARS-CoV-2 was similar in the lopinavir–ritonavir group and the standard-care group on any sampling day (day 5, 34.5% vs. 32.9%; day 10, 50.0% vs. 48.6%; day 14, 55.2% vs. 57.1%; day 21, 58.6% vs. 58.6%; and day 28, 60.3% vs. 58.6%) (Table S2).”
Quote: “SARS-CoV-2 RNA was still detected in 40.7% of the patients in the lopinavir–ritonavir group at end of the trial (day 28).” Also: “approximately 45% and 40% of the patients in lopinavir–ritonavir group had positive RNA detection by throat swabs on day 14 and day 28, respectively.”
As written, day-28 “detectable” 60.3% contradicts “still detected” 40.7% in the same arm. The pair are near-complements (60.3% + 40.7% ≈ 101%; day 14: 55.2% + ~45% ≈ 100%), so one series is likely the negative-PCR rate mislabeled.
**confirmed inconsistency**

## 3. `2020_Cao_A_Trial_of_Lopinavir_Ritonavir_in.xml` — glucocorticoids

Quote: “During the trial, systemic glucocorticoids were administered in 33.0% of the patients in the lopinavir–ritonavir group and in 35.7% of those in the standard-care group.”
Table 2: “Glucocorticoid therapy 67 (33.7) 32 (32.3) 35 (35.0)” with N=99 and N=100. 32/99 = 32.3%; 35/100 = 35.0%. Neither 33.0% nor 35.7% matches those counts.
**confirmed inconsistency**

## 4. `2011_Cohen_Prevention_of_HIV_1_Infection_with.xml` — 66% second-line

Quote: “Virologic failure was observed in 45 of 886 participants (5%) in the early-therapy group and in 5 of 184 participants in the delayed-therapy group who initiated antiretroviral therapy (3%) (P = 0.23). Of all treated participants, 66% initiated a second-line regimen.”
Treated = 886 + 184 = 1,070; failures = 50. Methods say second-line was for virologic failure. 66% of 1,070 is ~706 people; 66% appears once in this XML and has no matching numerator.
**confirmed inconsistency**

## 5. `2005_Auvert_Randomized_Controlled_Intervention_Trial_of_Male.xml` — percent signs on RR CIs

Quote: “There were 20 HIV infections (incidence rate = 0.85 per 100 person-years) in the intervention group and 49 (2.1 per 100 person-years) in the control group, corresponding to an RR of 0.40 (95% CI: 0.24%–0.68%; p < 0.001).”
Quote: “with an adjusted relative risk of 0.42 (95% CI: 0.34%–0.54%)”
The RR 0.40 is consistent with 20 vs 49 infections; the following sentence correctly gives protection as 60% (32%–76%). The % signs on the ratio CIs are unit errors, not a wrong RR.
**confirmed inconsistency**

## 6. `2012_Baeten_Antiretroviral_Prophylaxis_for_HIV_Prevention_in.xml` — 29 vs 30 infections

Quote: “Of 82 post-randomization HIV-1 infections, 17 were among those assigned TDF (incidence 0.65 per 100 person-years), 13 among those assigned FTC/TDF (incidence 0.50 per 100 person-years), and 52 among those assigned placebo”
Quote: “Among 29 subjects on the TDF and FTC/TDF arms who acquired HIV-1, 31% had tenofovir detected in a plasma sample at the seroconversion visit”
17 + 13 = 30 active-arm infections, then a 29-subject plasma analysis. This XML does not say why one person is omitted (Table S10 is not in the file).
**needs human check**

## 7. `2017_Rajasingham_Global_burden_of_disease_of_HIV.xml` — 15% of AIDS deaths

Quote: “In 2013, there were an estimated 1·4 million (range 1·1–1·6) AIDS-related deaths globally, per UNAIDS estimates.”
Quote: “Annual global deaths from cryptococcal meningitis were estimated at 181 100 (95% CI 119 400–234 300) … Globally, cryptococcal meningitis was responsible for 15% of AIDS-related deaths (95% CI 10–19).”
181 100 / 1.4 million = 12.9%; 181 100 / 1.1 million = 16.5%. The printed 15% (10–19) does not follow from either AIDS-death figure given in this XML.
**confirmed inconsistency**

## 8. `2015_Murray_Circulating_microRNAs_in_Sera_Correlate_with.xml` — inverted IQR

Quote (Table 4, column “n, Median (IQR)”, miR-150 cases): “126, 4.48 (4.48, 3.35)”
The control row on the same miRNA is a valid IQR: “246, 4.55 (3.25, 5.58)”. For cases the second bound 3.35 is below the median 4.48, which cannot be an IQR as written.
**confirmed inconsistency**

## 9. `2015_Murray_Circulating_microRNAs_in_Sera_Correlate_with.xml` — miR-245 vs miR-145

Quote (S2 Fig caption): “Only MiRs -31, -245, -150 and -223 showed significant correlation with nadir CD4+ T cell number.”
Quote (results): “expression of miRs -31 (r = 0.12), -150 (r = 0.10), -223 (r = 0.13) as well as miR-145 (r = 0.13) correlated with nadir CD4+ T cell counts”
Abstract and discussion name miR-145, not miR-245. The supporting caption disagrees with the paper’s own results.
**confirmed inconsistency**
