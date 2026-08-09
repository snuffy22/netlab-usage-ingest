from __future__ import annotations

from models import UsageSubmission
from normalize import normalize_submission


def test_collapses_and_combines_custom_identifiers() -> None:
    value = UsageSubmission.model_validate({
        'schema': 1,
        'batch_id': '6880174d-520c-45ab-b906-e2de54c81608',
        'period_start': '2026-08-01',
        'period_end': '2026-08-06',
        'netlab_version': '26.7',
        'metrics': [
            {
                'dimension': 'device',
                'item': 'private-a',
                'observations': 1,
                'instances': 2,
                'maximum': 2,
            },
            {
                'dimension': 'device',
                'item': 'private-b',
                'observations': 3,
                'instances': 4,
                'maximum': 3,
            },
            {
                'dimension': 'device',
                'item': 'eos',
                'observations': 2,
                'instances': 2,
                'maximum': 1,
            },
        ],
    })

    metrics = [metric.model_dump() for metric in normalize_submission(value).metrics]
    assert metrics == [
        {
            'dimension': 'device',
            'item': '_custom',
            'observations': 4,
            'instances': 6,
            'maximum': 3,
        },
        {
            'dimension': 'device',
            'item': 'eos',
            'observations': 2,
            'instances': 2,
            'maximum': 1,
        },
    ]


def test_fixed_dimensions_become_all() -> None:
    value = UsageSubmission.model_validate({
        'schema': 1,
        'batch_id': '6880174d-520c-45ab-b906-e2de54c81608',
        'period_start': '2026-08-01',
        'period_end': '2026-08-06',
        'netlab_version': '26.7',
        'metrics': [{
            'dimension': 'node',
            'item': 'anything',
            'observations': 1,
            'instances': 8,
            'maximum': 8,
        }],
    })
    assert normalize_submission(value).metrics[0].item == 'all'
