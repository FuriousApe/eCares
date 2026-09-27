from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Patient(_message.Message):
    __slots__ = ("patient_id", "first_name", "last_name", "date_of_birth", "gender", "phone", "language", "pcp_provider_name", "age")
    PATIENT_ID_FIELD_NUMBER: _ClassVar[int]
    FIRST_NAME_FIELD_NUMBER: _ClassVar[int]
    LAST_NAME_FIELD_NUMBER: _ClassVar[int]
    DATE_OF_BIRTH_FIELD_NUMBER: _ClassVar[int]
    GENDER_FIELD_NUMBER: _ClassVar[int]
    PHONE_FIELD_NUMBER: _ClassVar[int]
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    PCP_PROVIDER_NAME_FIELD_NUMBER: _ClassVar[int]
    AGE_FIELD_NUMBER: _ClassVar[int]
    patient_id: str
    first_name: str
    last_name: str
    date_of_birth: str
    gender: str
    phone: str
    language: str
    pcp_provider_name: str
    age: int
    def __init__(self, patient_id: _Optional[str] = ..., first_name: _Optional[str] = ..., last_name: _Optional[str] = ..., date_of_birth: _Optional[str] = ..., gender: _Optional[str] = ..., phone: _Optional[str] = ..., language: _Optional[str] = ..., pcp_provider_name: _Optional[str] = ..., age: _Optional[int] = ...) -> None: ...

class Enrollment(_message.Message):
    __slots__ = ("program_id", "program_version", "tier", "evaluated_at")
    PROGRAM_ID_FIELD_NUMBER: _ClassVar[int]
    PROGRAM_VERSION_FIELD_NUMBER: _ClassVar[int]
    TIER_FIELD_NUMBER: _ClassVar[int]
    EVALUATED_AT_FIELD_NUMBER: _ClassVar[int]
    program_id: str
    program_version: int
    tier: str
    evaluated_at: str
    def __init__(self, program_id: _Optional[str] = ..., program_version: _Optional[int] = ..., tier: _Optional[str] = ..., evaluated_at: _Optional[str] = ...) -> None: ...

class Need(_message.Message):
    __slots__ = ("program_id", "specialty", "cadence_days", "last_visit_date", "due_date", "has_upcoming")
    PROGRAM_ID_FIELD_NUMBER: _ClassVar[int]
    SPECIALTY_FIELD_NUMBER: _ClassVar[int]
    CADENCE_DAYS_FIELD_NUMBER: _ClassVar[int]
    LAST_VISIT_DATE_FIELD_NUMBER: _ClassVar[int]
    DUE_DATE_FIELD_NUMBER: _ClassVar[int]
    HAS_UPCOMING_FIELD_NUMBER: _ClassVar[int]
    program_id: str
    specialty: str
    cadence_days: int
    last_visit_date: str
    due_date: str
    has_upcoming: bool
    def __init__(self, program_id: _Optional[str] = ..., specialty: _Optional[str] = ..., cadence_days: _Optional[int] = ..., last_visit_date: _Optional[str] = ..., due_date: _Optional[str] = ..., has_upcoming: _Optional[bool] = ...) -> None: ...

