from __future__ import annotations

import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import urlparse

from app.dashboard import render_dashboard_html, render_dashboard_json
from app.config import AppConfig
from app.processor import EmailAutomationProcessor
from app.scheduler import AgentScheduler


LOGGER = logging.getLogger(__name__)


class AgentRuntimeServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        processor: EmailAutomationProcessor,
        scheduler: AgentScheduler,
        scheduler_thread: Thread,
        dashboard_page_size: int,
        app_config: AppConfig,
    ) -> None:
        super().__init__(server_address, RuntimeRequestHandler)
        self.processor = processor
        self.scheduler = scheduler
        self.scheduler_thread = scheduler_thread
        self.dashboard_page_size = dashboard_page_size
        self.app_config = app_config

    def health_payload(self) -> tuple[int, dict[str, object]]:
        snapshot = self.processor.db.get_dashboard_snapshot(limit=1)
        worker_alive = self.scheduler_thread.is_alive()
        status_code = 200 if worker_alive else 503
        return status_code, {
            "status": "ok" if worker_alive else "degraded",
            "worker_alive": worker_alive,
            "counts": snapshot.get("counts", {}),
        }


class RuntimeRequestHandler(BaseHTTPRequestHandler):
    server: AgentRuntimeServer

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/healthz":
            status_code, payload = self.server.health_payload()
            self._write_json(status_code, payload)
            return
        if parsed.path == "/api/dashboard":
            snapshot = self.server.processor.db.get_dashboard_snapshot(limit=self.server.dashboard_page_size)
            self._write_bytes(200, render_dashboard_json(snapshot), "application/json; charset=utf-8")
            return
        if parsed.path in {"/", "/dashboard"}:
            snapshot = self.server.processor.db.get_dashboard_snapshot(limit=self.server.dashboard_page_size)
            self._write_bytes(200, render_dashboard_html(snapshot).encode("utf-8"), "text/html; charset=utf-8")
            return
        self._write_json(404, {"status": "not_found"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/reprocess":
            self._write_json(404, {"status": "not_found"})
            return
        if not self._is_authorized():
            self._write_json(403, {"status": "forbidden", "message": "Set DASHBOARD_ADMIN_TOKEN and provide it as X-Admin-Token."})
            return
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0:
            self._write_json(400, {"status": "bad_request", "message": "Request body must include gmail_message_id."})
            return
        payload = json.loads(self.rfile.read(content_length))
        message_id = str(payload.get("gmail_message_id", "")).strip()
        if not message_id:
            self._write_json(400, {"status": "bad_request", "message": "gmail_message_id is required."})
            return
        try:
            self.server.processor.reprocess_message(message_id)
        except Exception as exc:
            LOGGER.exception("Manual reprocess failed", extra={"gmail_message_id": message_id, "status": "failed"})
            self._write_json(500, {"status": "failed", "gmail_message_id": message_id, "message": str(exc)})
            return
        self._write_json(200, {"status": "ok", "gmail_message_id": message_id})

    def log_message(self, format: str, *args) -> None:
        LOGGER.info("HTTP request", extra={"status": format % args})

    def _is_authorized(self) -> bool:
        expected = self.server.app_config.dashboard_admin_token
        if not expected:
            return False
        return self.headers.get("X-Admin-Token", "") == expected

    def _write_json(self, status_code: int, payload: dict[str, object]) -> None:
        self._write_bytes(status_code, json.dumps(payload, ensure_ascii=True).encode("utf-8"), "application/json; charset=utf-8")

    def _write_bytes(self, status_code: int, body: bytes, content_type: str) -> None:
        self.send_response(status_code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def serve_web_runtime(
    processor: EmailAutomationProcessor,
    app_config: AppConfig,
    bind_host: str,
    port: int,
    dashboard_page_size: int,
    interval_minutes: int,
) -> None:
    scheduler = AgentScheduler(processor=processor, interval_minutes=interval_minutes)
    scheduler_thread = scheduler.start_background()
    server = AgentRuntimeServer(
        (bind_host, port),
        processor=processor,
        scheduler=scheduler,
        scheduler_thread=scheduler_thread,
        dashboard_page_size=dashboard_page_size,
        app_config=app_config,
    )
    LOGGER.info("Runtime server started", extra={"status": "running"})
    server.serve_forever()
