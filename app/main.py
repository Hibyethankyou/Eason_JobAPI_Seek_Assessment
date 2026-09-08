from __future__ import annotations
import re # for email validation
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
 
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

class JobStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED" 

class Job(BaseModel):
    id: str
    title: str
    description: str
    location: str
    created_at: datetime
    status: JobStatus

class Application(BaseModel):
    id: str
    job_id: str
    candidate_name: str
    candidate_email: str
    submitted_at: datetime
 
class CreateJobRequest(BaseModel):
    title: str
    description: str
    location: str
 
    @field_validator("title", "description", "location")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must not be blank")
        return v.strip()
 
 
class SubmitApplicationRequest(BaseModel):
    candidate_name: str = Field(min_length=1)
    candidate_email: str
    @field_validator("candidate_name")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must not be blank")
        return v.strip()

    @field_validator("candidate_email")
    @classmethod
    def valid_email(cls, v: str) -> str:
        if not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", v or ""):
            raise ValueError("invalid email format")
        return v
 
 
#Domain Error Categories (for clean separation of concerns between Services and FastAPI)
class NotFoundError(Exception):
    pass
class ConflictError(Exception):
    pass
class ValidationError(Exception):
    pass
 
#JobRepository and ApplicationRepository are abstract base classes (ABCs) that define the interface for data access. 
class JobRepository(ABC):
    @abstractmethod
    def create(self, job: Job) -> Job: ...
 
    @abstractmethod
    def find_by_id(self, job_id: str) -> Optional[Job]: ...
 
    @abstractmethod
    def find_all(self, status: Optional[JobStatus] = None) -> list[Job]: ...
 
    @abstractmethod
    def update(self, job: Job) -> Job: ...
 
 
class ApplicationRepository(ABC):
    @abstractmethod
    def create(self, application: Application) -> Application: ...
 
    @abstractmethod
    def find_by_job_id(self, job_id: str) -> list[Application]: ...
 
 
#Using Short term Memory by temporarily storing data in memory for the purpose of this assessment.
class InMemoryJobRepository(JobRepository):
    def __init__(self) -> None:
        self._store: dict[str, Job] = {}
 
    def create(self, job: Job) -> Job:
        self._store[job.id] = job
        return job
 
    def find_by_id(self, job_id: str) -> Optional[Job]:
        return self._store.get(job_id)
 
    def find_all(self, status: Optional[JobStatus] = None) -> list[Job]:
        jobs = list(self._store.values())
        if status:
            return [j for j in jobs if j.status == status]
        else:
            return jobs 
        
    def update(self, job: Job) -> Job:
        self._store[job.id] = job
        return job
 
 
class InMemoryApplicationRepository(ApplicationRepository):
    def __init__(self) -> None:
        self._store: dict[str, Application] = {}
 
    def create(self, application: Application) -> Application:
        self._store[application.id] = application
        return application
 
    def find_by_job_id(self, job_id: str) -> list[Application]:
        return [a for a in self._store.values() if a.job_id == job_id]
 
 
#Business Rules for the Job and Application Service in Service Layer
class JobService:
    # Constructor injection: JobService only knows the JobRepository
    # interface, not whether it's in-memory or Postgres underneath.
    def __init__(self, job_repo: JobRepository) -> None:
        self._job_repo = job_repo
 
    def create_job(self, req: CreateJobRequest) -> Job:
        job = Job(
            id=str(uuid.uuid4()),
            title=req.title,
            description=req.description,
            location=req.location,
            created_at=datetime.now(timezone.utc),
            status=JobStatus.OPEN,
        )
        return self._job_repo.create(job)
 
    def get_job(self, job_id: str) -> Job:
        job = self._job_repo.find_by_id(job_id)
        if job is None:
            raise NotFoundError(f"Job {job_id} not found")
        return job
 
    def list_jobs(self, status: Optional[str] = None) -> list[Job]:
        if status is None:
            return self._job_repo.find_all()
        try:
            parsed_status = JobStatus(status)
        except ValueError:
            raise ValidationError("status must be OPEN or CLOSED")
        return self._job_repo.find_all(parsed_status)
 
    def close_job(self, job_id: str) -> Job:
        job = self.get_job(job_id)  # raises NotFoundError if missing
        if job.status == JobStatus.CLOSED:
            return job
        updated = job.model_copy(update={"status": JobStatus.CLOSED})
        return self._job_repo.update(updated)
#Prevent muttable state by using model_copy to create a new instance with updated status.
 
class ApplicationService:
    def __init__(self, application_repo: ApplicationRepository, job_repo: JobRepository) -> None:
        self._application_repo = application_repo
        self._job_repo = job_repo
 
    def submit_application(self, job_id: str, req: SubmitApplicationRequest) -> Application:
        job = self._job_repo.find_by_id(job_id)
        if job is None:
            raise NotFoundError(f"Job {job_id} not found")
 
        # Business rule where closed jobs reject new applications.
        if job.status == JobStatus.CLOSED:
            raise ConflictError(f"Job {job_id} is closed and no longer accepts applications")

        #Build application object and store in repo. 
        application = Application(
            id=str(uuid.uuid4()),
            job_id=job.id,
            candidate_name=req.candidate_name,
            candidate_email=req.candidate_email,
            submitted_at=datetime.now(timezone.utc),
        )
        return self._application_repo.create(application)
 
    def list_applications_for_job(self, job_id: str) -> list[Application]:
        # Confirms job exists so callers get a clean 404 instead of an empty [] without any message error.
        if self._job_repo.find_by_id(job_id) is None:
            raise NotFoundError(f"Job {job_id} not found")
        return self._application_repo.find_by_job_id(job_id)

job_repository = InMemoryJobRepository()
application_repository = InMemoryApplicationRepository()
job_service = JobService(job_repository)
application_service = ApplicationService(application_repository, job_repository)
 
app = FastAPI(title="Job Marketplace API")
 
@app.get("/")
def root() -> dict:
    return {"message": "Job Marketplace API is running. See /docs for interactive API docs."}
 
@app.exception_handler(NotFoundError)
async def not_found_handler(_req: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"error": str(exc)})
 
@app.exception_handler(ConflictError)
async def conflict_handler(_req: Request, exc: ConflictError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"error": str(exc)})
 
@app.exception_handler(ValidationError)
async def validation_handler(_req: Request, exc: ValidationError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"error": str(exc)})
 
# ---------------Jobs -----------------------------
 
@app.post("/jobs", response_model=Job, status_code=status.HTTP_201_CREATED)
def create_job(req: CreateJobRequest) -> Job:
    return job_service.create_job(req)
 
@app.get("/jobs", response_model=list[Job])
def list_jobs(status: Optional[str] = None) -> list[Job]:
    return job_service.list_jobs(status)
 
@app.get("/jobs/{job_id}", response_model=Job)
def get_job(job_id: str) -> Job:
    return job_service.get_job(job_id)
 
@app.post("/jobs/{job_id}/close", response_model=Job)
def close_job(job_id: str) -> Job:
    return job_service.close_job(job_id)
 
# ---------------Applications -----------------------------
 
@app.post(
    "/jobs/{job_id}/applications",
    response_model=Application,
    status_code=status.HTTP_201_CREATED,
)
def submit_application(job_id: str, req: SubmitApplicationRequest) -> Application:
    return application_service.submit_application(job_id, req)
 
 
@app.get("/jobs/{job_id}/applications", response_model=list[Application])
def list_applications(job_id: str) -> list[Application]:
    return application_service.list_applications_for_job(job_id)