class Task(_message.Message):
    __slots__ = ("task_id", "patient_id", "program_id", "tier", "specialty", "task_type", "status", "due_date", "days_overdue", "snooze_until", "resolution", "assigned_to", "program_version", "version", "created_at", "updated_at", "patient")
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    PATIENT_ID_FIELD_NUMBER: _ClassVar[int]
    PROGRAM_ID_FIELD_NUMBER: _ClassVar[int]
    TIER_FIELD_NUMBER: _ClassVar[int]
    SPECIALTY_FIELD_NUMBER: _ClassVar[int]
    TASK_TYPE_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    DUE_DATE_FIELD_NUMBER: _ClassVar[int]
    DAYS_OVERDUE_FIELD_NUMBER: _ClassVar[int]
    SNOOZE_UNTIL_FIELD_NUMBER: _ClassVar[int]
    RESOLUTION_FIELD_NUMBER: _ClassVar[int]
    ASSIGNED_TO_FIELD_NUMBER: _ClassVar[int]
    PROGRAM_VERSION_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    UPDATED_AT_FIELD_NUMBER: _ClassVar[int]
    PATIENT_FIELD_NUMBER: _ClassVar[int]
    task_id: int
    patient_id: str
    program_id: str
    tier: str
    specialty: str
    task_type: str
    status: str
    due_date: str
    days_overdue: int
    snooze_until: str
    resolution: str
    assigned_to: str
    program_version: int
    version: int
    created_at: str
    updated_at: str
    patient: Patient
    def __init__(self, task_id: _Optional[int] = ..., patient_id: _Optional[str] = ..., program_id: _Optional[str] = ..., tier: _Optional[str] = ..., specialty: _Optional[str] = ..., task_type: _Optional[str] = ..., status: _Optional[str] = ..., due_date: _Optional[str] = ..., days_overdue: _Optional[int] = ..., snooze_until: _Optional[str] = ..., resolution: _Optional[str] = ..., assigned_to: _Optional[str] = ..., program_version: _Optional[int] = ..., version: _Optional[int] = ..., created_at: _Optional[str] = ..., updated_at: _Optional[str] = ..., patient: _Optional[_Union[Patient, _Mapping]] = ...) -> None: ...

class AuditEntry(_message.Message):
    __slots__ = ("event_id", "occurred_at", "actor", "action", "entity", "patient_id", "before_json", "after_json", "request_id", "result")
    EVENT_ID_FIELD_NUMBER: _ClassVar[int]
    OCCURRED_AT_FIELD_NUMBER: _ClassVar[int]
    ACTOR_FIELD_NUMBER: _ClassVar[int]
    ACTION_FIELD_NUMBER: _ClassVar[int]
    ENTITY_FIELD_NUMBER: _ClassVar[int]
    PATIENT_ID_FIELD_NUMBER: _ClassVar[int]
    BEFORE_JSON_FIELD_NUMBER: _ClassVar[int]
    AFTER_JSON_FIELD_NUMBER: _ClassVar[int]
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    event_id: str
    occurred_at: str
    actor: str
    action: str
    entity: str
    patient_id: str
    before_json: str
    after_json: str
    request_id: str
    result: str
    def __init__(self, event_id: _Optional[str] = ..., occurred_at: _Optional[str] = ..., actor: _Optional[str] = ..., action: _Optional[str] = ..., entity: _Optional[str] = ..., patient_id: _Optional[str] = ..., before_json: _Optional[str] = ..., after_json: _Optional[str] = ..., request_id: _Optional[str] = ..., result: _Optional[str] = ...) -> None: ...

class Program(_message.Message):
    __slots__ = ("program_id", "version", "definition_json", "active")
    PROGRAM_ID_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    DEFINITION_JSON_FIELD_NUMBER: _ClassVar[int]
    ACTIVE_FIELD_NUMBER: _ClassVar[int]
    program_id: str
    version: int
    definition_json: str
    active: bool
    def __init__(self, program_id: _Optional[str] = ..., version: _Optional[int] = ..., definition_json: _Optional[str] = ..., active: _Optional[bool] = ...) -> None: ...

class SyncRun(_message.Message):
    __slots__ = ("run_id", "status", "started_at", "finished_at", "counts_json", "watermarks_json")
    RUN_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    STARTED_AT_FIELD_NUMBER: _ClassVar[int]
    FINISHED_AT_FIELD_NUMBER: _ClassVar[int]
    COUNTS_JSON_FIELD_NUMBER: _ClassVar[int]
    WATERMARKS_JSON_FIELD_NUMBER: _ClassVar[int]
    run_id: str
    status: str
    started_at: str
    finished_at: str
    counts_json: str
    watermarks_json: str
    def __init__(self, run_id: _Optional[str] = ..., status: _Optional[str] = ..., started_at: _Optional[str] = ..., finished_at: _Optional[str] = ..., counts_json: _Optional[str] = ..., watermarks_json: _Optional[str] = ...) -> None: ...

class GetMetaRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class GetMetaResponse(_message.Message):
    __slots__ = ("as_of_date", "last_sync_finished_at", "task_counts_by_status")
    class TaskCountsByStatusEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: int
        def __init__(self, key: _Optional[str] = ..., value: _Optional[int] = ...) -> None: ...
    AS_OF_DATE_FIELD_NUMBER: _ClassVar[int]
    LAST_SYNC_FINISHED_AT_FIELD_NUMBER: _ClassVar[int]
    TASK_COUNTS_BY_STATUS_FIELD_NUMBER: _ClassVar[int]
    as_of_date: str
    last_sync_finished_at: str
    task_counts_by_status: _containers.ScalarMap[str, int]
    def __init__(self, as_of_date: _Optional[str] = ..., last_sync_finished_at: _Optional[str] = ..., task_counts_by_status: _Optional[_Mapping[str, int]] = ...) -> None: ...

class RoleFilter(_message.Message):
    __slots__ = ("allowed_task_types", "role", "user_id")
    ALLOWED_TASK_TYPES_FIELD_NUMBER: _ClassVar[int]
    ROLE_FIELD_NUMBER: _ClassVar[int]
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    allowed_task_types: _containers.RepeatedScalarFieldContainer[str]
    role: str
    user_id: str
    def __init__(self, allowed_task_types: _Optional[_Iterable[str]] = ..., role: _Optional[str] = ..., user_id: _Optional[str] = ...) -> None: ...

class ListPatientsRequest(_message.Message):
    __slots__ = ("role_filter", "specialty", "task_type", "status", "program", "tier", "q", "limit", "cursor")
    ROLE_FILTER_FIELD_NUMBER: _ClassVar[int]
    SPECIALTY_FIELD_NUMBER: _ClassVar[int]
    TASK_TYPE_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    PROGRAM_FIELD_NUMBER: _ClassVar[int]
    TIER_FIELD_NUMBER: _ClassVar[int]
    Q_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    CURSOR_FIELD_NUMBER: _ClassVar[int]
    role_filter: RoleFilter
    specialty: str
    task_type: str
    status: str
    program: str
    tier: str
    q: str
    limit: int
    cursor: str
    def __init__(self, role_filter: _Optional[_Union[RoleFilter, _Mapping]] = ..., specialty: _Optional[str] = ..., task_type: _Optional[str] = ..., status: _Optional[str] = ..., program: _Optional[str] = ..., tier: _Optional[str] = ..., q: _Optional[str] = ..., limit: _Optional[int] = ..., cursor: _Optional[str] = ...) -> None: ...

class PatientWithContext(_message.Message):
    __slots__ = ("patient", "enrollments", "visible_tasks")
    PATIENT_FIELD_NUMBER: _ClassVar[int]
    ENROLLMENTS_FIELD_NUMBER: _ClassVar[int]
    VISIBLE_TASKS_FIELD_NUMBER: _ClassVar[int]
    patient: Patient
    enrollments: _containers.RepeatedCompositeFieldContainer[Enrollment]
    visible_tasks: _containers.RepeatedCompositeFieldContainer[Task]
    def __init__(self, patient: _Optional[_Union[Patient, _Mapping]] = ..., enrollments: _Optional[_Iterable[_Union[Enrollment, _Mapping]]] = ..., visible_tasks: _Optional[_Iterable[_Union[Task, _Mapping]]] = ...) -> None: ...

class ListPatientsResponse(_message.Message):
    __slots__ = ("items", "next_cursor")
    ITEMS_FIELD_NUMBER: _ClassVar[int]
    NEXT_CURSOR_FIELD_NUMBER: _ClassVar[int]
    items: _containers.RepeatedCompositeFieldContainer[PatientWithContext]
    next_cursor: str
    def __init__(self, items: _Optional[_Iterable[_Union[PatientWithContext, _Mapping]]] = ..., next_cursor: _Optional[str] = ...) -> None: ...

class GetPatientRequest(_message.Message):
    __slots__ = ("patient_id", "role_filter")
    PATIENT_ID_FIELD_NUMBER: _ClassVar[int]
    ROLE_FILTER_FIELD_NUMBER: _ClassVar[int]
    patient_id: str
    role_filter: RoleFilter
    def __init__(self, patient_id: _Optional[str] = ..., role_filter: _Optional[_Union[RoleFilter, _Mapping]] = ...) -> None: ...

