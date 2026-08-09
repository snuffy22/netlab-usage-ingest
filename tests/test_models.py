from __future__ import annotations

import copy
import datetime

import pytest
from pydantic import ValidationError

from models import UsageSubmission


def payload() -> dict:
    return {
        'schema': 1,
        'batch_id': '6880174d-520c-45ab-b906-e2de54c81608',
        'period_start': '2026-08-01',
        'period_end': '2026-08-06',
        'netlab_version': '26.7',
        'metrics': [{
            'dimension': 'device',
            'item': 'eos',
            'observations': 2,
            'instances': 7,
            'maximum': 5,
        }],
    }


def test_accepts_versioned_aggregate_payload() -> None:
    submission = UsageSubmission.model_validate(payload())
    assert submission.schema_version == 1
    assert submission.period_start == datetime.date(2026, 8, 1)
    assert str(submission.batch_id) == payload()['batch_id']
    assert submission.model_dump(mode='json', by_alias=True) == payload()


def test_rejects_unrecognized_root_fields() -> None:
    value = payload()
    value['hostname'] = 'private-host'
    with pytest.raises(ValidationError, match='Extra inputs are not permitted'):
        UsageSubmission.model_validate(value)


def test_rejects_invalid_count_relationships() -> None:
    value = copy.deepcopy(payload())
    value['metrics'][0]['maximum'] = 8
    with pytest.raises(ValidationError, match='maximum cannot exceed instances'):
        UsageSubmission.model_validate(value)


def test_rejects_overly_precise_version() -> None:
    value = payload()
    value['netlab_version'] = '26.7.1'
    with pytest.raises(ValidationError, match='string_pattern_mismatch'):
        UsageSubmission.model_validate(value)


def test_rejects_boolean_as_integer() -> None:
    value = copy.deepcopy(payload())
    value['metrics'][0]['instances'] = True
    with pytest.raises(ValidationError, match='valid integer'):
        UsageSubmission.model_validate(value)


def test_rejects_boolean_schema_version() -> None:
    value = payload()
    value['schema'] = True
    with pytest.raises(ValidationError, match='schema must be integer 1'):
        UsageSubmission.model_validate(value)


def test_rejects_non_iso_date_and_excessive_period() -> None:
    value = payload()
    value['period_start'] = '20260801'
    with pytest.raises(ValidationError, match='YYYY-MM-DD'):
        UsageSubmission.model_validate(value)

    value = payload()
    value['period_end'] = '2028-08-06'
    with pytest.raises(ValidationError, match='cannot exceed 366 days'):
        UsageSubmission.model_validate(value)
