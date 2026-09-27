"""Outbox: writing rows (called from any repository inside its transaction)
and the background relay that publishes them to Kafka.

Implementation choice (documented in full in ASSUMPTIONS.md): a dedicated OS
thread running its own asyncio event loop with `aiokafka`'s
`AIOKafkaProducer`. `aiokafka` is the Kafka dependency already in
pyproject.toml, and the rest of the Data Service is a synchronous gRPC
server — one thread with its own loop is the smallest way to use an
async-only client without moving the whole server to asyncio.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from libs.common.settings import get_settings
from services.data_service.db import session_scope
from services.data_service.models import Outbox

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
BATCH_SIZE = 20
POLL_INTERVAL_SECONDS = 1.0


def write_outbox(session: Session, *, topic: str, event_key: str, payload: dict[str, Any]) -> Outbox:
    row = Outbox(event_id=uuid.uuid4().hex, topic=topic, event_key=event_key, payload=payload)
    session.add(row)
    return row


def _claim_batch(session: Session) -> list[Outbox]:
    """`SELECT ... FOR UPDATE SKIP LOCKED`: safe even if the relay is ever
    split into several worker processes/containers, per the plan."""
    stmt = (
        select(Outbox)
        .where(Outbox.published_at.is_(None))
        .order_by(Outbox.id)
        .limit(BATCH_SIZE)
        .with_for_update(skip_locked=True)
    )
    return list(session.scalars(stmt))


def _encode(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, default=str).encode("utf-8")


async def publish_one(producer: Any, row: Outbox, dlq_topic: str) -> tuple[bool, int]:
    """Returns `(done, new_attempts)`. `done` is True once the row should be
    marked published — including the DLQ case, so a poison message can't
    jam the relay forever after `MAX_ATTEMPTS` failures."""
    attempts = row.attempts + 1
    try:
        await producer.send_and_wait(row.topic, key=row.event_key.encode(), value=_encode(row.payload))
        return True, attempts
    except Exception as exc:  # noqa: BLE001 - any publish failure is handled the same way
        logger.warning("outbox publish failed for id=%s attempt=%s: %s", row.id, attempts, exc)
        if attempts < MAX_ATTEMPTS:
            return False, attempts
        try:
            await producer.send_and_wait(dlq_topic, key=row.event_key.encode(), value=_encode(row.payload))
        except Exception:
            logger.exception("DLQ publish also failed for id=%s; leaving unpublished", row.id)
            return False, attempts
        return True, attempts


async def _relay_loop(stop_event: threading.Event) -> None:
    from aiokafka import AIOKafkaProducer

    settings = get_settings()
    producer = AIOKafkaProducer(bootstrap_servers=settings.kafka_bootstrap_servers)
    await producer.start()
    try:
        while not stop_event.is_set():
            with session_scope() as session:
                rows = _claim_batch(session)
                for row in rows:
                    done, attempts = await publish_one(producer, row, settings.kafka_topic_dlq)
                    row.attempts = attempts
                    if done:
                        row.published_at = datetime.utcnow()
            if not rows:
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
    finally:
        await producer.stop()


def run_relay_forever(stop_event: threading.Event) -> None:
    """Entry point for the relay thread; see `main.py`."""
    asyncio.run(_relay_loop(stop_event))


def start_relay_thread() -> tuple[threading.Thread, threading.Event]:
    stop_event = threading.Event()
    thread = threading.Thread(target=run_relay_forever, args=(stop_event,), daemon=True, name="outbox-relay")
    thread.start()
    return thread, stop_event
