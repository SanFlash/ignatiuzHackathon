# Deploy Aptiva on Render

## Blueprint deployment (recommended)

1. Sign in at https://dashboard.render.com and connect GitHub with access to `SanFlash/ignatiuzHackathon`.
2. Select **New > Blueprint**, choose this repository and branch `fix/question-speed-and-reliability`. Use `render.yaml` at the repository root.
3. Enter a strong `RECRUITER_PASSWORD` when prompted, review the free web service, then deploy. Render generates `SECRET_KEY` automatically.
4. In the web service's **Environment**, add `OPENAI_API_KEY` if you want AI-generated questions and written grading. Without it, the seeded bank and deterministic evaluator work immediately. Save/redeploy after changing variables.
5. Open the service's public HTTPS URL. `/health` must return `{"status":"ok"}`. Open `/recruiter`, enter the password, then start an assessment from the landing page and complete it.

The GitHub personal access token is for uploading code only. Do not add it to Render or commit it. Connect GitHub through Render's own authorization flow.

## Manual web service creation

If you prefer **New > Web Service**, connect the same repository and explicitly select the fixed branch. Use:

| Setting | Value |
| --- | --- |
| Runtime | Python 3 |
| Root directory | Leave blank |
| Build command | `pip install -r requirements-render.txt` |
| Start command | `gunicorn --config gunicorn.conf.py run:app` |
| Health check | `/health` |
| Instance | Free for demonstration |

Set `SECRET_KEY` to a stable random value, `RECRUITER_PASSWORD` to your recruiter login password, `COOKIE_SECURE=true`, and `DATABASE_MODE=demo`. Optionally add `OPENAI_API_KEY` and `OPENAI_MODEL=gpt-4o-mini`. Generate a secret locally with `python -c "import secrets; print(secrets.token_hex(32))"`.

The project pins Python 3.13.15 in `.python-version`. Remove any conflicting `PYTHON_VERSION` service variable or set it to the same version. Render's `PORT` is read by Gunicorn; do not use `python run.py` as the production start command.

## Storage, performance, and production

Demo mode stores data in one process. Gunicorn uses one worker with eight threads so requests share attempts and can handle concurrent AI waits. Do not increase worker count or service instances while using demo mode. Restarts, deployments and free-service spin-down discard demo assessments, answers and reports. Use demo candidate data only.

For persistent data, apply `supabase/schema.sql` in your Supabase SQL editor, then set `DATABASE_MODE=supabase`, `SUPABASE_URL`, and the server-side `SUPABASE_KEY` in Render. Create your assessment in the recruiter dashboard or explicitly run `python -m flask --app run:app seed-demo` from an environment connected to the same database. Startup intentionally does not modify remote data. Keep the one-worker default unless you have load-tested your deployment and database concurrency.

Free services can spin down when idle, making the first visit slow. For dependable response times, choose a paid instance in Render; code changes cannot eliminate platform cold starts. AI latency still depends on OpenAI. Health checks deliberately test process liveness without making paid model calls or requiring database availability.

This remains an MVP: add organization-scoped authentication, rate limiting, monitoring and backup policies before public recruitment use. A recruiter password does not rate-limit public candidate starts or their API usage.

## Troubleshooting

- **Build failure:** verify branch, root directory, Python version, and `requirements-render.txt`.
- **No bound port / failed health check:** use the exact Gunicorn start command and `/health`; inspect server startup logs.
- **Missing secret/password error:** set both required values in Render Environment and redeploy.
- **Invalid/expired form:** use HTTPS and a stable `SECRET_KEY`; open a fresh assessment after a demo restart. Keep `COOKIE_SECURE=false` for local HTTP only.
- **503/database errors:** check Supabase variables and schema; run `python -m flask --app run:app doctor` in the configured environment. `/health` succeeding does not prove database availability.
- **AI fallback:** check the key, model access and OpenAI quota. Never paste a key into logs or frontend JavaScript.

## References

- [Render Flask deployment](https://render.com/docs/deploy-flask)
- [Blueprint specification](https://render.com/docs/blueprint-spec)
- [Python version selection](https://render.com/docs/python-version)
- [Free-service limitations](https://render.com/docs/free)

## Local validation for this update

- Python 3.13.15; Render dependencies installed successfully.
- 115 pytest tests passed, including health isolation, HTTPS cookie behavior, recruiter protection and required production credentials.
- Gunicorn configuration ran the complete HTTP flow: 45 successful responses, 15 unique questions, login, report generation, recruiter creation, and rejection of a completed attempt's answer.
- Compile checks, dependency checks and YAML parsing/configuration checks passed.
- No live Render deployment or Render API schema validation was performed. Live OpenAI and Supabase checks still require those service credentials.

The repository's `downloads/adaptive-assessment-fixed.zip` is the packaged source snapshot plus portable Git history through the Render source commit. The later archive-upload commit is not embedded in that snapshot.
