from __future__ import annotations

import logging
import time

import schedule

from app.processor import EmailAutomationProcessor


LOGGER = logging.getLogger(__name__)


class AgentScheduler:
    def __init__(self, processor: EmailAutomationProcessor, interval_minutes: int) -> None:
        self.processor = processor
        self.interval_minutes = interval_minutes

    def start(self) -> None:
        self.processor.run_once()
        schedule.every(self.interval_minutes).minutes.do(self.processor.run_once)
        LOGGER.info("Scheduler started", extra={"status": "running"})
        while True:
            schedule.run_pending()
            time.sleep(1)

