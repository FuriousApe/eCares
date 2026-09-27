"""Failure:

(a) a duplicate `patient.changed` Kafka message for an already-evaluated
    patient must create no duplicate task -- a real `aiokafka` producer
    publishes the same message twice, and the tasks table is diffed before
    and after.
(b) stopping the `engine` container mid-run and restarting it must still
    converge to the correct final state (matching the oracle) once it
    catches up -- "at least once" delivery plus the idempotency key are what
    make this safe.
"""

from __future__ import annotations

import json
import time

import pytest
import sqlalchemy as sa
from aiokafka import AIOKafkaProducer

from libs.common.grpc_gen import dataservice_pb2 as pb
from libs.common.settings import get_settings
from tests.integration.support import (
    DEFAULT_AS_OF,
    compose,
    run_oracle,
    snapshot_tasks,
    wait_for_tasks_to_settle,
)


async def _publish_duplicate_patient_changed(patient_id: str) -> None:
    settings = get_settings()
    producer = AIOKafkaProducer(bootstrap_servers=settings.kafka_bootstrap_servers)
    await producer.start()
    try:
        payload = json.dumps({"patient_id": patient_id}).encode()
        key = patient_id.encode()
        # The literal duplicate: same key, same value, sent twice.
        await producer.send_and_wait(settings.kafka_topic_patient_changed, value=payload, key=key)
        await producer.send_and_wait(settings.kafka_topic_patient_changed, value=payload, key=key)
    finally:
        await producer.stop()


async def test_duplicate_kafka_message_creates_no_duplicate_task(mysql_engine):
    with mysql_engine.connect() as conn:
        patient_id = conn.execute(
            sa.text("SELECT patient_id FROM patients ORDER BY patient_id LIMIT 1")
        ).scalar_one()

    wait_for_tasks_to_settle(mysql_engine)
    before = snapshot_tasks(mysql_engine)

    await _publish_duplicate_patient_changed(patient_id)
    wait_for_tasks_to_settle(mysql_engine)
    after = snapshot_tasks(mysql_engine)

    # A duplicate message re-evaluates the same, unchanged patient snapshot,
    # which produces the same idempotency key as whatever prior evaluation
    # already applied it -- the second (and, here, third) delivery must
    # apply nothing.
    assert after == before


@pytest.mark.slow
def test_engine_restart_mid_run_still_converges(
    grpc_stub, mysql_engine, scheduler_client, clinical_client
):
    grpc_stub.EnqueueAllPatients(pb.EnqueueAllPatientsRequest())
    # A short, deliberate grace period so the engine has actually started
    # consuming/processing before it gets stopped -- this is what makes the
    # stop a "mid-run" interruption rather than "stopped before it started".
    time.sleep(2.0)

    stop = compose("stop", "engine")
    assert stop.returncode == 0, f"docker compose stop engine failed: {stop.stderr}"
    start = compose("start", "engine")
    assert start.returncode == 0, f"docker compose start engine failed: {start.stderr}"

    wait_for_tasks_to_settle(mysql_engine, timeout=180.0)

    # Convergence, checked two ways: (1) against a fresh oracle run at the
    # unchanged 2026-04-08 as-of date, and (2) a second full evaluation is a
    # no-op, reusing the idempotency guarantee as an independent signal that
    # the first run actually finished rather than silently half-applying.
    expected = run_oracle(DEFAULT_AS_OF)

    def _paginate(client) -> list[dict]:
        items: list[dict] = []
        cursor = None
        while True:
            params = {"limit": 200}
            if cursor:
                params["cursor"] = cursor
            resp = client.get("/tasks", params=params)
            resp.raise_for_status()
            body = resp.json()
            items.extend(body["items"])
            cursor = body.get("next_cursor")
            if not cursor:
                return items

    assert len(_paginate(scheduler_client)) == expected["tasks_scheduling"]
    assert len(_paginate(clinical_client)) == expected["tasks_total"]

    before = snapshot_tasks(mysql_engine)
    grpc_stub.EnqueueAllPatients(pb.EnqueueAllPatientsRequest())
    wait_for_tasks_to_settle(mysql_engine, timeout=180.0)
    after = snapshot_tasks(mysql_engine)
    assert after == before
