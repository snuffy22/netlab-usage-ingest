from __future__ import annotations

import copy
from types import SimpleNamespace

from fastapi.testclient import TestClient

from conftest import FakeD1, FakeLimiter


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


def test_health(client: TestClient) -> None:
    response = client.get('/v1/health')
    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}


def test_accepts_then_deduplicates(client: TestClient, db: FakeD1) -> None:
    accepted = client.post('/v1/submissions', json=payload())
    assert accepted.status_code == 202
    assert accepted.json()['status'] == 'accepted'

    duplicate = client.post('/v1/submissions', json=payload())
    assert duplicate.status_code == 200
    assert duplicate.json()['status'] == 'duplicate'

    row = db.connection.execute('''
        SELECT observations, instances, maximum
        FROM usage_aggregates
        WHERE dimension = 'device' AND item = 'eos'
    ''').fetchone()
    assert tuple(row) == (2, 7, 5)


def test_fastapi_rejects_extra_fields_without_echoing_input(client: TestClient) -> None:
    value = payload()
    value['hostname'] = 'private-host'
    response = client.post('/v1/submissions', json=value)
    assert response.status_code == 400
    assert response.json()['error'] == 'invalid submission'
    assert 'private-host' not in response.text


def test_rejects_wrong_content_type(client: TestClient) -> None:
    response = client.post('/v1/submissions', content='{}', headers={'Content-Type': 'text/plain'})
    assert response.status_code == 415


def test_rejects_oversized_body(client: TestClient, env: SimpleNamespace) -> None:
    env.MAX_BODY_BYTES = '1024'
    value = copy.deepcopy(payload())
    value['padding'] = 'x' * 2_000
    response = client.post('/v1/submissions', json=value)
    assert response.status_code == 413


def test_rate_limit_is_enforced(client: TestClient, env: SimpleNamespace) -> None:
    env.SUBMISSION_LIMITER = FakeLimiter(allowed=False)
    response = client.post('/v1/submissions', json=payload())
    assert response.status_code == 429


def test_unknown_route_keeps_simple_error_contract(client: TestClient) -> None:
    response = client.get('/missing')
    assert response.status_code == 404
    assert response.json() == {'error': 'not found'}
