# Validation — OpenAI-only build

## Implemented and verified locally

- `OPENAI_API_KEY` alone selects the official OpenAI endpoint, defaults to `gpt-4o-mini`, generates questions and evaluates written answers.
- Legacy provider keys and alternate base URL settings do not change the provider.
- Demo storage is the default; Supabase remains optional. `run.py --demo` overrides stale database settings explicitly.
- Question requests cap output at 360 tokens; written evaluation requests cap it at 240.
- Written answers are capped at 3,000 characters; generation context uses an 800-character answer excerpt and bounded recent context.
- Refresh, MCQ grading, report generation and interview follow-ups make no AI requests.
- Provider errors, malformed outputs and timeouts fall back locally; network/JSON failure cooldown avoids repeated calls for 60 seconds.
- Stored generated questions are displayed and graded from the same private snapshot. Server-selected skill, difficulty, identity and points cannot be changed by provider output.
- Existing CSRF, candidate ownership, duplicate/completion checks, bank locking, atomic persistence and safe diagnostic codes remain covered.

## Actual checks

Python 3.13.15. Dependencies installed; compilation, pytest, dependency checks and the live Flask HTTP walkthrough executed. See `pytest-results.txt` for the final regression count/timing and `http-validation.json` for the live result.

The complete generated-question AND AI-graded-answer flow was exercised using the real OpenAI SDK against `httpx.MockTransport`. The test verifies the official endpoint, token caps, exact displayed-question grading, full report, and number of generation/evaluation calls. This is a simulated provider test, not a live API call.

The live HTTP test uses the actual Flask server in demo/local fallback mode: 15 unique questions, 43 successful HTTP responses, completion/report creation, rejection of late submissions and recruiter creation.

## Limitations

No live OpenAI key was supplied, so account/model access, real response quality and actual token usage/cost remain unverified. Supabase schema/RPC execution and visual desktop/mobile browser validation also remain unverified. The managed browser previously blocked localhost. No claim of perfect operation in every environment is made.

## Relevant fixes retained

- Installed the requested Python runtime.
- Corrected initial test-scaffolding paths and made HTTP test-server startup/teardown deterministic.
- Added SOCKS support to the existing HTTPX transport and a safe AI-client initialization fallback.
- Repaired interrupted demo seeding without duplicating questions.
- Added explicit database mode, a doctor command and categorized 503 error references.
- Removed recruiter navigation from candidate focus mode.

The user's earlier 503 was not accompanied by its failing request/log; its exact cause remains unconfirmed. The diagnostics now distinguish database schema/access/connectivity errors and other application failures without exposing secrets.
