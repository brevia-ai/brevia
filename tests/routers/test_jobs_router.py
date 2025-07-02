"""Jobs router tests"""
import uuid
from fastapi.testclient import TestClient
from fastapi import FastAPI
from brevia.routers import jobs_router
from brevia.async_jobs import create_job

app = FastAPI()
app.include_router(jobs_router.router)
client = TestClient(app)


def test_jobs_ok():
    """Test /jobs/{uuid} success"""
    job = create_job('TestService', {})
    response = client.get(f'/jobs/{job.uuid}', headers={})
    assert response.status_code == 200
    data = response.json()
    assert data is not None
    assert data['uuid'] == str(job.uuid)


def test_jobs_fail():
    """Test /jobs/{uuid} failure"""
    response = client.get(f'/jobs/{uuid.uuid4()}', headers={})
    assert response.status_code == 404