class GetPatientResponse(_message.Message):
    __slots__ = ("patient", "enrollments", "needs", "visible_tasks")
    PATIENT_FIELD_NUMBER: _ClassVar[int]
    ENROLLMENTS_FIELD_NUMBER: _ClassVar[int]
    NEEDS_FIELD_NUMBER: _ClassVar[int]
    VISIBLE_TASKS_FIELD_NUMBER: _ClassVar[int]
    patient: Patient
    enrollments: _containers.RepeatedCompositeFieldContainer[Enrollment]
    needs: _containers.RepeatedCompositeFieldContainer[Need]
    visible_tasks: _containers.RepeatedCompositeFieldContainer[Task]
    def __init__(self, patient: _Optional[_Union[Patient, _Mapping]] = ..., enrollments: _Optional[_Iterable[_Union[Enrollment, _Mapping]]] = ..., needs: _Optional[_Iterable[_Union[Need, _Mapping]]] = ..., visible_tasks: _Optional[_Iterable[_Union[Task, _Mapping]]] = ...) -> None: ...

class ListTasksRequest(_message.Message):
    __slots__ = ("role_filter", "specialty", "task_type", "status", "program", "tier", "assigned_to", "overdue", "include_snoozed", "sort", "limit", "cursor")
    ROLE_FILTER_FIELD_NUMBER: _ClassVar[int]
    SPECIALTY_FIELD_NUMBER: _ClassVar[int]
    TASK_TYPE_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    PROGRAM_FIELD_NUMBER: _ClassVar[int]
    TIER_FIELD_NUMBER: _ClassVar[int]
    ASSIGNED_TO_FIELD_NUMBER: _ClassVar[int]
    OVERDUE_FIELD_NUMBER: _ClassVar[int]
    INCLUDE_SNOOZED_FIELD_NUMBER: _ClassVar[int]
    SORT_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    CURSOR_FIELD_NUMBER: _ClassVar[int]
    role_filter: RoleFilter
    specialty: str
    task_type: str
    status: _containers.RepeatedScalarFieldContainer[str]
    program: str
    tier: str
    assigned_to: str
    overdue: bool
    include_snoozed: bool
    sort: str
    limit: int
    cursor: str
    def __init__(self, role_filter: _Optional[_Union[RoleFilter, _Mapping]] = ..., specialty: _Optional[str] = ..., task_type: _Optional[str] = ..., status: _Optional[_Iterable[str]] = ..., program: _Optional[str] = ..., tier: _Optional[str] = ..., assigned_to: _Optional[str] = ..., overdue: _Optional[bool] = ..., include_snoozed: _Optional[bool] = ..., sort: _Optional[str] = ..., limit: _Optional[int] = ..., cursor: _Optional[str] = ...) -> None: ...

class ListTasksResponse(_message.Message):
    __slots__ = ("items", "next_cursor")
    ITEMS_FIELD_NUMBER: _ClassVar[int]
    NEXT_CURSOR_FIELD_NUMBER: _ClassVar[int]
    items: _containers.RepeatedCompositeFieldContainer[Task]
    next_cursor: str
    def __init__(self, items: _Optional[_Iterable[_Union[Task, _Mapping]]] = ..., next_cursor: _Optional[str] = ...) -> None: ...

class GetTaskRequest(_message.Message):
    __slots__ = ("task_id", "role_filter")
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    ROLE_FILTER_FIELD_NUMBER: _ClassVar[int]
    task_id: int
    role_filter: RoleFilter
    def __init__(self, task_id: _Optional[int] = ..., role_filter: _Optional[_Union[RoleFilter, _Mapping]] = ...) -> None: ...

class GetTaskResponse(_message.Message):
    __slots__ = ("task", "history")
    TASK_FIELD_NUMBER: _ClassVar[int]
    HISTORY_FIELD_NUMBER: _ClassVar[int]
    task: Task
    history: _containers.RepeatedCompositeFieldContainer[AuditEntry]
    def __init__(self, task: _Optional[_Union[Task, _Mapping]] = ..., history: _Optional[_Iterable[_Union[AuditEntry, _Mapping]]] = ...) -> None: ...

class ListProgramsRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ListProgramsResponse(_message.Message):
    __slots__ = ("items",)
    ITEMS_FIELD_NUMBER: _ClassVar[int]
    items: _containers.RepeatedCompositeFieldContainer[Program]
    def __init__(self, items: _Optional[_Iterable[_Union[Program, _Mapping]]] = ...) -> None: ...

class ClaimTaskRequest(_message.Message):
    __slots__ = ("task_id", "version", "role_filter")
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    ROLE_FILTER_FIELD_NUMBER: _ClassVar[int]
    task_id: int
    version: int
    role_filter: RoleFilter
    def __init__(self, task_id: _Optional[int] = ..., version: _Optional[int] = ..., role_filter: _Optional[_Union[RoleFilter, _Mapping]] = ...) -> None: ...

class CompleteTaskRequest(_message.Message):
    __slots__ = ("task_id", "version", "resolution", "note", "role_filter")
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    RESOLUTION_FIELD_NUMBER: _ClassVar[int]
    NOTE_FIELD_NUMBER: _ClassVar[int]
    ROLE_FILTER_FIELD_NUMBER: _ClassVar[int]
    task_id: int
    version: int
    resolution: str
    note: str
    role_filter: RoleFilter
    def __init__(self, task_id: _Optional[int] = ..., version: _Optional[int] = ..., resolution: _Optional[str] = ..., note: _Optional[str] = ..., role_filter: _Optional[_Union[RoleFilter, _Mapping]] = ...) -> None: ...

class DeclineTaskRequest(_message.Message):
    __slots__ = ("task_id", "version", "reason", "snooze_days", "role_filter")
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    SNOOZE_DAYS_FIELD_NUMBER: _ClassVar[int]
    ROLE_FILTER_FIELD_NUMBER: _ClassVar[int]
    task_id: int
    version: int
    reason: str
    snooze_days: int
    role_filter: RoleFilter
    def __init__(self, task_id: _Optional[int] = ..., version: _Optional[int] = ..., reason: _Optional[str] = ..., snooze_days: _Optional[int] = ..., role_filter: _Optional[_Union[RoleFilter, _Mapping]] = ...) -> None: ...

class SnoozeTaskRequest(_message.Message):
    __slots__ = ("task_id", "version", "until", "reason", "role_filter")
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    UNTIL_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    ROLE_FILTER_FIELD_NUMBER: _ClassVar[int]
    task_id: int
    version: int
    until: str
    reason: str
    role_filter: RoleFilter
    def __init__(self, task_id: _Optional[int] = ..., version: _Optional[int] = ..., until: _Optional[str] = ..., reason: _Optional[str] = ..., role_filter: _Optional[_Union[RoleFilter, _Mapping]] = ...) -> None: ...

class TaskResponse(_message.Message):
    __slots__ = ("task",)
    TASK_FIELD_NUMBER: _ClassVar[int]
    task: Task
    def __init__(self, task: _Optional[_Union[Task, _Mapping]] = ...) -> None: ...

class StartSyncRunRequest(_message.Message):
    __slots__ = ("source",)
    SOURCE_FIELD_NUMBER: _ClassVar[int]
    source: str
    def __init__(self, source: _Optional[str] = ...) -> None: ...

class StartSyncRunResponse(_message.Message):
    __slots__ = ("run_id",)
    RUN_ID_FIELD_NUMBER: _ClassVar[int]
    run_id: str
    def __init__(self, run_id: _Optional[str] = ...) -> None: ...

class FactRow(_message.Message):
    __slots__ = ("fields",)
    class FieldsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    FIELDS_FIELD_NUMBER: _ClassVar[int]
    fields: _containers.ScalarMap[str, str]
    def __init__(self, fields: _Optional[_Mapping[str, str]] = ...) -> None: ...

