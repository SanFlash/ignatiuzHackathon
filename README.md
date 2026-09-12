# Aptiva — OpenAI Adaptive Assessment

**One API key enables both question generation and written-answer evaluation.** No Supabase account or other AI provider is needed for local use.

1. Install dependencies using the Windows or Linux/macOS commands below.
2. Copy `.env.example` to `.env` and set `OPENAI_API_KEY`.
3. Run `python run.py --demo` with your virtual environment's Python.
4. Open http://127.0.0.1:5000 and start the assessment.

Minimal `.env`:

```env
OPENAI_API_KEY=your-openai-api-key
```

`OPENAI_MODEL` defaults to `gpt-4o-mini`; `DATABASE_MODE` defaults to `demo`. The endpoint is fixed to `https://api.openai.com/v1`. Legacy OpenRouter settings and alternate base URLs are ignored. Remove old settings from your `.env` to keep configuration clear. `--demo` explicitly ignores stale Supabase settings without deleting any database data.

### Low-token behavior

| Operation | AI request |
|---|---|
| Generate each new question | Maximum 360 output tokens |
| Evaluate a written answer | Maximum 240 output tokens |
| Grade an MCQ | Local, zero AI tokens |
| Refresh an existing question | Saved snapshot, zero AI tokens |
| Build report / interview follow-ups | Local, zero AI tokens |

The generation prompt includes only the current skill/difficulty, a short answer excerpt and a few gaps/recent questions. Written answers are limited to 3,000 characters in both the UI and backend. There is no full-chat-history replay. A written-answer turn may make two calls: grading first, then generation at the deterministically updated difficulty. These are request caps, not promised total usage or price.

Timeouts, unavailable credits, bad keys and malformed results use the local bank/evaluator. Network/JSON failures activate a 60-second cooldown; requests have a 12-second timeout and no automatic retries. The report labels evaluation sources. Generated answer keys and grading still require human review.

### If a 503 occurs

Run with `--demo` to remove database setup as a dependency. For persistent storage, run the updated entire `supabase/schema.sql` before using `DATABASE_MODE=supabase`. This includes the saved-question column and atomic RPC upgrade. The error screen now includes a safe category and reference; `python -m flask --app run:app doctor` checks database setup. The exact cause of a remote 503 requires its log.

### API references

