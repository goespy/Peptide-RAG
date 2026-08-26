# QA Query-Wording Research

Status: working research artifact; not an approved QA oracle

Collected: 2026-08-13 (America/New_York)

## Purpose

Use realistic public-facing search language to shape the wording of the QA
oracle. This research is used only to identify information needs. PubMed
records in the frozen corpus remain the sole source for acceptable answers,
answerability labels, and evidence spans.

## Source limitation

Direct Google collection was attempted twice and blocked by Google's
"unusual traffic" CAPTCHA. No CAPTCHA was bypassed, and no results are labeled
as Google autocomplete, People Also Ask, related searches, or search-volume
data. The fallback below uses general web-search result patterns. It supports
realistic wording, but it does not establish query popularity or rank.

## Recorded fallback searches

- `BPC-157 common questions benefits healing safety`
- `GHK-Cu common questions hair growth skin benefits`
- `TB-500 common questions healing recovery safety`
- `ipamorelin common questions growth hormone benefits safety`
- `tesamorelin common questions belly fat benefits side effects`
- `Epitalon common questions anti aging lifespan sleep`
- `MOTS-c common questions weight loss exercise metabolism`
- `PT-141 common questions libido sexual dysfunction safety`

## Recurring information-needs observed

| Topic | Candidate user language | Oracle constraint |
|---|---|---|
| BPC-157 | tissue or tendon healing; gut or ulcer effects; human evidence and safety | distinguish animal findings from human evidence |
| GHK/GHK-Cu | hair regrowth; skin or wound repair | distinguish combination-product and animal evidence from GHK-Cu-alone human evidence |
| TB-500 | injury, tendon, or wound healing; human evidence; relationship to thymosin beta-4 | do not transfer every thymosin beta-4 finding to TB-500 |
| Ipamorelin | growth-hormone release; muscle or body-composition claims; safety | do not treat related secretagogues as ipamorelin evidence |
| Tesamorelin | belly-fat reduction; general weight loss; side effects | preserve the HIV-lipodystrophy indication and population |
| Epitalon | longevity or lifespan; sleep, melatonin, or circadian effects | identify the tested species and avoid human anti-aging claims |
| MOTS-c | weight loss or metabolism; exercise performance; longevity | identify animal versus human results |
| PT-141 | libido; erectile dysfunction; who it was studied in; side effects | distinguish study populations and approved-use claims from corpus evidence |

## Example sources that shaped the intent categories

- [AAMC: questions to ask about peptides](https://www.aamc.org/news/10-questions-ask-your-doctor-about-peptides)
- [OPSS: BPC-157 claims and evidence limitations](https://www.opss.org/article/bpc-157-prohibited-peptide-and-unapproved-drug-found-health-and-wellness-products)
- [Healthline: copper peptides for skin and hair](https://www.healthline.com/health/copper-peptides)
- [MedlinePlus: tesamorelin drug information](https://medlineplus.gov/druginfo/meds/a611035.html)
- [Nature Communications: MOTS-c, exercise, and physical decline](https://www.nature.com/articles/s41467-020-20790-0)
- [PubMed: PT-141 study in healthy men and patients with erectile dysfunction](https://pubmed.ncbi.nlm.nih.gov/14999221/)

## Decision rule

A candidate question enters `data/qa_draft.json` only after:

1. Its wording represents one of the recorded public-facing information needs.
2. The frozen corpus contains sufficient direct evidence, or the case is
   deliberately labeled unanswerable.
3. Exact evidence text, character offsets, PMID, and text hash validate.
4. The project owner explicitly approves the case.

## Oracle question mix

The 15 answerable cases intentionally combine two levels of difficulty:

- 7 broad, user-oriented questions resembling realistic search or application
  input.
- 8 specific research questions that test whether the system preserves study
  design, species, population, mechanism, numerical results, and limitations.

The five unanswerable cases use realistic claim-style wording. This mix keeps
the oracle representative of the public search experience without discarding
the project's harder evidence-comprehension tests.
