# QA Oracle Human Review

> **Human review complete—ready to freeze.** Every case has explicit project-owner approval.

- Corpus SHA-256: `231E048971C34EF9203ED3BB20587DDE4C95141AC7EFD2746C85C078A844212C`
- Qrels v2 SHA-256: `B30E1B7868EFFB580155442917C2BB0105ECC00E13527A103F6325B6A2B32ED6`
- Development: `qa01`–`qa10`, `qa16`–`qa18` (10 answerable / 3 unanswerable)
- Holdout: `qa11`–`qa15`, `qa19`–`qa20` (5 answerable / 2 unanswerable)

## Review instructions

Read every cited abstract span. Approve, edit, or reject each case; verify that an answerable answer says no more than its support, and that an unanswerable case has no sufficient direct corpus evidence. Strict lexical checks are deterministic but not exhaustive.

## qa01 — answerable (development)

**Question:** What effect did BPC-157 have on liver injury in the reported rat models?

- Decision: [x] Approve  [ ] Edit  [ ] Reject
- Reviewer: project_owner
- Notes: Approved by the project owner during sequential QA review.

- Sources: [PMID 7901724](https://pubmed.ncbi.nlm.nih.gov/7901724/)
- Acceptable answer: In rat models of bile duct and hepatic artery ligation, restraint stress, and CCl4 injury, intragastric or intraperitoneal BPC-157 significantly prevented liver necrosis or fatty changes.
- Exact support 1: PMID `7901724` offsets `0:624`; SHA-256: `A891A841311236641859062D005B13442FE0C33F2C14E097423FFF004BA4C2C6`

### Exact abstract support 1

The hepatoprotective effects of a newly synthesized 15 amino acid fragment code named BPC 157 was evaluated in comparison with the reference standards (bromocriptine, amantadine and somatostatin) in various experimental models of liver injury in rats: 24 h-bile duct+hepatic artery ligation 48 h-restraint stress and CCl4 administration. BPC 157 administered either intragastrically or intraperitoneally, significantly prevented the development of liver necrosis or fatty changes in rats subjected to 24 h bile duct + hepatic artery ligation, 48 h-restraint stress, CCl4 treatment (1 ml/kg i.p., sacrifice 48 h thereafter).

## qa02 — answerable (development)

**Question:** Does GHK or GHK-Cu help regrow hair?

- Decision: [x] Approve  [ ] Edit  [ ] Reject
- Reviewer: project_owner
- Notes: Approved after replacing the abstract-specific neurodegeneration question with a broader real-user hair-regrowth question.

- Sources: [PMID 27489425](https://pubmed.ncbi.nlm.nih.gov/27489425/), [PMID 38026438](https://pubmed.ncbi.nlm.nih.gov/38026438/)
- Acceptable answer: The corpus suggests potential, but it does not prove that GHK or GHK-Cu alone regrows human hair. In a 45-person trial of a combined 5-ALA/GHK product, hair counts increased and the 50 mg/ml group had a significantly larger hair-count change ratio than placebo, while hair length and thickness did not differ significantly. Because the product contained both 5-ALA and GHK, the trial cannot isolate GHK's contribution. A separate mouse study of a topical GHK-Cu delivery system reported effectiveness and greater activation of the hair-growth-related Wnt/beta-catenin pathway.
- Exact support 1: PMID `27489425` offsets `402:576`; SHA-256: `BC9E79317C3768C831EDD0F9B0CB27CCC1CDD12CFADAEE1D4D4985C6DED3E691`

### Exact abstract support 1

METHODS: Forty-five patients with male pattern hair loss were treated with ALAVAX 100 mg/ml (group A), ALAVAX 50 mg/ml (group B) or placebo (group C) once a day for 6 months.

- Exact support 2: PMID `27489425` offsets `701:969`; SHA-256: `C289FFE199AF4ECBC854017B2E72301E8EF5044312DD4267B6FD928EA0AED515`

### Exact abstract support 2

RESULTS: An increase in hair count for 6 months was 52.6 (p<0.05) in group A, 71.5 (p<0.05) in group B, and 9.6 in group C. The ratio of changes in hair count between group B (2.38) and group C (1.21) at 6 months showed a statistically significant difference (p<0.05).

- Exact support 3: PMID `27489425` offsets `1097:1248`; SHA-256: `2B47F43C56B37F4C4140452E2EB33A224A63373AA4F762E4A72E28151B3FF608`

### Exact abstract support 3

There was no statistically significant difference in hair length and hair thickness among 3 groups at 6 months. There was no adverse event in 3 groups.

- Exact support 4: PMID `38026438` offsets `0:223`; SHA-256: `2563F266139E315F9C114DAC2DD94EB1922621BB349D5A2FA5431AFF34F0741A`

### Exact abstract support 4

Copper peptides (GHK-Cu) are a powerful hair growth promoter with minimal side effects when compared with minoxidil and finasteride; however, challenges in delivering GHK-Cu topically limits their non-invasive applications.

- Exact support 5: PMID `38026438` offsets `610:993`; SHA-256: `B9E26AF52964F9EDE6A1637433495B01E28461C912BA6637742AF0478495384D`

### Exact abstract support 5

Experiments in mice validated the effectiveness of our proposed IL-M system. Furthermore, the exact effects of the IL-M system on the expression of growth factors, such as vascular endothelial growth factor, were revealed, and it was found that microemulsion increased the activation of the Wnt/β-catenin signaling pathway, which includes factors involved in hair growth regulation.

## qa03 — answerable (development)

**Question:** Does TB-500 help injuries or wounds heal?

- Decision: [x] Approve  [ ] Edit  [ ] Reject
- Reviewer: project_owner
- Notes: Approved after replacing the abstract-specific protein-conformation question with a realistic TB-500 healing question.

- Sources: [PMID 42542926](https://pubmed.ncbi.nlm.nih.gov/42542926/), [PMID 38382158](https://pubmed.ncbi.nlm.nih.gov/38382158/), [PMID 41476424](https://pubmed.ncbi.nlm.nih.gov/41476424/)
- Acceptable answer: Preclinical evidence suggests possible healing effects, but benefit in people has not been established. In a rat Achilles-tendon repair study, TB-500 significantly improved maximum load to failure and several histopathology scores compared with controls. In a separate laboratory study, only the Ac-LKKTE metabolite showed significant wound-healing activity, leading the authors to suggest that previously reported activity might come from that metabolite rather than parent TB-500. A narrative review reported that human orthopaedic data are lacking.
- Exact support 1: PMID `42542926` offsets `1132:1668`; SHA-256: `5A90BF8A4D2F526E3EF292585D4775C823FC1E2B1F3F66BBCFBFC82D73C5DD4A`

### Exact abstract support 1

Biomechanical testing revealed higher maximum load to failure values in the BPC-157 and TB-500 groups compared to controls, reaching statistical significance in the TB-500 group (p < 0.05). Histopathological evaluation demonstrated significantly lower total Bonar scores in the TB-500 group (p = 0.016) and significantly lower total Movin scores in the TB-500 and BPC + TB groups (p = 0.017 and p = 0.040, respectively) relative to controls, indicating improved tendon architecture, collagen alignment, and reduced degenerative changes.

- Exact support 2: PMID `38382158` offsets `1300:1444`; SHA-256: `FB384110CA0B52F17030302ECCE64E3D6DB5557035F6EA30E58D2A632C35A178`

### Exact abstract support 2

No cytotoxicity of the parent and its metabolites was found. Ac-LKKTE only showed a significant wound healing activity compared to the control.

- Exact support 3: PMID `38382158` offsets `1444:1790`; SHA-256: `FCF9F0D6BA7ADA8F8E9239A23F535E219D7C04B672076DDFEF58B39D4C18A616`

### Exact abstract support 3

CONCLUSION: The study provides a valuable tool for quantifying TB-500 and its metabolites, contributing to the understanding of metabolism and potential therapeutic applications. Our results also suggest that the previously reported wound-healing activity of TB-500 in literature may be due to its metabolite Ac-LKKTE rather than the parent form.

- Exact support 4: PMID `41476424` offsets `1425:1603`; SHA-256: `75254BEE18C1BB7F755029D89BA735969510A3F51A6DE1D62EFDF1483B414B77`

### Exact abstract support 4

TB-4 and its derivative TB-500 promoted angiogenesis and tissue repair in preclinical models, but human orthopaedic data are lacking, and both remain banned substances in sports.

## qa04 — answerable (development)

**Question:** Does ipamorelin increase growth hormone?

- Decision: [x] Approve  [ ] Edit  [ ] Reject
- Reviewer: project_owner
- Notes: Approved after replacing the medicinal-chemistry question with a realistic question about growth-hormone release.

- Sources: [PMID 10496658](https://pubmed.ncbi.nlm.nih.gov/10496658/), [PMID 9849822](https://pubmed.ncbi.nlm.nih.gov/9849822/)
- Acceptable answer: Under the studied conditions, yes. In healthy male volunteers receiving intravenous ipamorelin at five tested infusion rates, every dose induced a single growth-hormone release episode. The response peaked at about 0.67 hours and then declined exponentially to negligible concentrations. Other laboratory and animal profiling also described ipamorelin as a potent growth-hormone secretagogue. These findings establish an acute hormonal effect under research conditions; they do not establish muscle-building, weight-loss, or anti-aging benefits.
- Exact support 1: PMID `10496658` offsets `0:428`; SHA-256: `2684DC8AC715B3EF569C971CE7C08F67D161DD9E12963D7E3D5CEB6F94EEDBEF`

### Exact abstract support 1

PURPOSE: To examine the pharmacokinetics (PK) and pharmacodynamics (PD) of ipamorelin, a growth hormone (GH) releasing peptide, in healthy volunteers. METHODS: A trial was conducted with a dose escalation design comprising 5 different infusion rates (4.21, 14.02, 42.13, 84.27 and 140.45 nmol/kg over 15 minutes) with eight healthy male subjects at each dose level. Concentrations of ipamorelin and growth hormone were measured.

- Exact support 2: PMID `10496658` offsets `616:799`; SHA-256: `66F4F81BF5BF542BE4BE3BD056F6DF108BEADEA9D098EB91FA6940C8F41A59D4`

### Exact abstract support 2

The time course of GH stimulation by ipamorelin showed a single episode of GH release with a peak at 0.67 hours and an exponential decline to negligible GH concentration at all doses.

- Exact support 3: PMID `10496658` offsets `1039:1228`; SHA-256: `A7F73520D39F3A797E6247EBA2129280035E94834562FE3D01240CD236BDB76E`

### Exact abstract support 3

Ipamorelin induces the release of GH at all dose levels with the concentration (SC50) required for half-maximal GH stimulation of 214 nmol/L and a maximal GH production rate of 694 mIU/L/h.

- Exact support 4: PMID `9849822` offsets `0:246`; SHA-256: `5942A867D903C27DFCF44E902116B35126192825FA22CE3CC52F9AC71A58AB83`

### Exact abstract support 4

The development and pharmacology of a new potent growth hormone (GH) secretagogue, ipamorelin, is described. Ipamorelin is a pentapeptide (Aib-His-D-2-Nal-D-Phe-Lys-NH2), which displays high GH releasing potency and efficacy in vitro and in vivo.

## qa05 — answerable (development)

**Question:** Does tesamorelin reduce belly fat?

- Decision: [x] Approve  [ ] Edit  [ ] Reject
- Reviewer: project_owner
- Notes: Approved as part of the complete 20-question slate on 2026-08-14.

- Sources: [PMID 20101189](https://pubmed.ncbi.nlm.nih.gov/20101189/)
- Acceptable answer: Yes, in the population that was studied: people with HIV-associated abdominal-fat accumulation. In a 404-patient trial, visceral adipose tissue decreased 10.9% with tesamorelin versus 0.6% with placebo after six months. Patients who continued tesamorelin reached an approximately 18% reduction after 12 months, while the earlier improvement was rapidly lost after switching to placebo. These results do not establish tesamorelin as a general weight-loss treatment.
- Exact support 1: PMID `20101189` offsets `322:496`; SHA-256: `A008ACD27288FD5598D3A62A35C2A79F6021292C92556E63C70598A78642105B`

### Exact abstract support 1

METHODS: A 12-month study of 404 HIV-infected patients with excess abdominal fat in the context of antiretroviral therapy was conducted between January 2007 and October 2008.

- Exact support 2: PMID `20101189` offsets `1187:1341`; SHA-256: `1BFEA09A131BD2EAA71668981D07DF1A9D59FF18A8777D66470FC98D70F27BEA`

### Exact abstract support 2

RESULTS: VAT decreased by -10.9% (-21 cm(2)) in the tesamorelin group vs. -0.6% (-1 cm(2)) in the placebo group in the 6-month efficacy phase, P < 0.0001.

- Exact support 3: PMID `20101189` offsets `1793:2003`; SHA-256: `812500409E5E2C9D7C2DB0E473A98E748034AD6D67A85A64673B560F4D470CC7`

### Exact abstract support 3

VAT was reduced by approximately 18% (P < 0.001) in patients continuing tesamorelin for 12 months. The initial improvements over 6 months in VAT were rapidly lost in those switching from tesamorelin to placebo.

## qa06 — answerable (development)

**Question:** What effect did developmental exposure to Epitalon have on adult fruit-fly lifespan?

- Decision: [x] Approve  [ ] Edit  [ ] Reject
- Reviewer: project_owner
- Notes: Approved as a specific research question in the complete slate on 2026-08-14.

- Sources: [PMID 11087911](https://pubmed.ncbi.nlm.nih.gov/11087911/)
- Acceptable answer: Epitalon exposure during development increased adult Drosophila lifespan by 11% to 16% at the tested low concentrations, and the increase was not dose-dependent.
- Exact support 1: PMID `11087911` offsets `147:566`; SHA-256: `F795E3299EAAA970DC25A31DA748F74B1DB4F13DB3F206958D822105C693BAC6`

### Exact abstract support 1

The substance was added to the culture medium only at the developmental stage (from egg to larva). Epitalon significantly increased the lifespan (LS) of imagoes by 11-16% when applied at unprecedented low concentrations-from 0.001 x 10(-6) to 5 x 10(-6) wt.% of culture medium for males and from 0.01 x 10(-6) to 0.1 x 10(-6) wt.% of culture medium for females. The increase in LS did not depend on the substance dose.

## qa07 — answerable (development)

**Question:** Does MOTS-c help with weight loss or metabolism?

- Decision: [x] Approve  [ ] Edit  [ ] Reject
- Reviewer: project_owner
- Notes: Approved as part of the complete 20-question slate on 2026-08-14.

- Sources: [PMID 25738459](https://pubmed.ncbi.nlm.nih.gov/25738459/)
- Acceptable answer: The corpus shows promising metabolic effects in mice, not proof of a human weight-loss treatment. In the reported mouse experiments, MOTS-c prevented age-dependent and high-fat-diet-induced insulin resistance and prevented diet-induced obesity. Human treatment efficacy cannot be inferred from those animal findings.
- Exact support 1: PMID `25738459` offsets `721:1011`; SHA-256: `E13B71C9AC777990D6668813026CFF8816CC2B8A9DADF63112B580ABB994E422`

### Exact abstract support 1

MOTS-c treatment in mice prevented age-dependent and high-fat-diet-induced insulin resistance, as well as diet-induced obesity. These results suggest that mitochondria may actively regulate metabolic homeostasis at the cellular and organismal level via peptides encoded within their genome.

## qa08 — answerable (development)

**Question:** Does PT-141 help with erectile dysfunction?

- Decision: [x] Approve  [ ] Edit  [ ] Reject
- Reviewer: project_owner
- Notes: Approved as part of the complete 20-question slate on 2026-08-14.

- Sources: [PMID 14963471](https://pubmed.ncbi.nlm.nih.gov/14963471/), [PMID 14999221](https://pubmed.ncbi.nlm.nih.gov/14999221/)
- Acceptable answer: Short-term controlled studies found that PT-141 produced statistically significant erectile responses. Intranasal doses above 7 mg produced significant responses versus placebo with onset at about 30 minutes, and subcutaneous 4 mg and 6 mg doses produced significant responses in erectile-dysfunction patients who reported an inadequate Viagra response. Flushing and nausea were common in the intranasal studies. These findings concern acute erectile response and do not establish long-term outcomes.
- Exact support 1: PMID `14963471` offsets `0:347`; SHA-256: `01C1F700A5EF2F61C41FD4425682933DF2058E707E9CA4CEE0E8E8928047DE49`

### Exact abstract support 1

PT-141, a cyclic heptapeptide melanocortin analog, was evaluated following intranasal administration in healthy male subjects and in Viagra-responsive erectile dysfunction (ED) patients. Erectile response was assessed by RigiScan trade mark in healthy subjects without visual sexual stimulation (VSS) and in Viagra-responsive ED patients with VSS.

- Exact support 2: PMID `14963471` offsets `503:725`; SHA-256: `339E457FC9856938D775FE3845836BAF6827707507120468106353F10A66BE7E`

### Exact abstract support 2

In both studies, an erectile response induced by PT-141 administration was statistically significant, compared to placebo, at doses greater than 7 mg, with the onset of the first erection occurring in approximately 30 min.

- Exact support 3: PMID `14963471` offsets `726:1029`; SHA-256: `850353A0F4FC983A518A2C8244DEBDAC66C6003BC867B1A9842387BBB0476D9B`

### Exact abstract support 3

PT-141 was safely administered and well tolerated in both studies. A maximum-tolerated dose was not identified. Flushing and nausea were the most common adverse events reported in both studies and no clinically significant changes in vital signs, laboratory tests, ECGs, or physical exams were observed.

- Exact support 4: PMID `14999221` offsets `746:932`; SHA-256: `231486E242E1EAB84E855126B4DDA06A366ECB804AD8AF54C22E1CC27F2C39E6`

### Exact abstract support 4

ED patients were treated with placebo, 4 or 6 mg PT-141 in a crossover design in the presence of VSS. The erectile response induced by PT-141 was statistically significant at both doses.

## qa09 — answerable (development)

**Question:** What did the rat study report about BPC-157 in experimental stomach and duodenal ulcer models?

- Decision: [x] Approve  [ ] Edit  [ ] Reject
- Reviewer: project_owner
- Notes: Approved as a specific research question in the complete slate on 2026-08-14.

- Sources: [PMID 7904712](https://pubmed.ncbi.nlm.nih.gov/7904712/)
- Acceptable answer: The study reported protection of the stomach and duodenum together with an anti-inflammatory effect when BPC-157 was investigated in three rat ulcer models.
- Exact support 1: PMID `7904712` offsets `0:458`; SHA-256: `F1AC7F6E26D8F6ADCAFAA6C4588C97848A79AE22CDB12CD3665FCEC131A8468F`

### Exact abstract support 1

The protection of stomach and duodenum in conjecture with anti-inflammatory effect was demonstrated for a novel 15 amino acid peptide, coded BPC 157, a fragment of the recently discovered gastric juice peptide BPC. BPC 157 (i.p./i.g.) was investigated in rats in comparison with several reference standards in three experimental ulcer models (48 h-restraint stress, subcutaneous cysteamine, intragastrical 96% ethanol ulcer tests) (pre-/co-/post-treatment).

## qa10 — answerable (development)

**Question:** How did intra-articular GHK-Cu affect graft healing after ACL reconstruction in rats?

- Decision: [x] Approve  [ ] Edit  [ ] Reject
- Reviewer: project_owner
- Notes: Approved as a specific research question in the complete slate on 2026-08-14.

- Sources: [PMID 25731775](https://pubmed.ncbi.nlm.nih.gov/25731775/)
- Acceptable answer: Intra-articular GHK-Cu improved graft healing after ACL reconstruction in rats, but the beneficial effects did not persist after treatment stopped.
- Exact support 1: PMID `25731775` offsets `1249:1434`; SHA-256: `66C52E5B426787F35E0FAEB31F5A54921B20ABA24CED17D80682ABC8F73635F7`

### Exact abstract support 1

Intra-articular supplementation with a bioactive small molecule GHK-Cu improved graft healing following ACLR in rat, but the beneficial effects could not last as treatment discontinued.

## qa11 — answerable (holdout)

**Question:** What peptide did researchers identify as the key ingredient of TB-500, and how is it related to thymosin beta-4?

- Decision: [x] Approve  [ ] Edit  [ ] Reject
- Reviewer: project_owner
- Notes: Approved as a specific research question in the complete slate on 2026-08-14.

- Sources: [PMID 23084823](https://pubmed.ncbi.nlm.nih.gov/23084823/)
- Acceptable answer: Researchers identified TB-500's key ingredient as LKKTETQ with artificial acetylation at the N-terminus, also described as N-acetylated LKKTETQ. LKKTETQ corresponds to residues 17-23, the active region of thymosin beta-4 associated in the abstract with actin binding, cell migration, and wound healing.
- Exact support 1: PMID `23084823` offsets `0:383`; SHA-256: `3C043B11D077F50C868C9D5DCDE5F32EDC9DA18D6C666F0730DAC781BF8BED90`

### Exact abstract support 1

A veterinary preparation known as TB-500 and containing a synthetic version of the naturally occurring peptide LKKTETQ has emerged. The peptide segment (17)LKKTETQ(23) is the active site within the protein thymosin β(4) responsible for actin binding, cell migration and wound healing. The key ingredient of TB-500 is the peptide LKKTETQ with artificial acetylation of the N-terminus.

## qa12 — answerable (holdout)

**Question:** Does ipamorelin reduce body fat?

- Decision: [x] Approve  [ ] Edit  [ ] Reject
- Reviewer: project_owner
- Notes: Approved as part of the complete 20-question slate on 2026-08-14.

- Sources: [PMID 11162489](https://pubmed.ncbi.nlm.nih.gov/11162489/)
- Acceptable answer: The reported mouse study did not support that claim; it found the opposite under its experimental conditions. Ipamorelin produced about a 15% body-weight increase by two weeks, increased fat-pad weight relative to body weight, and—when grouped with another growth-hormone secretagogue—increased relative body fat in growth-hormone-intact mice. The authors concluded that growth-hormone secretagogues increased body fat through growth-hormone-independent mechanisms. These animal results do not establish the effect in people.
- Exact support 1: PMID `11162489` offsets `0:263`; SHA-256: `E170B7D62D7B90A7A3CB3E7A7CA15BA606BAED09E8D17A33B5E0327394E85F24`

### Exact abstract support 1

Growth hormone secretagogues (GHSs) stimulate growth hormone (GH) secretion, which is lipolytic. Here we compared the effects of twice daily s.c. treatment of GH and the GHS, ipamorelin, on body fat in GH-deficient (lit/lit) and in GH-intact (+/lit and +/+) mice.

- Exact support 2: PMID `11162489` offsets `264:558`; SHA-256: `FAA7D257AE0816300D74D78FB8FE1DA97F05CECC8DFB37A81347EB592665E899`

### Exact abstract support 2

In +/lit and lit/lit mice ipamorelin induced a small (15%) increase in body weight by 2 weeks, that was not further augmented by 9 weeks. GH treatment markedly enhanced body weight in both groups. Ipamorelin also increased fat pad weights relative to body weight in both lit/lit and +/lit mice.

- Exact support 3: PMID `11162489` offsets `559:719`; SHA-256: `6D27D3C2B3C8E935886800F2ED1EE38BCF47AB739B84580B049CF76CE05A3789`

### Exact abstract support 3

Two weeks GHS treatment (ipamorelin or GHRP-6) also increased relative body fat, quantified by in vivo dual energy X-ray absorpiometry (DEXA) in GH-intact mice.

- Exact support 4: PMID `11162489` offsets `894:987`; SHA-256: `3CB2A3BB8A737DAB054B8D1F07FCD3ADFCF3C87B5656A0C7CD831A0D02A2A6E4`

### Exact abstract support 4

Thus, GHSs increase body fat by GH-independent mechanisms that may include increased feeding.

## qa13 — answerable (holdout)

**Question:** What effects did tesamorelin have on visceral fat and triglycerides in the HIV trial, and what did the trial report about adverse events?

- Decision: [x] Approve  [ ] Edit  [ ] Reject
- Reviewer: project_owner
- Notes: Approved as a specific research question in the complete slate on 2026-08-14.

- Sources: [PMID 18057338](https://pubmed.ncbi.nlm.nih.gov/18057338/)
- Acceptable answer: Visceral adipose tissue decreased by 15.2% with tesamorelin versus a 5.0% increase with placebo, and triglycerides decreased by 50 mg/dL versus a 9 mg/dL increase. Overall adverse-event rates did not differ significantly, although more tesamorelin participants withdrew because of an adverse event.
- Exact support 1: PMID `18057338` offsets `932:1318`; SHA-256: `7C7220A3D31E5D56F5BD95D686C6BFFCCA6A54CF6C1EDBD1B688D3267D3BF0B2`

### Exact abstract support 1

RESULTS: The measure of visceral adipose tissue decreased by 15.2% in the tesamorelin group and increased by 5.0% in the placebo group; the levels of triglycerides decreased by 50 mg per deciliter and increased by 9 mg per deciliter, respectively, and the ratio of total cholesterol to HDL cholesterol decreased by 0.31 and increased by 0.21, respectively (P<0.001 for all comparisons).

- Exact support 2: PMID `18057338` offsets `1535:1704`; SHA-256: `8834E57C95545ACBDC71B05C2C486300E95400E7ED21464DE69F50ED16B0DE03`

### Exact abstract support 2

Adverse events did not differ significantly between the two study groups, but more patients in the tesamorelin group withdrew from the study because of an adverse event.

## qa14 — answerable (holdout)

**Question:** How did Epitalon affect evening melatonin and cortisol rhythm in older monkeys?

- Decision: [x] Approve  [ ] Edit  [ ] Reject
- Reviewer: project_owner
- Notes: Approved as a specific research question in the complete slate on 2026-08-14.

- Sources: [PMID 11524632](https://pubmed.ncbi.nlm.nih.gov/11524632/)
- Acceptable answer: Epitalon significantly stimulated evening melatonin synthesis in senescent monkeys and normalized the circadian rhythm of cortisol secretion.
- Exact support 1: PMID `11524632` offsets `346:522`; SHA-256: `99E4D630A16DAF7CDCF50B8B8688BCCC16836DC47AF6D47A46EC4CF00CC0CA7E`

### Exact abstract support 1

RESULTS: Epitalon was proven to significantly stimulate melatonin synthesis in senescent monkeys in the evening, thereby normalising the circadian rhythm of cortisol secretion.

## qa15 — answerable (holdout)

**Question:** What hypothesis did the authors make about the MOTS-c m.1382A>C variant and Japanese longevity?

- Decision: [x] Approve  [ ] Edit  [ ] Reject
- Reviewer: project_owner
- Notes: Approved as a specific research question in the complete slate on 2026-08-14.

- Sources: [PMID 26289118](https://pubmed.ncbi.nlm.nih.gov/26289118/)
- Acceptable answer: The authors suggested, while noting that more research was needed, that the Northeast-Asian-specific m.1382A>C polymorphism in MOTS-c-encoding mitochondrial DNA might contribute to Japanese longevity.
- Exact support 1: PMID `26289118` offsets `123:501`; SHA-256: `F41E7F1603C630C5476DC681FBF1115735ECD7BEE8B56456D0DF837E83C0D6EF`

### Exact abstract support 1

These include humanin, and the recently discovered mitochondrial open reading frame of the 12S rRNA-c (MOTS-c). Although more research is needed, we suggest that the m.1382A>C polymorphism located in the MOTS-c encoding mtDNA, which is specific for the Northeast Asian population, may be among the putative biological mechanisms explaining the high longevity of Japanese people.

## qa16 — unanswerable (development)

**Question:** What is the safest effective BPC-157 dose for healing a human tendon injury?

- Decision: [x] Approve  [ ] Edit  [ ] Reject
- Reviewer: project_owner
- Notes: Approved after the documented multi-query corpus insufficiency audit on 2026-08-14.

- Expected response: Insufficient evidence in this frozen abstract corpus.
- Strict query tokens: peptide `bpc, 157`; claim `human, tendon, dose`.
- Strict conjunction candidates requiring manual review: `21030672`, `25415472`, `36551977`, `38980576`
- Manually audited PMIDs: `21030672`, `25415472`, `40131143`, `40756949`, `41476424`, `42198317`
- Caveat: Strict matches contain related preclinical or review language, not a validated safe and effective human tendon regimen; the corpus-only conclusion is not a universal claim of absence.

## qa17 — unanswerable (development)

**Question:** Does injectable GHK-Cu reverse human skin aging better than topical GHK-Cu?

- Decision: [x] Approve  [ ] Edit  [ ] Reject
- Reviewer: project_owner
- Notes: Approved after the documented multi-query corpus insufficiency audit on 2026-08-14.

- Expected response: Insufficient evidence in this frozen abstract corpus.
- Strict query tokens: peptide `ghk, cu`; claim `injectable, topical, skin`.
- Strict conjunction matches: none.
- Manually audited PMIDs: `16847171`, `18644225`, `40716276`, `42573538`
- Caveat: No strict head-to-head route match was found; separate route-specific findings cannot answer an unperformed human comparison, and the corpus-only conclusion is not universal.

## qa18 — unanswerable (development)

**Question:** Does TB-500 speed recovery after surgery in humans?

- Decision: [x] Approve  [ ] Edit  [ ] Reject
- Reviewer: project_owner
- Notes: Approved after the documented multi-query corpus insufficiency audit on 2026-08-14.

- Expected response: Insufficient evidence in this frozen abstract corpus.
- Strict query tokens: peptide `tb, 500`; claim `human, surgery`.
- Strict conjunction matches: none.
- Manually audited PMIDs: `38382158`, `41476424`, `42160466`, `42542926`, `42578445`
- Caveat: No strict human-surgery TB-500 match was found; related preclinical or thymosin beta-4 evidence does not establish human postoperative recovery, and the corpus-only conclusion is not universal.

## qa19 — unanswerable (holdout)

**Question:** Does ipamorelin cause lasting muscle gain in healthy adults?

- Decision: [x] Approve  [ ] Edit  [ ] Reject
- Reviewer: project_owner
- Notes: Approved after the documented multi-query corpus insufficiency audit on 2026-08-14.

- Expected response: Insufficient evidence in this frozen abstract corpus.
- Strict query tokens: peptide `ipamorelin`; claim `muscle, human`.
- Strict conjunction candidates requiring manual review: `41476424`, `42578445`
- Manually audited PMIDs: `10496658`, `32257855`, `41476424`, `42021992`, `42395176`, `42578445`
- Caveat: Strict matches are reviews discussing related evidence and gaps, not trials establishing durable muscle gain in healthy adults; the corpus-only conclusion is not universal.

## qa20 — unanswerable (holdout)

**Question:** Is PT-141 safe and effective for long-term treatment of low libido in men?

- Decision: [x] Approve  [ ] Edit  [ ] Reject
- Reviewer: project_owner
- Notes: Approved after the documented multi-query corpus insufficiency audit on 2026-08-14.

- Expected response: Insufficient evidence in this frozen abstract corpus.
- Strict query tokens: peptide `pt, 141`; claim `libido, men, long, term`.
- Strict conjunction matches: none.
- Manually audited PMIDs: `12851303`, `14963471`, `14999221`, `15833522`, `17584134`, `42021992`
- Caveat: No strict long-term male-libido match was found; acute erectile response, low libido, and long-term treatment are distinct outcomes, and the corpus-only conclusion is not universal.
