# Submission schema v1

`POST /v1/submissions` accepts `application/json` with a default maximum body
size of 65,536 bytes.

```json
{
  "schema": 1,
  "batch_id": "6880174d-520c-45ab-b906-e2de54c81608",
  "period_start": "2026-08-01",
  "period_end": "2026-08-06",
  "netlab_version": "26.7",
  "metrics": [
    {
      "dimension": "device",
      "item": "eos",
      "observations": 2,
      "instances": 7,
      "maximum": 5
    }
  ]
}
```

The FastAPI request body is represented by the Pydantic
`UsageSubmission` model in `src/models.py`.

## Submission fields

| Field | Constraint |
|---|---|
| `schema` | Integer literal `1`; booleans are rejected |
| `batch_id` | Random UUID version 4 |
| `period_start` | ISO date in `YYYY-MM-DD` format |
| `period_end` | ISO date on or after `period_start`, at most 366 days later |
| `netlab_version` | Coarse `major.minor` string |
| `metrics` | Between 1 and 256 metric objects |

Unknown submission and metric fields are rejected.

## Metric fields

Allowed dimensions are `topology`, `node`, `link`, `provider`, `device`,
`module`, `plugin`, and `command`.

`observations`, `instances`, and `maximum` must be JSON integers, not booleans
or numeric strings. The service applies bounded maximum values and requires
`maximum <= instances`.

`batch_id` is a random, single-use retry key. It is retained only for the
configured deduplication window and must not identify an installation.

Unknown item values are normalized again on the server to `_custom` or
`_other`. The service stores aggregate rows and does not store the submitted
JSON document.

## Error response

Invalid submissions return HTTP 400:

```json
{
  "error": "invalid submission",
  "details": [
    {
      "location": "metrics.0.maximum",
      "message": "Value error, maximum cannot exceed instances",
      "type": "value_error"
    }
  ]
}
```

Error details include locations and validation messages but do not echo input
values.