The implementation uses [OpenAI Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create) with the [GPT-4o mini](https://developers.openai.com/api/docs/models/gpt-4o-mini) default. Live API access depends on your account/key. Tests use simulated provider responses; no live key was supplied during development.

---

A runnable Python/Flask assessment application with Jinja2, CSS and vanilla JavaScript. No frontend build system, external AI key or database account is needed to run the complete demo.

**Validated runtime: Python 3.13.15. Target: Python 3.13+.**

## Features

- Responsive dark interface: landing page, recruiter workspace, candidate assessment and evidence report.
- Recruiters can create assessments and add MCQ, subjective or future-use coding questions.
- Twenty-five authored Python Backend Developer questions: five competencies, each with difficulty levels 1–5.
- Deterministic adaptive selection based on skill estimate, difficulty match, uncertainty, gaps and coverage.
- MCQ grading and local rubric-based subjective grading; OpenAI answer-aware questions and written-answer evaluation.
- Per-competency skill estimates, confidence heuristics, evidence and targeted interview follow-ups.
- In-memory demo repository or Supabase PostgreSQL persistence.
- Atomic answer/state/report commits, optimistic concurrency and duplicate protection.
- Candidate session ownership, CSRF validation, safe errors, escaped templates, security headers and optional recruiter password.
- Printable report via the browser's Print / Save PDF dialog.

## Quick start — Windows

Install Python 3.13 from python.org, extract the archive, then open PowerShell in the extracted parent directory:

```powershell
cd adaptive-assessment
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe run.py
```

Open **http://127.0.0.1:5000** in your browser. Leave Supabase and AI variables empty for the demo.

These commands directly use the virtual environment's Python, so PowerShell execution-policy changes are unnecessary. Optional activation:

```powershell
.\.venv\Scripts\Activate.ps1
```

For Command Prompt, use `copy .env.example .env` instead of `Copy-Item` and `.venv\Scripts\activate.bat` for optional activation.

## Quick start — Linux/macOS

Install Python 3.13, extract the archive, then:

```bash
cd adaptive-assessment
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
.venv/bin/python run.py
```

Optional activation: `source .venv/bin/activate`. Stop the server with Ctrl+C.

The development server binds to loopback only and disables debug mode. `FLASK_ENV` is documented for compatibility with the requested configuration; Flask 3 does not use it to enable debugging.

## Try the complete workflow

1. Open the landing page and select **Try an assessment**.
2. Enter a test candidate name and begin.
3. Select an MCQ option or write a technical answer, then submit.
4. Notice that competency and difficulty change as evidence accumulates.
5. Complete up to 15 questions in the seeded assessment.
6. Read the score, competency profile, source-labelled answer evidence and interview follow-ups.
7. Open **Recruiter workspace** to review candidate activity and completed reports.
8. Use **Create assessment**, enter competencies and limits, then add questions for each competency.

The candidate's current question is preserved across refreshes. Submissions are final. Multiple tabs cannot submit the same question twice. A repeated request receives HTTP 409; refreshing the attempt shows its latest state.

The bank is locked after the first attempt to avoid changing questions during an assessment. For changes, create a new assessment. Coding questions can be stored, but are explicitly excluded from live selection until a secure execution service is implemented.

## Architecture

```text
Flask route → service → repository → memory / Supabase
                  ↓
          AdaptiveEngine + AIService
```

- `CatalogService`: assessment/question validation and recruiter summaries.
- `AssessmentService`: start, answer, public projection, completion and report orchestration.
- `AdaptiveEngine`: deterministic selection and state transitions; no Flask/database dependency.
- `AIService`: deterministic MCQ/local written scoring, optional LLM, validated structured results and fallback interview questions.
- `Repository`: persistence contract; in-memory implementation uses an `RLock` and deep copies.
- `SupabaseRepository`: real Python SDK calls, explicit pagination and PostgreSQL RPCs for multi-row transactions.

The frontend only submits candidate input. It never supplies scores or chooses the next question. Candidate responses from the server are explicitly whitelisted to exclude correct answers, rubrics and internal state.

## Folder structure

```text
adaptive-assessment/
├── app/
│   ├── __init__.py                 # App factory, configuration, CSRF, safe errors
│   ├── diagnostics.py
│   ├── errors.py
│   ├── routes.py                  # Blueprint and access checks
│   ├── seed.py                    # 25-question demonstration bank
│   ├── repositories/
│   │   ├── repository.py          # Protocol + in-memory persistence
│   │   └── supabase_repository.py
│   ├── services/
│   │   ├── adaptive_engine.py
│   │   ├── ai_service.py
│   │   ├── assessment_service.py
│   │   ├── catalog_service.py
│   │   └── question_service.py
│   ├── templates/
│   │   ├── base.html
│   │   ├── index.html
│   │   ├── recruiter.html
│   │   ├── create_assessment.html
│   │   ├── questions.html
│   │   ├── start.html
│   │   ├── assessment.html
│   │   ├── report.html
│   │   ├── login.html
│   │   └── error.html
│   └── static/
│       ├── style.css
│       └── app.js
├── supabase/schema.sql
├── tests/
│   ├── conftest.py
│   ├── test_adaptive_engine.py
│   ├── test_assessment_service.py
│   ├── test_ai_service.py
│   ├── test_routes.py
│   ├── test_supabase_repository.py
│   ├── test_openai_integration.py
│   └── e2e_http.py
├── docs/
│   ├── adaptive-logic.md
│   ├── VALIDATION.md
│   └── http-validation.json
├── .env.example
├── .gitignore
├── requirements.txt
├── requirements.lock.txt
├── pytest.ini
├── run.py
└── README.md
```

## Environment variables

| Variable | Requirement / behavior |
|---|---|
| `DATABASE_MODE` | Defaults to `demo`. `supabase` enables persistence; `auto` explicitly enables legacy credential-based selection. |
| `FLASK_ENV` | Optional compatibility setting. Debug mode remains off in `run.py`. |
| `SECRET_KEY` | Set a strong random value before sharing. If blank or `change-me`, an ephemeral secret is generated. This invalidates sessions on restart. |
| `SUPABASE_URL` | Leave blank for demo, or set your Supabase project URL. |
| `SUPABASE_KEY` | Server-only Supabase service-role key. Required with the URL; never use it in browser code. |
| `OPENAI_API_KEY` | The only credential needed locally. Enables OpenAI questions and written grading. Missing key uses the local fallback. |
| `OPENAI_MODEL` | Optional; defaults to `gpt-4o-mini`. Select a JSON-capable model available to your OpenAI account. |
| `RECRUITER_PASSWORD` | Optional local MVP workspace password. Blank enables openly accessible demo recruitment tools. Set before sharing. |
| `COOKIE_SECURE` | `false` for local HTTP; `true` with HTTPS. |

Generate a secret using your virtual environment's Python:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Copy it into `.env`. Do not commit `.env`. Backend credentials never appear in templates or static JavaScript. Changing environment variables requires restarting the application.

If only one Supabase variable is set, startup stops with a clear configuration error. A database error does **not** silently switch an existing persistent application into memory mode.

## Supabase setup

1. Create a Supabase project.
2. Open its SQL editor and run the complete `supabase/schema.sql`.
3. Set `DATABASE_MODE=supabase`, `SUPABASE_URL` and a server-only `SUPABASE_KEY` in `.env`.
4. Set a stable `SECRET_KEY` and `RECRUITER_PASSWORD`.
5. Seed the demonstration bank once, or use the recruiter UI to create your own assessments:

Windows:

```powershell
.\.venv\Scripts\python.exe -m flask --app run:app seed-demo
.\.venv\Scripts\python.exe run.py
```

Linux/macOS:

```bash
.venv/bin/python -m flask --app run:app seed-demo
.venv/bin/python run.py
```

Remote databases are never seeded automatically during server startup. Demo memory mode is seeded automatically for convenience.

### Database design

The SQL creates `organizations`, `users`, `jobs`, `competencies`, `assessments`, `questions`, `attempts`, `responses`, and `candidate_reports` with UUID keys, foreign keys, constraints and indexes.

- Assessment creation atomically creates its job and links competencies within one default workspace.
- A database trigger links each question to its competency.
- Candidate creation and attempt creation occur in one transaction.
- `responses` is unique on `(attempt_id, question_id)`; the standalone repository response save method supports upsert on these columns.
- The actual answer workflow uses `commit_assessment_answer`, which locks the attempt, checks the expected version, and commits the response, updated state and final report together. Duplicate/stale submissions are rejected instead of overwriting evidence.
- Row Level Security is enabled on every table. No anonymous/browser policies are installed. Only the backend's service-role key has the intended access.
- RPC execution is revoked from public, anonymous and authenticated client roles and granted to `service_role`.
- The MVP uses one default organization. Real organization isolation requires authenticated tenant routing and policies before multi-tenant deployment.

**Live Supabase persistence was not tested against an account in this build.** SDK contracts were exercised with simulated HTTP responses. Apply the schema and run a real integration smoke test before relying on persistent data.

## OpenAI setup and evaluation safety

Set `OPENAI_API_KEY` and restart. No other AI configuration is required. Question generation preserves server-chosen competency, difficulty, type and points. The generated question and its correct answer/rubric are saved privately on the attempt and graded from that exact snapshot. They never overwrite the shared recruiter bank.

The AI receives technical assessment context and the submitted answer, not the candidate name. Keep sensitive information out of answers and put consent/retention policies in place before real recruitment use. JSON results are validated for finite bounded correctness, expected lists/text and verbatim evidence quotes. The system prompt treats answers as untrusted data, restricts output to technical competency evidence, and prohibits protected-characteristic inference and hiring decisions.

MCQs are graded deterministically against the saved correct answer. Written answers use OpenAI when available, with an explicitly labelled local rubric fallback. Neither local heuristics nor model grading are calibrated employment decisions. Skill updates and next-question selection stay deterministic; only question wording and written evaluation are model-generated.

## Demo mode

When `DATABASE_MODE=demo`, or when auto mode has no Supabase credentials, **DEMO MODE** is displayed. Data is held in memory and lost on restart. Use a single server process: multiple independent memory workers would not share state. No fabricated candidate activity or results are preloaded. The landing page's animated engine diagram is explicitly labelled illustrative.

No OpenAI key means no AI network requests. Installed SDK dependencies are not required to authenticate for demo mode. The local evaluator matches rubric concepts and synonyms and moderates coverage by answer length. It cannot establish semantic correctness, detect all negation or prevent keyword stuffing; it labels its results accordingly.

## Running tests

Windows:

```powershell
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m compileall app run.py
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe tests\e2e_http.py --spawn
```

Linux/macOS:

```bash
.venv/bin/python --version
.venv/bin/python -m compileall app run.py
.venv/bin/python -m pytest -q
.venv/bin/python -m pip check
.venv/bin/python tests/e2e_http.py --spawn
```

The live HTTP test's `--spawn` option starts an isolated demo server on port 5000, waits for readiness, creates test data, executes the flow and shuts down. Stop any existing server on that port first. It uses only Python standard-library networking and the real Flask HTTP server. Without `--spawn`, it targets an already-running local demo server.

`requirements.txt` bounds the direct dependencies, including the HTTPX SOCKS extra. `requirements.lock.txt` records the complete installed Python 3.13 Linux resolution used for validation; it is available for exact reproduction with `pip install -r requirements.lock.txt`. For other platforms, the direct requirements allow platform-specific dependency resolution.

See `docs/VALIDATION.md` for actual results and the visual-validation limitation.

## API / page routes

| Method | Route | Behavior |
|---|---|---|
| GET | `/` | Landing and assessment list |
| GET | `/recruiter` | Workspace; optional password gate |
| GET, POST | `/recruiter/login` | Password form / session sign-in |
| POST | `/recruiter/logout` | End recruiter session |
| GET, POST | `/recruiter/assessments/new` | Form / create assessment |
| GET, POST | `/recruiter/assessments/<assessment_id>/questions` | View bank / add question |
| GET, POST | `/assessment/<assessment_id>/start` | Candidate form / create attempt |
| GET | `/assessment/<attempt_id>` | Current question or redirect to report |
| POST | `/assessment/<attempt_id>/answer` | Validate answer and advance |
| GET | `/report/<attempt_id>` | Completed evidence report |
| GET | `/api/attempt/<attempt_id>` | Candidate-safe JSON projection |

The start GET has no attempt-creation side effect. The start POST takes `candidate_name` and `csrf_token`. After start, the same browser session owns the attempt. Recruiter sessions can review attempts. The last 30 started attempt IDs are retained in the candidate session; this is an MVP convenience, not durable authentication.

Answer POST accepts a form or JSON. JSON example:

```json
{"question_id": "current-question-uuid", "answer": "Exact option text or written answer"}
```

For JSON, supply `X-CSRF-Token` from the current session's form and retain the session cookie. Form submissions include the hidden `csrf_token`. JSON success returns the same candidate-safe shape as GET `/api/attempt/<id>`; normal form submission redirects to the next page/report. API errors use `{"error":"safe message"}`.

Common responses: 400 invalid input/CSRF; 403 session access denied; 404 unknown item; 409 stale/duplicate/completed answer or unavailable report; 413 oversized body; 503 dependency failure. Technical traceback frames are logged server-side; end users never receive stack traces or credential-bearing exception text.

## Adaptive algorithm

Initial state per competency: level **2.5**, evidence confidence **0.15**, count **0**.

Selection first removes answered and unsupported coding questions. A coverage guard restricts selection to competencies with the least evidence among those with available questions. Remaining candidates receive:

```text
0.42 × difficulty match
+ 0.20 × skill gap
+ 0.20 × uncertainty
+ 0.13 × coverage priority
+ 0.05 × assessment priority
```

A stable ID tie-break ensures deterministic replay. Correct answers tend to increase the estimate; weak answers lower it. Difficulty follows that estimate while coverage prevents one competency from dominating. The hard coverage guard is intentionally stronger than a soft repetition penalty.

Completion occurs at the question cap, on pool exhaustion, or when every skill has at least two observations, every confidence exceeds the target and at least `max(4, 2 × competency_count)` questions have been answered. Small pools can finish before the minimum only because no supported questions remain; the report explicitly says pool exhausted.

Detailed equations, limitations and a worked example are in `docs/adaptive-logic.md`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `python` not found | Use `py -3.13` on Windows or `python3.13` on Linux/macOS. |
| `ModuleNotFoundError` | Install requirements with the same virtual-environment Python used to run the server. |
| Port 5000 already used | Stop the other process or use `python -m flask --app run:app run --port 5001`. The HTTP smoke script expects 5000. |
| Demo results disappeared | Memory resets on restart. Configure Supabase for persistence. |
| Form expired | Reload the page. A changed/ephemeral secret invalidates existing sessions. |
| Session not retained locally | Keep `COOKIE_SECURE=false` for local HTTP. |
| 403 opening attempt | Use the browser that started it, or an authenticated recruiter session. |
| Supabase 503 / relation missing | Run the entire schema and check URL, service-role key and server logs. |
| Empty remote landing page | Run the seed CLI once or create an assessment in the workspace. |
| Assessment cannot start | Add at least one MCQ/subjective question per competency; coding-only banks cannot run. |
| Target confidence not reached | Add more questions per competency or raise the question cap. The cap/exhaustion still terminates safely. |
| LLM configured but local score used | Check account access, model, endpoint, timeout and JSON-mode support. Inspect the warning log. |
| Double-click / stale-tab conflict | Reload the assessment. No duplicate evidence was added. |

## Production checklist and security notes

- Replace the shared recruiter password with Supabase Auth, durable candidate identity, RBAC and organization-scoped access.
- Remove open recruiter mode before exposing the application. In local demo mode, visitors can enter the recruiter workspace and inspect answers; it is not an exam-security boundary.
- Keep a stable secret, HTTPS, secure cookies, protected environment configuration and restricted service credentials.
- Add login/assessment rate limiting, abuse protection, invitation expiry, attempt policies and an audit trail.
- Keep existing CSRF, escaped templates, input validation, server-side scoring, no-store responses and restrictive CSP.
- Use a production WSGI server and Supabase, not Flask's development server or multiprocess in-memory mode.
- Test real PostgreSQL RPC transactions, database outages and multi-worker concurrency under load.
- Define consent, privacy, retention/deletion and access policies for candidate answers and external AI evaluation.
- Calibrate questions, rubric weights and adaptive estimates with expert-reviewed data; audit fairness and accessibility.
- Treat overall scores as sampled evidence: candidates may see different questions, so raw percentages are not standardized comparable hiring rankings.
- Manually inspect desktop/mobile browsers, keyboard/screen-reader interactions and printed reports before release.

## Future enhancements

Highest priority: real authenticated tenant/candidate access and a live Supabase integration suite. Next: expert rubric calibration, question versioning/import/edit, richer audit trails and pagination in recruiter views, stronger response-quality validation, and optional AI observability. Coding execution requires a separately sandboxed runner with strict CPU, memory, time and network isolation; do not execute submitted code inside Flask.

## Reference documentation

- [Supabase Python client](https://supabase.com/docs/reference/python/introduction)
- [Supabase Python upsert](https://supabase.com/docs/reference/python/upsert)
- [Supabase Python RPC](https://supabase.com/docs/reference/python/rpc)
- [OpenAI structured outputs introduction](https://openai.com/index/introducing-structured-outputs-in-the-api/)
