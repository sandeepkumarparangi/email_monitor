# AI Email Monitoring and Automation Agent (Python)

Automates:

1. Gmail polling every 5 minutes
2. Email classification + Gmail labeling
3. Interview extraction (date/time/timezone/link/instructions/recruiter)
4. Google Calendar create/update with duplicate prevention
5. Interview backup records + attachment backup (Google Drive or local provider)
6. SQLite idempotency, processing state, and review dashboard data

---

## Project Structure

```text
app/
  config.py
  logging_utils.py
  retry_utils.py
  models.py
  database.py
  google_auth.py
  gmail_service.py
  classifier.py
  interview_extractor.py
  calendar_service.py
  cloud_storage.py
  processor.py
  scheduler.py
  init_db.py
  main.py
  mock_runner.py
tests/
  mock_emails.json
  fakes.py
  test_classifier.py
  test_interview_extractor.py
  test_timezone_conversion.py
  test_duplicate_detection.py
  test_cloud_backup.py
  test_workflow.py
.env.example
.gitignore
requirements.txt
README.md
```

---

## 1) Google OAuth Setup

1. Go to Google Cloud Console.
2. Create a project (or reuse one).
3. Enable APIs:
   - Gmail API
   - Google Calendar API
   - Google Drive API
4. Configure OAuth consent screen (External or Internal as needed).
5. Create OAuth Client ID:
   - Application type: Desktop app
6. Download the client JSON and save as `credentials.json` in project root.

Least-privilege scopes used:

- Gmail read/modify (read + labels): `gmail.readonly`, `gmail.modify`
- Calendar events only: `calendar.events`
- Drive app-managed files: `drive.file`

---

## 2) Gmail API Setup Notes

- Ensure Gmail API is enabled in your GCP project.
- On first run, browser OAuth prompts for Gmail access.
- The app reads inbox messages and applies labels only.
- It does **not** send/delete email.

---

## 3) Google Calendar API Setup Notes

- Ensure Calendar API is enabled.
- Set `CALENDAR_ID=primary` (or your target calendar ID).
- Events include:
  - Title: `Interview - {Company} - {Job Title}`
  - Description with recruiter, original timezone, meeting data, Gmail references
  - Reminders: 24h and 1h before
- Duplicate prevention:
  - Gmail Message ID as private extended property
  - Thread-based update path
  - Heuristic duplicate lookup by company/time/meeting URL

---

## 4) Google Drive / Cloud Backup Setup

### Preferred: Google Drive (free-tier friendly)

- Keep `STORAGE_PROVIDER=drive`
- Ensure Drive API enabled and scope granted.
- Backups saved under `DRIVE_ROOT_FOLDER` (default: `Job Search`)

### Alternative Provider-Friendly Design

- Set `STORAGE_PROVIDER=local` for local filesystem backups.
- Storage layer is abstracted (`CloudStorageProvider`) so another provider can be added.

---

## 5) Local Installation (macOS)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Then edit `.env` as needed.

---

## 6) Database Initialization

```bash
python -m app.init_db
```

Creates SQLite tables:

- `emails`
- `interviews`

Idempotency:

- `emails.gmail_message_id` is primary key
- `processed_at` prevents reprocessing same message
- failed emails are retained with retry metadata

---

## 7) Runtime Modes

The agent supports three runtime modes:

- `worker` - default long-running Gmail poller
- `web` - Railway-friendly mode with the worker plus a lightweight HTTP server
- `healthcheck` - one-shot startup/DB readiness check

Set `APP_RUNTIME_MODE` in `.env` or pass `--mode`.

### Worker mode

```bash
python -m app.main --mode worker
```

### Web mode

```bash
python -m app.main --mode web
```

This serves:

- `GET /healthz` - liveness/worker health
- `GET /dashboard` - HTML review dashboard
- `GET /api/dashboard` - JSON snapshot for ambiguous invites and failures
- `POST /api/reprocess` - manually reprocess one Gmail message by `gmail_message_id`

### Healthcheck mode

```bash
python -m app.main --mode healthcheck
```

---

## 8) Run the Agent Locally

Start:

```bash
python -m app.main --mode worker
```

This runs continuously and checks Gmail every `CHECK_INTERVAL_MINUTES` (default 5). For local dashboard access, use `--mode web`.

Stop:

- Press `Ctrl + C`

Optional background run:

```bash
nohup python -m app.main > logs.out 2>&1 &
```

Stop background process:

```bash
ps aux | grep "python -m app.main"
kill <PID>
```

---

## 9) Railway Deployment

This repo now includes Railway-ready files:

- [Procfile](/Users/sandeepkumarparangi/Projects/ai-email-agent.worktrees/ai-email-agent-prod-improvements/Procfile)
- [railway.toml](/Users/sandeepkumarparangi/Projects/ai-email-agent.worktrees/ai-email-agent-prod-improvements/railway.toml)
- [scripts/start_railway.sh](/Users/sandeepkumarparangi/Projects/ai-email-agent.worktrees/ai-email-agent-prod-improvements/scripts/start_railway.sh)

Recommended Railway environment variables:

