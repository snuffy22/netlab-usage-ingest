from __future__ import annotations

import datetime
from typing import Any, Literal

from models import UsageSubmission

IngestResult = Literal['accepted', 'duplicate']

_BATCH_INSERT = '''
    INSERT INTO accepted_batches (batch_id, received_day, schema_version)
    VALUES (?, ?, ?)
'''

_AGGREGATE_UPSERT = '''
    INSERT INTO usage_aggregates (
        period_start, period_end, schema_version, netlab_version,
        dimension, item, observations, instances, maximum, updated_day
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT (
        period_start, period_end, schema_version, netlab_version, dimension, item
    ) DO UPDATE SET
        observations = usage_aggregates.observations + excluded.observations,
        instances = usage_aggregates.instances + excluded.instances,
        maximum = MAX(usage_aggregates.maximum, excluded.maximum),
        updated_day = excluded.updated_day
'''


async def ingest_submission(db: Any, submission: UsageSubmission) -> IngestResult:
    received_day = datetime.datetime.now(datetime.UTC).date().isoformat()
    batch_id = str(submission.batch_id)
    statements = [
        db.prepare(_BATCH_INSERT).bind(batch_id, received_day, submission.schema_version)
    ]

    for metric in submission.metrics:
        statements.append(db.prepare(_AGGREGATE_UPSERT).bind(
            submission.period_start.isoformat(),
            submission.period_end.isoformat(),
            submission.schema_version,
            submission.netlab_version,
            metric.dimension,
            metric.item,
            metric.observations,
            metric.instances,
            metric.maximum,
            received_day))

    try:
        await db.batch(statements)
        return 'accepted'
    except Exception:
        existing = await db.prepare(
            'SELECT batch_id FROM accepted_batches WHERE batch_id = ? LIMIT 1'
        ).bind(batch_id).first('batch_id')
        if existing is not None:
            return 'duplicate'
        raise


async def prune_accepted_batches(db: Any, retention_days: int = 30) -> None:
    retention_days = min(max(retention_days, 1), 365)
    await db.prepare('''
        DELETE FROM accepted_batches
        WHERE received_day < date('now', ?)
    ''').bind(f'-{retention_days} days').run()
