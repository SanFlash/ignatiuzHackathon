# Fixes and delivery notes

## Branch baseline

- Input: `adaptive-assessment (3).zip`.
- Input SHA-256: `577f903627c1994f5c75a7b1486753bd9d47743aae55efac50278b035757cdf2`.
- Baseline commit: `2279f84090ed8d7ca0ecca1f9290836d39f03e18`.
- Fix branch: `fix/question-speed-and-reliability`.
- The source ZIP matched the earlier OpenAI-only build byte for byte. Baseline tests: 93 passed.
- The delivery includes full source and a portable Git bundle containing both baseline and fix branches.

## Performance measurements

Controlled experiment: 100 ms per simulated provider request, 5 ms per repository read, median of three runs. Human answer time and actual network latency are excluded. The same benchmark script was run against both branches.

| Scenario | Before | After | Reduction | Reads before → after |
|---|---:|---:|---:|---:|
| Eligible written-answer transition | 241.92 ms | 126.66 ms | 47.6% | 8 → 5 |
| Complete 15-question assessment | 2836.62 ms | 2110.23 ms | 25.6% | 121 → 77 |

API calls for the full set stayed at **15 question-generation calls and 7 written-evaluation calls** in this test trajectory. No extra alternatives were generated. Other answer paths can have different counts. These measurements do not guarantee real OpenAI speed.

## Changes

1. Overlap grading and generation only when the hard competency-coverage rule proves next selection cannot depend on the pending grade. The answer is supplied to both calls. Grade-dependent turns remain sequential.
2. Build response JSON from committed state instead of reloading the attempt, assessment and bank. Candidate-owned requests avoid an additional duplicate lookup.
3. Update the question and progress in place using vanilla JavaScript and the existing JSON route. The server still controls all scoring and selection; ordinary form submission works without fetch.
4. Preserve the answer on validation/network failures. A lost response triggers a read-only progress check, not another answer submission. An explicit progress check is available when save status is uncertain.
5. Reject duplicate in-flight work before paid API calls within the same service process. Different attempts remain concurrent. Existing database version/unique constraints protect cross-process persistence.
6. Normalize generated, legacy and recruiter-entered MCQ options and answer keys for outer whitespace. Reject blank or duplicate generated rubric concepts.
7. Pass the full question to written evaluation; the previous 1,000-character truncation could omit an important final requirement.
8. Compare UTF-8 encoded CSRF/password values so Unicode input does not raise the TypeError that previously became a generic 503.
9. Show 100% progress for completed assessments even when they end before the maximum count.
10. Cache CSS/JavaScript using content-versioned asset URLs. Candidate pages and API data remain no-store.

## Verification

- Final Python regression output: `docs/pytest-results.txt`.
- Seven DOM interaction checks passed: `docs/ui-validation.json`. This is DOM simulation, not visual browser validation.
- Actual Flask HTTP flow passed: 15 unique questions, report, late-answer rejection and recruiter creation (`docs/http-validation.json`).
- Compilation, dependency consistency and database doctor succeeded. No extra application dependency or frontend build system was added.

## Run the fixed source

Extract into a new folder, copy your `.env` containing `OPENAI_API_KEY`, install requirements in a virtual environment, then run `python run.py --demo`. See README for exact Windows and Linux/macOS commands.

Optional branch checkout from the extracted folder:

```bash
git clone branch-history.bundle aptiva-git
cd aptiva-git
git switch fix/question-speed-and-reliability
```

## Remaining limits

No live OpenAI key or Supabase project was supplied. Real provider speed/quality and database transactions have not been verified. Desktop/mobile visual rendering and print output have not been inspected in a real browser. Multiple server processes may still make redundant provider calls before the database rejects a duplicate; distributed exactly-once billing is not claimed. The implemented fixes address reproduced defects and measured bottlenecks, not a guarantee that every possible issue is absent.
