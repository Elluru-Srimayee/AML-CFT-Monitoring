from fastapi.testclient import TestClient
import os

from src.api import server


client = TestClient(server.app)


def test_health():
    r = client.get('/api/health')
    assert r.status_code == 200
    assert r.json().get('status') == 'ok'


def test_alerts_list_empty_or_present():
    r = client.get('/api/alerts/list')
    assert r.status_code == 200
    data = r.json()
    assert 'total' in data
    assert 'alerts' in data


def test_cases_list():
    r = client.get('/api/cases')
    assert r.status_code in (200, 404)
    if r.status_code == 200:
        data = r.json()
        assert 'cases' in data


def test_run_pipeline_smoke():
    # run with a small sample to smoke test pipeline
    r = client.get('/api/run?sample=10')
    assert r.status_code == 200
    data = r.json()
    assert 'summary' in data
    assert isinstance(data.get('alerts'), list)
    assert isinstance(data.get('cases'), list)


def test_run_pipeline_can_skip_cases():
    r = client.get('/api/run?sample=10&generate_cases=false')
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data.get('alerts'), list)
    assert data.get('cases') == []
    assert data.get('summary', {}).get('cases') == 0