class UpsertFactsRequest(_message.Message):
    __slots__ = ("run_id", "resource_type", "chunk_number", "rows")
    RUN_ID_FIELD_NUMBER: _ClassVar[int]
    RESOURCE_TYPE_FIELD_NUMBER: _ClassVar[int]
    CHUNK_NUMBER_FIELD_NUMBER: _ClassVar[int]
    ROWS_FIELD_NUMBER: _ClassVar[int]
    run_id: str
    resource_type: str
    chunk_number: int
    rows: _containers.RepeatedCompositeFieldContainer[FactRow]
    def __init__(self, run_id: _Optional[str] = ..., resource_type: _Optional[str] = ..., chunk_number: _Optional[int] = ..., rows: _Optional[_Iterable[_Union[FactRow, _Mapping]]] = ...) -> None: ...

class RejectedRow(_message.Message):
    __slots__ = ("raw", "reason")
    class RawEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    RAW_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    raw: _containers.ScalarMap[str, str]
    reason: str
    def __init__(self, raw: _Optional[_Mapping[str, str]] = ..., reason: _Optional[str] = ...) -> None: ...

class UpsertFactsResponse(_message.Message):
    __slots__ = ("accepted_count", "rejected")
    ACCEPTED_COUNT_FIELD_NUMBER: _ClassVar[int]
    REJECTED_FIELD_NUMBER: _ClassVar[int]
    accepted_count: int
    rejected: _containers.RepeatedCompositeFieldContainer[RejectedRow]
    def __init__(self, accepted_count: _Optional[int] = ..., rejected: _Optional[_Iterable[_Union[RejectedRow, _Mapping]]] = ...) -> None: ...

class CompleteSyncRunRequest(_message.Message):
    __slots__ = ("run_id", "status")
    RUN_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    run_id: str
    status: str
    def __init__(self, run_id: _Optional[str] = ..., status: _Optional[str] = ...) -> None: ...

class CompleteSyncRunResponse(_message.Message):
    __slots__ = ("run", "changed_patient_ids")
    RUN_FIELD_NUMBER: _ClassVar[int]
    CHANGED_PATIENT_IDS_FIELD_NUMBER: _ClassVar[int]
    run: SyncRun
    changed_patient_ids: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, run: _Optional[_Union[SyncRun, _Mapping]] = ..., changed_patient_ids: _Optional[_Iterable[str]] = ...) -> None: ...

class ListSyncRunsRequest(_message.Message):
    __slots__ = ("limit",)
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    limit: int
    def __init__(self, limit: _Optional[int] = ...) -> None: ...

class ListSyncRunsResponse(_message.Message):
    __slots__ = ("items",)
    ITEMS_FIELD_NUMBER: _ClassVar[int]
    items: _containers.RepeatedCompositeFieldContainer[SyncRun]
    def __init__(self, items: _Optional[_Iterable[_Union[SyncRun, _Mapping]]] = ...) -> None: ...

class ProgramDefinition(_message.Message):
    __slots__ = ("program_id", "version", "definition_json", "active")
    PROGRAM_ID_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    DEFINITION_JSON_FIELD_NUMBER: _ClassVar[int]
    ACTIVE_FIELD_NUMBER: _ClassVar[int]
    program_id: str
    version: int
    definition_json: str
    active: bool
    def __init__(self, program_id: _Optional[str] = ..., version: _Optional[int] = ..., definition_json: _Optional[str] = ..., active: _Optional[bool] = ...) -> None: ...

class UpsertProgramsRequest(_message.Message):
    __slots__ = ("programs",)
    PROGRAMS_FIELD_NUMBER: _ClassVar[int]
    programs: _containers.RepeatedCompositeFieldContainer[ProgramDefinition]
    def __init__(self, programs: _Optional[_Iterable[_Union[ProgramDefinition, _Mapping]]] = ...) -> None: ...

class UpsertProgramsResponse(_message.Message):
    __slots__ = ("upserted_count",)
    UPSERTED_COUNT_FIELD_NUMBER: _ClassVar[int]
    upserted_count: int
    def __init__(self, upserted_count: _Optional[int] = ...) -> None: ...

