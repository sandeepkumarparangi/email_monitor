from __future__ import annotations

import logging
import time
from threading import Thread

import schedule

from app.processor import EmailAutomationProcessor


LOGGER = logging.getLogger(__name__)


class AgentScheduler:
    def __init__(self, processor: EmailAutomationProcessor, interval_minutes: int) -> None:
        self.processor = processor
        self.interval_minutes = interval_minutes
        self._scheduler = schedule.Scheduler()

    def run_forever(self) -> None:
        self.processor.run_once()
        self._scheduler.every(self.interval_minutes).minutes.do(self.processor.run_once)
        LOGGER.info("Scheduler started", extra={"status": "running"})
        while True:
            self._scheduler.run_pending()
            time.sleep(1)

    def start(self) -> None:
        self.run_forever()

    def start_background(self) -> Thread:
        thread = Thread(target=self.run_forever, name="agent-scheduler", daemon=True)
        thread.start()
        return thread
