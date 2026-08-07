from __future__ import annotations

import html
import json
from typing import Any


def render_dashboard_html(snapshot: dict[str, Any]) -> str:
    counts = snapshot.get("counts", {})
    needs_review = snapshot.get("needs_review", [])
    failures = snapshot.get("failures", [])
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>AI Email Agent Review Dashboard</title>
    <style>
      body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 24px; color: #111827; }}
      h1, h2 {{ margin-bottom: 8px; }}
      .counts {{ display: flex; gap: 12px; flex-wrap: wrap; margin: 16px 0 24px; }}
      .card {{ background: #f3f4f6; border-radius: 10px; padding: 12px 16px; min-width: 180px; }}
      table {{ width: 100%; border-collapse: collapse; margin-bottom: 28px; }}
      th, td {{ border: 1px solid #e5e7eb; padding: 10px; vertical-align: top; text-align: left; }}
      th {{ background: #f9fafb; }}
      code {{ white-space: nowrap; }}
      .muted {{ color: #6b7280; }}
    </style>
  </head>
  <body>
    <h1>AI Email Agent Review Dashboard</h1>
    <p class="muted">Review ambiguous interview invites and recent processing failures.</p>
    <div class="counts">
      <div class="card"><strong>Needs review</strong><div>{_escape(counts.get("needs_review_count", 0))}</div></div>
      <div class="card"><strong>Failures</strong><div>{_escape(counts.get("failed_count", 0))}</div></div>
      <div class="card"><strong>Processed</strong><div>{_escape(counts.get("processed_count", 0))}</div></div>
    </div>
    <h2>Ambiguous interview invites</h2>
    {_render_needs_review_table(needs_review)}
    <h2>Recent failures</h2>
    {_render_failures_table(failures)}
  </body>
</html>
"""


def render_dashboard_json(snapshot: dict[str, Any]) -> bytes:
    return json.dumps(snapshot, ensure_ascii=True).encode("utf-8")


def _render_needs_review_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "<p>No invites currently require review.</p>"
    rendered_rows = []
    for row in rows:
        rendered_rows.append(
            "<tr>"
            f"<td><code>{_escape(row.get('gmail_message_id'))}</code></td>"
            f"<td>{_escape(row.get('subject'))}<div class=\"muted\">{_escape(row.get('sender'))}</div></td>"
            f"<td>{_escape(row.get('company'))}<div class=\"muted\">{_escape(row.get('job_title'))}</div></td>"
            f"<td>{_escape(row.get('interview_start'))}<div class=\"muted\">{_escape(row.get('interview_end'))}</div></td>"
            f"<td>{_escape(row.get('action'))}<div class=\"muted\">{_escape(row.get('missing_fields'))}</div></td>"
            f"<td>{_escape(row.get('review_reason'))}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr>"
        "<th>Message</th><th>Email</th><th>Company / Role</th><th>Schedule</th><th>Action</th><th>Reason</th>"
        "</tr></thead><tbody>"
        + "".join(rendered_rows)
        + "</tbody></table>"
    )


def _render_failures_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "<p>No recent failures.</p>"
    rendered_rows = []
    for row in rows:
        rendered_rows.append(
            "<tr>"
            f"<td><code>{_escape(row.get('gmail_message_id'))}</code></td>"
            f"<td>{_escape(row.get('subject'))}<div class=\"muted\">{_escape(row.get('sender'))}</div></td>"
            f"<td>{_escape(row.get('retry_count'))}</td>"
            f"<td>{_escape(row.get('last_error'))}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr>"
        "<th>Message</th><th>Email</th><th>Retries</th><th>Error</th>"
        "</tr></thead><tbody>"
        + "".join(rendered_rows)
        + "</tbody></table>"
    )


def _escape(value: Any) -> str:
    return html.escape("" if value is None else str(value))
