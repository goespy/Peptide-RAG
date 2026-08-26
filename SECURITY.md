# Security Policy

Peptide-RAG is a research-literature demonstration, not a medical service. Do
not submit health information, credentials, or other sensitive data in a public
issue.

For a suspected vulnerability, use GitHub's private vulnerability-reporting
feature when available. If that feature is unavailable, open a minimal public
issue requesting a private contact channel without including exploit details or
secrets.

The application intentionally keeps provider keys server-side, avoids raw query
logging, limits query length and result counts, rate-limits public endpoints,
and fails closed to retrieved evidence when answer generation is unavailable.
Security reports should identify the affected revision and provide only the
minimum reproduction information needed to investigate safely.
