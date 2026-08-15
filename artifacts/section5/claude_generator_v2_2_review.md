# Claude Opus Generator-v2.2 Review

Date: 2026-08-14
Review method: Claude Code subscription, `--model opus`, read-only `Read` and `Grep` tools
Scope excluded: secrets, `.env`, QA/holdout content, provider calls, paid judging, and file modification

## Initial verdict

`CHANGES_REQUIRED` — Opus confirmed that the GPT-only subset flowed correctly
through costing, live execution, offline replay, and reporting, but found that
the diagnostic's default output paths still targeted the preserved generator-v2
artifacts. An explicit `--overwrite` could therefore have erased the negative
Qwen/Gemma evidence that v2.2 claims to preserve.

Opus also noted adjacent missing bindings for the frozen model-catalog hash and
the config's zero-judge declaration.

## Resolution

Codex implemented and tested the following invariants:

- default paths now select the v2.2 config, refreshed catalog, v2.2 outputs, and
  v2.2 summary;
- v2.2 freezes exact, distinct output paths;
- actual QA, development-context, and model-catalog hashes must match the frozen
  config before costing, credentials, calls, or writes;
- the diagnostic must declare exactly zero judge calls;
- selected models remain the frozen config subset across costing, live calls,
  offline replay, usage, and reporting;
- any existing output or summary whose content hash matches a recorded parent
  artifact is protected even when `--overwrite` is present; and
- frozen output paths must remain inside the repository.

A no-network integration test now runs the real default estimator, confirms it
contains only `openai/gpt-oss-20b`, confirms zero judge calls, and proves the
parent generator-v2 hashes do not change.

## Final verdict

`PASS` — Opus found no remaining release blockers and explicitly confirmed that
the silent-clobber, catalog-binding, and judge-binding findings were resolved.

The complete GPT-only conservative estimate remains `$0.01111358`, under the
frozen `$0.02` experiment cap. No paid provider or holdout call occurred during
review or remediation.