- `APP_RUNTIME_MODE=web`
- `PORT` provided by Railway
- `BIND_HOST=0.0.0.0`
- `DATABASE_PATH=/data/agent_state.db` if using a mounted persistent volume
- `GOOGLE_CREDENTIALS_JSON` or `GOOGLE_CREDENTIALS_JSON_B64`
- `GOOGLE_TOKEN_JSON` or `GOOGLE_TOKEN_JSON_B64`
- `DASHBOARD_ADMIN_TOKEN` for protected manual reprocessing
- your normal non-secret agent settings from `.env.example`

Railway will start the app in web mode and use `/healthz` for health checks.

Important:

- Railway is a non-interactive environment, so it cannot complete the local browser OAuth flow.
- Generate your Google OAuth token locally first, then store the resulting `credentials.json` and `token.json` content in Railway variables as raw JSON or base64-encoded JSON.
- If these variables are missing, the app now fails with a clear configuration error instead of a generic file-not-found stack trace.

To manually retry an already-processed email after a parser fix or config fix:

```bash
curl -X POST "https://<your-railway-domain>/api/reprocess" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: <your-dashboard-admin-token>" \
  -d '{"gmail_message_id":"19fa0f67bce5a977"}'
```

This is useful when a message was previously marked `Processed-By-AI-Agent` or stored as `needs_review` before a fix was deployed.

---

## 10) Run as a macOS launchd Service (Auto-start)

From the project root:

```bash
chmod +x scripts/install_launchd.sh scripts/uninstall_launchd.sh
./scripts/install_launchd.sh
```

Check service status:

```bash
launchctl print gui/$(id -u)/com.ai.email.agent | cat
```

Follow logs:

```bash
tail -f logs/agent.stdout.log
tail -f logs/agent.stderr.log
```

Restart service:

```bash
launchctl kickstart -k gui/$(id -u)/com.ai.email.agent
```

Uninstall/stop service:

```bash
./scripts/uninstall_launchd.sh
```

Note: if you previously uninstalled the service, the installer re-enables the label automatically before bootstrapping it again.

---

## 11) Interview Extraction and Update Handling

The processor now handles more production scheduling cases:

- parses inline or attached `.ics` invites when present
- uses ICS `UID` and `SEQUENCE` to identify updates/reschedules
- matches follow-up messages across thread changes using thread ID, meeting link, calendar UID, and normalized subject
- treats availability requests and incomplete invites as review items instead of creating weak calendar events

---

## 12) Testing Instructions

Install dependencies first, then:

```bash
pytest -q
```

Targeted validation used for the production improvements:

```bash
pytest -q tests/test_interview_extractor.py tests/test_workflow.py tests/test_dashboard.py tests/test_google_auth.py
python -m app.main --mode healthcheck
```

Included tests:

- Email classification
- Interview detection
- Date/time extraction
- Timezone conversion
- Duplicate/idempotency behavior
- Calendar create/update behavior (mocked)
- Cloud backup logic
- End-to-end mock chain:
  `Gmail -> Classification -> Interview Extraction -> Duplicate Check -> Calendar -> Cloud Backup -> DB`

Run offline mock workflow:

```bash
python -m app.mock_runner
```

This uses `tests/mock_emails.json` and fake Gmail/Calendar services.

---

## 13) Reliability and Safety Features

- Structured JSON logging
- Retry with exponential backoff for API operations
- OAuth token refresh via Google auth client
- Duplicate prevention via DB + calendar checks + thread update logic
- ICS-aware update detection using calendar UID / sequence
- Interview ambiguity handling:
  - labels as `Interview - Needs Review`
  - dashboard surfacing for ambiguous invites and failures
  - no calendar event created when critical data missing
- Attachment filename sanitization
- No attachment execution
- No auto-send/no auto-delete behavior

---

## 14) Troubleshooting Guide

### OAuth errors
- Confirm `credentials.json` is valid Desktop OAuth client.
- Delete `token.json` and re-authenticate.
- If you change scopes/features (e.g., enable Drive backups), delete `token.json` and re-run so Google can grant the new scopes.

### Gmail label not appearing
- Verify Gmail scope includes `gmail.modify`.
- Re-run app; labels are auto-created.

### Calendar duplicates
- Check if meeting URL/company changed significantly.
- Verify thread continuity in Gmail (same thread ID for updates).
- If the recruiter sends a new thread, confirm the invite includes the same meeting link or ICS UID.

### Railway healthcheck / dashboard issues
- Confirm `APP_RUNTIME_MODE=web`.
- Confirm Railway can reach `PORT` on `BIND_HOST=0.0.0.0`.
- Check `/healthz` and `/api/dashboard`.

### Drive upload failures
- Confirm Drive API enabled and `drive.file` scope granted.
- Re-authenticate if scope changed.

### Timezone/date parsing issues
- Set correct `LOCAL_TIMEZONE` in `.env`.
- Ambiguous invite emails are intentionally marked for manual review.

---

## 15) Security Notes

- Never hardcode credentials.
- `.env`, `credentials*.json`, `token*.json`, local DB files, and `.venv/` are git-ignored.
- Least-privilege OAuth scopes only.
- No email sending unless explicitly added later.
- No attachment execution.