class DiagnosisFact(_message.Message):
    __slots__ = ("icd_code", "diagnosed_date")
    ICD_CODE_FIELD_NUMBER: _ClassVar[int]
    DIAGNOSED_DATE_FIELD_NUMBER: _ClassVar[int]
    icd_code: str
    diagnosed_date: str
    def __init__(self, icd_code: _Optional[str] = ..., diagnosed_date: _Optional[str] = ...) -> None: ...

class LabFact(_message.Message):
    __slots__ = ("test_name", "result_value", "result_date")
    TEST_NAME_FIELD_NUMBER: _ClassVar[int]
    RESULT_VALUE_FIELD_NUMBER: _ClassVar[int]
    RESULT_DATE_FIELD_NUMBER: _ClassVar[int]
    test_name: str
    result_value: float
    result_date: str
    def __init__(self, test_name: _Optional[str] = ..., result_value: _Optional[float] = ..., result_date: _Optional[str] = ...) -> None: ...

class EncounterFact(_message.Message):
    __slots__ = ("specialty", "encounter_date", "provider_name", "is_upcoming")
    SPECIALTY_FIELD_NUMBER: _ClassVar[int]
    ENCOUNTER_DATE_FIELD_NUMBER: _ClassVar[int]
    PROVIDER_NAME_FIELD_NUMBER: _ClassVar[int]
    IS_UPCOMING_FIELD_NUMBER: _ClassVar[int]
    specialty: str
    encounter_date: str
    provider_name: str
    is_upcoming: bool
    def __init__(self, specialty: _Optional[str] = ..., encounter_date: _Optional[str] = ..., provider_name: _Optional[str] = ..., is_upcoming: _Optional[bool] = ...) -> None: ...

class GetPatientSnapshotRequest(_message.Message):
    __slots__ = ("patient_id", "as_of_date")
    PATIENT_ID_FIELD_NUMBER: _ClassVar[int]
    AS_OF_DATE_FIELD_NUMBER: _ClassVar[int]
    patient_id: str
    as_of_date: str
    def __init__(self, patient_id: _Optional[str] = ..., as_of_date: _Optional[str] = ...) -> None: ...

class GetPatientSnapshotResponse(_message.Message):
    __slots__ = ("patient", "diagnoses", "labs", "encounters", "snapshot_hash")
    PATIENT_FIELD_NUMBER: _ClassVar[int]
    DIAGNOSES_FIELD_NUMBER: _ClassVar[int]
    LABS_FIELD_NUMBER: _ClassVar[int]
    ENCOUNTERS_FIELD_NUMBER: _ClassVar[int]
    SNAPSHOT_HASH_FIELD_NUMBER: _ClassVar[int]
    patient: Patient
    diagnoses: _containers.RepeatedCompositeFieldContainer[DiagnosisFact]
    labs: _containers.RepeatedCompositeFieldContainer[LabFact]
    encounters: _containers.RepeatedCompositeFieldContainer[EncounterFact]
    snapshot_hash: str
    def __init__(self, patient: _Optional[_Union[Patient, _Mapping]] = ..., diagnoses: _Optional[_Iterable[_Union[DiagnosisFact, _Mapping]]] = ..., labs: _Optional[_Iterable[_Union[LabFact, _Mapping]]] = ..., encounters: _Optional[_Iterable[_Union[EncounterFact, _Mapping]]] = ..., snapshot_hash: _Optional[str] = ...) -> None: ...

class NeedResult(_message.Message):
    __slots__ = ("specialty", "cadence_days", "last_visit_date", "due_date", "has_upcoming", "decision", "next_check_candidate")
    SPECIALTY_FIELD_NUMBER: _ClassVar[int]
    CADENCE_DAYS_FIELD_NUMBER: _ClassVar[int]
    LAST_VISIT_DATE_FIELD_NUMBER: _ClassVar[int]
    DUE_DATE_FIELD_NUMBER: _ClassVar[int]
    HAS_UPCOMING_FIELD_NUMBER: _ClassVar[int]
    DECISION_FIELD_NUMBER: _ClassVar[int]
    NEXT_CHECK_CANDIDATE_FIELD_NUMBER: _ClassVar[int]
    specialty: str
    cadence_days: int
    last_visit_date: str
    due_date: str
    has_upcoming: bool
    decision: str
    next_check_candidate: str
    def __init__(self, specialty: _Optional[str] = ..., cadence_days: _Optional[int] = ..., last_visit_date: _Optional[str] = ..., due_date: _Optional[str] = ..., has_upcoming: _Optional[bool] = ..., decision: _Optional[str] = ..., next_check_candidate: _Optional[str] = ...) -> None: ...

