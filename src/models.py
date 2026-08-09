from __future__ import annotations

import datetime
import re
from typing import Annotated, Literal

from pydantic import (
    UUID4,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

Dimension = Literal[
    'topology', 'node', 'link', 'provider', 'device', 'module', 'plugin', 'command'
]

MAX_METRICS = 256
MAX_OBSERVATIONS = 1_000_000
MAX_INSTANCES = 100_000_000
MAXIMUM_PER_OBSERVATION = 100_000
MAX_PERIOD_DAYS = 366

_DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')

MetricItem = Annotated[
    str,
    StringConstraints(
        strict=True,
        min_length=1,
        max_length=64,
        pattern=r'^(?:_[a-z]+|[a-z0-9][a-z0-9_.-]{0,63})$',
    ),
]

NetlabVersion = Annotated[
    str,
    StringConstraints(strict=True, pattern=r'^\d{1,4}\.\d{1,4}$'),
]

StrictCount = Annotated[int, Field(strict=True, ge=0)]


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        frozen=True,
        populate_by_name=True,
    )


class UsageMetric(StrictModel):
    dimension: Dimension
    item: MetricItem
    observations: Annotated[StrictCount, Field(ge=1, le=MAX_OBSERVATIONS)]
    instances: Annotated[StrictCount, Field(le=MAX_INSTANCES)]
    maximum: Annotated[StrictCount, Field(le=MAXIMUM_PER_OBSERVATION)]

    @field_validator('item', mode='before')
    @classmethod
    def lowercase_item(cls, value: object) -> object:
        return value.lower() if isinstance(value, str) else value

    @model_validator(mode='after')
    def maximum_cannot_exceed_instances(self) -> UsageMetric:
        if self.maximum > self.instances:
            raise ValueError('maximum cannot exceed instances')
        return self


class UsageSubmission(StrictModel):
    schema_version: Literal[1] = Field(alias='schema')
    batch_id: UUID4
    period_start: datetime.date
    period_end: datetime.date
    netlab_version: NetlabVersion
    metrics: Annotated[list[UsageMetric], Field(min_length=1, max_length=MAX_METRICS)]

    @field_validator('schema_version', mode='before')
    @classmethod
    def reject_boolean_schema_version(cls, value: object) -> object:
        if isinstance(value, bool):
            raise ValueError('schema must be integer 1')
        return value

    @field_validator('period_start', 'period_end', mode='before')
    @classmethod
    def require_iso_date(cls, value: object) -> object:
        if isinstance(value, str) and not _DATE_RE.fullmatch(value):
            raise ValueError('date must use YYYY-MM-DD')
        return value

    @model_validator(mode='after')
    def period_must_be_ordered_and_bounded(self) -> UsageSubmission:
        period_days = (self.period_end - self.period_start).days
        if period_days < 0:
            raise ValueError('period_end must not precede period_start')
        if period_days > MAX_PERIOD_DAYS:
            raise ValueError(f'submission period cannot exceed {MAX_PERIOD_DAYS} days')
        return self


class SubmissionResponse(StrictModel):
    status: Literal['accepted', 'duplicate']
    batch_id: UUID4


class HealthResponse(StrictModel):
    status: Literal['ok', 'unavailable']


class ErrorDetail(StrictModel):
    location: str
    message: str
    type: str


class ErrorResponse(StrictModel):
    error: str
    details: list[ErrorDetail] | None = None
