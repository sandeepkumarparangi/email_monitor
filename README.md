# AI Email Monitoring and Automation Agent (Python)

Automates:

1. Gmail polling every 5 minutes
2. Email classification + Gmail labeling
3. Interview extraction (date/time/timezone/link/instructions/recruiter)
4. Google Calendar create/update with duplicate prevention
5. Interview backup records + attachment backup (Google Drive or local provider)
6. SQLite idempotency and processing state

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

## 7) Run the Agent

Start:

```bash
python -m app.main
```

This runs continuously and checks Gmail every `CHECK_INTERVAL_MINUTES` (default 5).

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

## 8) Run as a macOS launchd Service (Auto-start)

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

## 9) Testing Instructions

Install dependencies first, then:

```bash
pytest -q
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

## 10) Reliability and Safety Features

- Structured JSON logging
- Retry with exponential backoff for API operations
- OAuth token refresh via Google auth client
- Duplicate prevention via DB + calendar checks + thread update logic
- Interview ambiguity handling:
  - labels as `Interview - Needs Review`
  - no calendar event created when critical data missing
- Attachment filename sanitization
- No attachment execution
- No auto-send/no auto-delete behavior

---

## 11) Troubleshooting Guide

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

### Drive upload failures
- Confirm Drive API enabled and `drive.file` scope granted.
- Re-authenticate if scope changed.

### Timezone/date parsing issues
- Set correct `LOCAL_TIMEZONE` in `.env`.
- Ambiguous invite emails are intentionally marked for manual review.

---

## 12) Security Notes

- Never hardcode credentials.
- `.env`, `credentials.json`, `token.json`, and DB files are git-ignored.
- Least-privilege OAuth scopes only.
- No email sending unless explicitly added later.
- No attachment execution.
