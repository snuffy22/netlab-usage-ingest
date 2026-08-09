from __future__ import annotations

import asyncio

from conftest import FakeD1

from models import UsageSubmission
from storage import ingest_submission


def test_batch_is_idempotent(db: FakeD1) -> None:
    async def scenario() -> None:
        submission = UsageSubmission.model_validate({
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
        })

        assert await ingest_submission(db, submission) == 'accepted'
        assert await ingest_submission(db, submission) == 'duplicate'

        row = db.connection.execute('''
            SELECT observations, instances, maximum
            FROM usage_aggregates
            WHERE dimension = 'device' AND item = 'eos'
        ''').fetchone()
        assert tuple(row) == (2, 7, 5)

    asyncio.run(scenario())
