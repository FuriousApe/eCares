"""GET /patients, GET /patients/{patient_id}."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from libs.common.grpc_gen import dataservice_pb2 as pb
from libs.common.settings import get_settings
from services.worklist_api import mapping
from services.worklist_api.deps import CallerDep, StubDep
from services.worklist_api.grpc_calls import call
from services.worklist_api.schemas import (
    ListPatientsResponseOut,
    PatientDetailOut,
    PatientWithContextOut,
)

router = APIRouter(tags=["patients"])


@router.get("/patients", response_model=ListPatientsResponseOut)
def list_patients(
    caller: CallerDep,
    stub: StubDep,
    specialty: str | None = None,
    task_type: str | None = None,
    status: str | None = None,
    program: str | None = None,
    tier: str | None = None,
    q: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: str | None = None,
) -> ListPatientsResponseOut:
    req = pb.ListPatientsRequest(role_filter=mapping.role_filter(caller), limit=limit)
    if specialty:
        req.specialty = specialty
    if task_type:
        req.task_type = task_type
    if status:
        req.status = status
    if program:
        req.program = program
    if tier:
        req.tier = tier
    if q:
        req.q = q
    if cursor:
        req.cursor = cursor

    resp = call(stub.ListPatients, req)
    return ListPatientsResponseOut(
        items=[
            PatientWithContextOut(
                patient=mapping.patient_out(item.patient),
                enrollments=[mapping.enrollment_out(e) for e in item.enrollments],
                visible_tasks=[
                    mapping.task_out(t, get_settings().effective_as_of_date())
                    for t in item.visible_tasks
                ],
            )
            for item in resp.items
        ],
        next_cursor=resp.next_cursor if resp.HasField("next_cursor") else None,
    )


@router.get("/patients/{patient_id}", response_model=PatientDetailOut)
def get_patient(patient_id: str, caller: CallerDep, stub: StubDep) -> PatientDetailOut:
    req = pb.GetPatientRequest(patient_id=patient_id, role_filter=mapping.role_filter(caller))
    resp = call(stub.GetPatient, req)
    as_of = get_settings().effective_as_of_date()
    return PatientDetailOut(
        patient=mapping.patient_out(resp.patient),
        enrollments=[mapping.enrollment_out(e) for e in resp.enrollments],
        needs=[mapping.need_out(n) for n in resp.needs],
        visible_tasks=[mapping.task_out(t, as_of) for t in resp.visible_tasks],
    )