class ProgramResult(_message.Message):
    __slots__ = ("program_id", "program_version", "eligible", "tier", "needs", "tier_recheck_at")
    PROGRAM_ID_FIELD_NUMBER: _ClassVar[int]
    PROGRAM_VERSION_FIELD_NUMBER: _ClassVar[int]
    ELIGIBLE_FIELD_NUMBER: _ClassVar[int]
    TIER_FIELD_NUMBER: _ClassVar[int]
    NEEDS_FIELD_NUMBER: _ClassVar[int]
    TIER_RECHECK_AT_FIELD_NUMBER: _ClassVar[int]
    program_id: str
    program_version: int
    eligible: bool
    tier: str
    needs: _containers.RepeatedCompositeFieldContainer[NeedResult]
    tier_recheck_at: str
    def __init__(self, program_id: _Optional[str] = ..., program_version: _Optional[int] = ..., eligible: _Optional[bool] = ..., tier: _Optional[str] = ..., needs: _Optional[_Iterable[_Union[NeedResult, _Mapping]]] = ..., tier_recheck_at: _Optional[str] = ...) -> None: ...

class SaveEvaluationResultRequest(_message.Message):
    __slots__ = ("patient_id", "idempotency_key", "program_results", "evaluated_at", "next_eval_at")
    PATIENT_ID_FIELD_NUMBER: _ClassVar[int]
    IDEMPOTENCY_KEY_FIELD_NUMBER: _ClassVar[int]
    PROGRAM_RESULTS_FIELD_NUMBER: _ClassVar[int]
    EVALUATED_AT_FIELD_NUMBER: _ClassVar[int]
    NEXT_EVAL_AT_FIELD_NUMBER: _ClassVar[int]
    patient_id: str
    idempotency_key: str
    program_results: _containers.RepeatedCompositeFieldContainer[ProgramResult]
    evaluated_at: str
    next_eval_at: str
    def __init__(self, patient_id: _Optional[str] = ..., idempotency_key: _Optional[str] = ..., program_results: _Optional[_Iterable[_Union[ProgramResult, _Mapping]]] = ..., evaluated_at: _Optional[str] = ..., next_eval_at: _Optional[str] = ...) -> None: ...

class SaveEvaluationResultResponse(_message.Message):
    __slots__ = ("applied", "tasks_created", "tasks_closed")
    APPLIED_FIELD_NUMBER: _ClassVar[int]
    TASKS_CREATED_FIELD_NUMBER: _ClassVar[int]
    TASKS_CLOSED_FIELD_NUMBER: _ClassVar[int]
    applied: bool
    tasks_created: int
    tasks_closed: int
    def __init__(self, applied: _Optional[bool] = ..., tasks_created: _Optional[int] = ..., tasks_closed: _Optional[int] = ...) -> None: ...

class EnqueueDuePatientsRequest(_message.Message):
    __slots__ = ("as_of_date",)
    AS_OF_DATE_FIELD_NUMBER: _ClassVar[int]
    as_of_date: str
    def __init__(self, as_of_date: _Optional[str] = ...) -> None: ...

class EnqueueDuePatientsResponse(_message.Message):
    __slots__ = ("enqueued_count",)
    ENQUEUED_COUNT_FIELD_NUMBER: _ClassVar[int]
    enqueued_count: int
    def __init__(self, enqueued_count: _Optional[int] = ...) -> None: ...

class EnqueueAllPatientsRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class EnqueueAllPatientsResponse(_message.Message):
    __slots__ = ("enqueued_count",)
    ENQUEUED_COUNT_FIELD_NUMBER: _ClassVar[int]
    enqueued_count: int
    def __init__(self, enqueued_count: _Optional[int] = ...) -> None: ...
