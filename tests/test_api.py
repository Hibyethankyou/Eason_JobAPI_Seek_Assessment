import pytest
from fastapi.testclient import TestClient

from app.main import (
    app,
    application_repository,
    job_repository,
)


client = TestClient(app)

# for preventing test data from leaking between tests
# We clear the in-memory storage before and after each test
@pytest.fixture(autouse=True)
def clear_in_memory_storage():
    job_repository._store.clear()
    application_repository._store.clear()
    yield
    job_repository._store.clear()
    application_repository._store.clear()


def create_job() -> dict:
    response = client.post(
        "/jobs",
        json={
            "title": "Graduate Software Engineer",
            "description": "Build and maintain software products",
            "location": "Kuala Lumpur",
        },
    )

    assert response.status_code == 201
    return response.json()


def test_create_job():
    response = client.post(
        "/jobs",
        json={
            "title": "Graduate Software Engineer",
            "description": "Build and maintain software products",
            "location": "Kuala Lumpur",
        },
    )

    assert response.status_code == 201

    job = response.json()

    assert job["title"] == "Graduate Software Engineer"
    assert job["description"] == "Build and maintain software products"
    assert job["location"] == "Kuala Lumpur"
    assert job["status"] == "OPEN"
    assert "id" in job
    assert "created_at" in job


def test_get_existing_job():
    job = create_job()

    response = client.get(f"/jobs/{job['id']}")

    assert response.status_code == 200
    assert response.json()["id"] == job["id"]


def test_get_nonexistent_job_returns_404():
    response = client.get("/jobs/not-a-real-id")

    assert response.status_code == 404
    assert "not found" in response.json()["error"]


def test_filter_jobs_by_status():
    open_job = create_job()
    closed_job = create_job()

    client.post(f"/jobs/{closed_job['id']}/close")

    response = client.get("/jobs?status=OPEN")

    assert response.status_code == 200

    returned_ids = [job["id"] for job in response.json()]

    assert open_job["id"] in returned_ids
    assert closed_job["id"] not in returned_ids


def test_close_job():
    job = create_job()

    response = client.post(f"/jobs/{job['id']}/close")

    assert response.status_code == 200
    assert response.json()["status"] == "CLOSED"


def test_submit_application_to_open_job():
    job = create_job()

    response = client.post(
        f"/jobs/{job['id']}/applications",
        json={
            "candidate_name": "Eason Ong",
            "candidate_email": "eason@example.com",
        },
    )

    assert response.status_code == 201

    application = response.json()

    assert application["job_id"] == job["id"]
    assert application["candidate_name"] == "Eason Ong"
    assert application["candidate_email"] == "eason@example.com"
    assert "id" in application
    assert "submitted_at" in application


def test_closed_job_rejects_application():
    job = create_job()

    client.post(f"/jobs/{job['id']}/close")

    response = client.post(
        f"/jobs/{job['id']}/applications",
        json={
            "candidate_name": "Eason Ong",
            "candidate_email": "eason@example.com",
        },
    )

    assert response.status_code == 409
    assert "closed" in response.json()["error"]


def test_list_applications_for_job():
    job = create_job()

    client.post(
        f"/jobs/{job['id']}/applications",
        json={
            "candidate_name": "Eason Ong",
            "candidate_email": "eason@example.com",
        },
    )

    response = client.get(f"/jobs/{job['id']}/applications")

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["candidate_name"] == "Eason Ong"


def test_invalid_email_returns_422():
    job = create_job()

    response = client.post(
        f"/jobs/{job['id']}/applications",
        json={
            "candidate_name": "Eason Ong",
            "candidate_email": "invalid-email",
        },
    )

    assert response.status_code == 422


def test_invalid_status_returns_400():
    response = client.get("/jobs?status=INVALID")

    assert response.status_code == 400
    assert response.json()["error"] == "status must be OPEN or CLOSED"