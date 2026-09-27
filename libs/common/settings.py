"""Shared settings, read once from the environment.

One `ROLE` env var picks which service a container runs (see each service's
`__main__.py`). `DS_ROLES` further splits the Data Service's own interactive /
bulk / relay loops, so separating them into containers later is a Compose
change, not a code change.
"""

from __future__ import annotations

from datetime import date
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)

    # Which service this container runs.
    role: str = "worklist-api"
    # data-service sub-roles, comma separated: interactive,bulk,relay
    ds_roles: str = "interactive,bulk,relay"

    # The date every rule is evaluated against. Production default is today;
    # the seed run pins it so results are repeatable against the CSV snapshot.
    as_of_date: date | None = None

    # MySQL
    mysql_host: str = "mysql"
    mysql_port: int = 3306
    mysql_user: str = "care_gap"
    mysql_password: str = "care_gap"
    mysql_database: str = "care_gap"

    # Redis
    redis_host: str = "redis"
    redis_port: int = 6379

    # Kafka
    kafka_bootstrap_servers: str = "kafka:9092"
    kafka_topic_patient_changed: str = "patient.changed"
    kafka_topic_dlq: str = "patient.changed.dlq"
    kafka_consumer_group: str = "engine"
    kafka_max_retries: int = 3

    # gRPC
    grpc_host: str = "0.0.0.0"
    grpc_port: int = 50051
    data_service_target: str = "data-service:50051"

    # HTTP
    http_port: int = 8000

    # Worklist cache TTL, seconds.
    worklist_cache_ttl_seconds: int = 30

    # Scheduler sweep interval, seconds.
    scheduler_interval_seconds: int = 60

    # Program definitions.
    programs_dir: str = "seeds/programs"

    # Specialties treated as primary care (never get a referral task).
    primary_care_specialties: str = "PCP"

    # Default decline snooze, days.
    default_decline_snooze_days: int = 90

    @property
    def sqlalchemy_url(self) -> str:
        return (
            f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}?charset=utf8mb4"
        )

    @property
    def ds_role_set(self) -> set[str]:
        return {r.strip() for r in self.ds_roles.split(",") if r.strip()}

    @property
    def primary_care_specialty_set(self) -> set[str]:
        return {s.strip() for s in self.primary_care_specialties.split(",") if s.strip()}

    def effective_as_of_date(self) -> date:
        return self.as_of_date or date.today()


@lru_cache
def get_settings() -> Settings:
    return Settings()
