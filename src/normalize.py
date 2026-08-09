from __future__ import annotations

from allowlists import normalize_item
from models import UsageMetric, UsageSubmission


def normalize_submission(submission: UsageSubmission) -> UsageSubmission:
    combined: dict[tuple[str, str], dict[str, int | str]] = {}

    for metric in submission.metrics:
        item = normalize_item(metric.dimension, metric.item)
        key = (metric.dimension, item)
        existing = combined.get(key)
        if existing is None:
            combined[key] = {
                'dimension': metric.dimension,
                'item': item,
                'observations': metric.observations,
                'instances': metric.instances,
                'maximum': metric.maximum,
            }
            continue

        existing['observations'] = int(existing['observations']) + metric.observations
        existing['instances'] = int(existing['instances']) + metric.instances
        existing['maximum'] = max(int(existing['maximum']), metric.maximum)

    metrics = [UsageMetric.model_validate(combined[key]) for key in sorted(combined)]
    return UsageSubmission(
        schema=1,
        batch_id=submission.batch_id,
        period_start=submission.period_start,
        period_end=submission.period_end,
        netlab_version=submission.netlab_version,
        metrics=metrics,
    )
