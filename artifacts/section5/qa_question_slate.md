# QA Question Slate

Status: approved by the project owner on 2026-08-14

Prepared: 2026-08-14 (America/New_York)

This sheet proposes the exact wording for the 20-case QA oracle. It contains
seven broad answerable questions, eight specific answerable questions, and
five realistic unanswerable questions. All 20 questions received explicit
project-owner approval. Their evidence and review state are recorded in
`data/qa_draft.json`; the generated `data/qa.json` is the frozen oracle.

| ID | Type | Style | Status | Proposed question |
|---|---|---|---|---|
| qa01 | Answerable | Specific | Approved | What effect did BPC-157 have on liver injury in the reported rat models? |
| qa02 | Answerable | Broad | Approved | Does GHK or GHK-Cu help regrow hair? |
| qa03 | Answerable | Broad | Approved | Does TB-500 help injuries or wounds heal? |
| qa04 | Answerable | Broad | Approved | Does ipamorelin increase growth hormone? |
| qa05 | Answerable | Broad | Approved | Does tesamorelin reduce belly fat? |
| qa06 | Answerable | Specific | Approved | What effect did developmental exposure to Epitalon have on adult fruit-fly lifespan? |
| qa07 | Answerable | Broad | Approved | Does MOTS-c help with weight loss or metabolism? |
| qa08 | Answerable | Broad | Approved | Does PT-141 help with erectile dysfunction? |
| qa09 | Answerable | Specific | Approved | What did the rat study report about BPC-157 in experimental stomach and duodenal ulcer models? |
| qa10 | Answerable | Specific | Approved | How did intra-articular GHK-Cu affect graft healing after ACL reconstruction in rats? |
| qa11 | Answerable | Specific | Approved | What peptide did researchers identify as the key ingredient of TB-500, and how is it related to thymosin beta-4? |
| qa12 | Answerable | Broad | Approved | Does ipamorelin reduce body fat? |
| qa13 | Answerable | Specific | Approved | What effects did tesamorelin have on visceral fat and triglycerides in the HIV trial, and what did the trial report about adverse events? |
| qa14 | Answerable | Specific | Approved | How did Epitalon affect evening melatonin and cortisol rhythm in older monkeys? |
| qa15 | Answerable | Specific | Approved | What hypothesis did the authors make about the MOTS-c m.1382A>C variant and Japanese longevity? |
| qa16 | Unanswerable | Realistic claim | Approved after audit | What is the safest effective BPC-157 dose for healing a human tendon injury? |
| qa17 | Unanswerable | Realistic claim | Approved after audit | Does injectable GHK-Cu reverse human skin aging better than topical GHK-Cu? |
| qa18 | Unanswerable | Realistic claim | Approved after audit | Does TB-500 speed recovery after surgery in humans? |
| qa19 | Unanswerable | Realistic claim | Approved after audit | Does ipamorelin cause lasting muscle gain in healthy adults? |
| qa20 | Unanswerable | Realistic claim | Approved after audit | Is PT-141 safe and effective for long-term treatment of low libido in men? |

## Split-integrity intent

Where two cases cover the same peptide, their supporting PMIDs should remain
different across the development and holdout splits. This must be checked when
the pending cases are evidence-bound. The unanswerable cases require a fresh
corpus-wide insufficiency review; keyword absence alone is not proof that a
claim is unsupported.
