## TechStack
Using Python 3.11+, FastAPI, in-memory storage (no external DB required).

## 1. How to Run
1. create a virtual env (optional but recommended)
    python -m venv .venv
    source .venv/bin/activate        # on Windows: .venv\Scripts\activate

2. install dependencies
    pip install -r requirements.txt

3. run the API
    uvicorn main:app --reload

    The API will be available at `http://localhost:8000`.
    FastAPI auto-generates interactive docs at `http://localhost:8000/docs`
    Swagger UI is the quickest way to try every endpoint without Postman or
    curl. Each endpoint has a "Try it out" button that sends a real request
    and shows the response and status code.

-----------------------------------------------------------------------------------------------------------------------------------------

## 2. How to Run tests

    pip install pytest
    pytest -v

## Example requests
1. create a job
    curl -X POST http://localhost:8000/jobs \
    -H "Content-Type: application/json" \
    -d '{"title": "Backend Engineer", "description": "Build APIs", "location": "Kuala Lumpur"}'

2. get a single job
    curl http://localhost:8000/jobs/<job_id>

3. list all jobs, optionally filtered by status
    curl http://localhost:8000/jobs
    curl "http://localhost:8000/jobs?status=OPEN"

4. apply to a job
    curl -X POST http://localhost:8000/jobs/<job_id>/applications \
    -H "Content-Type: application/json" \
    -d '{"candidate_name": "Jane Tan", "candidate_email": "jane@example.com"}'

5. list applications for a job
    curl http://localhost:8000/jobs/<job_id>/applications

6. close a job
    curl -X POST http://localhost:8000/jobs/<job_id>/close

-----------------------------------------------------------------------------------------------------------------------------------------

## 3. Design Overview

The code is organised into four layers, each depending only on the layer below it (never sideways, never upward):

Router (FastAPI)  ->  Service (business rules)  ->  Repository (data access)


1. The Repository is an abstract interface (`ABC`). `InMemoryJobRepository` and `InMemoryApplicationRepository` are just one implementation. Swapping to Postgres/Mongo later means writing a new class that implements the same interface.

2. Business rules live only in the Service layer, not in routes. For example, "a closed job can't accept new applications" is enforced in `ApplicationService.submit_application`, not in the route handler. This means the rule can be unit tested by instantiating the service directly with an in-memory repo — no HTTP server needed.

3. Domain errors, not HTTP codes, are raised from services (`NotFoundError`, `ConflictError`, `ValidationError`). FastAPI exception handlers translate these to 404 / 409 / 400 in one place, so routes stay thin and don't repeat `if not found: return 404` logic.

4. Request/response DTOs are separate from domain models.`CreateJobRequest` and `SubmitApplicationRequest` validate input shape (blank-string checks, email format); `Job` and `Application` represent the domain. This means the external API contract can evolve without touching internal logic.

5. Immutability on update:`close_job` uses `model_copy(update=...)` rather than mutating the fetched `Job` in place, to avoid accidental shared-reference bugs.

6. `close_job` is idempotent,closing an already-closed job is a no-op, not an error, since retries/double-clicks shouldn't fail.

-----------------------------------------------------------------------------------------------------------------------------------------

## 4. Assumptions

 1. Storage is in-memory (a Python `dict`) and resets on restart — acceptable per the assessment brief, 
    and isolated behind a repository interface so it can be swapped without touching business logic.
    
2.  No authentication/authorisation — anyone can create jobs or apply, as
    explicitly scoped out of the assessment.

3.  A candidate can apply to the same job more than once (no duplicate-check
    by email). Real-world marketplaces usually block duplicate applications,
    but the brief didn't specify this, so I left it open rather than guessing
    a rule.

4.  The `status` query parameter on `GET /jobs` accepts exactly `OPEN` or
    `CLOSED` (case-sensitive); anything else returns `400`.

5.  `title`, `description`, `location`, and `candidate_name` are all
    rejected if blank/whitespace-only; `candidate_email` must match a basic
    email pattern. 

6.   Timestamps are UTC ISO-8601, generated server-side, but on clients never set
    `created_at` / `submitted_at`.

7.  No pagination on list endpoints, since the dataset is expected to be
    small for this exercise.

-----------------------------------------------------------------------------------------------------------------------------------------

## 5. What I'd Improve With More Time

1. Persistence: 
    Add a real `PostgresJobRepository` / `SqlAlchemyJobRepository` implementing the same interface.

2. Auth:  
    Simple bearer-token auth so only the job owner can close a job.

3. Pagination & sorting:
    Apply on `GET /jobs` and `GET /jobs/{id}/applications` for larger datasets.

4. Duplicate application guard :
    (Same email + job)with a `409`, once the intended business rule is confirmed.

5. Structured logging & request IDs: 
    For traceability across layers.

6. Optimistic concurrency on `close_job` (e.g. version field):
    To avoid race conditions if two requests close/read concurrently.

7. Integration tests:
    Against the actual HTTP layer (via `TestClient`) in addition to service-level unit tests, 
    to cover status codes and JSON shape end-to-end.

8. Dockerfile:
    For one-command local run without a manual venv setup.

