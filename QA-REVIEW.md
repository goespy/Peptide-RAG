# QA Oracle Human Review

> **Candidate pool only — not approved.** Do not use these cases for RAG tuning or evaluation until the project owner records approval.

- Corpus SHA-256: `231E048971C34EF9203ED3BB20587DDE4C95141AC7EFD2746C85C078A844212C`
- Qrels v2 SHA-256: `B30E1B7868EFFB580155442917C2BB0105ECC00E13527A103F6325B6A2B32ED6`
- Development: `qa01`–`qa10`, `qa16`–`qa18` (10 answerable / 3 unanswerable)
- Holdout: `qa11`–`qa15`, `qa19`–`qa20` (5 answerable / 2 unanswerable)

## Review instructions

Read every cited abstract span. Approve, edit, or reject each case; verify that an answerable answer says no more than its support, and that an unanswerable case has no direct corpus evidence. Lexical absence checks are deterministic but not exhaustive.

## qa01 — answerable (development)

**Question:** BPC 157 liver necrosis rats?

- Decision: [ ] Approve  [ ] Edit  [ ] Reject
- Reviewer:
- Notes:

- Source: [PMID 7901724](https://pubmed.ncbi.nlm.nih.gov/7901724/)
- Acceptable answer: The hepatoprotective effects of a newly synthesized 15 amino acid fragment code named BPC 157 was evaluated in comparison with the reference standards (bromocriptine, amantadine and somatostatin) in various experimental models of liver injury in rats: 24 h-bile duct+hepatic artery ligation 48 h-restraint stress and CCl4 administration. BPC 157 administered either intragastrically or intraperitoneally, significantly prevented the development of liver necrosis or fatty changes in rats subjected to 24 h bile duct + hepatic artery ligation, 48 h-restraint stress, CCl4 treatment (1 ml/kg i.p., sacrifice 48 h thereafter).
- Exact support offsets: `0:624`; SHA-256: `A891A841311236641859062D005B13442FE0C33F2C14E097423FFF004BA4C2C6`

### Exact abstract support

The hepatoprotective effects of a newly synthesized 15 amino acid fragment code named BPC 157 was evaluated in comparison with the reference standards (bromocriptine, amantadine and somatostatin) in various experimental models of liver injury in rats: 24 h-bile duct+hepatic artery ligation 48 h-restraint stress and CCl4 administration. BPC 157 administered either intragastrically or intraperitoneally, significantly prevented the development of liver necrosis or fatty changes in rats subjected to 24 h bile duct + hepatic artery ligation, 48 h-restraint stress, CCl4 treatment (1 ml/kg i.p., sacrifice 48 h thereafter). 

## qa02 — answerable (development)

**Question:** GHK Cu cognitive decline neurodegeneration?

- Decision: [ ] Approve  [ ] Edit  [ ] Reject
- Reviewer:
- Notes:

- Source: [PMID 22666519](https://pubmed.ncbi.nlm.nih.gov/22666519/)
- Acceptable answer: We propose GHK tripeptide as a possible therapeutic agent against age-associated neurodegeneration and cognitive decline.
- Exact support offsets: `1269:1390`; SHA-256: `85187BC46DE03E7B6BDF67A4811F6F826B00AABC7DD9D85FA9453420FEF8F515`

### Exact abstract support

We propose GHK tripeptide as a possible therapeutic agent against age-associated neurodegeneration and cognitive decline.

## qa03 — answerable (development)

**Question:** thymosin beta 4 backbone conformations?

- Decision: [ ] Approve  [ ] Edit  [ ] Reject
- Reviewer:
- Notes:

- Source: [PMID 1304362](https://pubmed.ncbi.nlm.nih.gov/1304362/)
- Acceptable answer: The procedure is applied to the calculation of the local backbone conformations of myoglobin and lysozyme whose structures have been solved by X-ray analysis and thymosin beta 4, a polypeptide of 43 amino acid residues whose structure was recently investigated by NMR spectroscopy.
- Exact support offsets: `977:1259`; SHA-256: `1FD9FE1D923B920AF35E0D71C6E3B4D9AAF75CB6D7C37CF699F426D1D27DD8A8`

### Exact abstract support

The procedure is applied to the calculation of the local backbone conformations of myoglobin and lysozyme whose structures have been solved by X-ray analysis and thymosin beta 4, a polypeptide of 43 amino acid residues whose structure was recently investigated by NMR spectroscopy. 

## qa04 — answerable (development)

**Question:** ipamorelin oral bioavailability growth hormone?

- Decision: [ ] Approve  [ ] Edit  [ ] Reject
- Reviewer:
- Notes:

- Source: [PMID 9733495](https://pubmed.ncbi.nlm.nih.gov/9733495/)
- Acceptable answer: A new series of GH secretagogues derived from ipamorelin is described. In an attempt to obtain oral bioavailability, by reducing the size and the number of potential hydrogen-bonding sites of the compounds, a strategy using the peptidomimetic fragment 3-(aminomethyl)benzoic acid and sequential backbone N-methylations was applied.
- Exact support offsets: `0:332`; SHA-256: `C70BC1AB79A8EC878FF84BE2A3B073745A8902600148FB09593714310F149B99`

### Exact abstract support

A new series of GH secretagogues derived from ipamorelin is described. In an attempt to obtain oral bioavailability, by reducing the size and the number of potential hydrogen-bonding sites of the compounds, a strategy using the peptidomimetic fragment 3-(aminomethyl)benzoic acid and sequential backbone N-methylations was applied. 

## qa05 — answerable (development)

**Question:** tesamorelin HIV lipodystrophy clinical trials?

- Decision: [ ] Approve  [ ] Edit  [ ] Reject
- Reviewer:
- Notes:

- Source: [PMID 17086939](https://pubmed.ncbi.nlm.nih.gov/17086939/)
- Acceptable answer: Phase III clinical trials for the treatment of HIV-associated lipodystrophy and phase II clinical trials for sleep disorder, chronic obstructive pulmonary disorder, hip fracture and immune system dysfunction are underway. Phase II trials are also assessing the influenza vaccination immune response and cognitive effects of tesamorelin.
- Exact support offsets: `275:611`; SHA-256: `3E803681A700E542A24C1040623C2168D9665A7F89E69D88891D5990EF0D7338`

### Exact abstract support

Phase III clinical trials for the treatment of HIV-associated lipodystrophy and phase II clinical trials for sleep disorder, chronic obstructive pulmonary disorder, hip fracture and immune system dysfunction are underway. Phase II trials are also assessing the influenza vaccination immune response and cognitive effects of tesamorelin.

## qa06 — answerable (development)

**Question:** epitalon drosophila lifespan increase?

- Decision: [ ] Approve  [ ] Edit  [ ] Reject
- Reviewer:
- Notes:

- Source: [PMID 11087911](https://pubmed.ncbi.nlm.nih.gov/11087911/)
- Acceptable answer: The substance was added to the culture medium only at the developmental stage (from egg to larva). Epitalon significantly increased the lifespan (LS) of imagoes by 11-16% when applied at unprecedented low concentrations-from 0.001 x 10(-6) to 5 x 10(-6) wt.% of culture medium for males and from 0.01 x 10(-6) to 0.1 x 10(-6) wt.% of culture medium for females. The increase in LS did not depend on the substance dose.
- Exact support offsets: `147:566`; SHA-256: `F795E3299EAAA970DC25A31DA748F74B1DB4F13DB3F206958D822105C693BAC6`

### Exact abstract support

The substance was added to the culture medium only at the developmental stage (from egg to larva). Epitalon significantly increased the lifespan (LS) of imagoes by 11-16% when applied at unprecedented low concentrations-from 0.001 x 10(-6) to 5 x 10(-6) wt.% of culture medium for males and from 0.01 x 10(-6) to 0.1 x 10(-6) wt.% of culture medium for females. The increase in LS did not depend on the substance dose. 

## qa07 — answerable (development)

**Question:** MOTS c metabolic obesity insulin resistance?

- Decision: [ ] Approve  [ ] Edit  [ ] Reject
- Reviewer:
- Notes:

- Source: [PMID 25738459](https://pubmed.ncbi.nlm.nih.gov/25738459/)
- Acceptable answer: MOTS-c treatment in mice prevented age-dependent and high-fat-diet-induced insulin resistance, as well as diet-induced obesity. These results suggest that mitochondria may actively regulate metabolic homeostasis at the cellular and organismal level via peptides encoded within their genome.
- Exact support offsets: `721:1011`; SHA-256: `E13B71C9AC777990D6668813026CFF8816CC2B8A9DADF63112B580ABB994E422`

### Exact abstract support

MOTS-c treatment in mice prevented age-dependent and high-fat-diet-induced insulin resistance, as well as diet-induced obesity. These results suggest that mitochondria may actively regulate metabolic homeostasis at the cellular and organismal level via peptides encoded within their genome.

## qa08 — answerable (development)

**Question:** PT 141 melanocortin sexual dysfunction?

- Decision: [ ] Approve  [ ] Edit  [ ] Reject
- Reviewer:
- Notes:

- Source: [PMID 12851303](https://pubmed.ncbi.nlm.nih.gov/12851303/)
- Acceptable answer: The results suggest that PT-141 holds promise as a new treatment for sexual dysfunction.
- Exact support offsets: `681:769`; SHA-256: `6A964341B3EEE2E036AE2BBDBF21E6FBAF9ACB7C778C405E80B1F16CC81437C9`

### Exact abstract support

The results suggest that PT-141 holds promise as a new treatment for sexual dysfunction.

## qa09 — answerable (development)

**Question:** BPC 157 gastric duodenal lesions rats?

- Decision: [ ] Approve  [ ] Edit  [ ] Reject
- Reviewer:
- Notes:

- Source: [PMID 7904712](https://pubmed.ncbi.nlm.nih.gov/7904712/)
- Acceptable answer: The protection of stomach and duodenum in conjecture with anti-inflammatory effect was demonstrated for a novel 15 amino acid peptide, coded BPC 157, a fragment of the recently discovered gastric juice peptide BPC. BPC 157 (i.p./i.g.) was investigated in rats in comparison with several reference standards in three experimental ulcer models (48 h-restraint stress, subcutaneous cysteamine, intragastrical 96% ethanol ulcer tests) (pre-/co-/post-treatment).
- Exact support offsets: `0:458`; SHA-256: `F1AC7F6E26D8F6ADCAFAA6C4588C97848A79AE22CDB12CD3665FCEC131A8468F`

### Exact abstract support

The protection of stomach and duodenum in conjecture with anti-inflammatory effect was demonstrated for a novel 15 amino acid peptide, coded BPC 157, a fragment of the recently discovered gastric juice peptide BPC. BPC 157 (i.p./i.g.) was investigated in rats in comparison with several reference standards in three experimental ulcer models (48 h-restraint stress, subcutaneous cysteamine, intragastrical 96% ethanol ulcer tests) (pre-/co-/post-treatment). 

## qa10 — answerable (development)

**Question:** GHK Cu healing ACL reconstruction rat?

- Decision: [ ] Approve  [ ] Edit  [ ] Reject
- Reviewer:
- Notes:

- Source: [PMID 25731775](https://pubmed.ncbi.nlm.nih.gov/25731775/)
- Acceptable answer: Intra-articular supplementation with a bioactive small molecule GHK-Cu improved graft healing following ACLR in rat, but the beneficial effects could not last as treatment discontinued.
- Exact support offsets: `1249:1434`; SHA-256: `66C52E5B426787F35E0FAEB31F5A54921B20ABA24CED17D80682ABC8F73635F7`

### Exact abstract support

Intra-articular supplementation with a bioactive small molecule GHK-Cu improved graft healing following ACLR in rat, but the beneficial effects could not last as treatment discontinued.

## qa11 — answerable (holdout)

**Question:** TB 500 wound healing metabolites?

- Decision: [ ] Approve  [ ] Edit  [ ] Reject
- Reviewer:
- Notes:

- Source: [PMID 38382158](https://pubmed.ncbi.nlm.nih.gov/38382158/)
- Acceptable answer: Also, the metabolite Ac-LKK was a long-term metabolite of TB-500 detected up to 72 hr. No cytotoxicity of the parent and its metabolites was found. Ac-LKKTE only showed a significant wound healing activity compared to the control.
- Exact support offsets: `1213:1444`; SHA-256: `E96514A829AD560FD99280E25AD01B2C63017A2240D468703A0C9448F1DBC70A`

### Exact abstract support

Also, the metabolite Ac-LKK was a long-term metabolite of TB-500 detected up to 72 hr. No cytotoxicity of the parent and its metabolites was found. Ac-LKKTE only showed a significant wound healing activity compared to the control. 

## qa12 — answerable (holdout)

**Question:** ipamorelin growth hormone release receptor?

- Decision: [ ] Approve  [ ] Edit  [ ] Reject
- Reviewer:
- Notes:

- Source: [PMID 9849822](https://pubmed.ncbi.nlm.nih.gov/9849822/)
- Acceptable answer: A pharmacological profiling using GHRP and growth hormone-releasing hormone (GHRH) antagonists clearly demonstrated that ipamorelin, like GHRP-6, stimulates GH release via a GHRP-like receptor.
- Exact support offsets: `617:811`; SHA-256: `CDABEAB566B813E5625AAF56B7C2B507EEA43EDD139ECE5B30DD528448B09154`

### Exact abstract support

A pharmacological profiling using GHRP and growth hormone-releasing hormone (GHRH) antagonists clearly demonstrated that ipamorelin, like GHRP-6, stimulates GH release via a GHRP-like receptor. 

## qa13 — answerable (holdout)

**Question:** tesamorelin HIV visceral adipose triglycerides safety?

- Decision: [ ] Approve  [ ] Edit  [ ] Reject
- Reviewer:
- Notes:

- Source: [PMID 18057338](https://pubmed.ncbi.nlm.nih.gov/18057338/)
- Acceptable answer: METHODS: We randomly assigned 412 patients with HIV (86% of whom were men) who had an accumulation of abdominal fat to receive a daily subcutaneous injection of either 2 mg of tesamorelin or placebo for 26 weeks. The primary end point was the percent change from baseline in visceral adipose tissue as shown on computed tomography.
- Exact support offsets: `335:667`; SHA-256: `CF2647DD4D81F9E84A936F8D9BAA0086BA7B1B09585C7D4822F65840A6718282`

### Exact abstract support

METHODS: We randomly assigned 412 patients with HIV (86% of whom were men) who had an accumulation of abdominal fat to receive a daily subcutaneous injection of either 2 mg of tesamorelin or placebo for 26 weeks. The primary end point was the percent change from baseline in visceral adipose tissue as shown on computed tomography. 

## qa14 — answerable (holdout)

**Question:** epitalon evening melatonin cortisol secretion?

- Decision: [ ] Approve  [ ] Edit  [ ] Reject
- Reviewer:
- Notes:

- Source: [PMID 11524632](https://pubmed.ncbi.nlm.nih.gov/11524632/)
- Acceptable answer: RESULTS: Epitalon was proven to significantly stimulate melatonin synthesis in senescent monkeys in the evening, thereby normalising the circadian rhythm of cortisol secretion.
- Exact support offsets: `346:522`; SHA-256: `99E4D630A16DAF7CDCF50B8B8688BCCC16836DC47AF6D47A46EC4CF00CC0CA7E`

### Exact abstract support

RESULTS: Epitalon was proven to significantly stimulate melatonin synthesis in senescent monkeys in the evening, thereby normalising the circadian rhythm of cortisol secretion.

## qa15 — answerable (holdout)

**Question:** MOTS c mitochondrial polymorphism longevity?

- Decision: [ ] Approve  [ ] Edit  [ ] Reject
- Reviewer:
- Notes:

- Source: [PMID 26289118](https://pubmed.ncbi.nlm.nih.gov/26289118/)
- Acceptable answer: These include humanin, and the recently discovered mitochondrial open reading frame of the 12S rRNA-c (MOTS-c). Although more research is needed, we suggest that the m.1382A>C polymorphism located in the MOTS-c encoding mtDNA, which is specific for the Northeast Asian population, may be among the putative biological mechanisms explaining the high longevity of Japanese people.
- Exact support offsets: `123:501`; SHA-256: `F41E7F1603C630C5476DC681FBF1115735ECD7BEE8B56456D0DF837E83C0D6EF`

### Exact abstract support

These include humanin, and the recently discovered mitochondrial open reading frame of the 12S rRNA-c (MOTS-c). Although more research is needed, we suggest that the m.1382A>C polymorphism located in the MOTS-c encoding mtDNA, which is specific for the Northeast Asian population, may be among the putative biological mechanisms explaining the high longevity of Japanese people.

## qa16 — unanswerable (development)

**Question:** Does BPC-157 cure cancer in humans?

- Decision: [ ] Approve  [ ] Edit  [ ] Reject
- Reviewer:
- Notes:

- Proposed response: Insufficient evidence in this frozen abstract corpus.
- Lexical check: no matching PMID for peptide tokens `bpc, 157` plus claim tokens `cure, cancer, human`.
- Caveat: No matches under this deterministic lexical check; absence is not exhaustive evidence that no support exists.

## qa17 — unanswerable (development)

**Question:** What dose of GHK-Cu safely treats Alzheimer's disease during pregnancy?

- Decision: [ ] Approve  [ ] Edit  [ ] Reject
- Reviewer:
- Notes:

- Proposed response: Insufficient evidence in this frozen abstract corpus.
- Lexical check: no matching PMID for peptide tokens `ghk, cu` plus claim tokens `dose, alzheimer, pregnancy`.
- Caveat: No matches under this deterministic lexical check; absence is not exhaustive evidence that no support exists.

## qa18 — unanswerable (development)

**Question:** Does TB-500 reverse kidney failure in humans?

- Decision: [ ] Approve  [ ] Edit  [ ] Reject
- Reviewer:
- Notes:

- Proposed response: Insufficient evidence in this frozen abstract corpus.
- Lexical check: no matching PMID for peptide tokens `tb, 500` plus claim tokens `reverse, kidney, failure, human`.
- Caveat: No matches under this deterministic lexical check; absence is not exhaustive evidence that no support exists.

## qa19 — unanswerable (holdout)

**Question:** Can ipamorelin replace insulin for type 1 diabetes?

- Decision: [ ] Approve  [ ] Edit  [ ] Reject
- Reviewer:
- Notes:

- Proposed response: Insufficient evidence in this frozen abstract corpus.
- Lexical check: no matching PMID for peptide tokens `ipamorelin` plus claim tokens `replace, insulin, type, diabetes`.
- Caveat: No matches under this deterministic lexical check; absence is not exhaustive evidence that no support exists.

## qa20 — unanswerable (holdout)

**Question:** Does PT-141 prevent myocardial infarction?

- Decision: [ ] Approve  [ ] Edit  [ ] Reject
- Reviewer:
- Notes:

- Proposed response: Insufficient evidence in this frozen abstract corpus.
- Lexical check: no matching PMID for peptide tokens `pt, 141` plus claim tokens `prevent, myocardial, infarction`.
- Caveat: No matches under this deterministic lexical check; absence is not exhaustive evidence that no support exists.
