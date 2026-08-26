# Third-Party Literature Data Notice

The MIT license in [`LICENSE`](LICENSE) applies to the original Peptide-RAG
software and project documentation. It does **not** grant rights to third-party
literature content.

This repository contains a frozen educational evaluation corpus built from
PubMed citation records, titles, and abstracts, together with derivative chunks,
review packets, retrieval contexts, embeddings, and screenshots. Peptide-RAG
does not claim ownership of that literature. The National Library of Medicine
(NLM) does not claim copyright in PubMed abstracts, but publishers or authors
may hold copyright in individual records. NCBI does not endorse this project.

Users who reproduce, redistribute, or make commercial use of the literature
content are responsible for determining and following the applicable rights and
restrictions. See the [NCBI website and data usage policies and
disclaimers](https://www.ncbi.nlm.nih.gov/home/about/policies/).

The included corpus exists to make the assignment's frozen judgments, measured
retrieval results, and offline evaluation reproducible. Each search result links
back to its PubMed record. To build a fresh corpus directly from NCBI instead,
run `scripts/fetch_pubmed.py` as documented in [`README.md`](README.md) and
comply with the NCBI E-utilities usage requirements.

Questions about repository content or a rights-holder removal request should be
opened through the repository's GitHub issue tracker without including private
or sensitive information.
