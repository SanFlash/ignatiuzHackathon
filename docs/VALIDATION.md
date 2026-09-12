# Validation — uploaded baseline fix branch

The original uploaded branch passed 93 Python tests before edits. The updated result is recorded in `pytest-results.txt`; new coverage includes concurrency eligibility, overlapping calls, single-process duplicate suppression, cross-service atomic commits, simultaneous different candidates, full question context, normalized options, Unicode inputs, completed progress, static caching and lock cleanup after failures.

Seven additional DOM interaction checks passed using an isolated jsdom test harness (a QA-only tool, not an application dependency). They cover JSON question updates, mixed answer controls, focus/progress/CSRF, safe text rendering, double-click suppression, validation errors preserving drafts, lost-response reconciliation and native form fallback. This is DOM simulation, not visual browser verification; see `ui-validation.json`.

The installed Python HTTPX client explicitly supports use across threads. A synchronization-barrier test proves evaluation and generation overlap on eligible turns. A score sweep checks unchanged selection from correctness 0 through 1. Grade-dependent and terminal turns do not use the concurrent path.

Before/after controlled benchmarks use the identical runner against the committed upload baseline and the fix branch, with fixed simulated provider and repository delays. `performance-before.json`, `performance-after.json` and `performance-summary.json` record measured medians and request/read counts. These numbers exclude human answer time and are not live OpenAI latency claims. Run `python tests/benchmark_transitions.py` to reproduce the current-branch experiment.

The actual Flask HTTP server also completed the no-key fallback walkthrough, with 15 unique questions, generated report, rejected late submission and working recruiter creation. See `http-validation.json`. Compilation, dependency checks and the database doctor command succeeded.

## Remaining validation limits

No live OpenAI key or Supabase project was supplied. Real provider speed/quality, model/account permissions and PostgreSQL transactions remain unverified. Visual desktop/mobile and print layout checks remain unperformed; a previous managed browser attempt blocked localhost. The repository includes safe fallback paths, but tests cannot certify the absence of every possible defect or a production security posture.
