"""Ghi fetch_log và trạng thái nguồn vào PostgreSQL.

Mỗi lần ghi dùng session riêng và commit ngay: log và lệnh pause không bị mất khi job lỗi rồi rollback.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import Engine, select, update
from sqlalchemy.orm import Session

from app.contracts import SourceStatus
from app.db.models import DataSource, FetchLog
from ingestion.core.http import FetchLogEntry

log = logging.getLogger(__name__)


class DbFetchLog:
    def __init__(self, engine: Engine, job_id: uuid.UUID):
        self.engine = engine
        self.job_id = job_id

    def record(self, entry: FetchLogEntry) -> None:
        with Session(self.engine) as s:
            s.add(
                FetchLog(
                    job_id=self.job_id,
                    source_id=entry.source_id,
                    url_hash=entry.url_hash,
                    request_url=entry.request_url,
                    http_status=entry.http_status,
                    latency_ms=entry.latency_ms,
                    outcome=entry.outcome,
                )
            )
            s.commit()


class DbSourceStatus:
    def __init__(self, engine: Engine):
        self.engine = engine

    def is_paused(self, source_id: str) -> bool:
        """Không có dòng trong data_sources cũng coi như paused (fail closed): phải seed trước khi crawl."""
        with Session(self.engine) as s:
            status = s.scalar(select(DataSource.status).where(DataSource.source_id == source_id))
        return status != SourceStatus.ACTIVE.value

    def pause(self, source_id: str, reason: str) -> None:
        with Session(self.engine) as s:
            s.execute(
                update(DataSource).where(DataSource.source_id == source_id).values(status=SourceStatus.PAUSED.value)
            )
            s.commit()
        log.warning("data_sources.%s -> paused (%s)", source_id, reason)
