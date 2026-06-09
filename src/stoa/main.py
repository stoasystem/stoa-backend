from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

from stoa.config import settings
from stoa.routers import (
    admin,
    auth,
    billing,
    conversations,
    files,
    notifications,
    parents,
    practice,
    questions,
    students,
    teachers,
    tutors,
)

app = FastAPI(
    title="STOA API",
    description="STOA learning platform backend — Zurich, Switzerland",
    version="0.1.0",
    docs_url="/docs" if settings.environment != "production" else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(conversations.router, prefix="/conversations", tags=["conversations"])
app.include_router(conversations.teacher_help_router, prefix="/teacher-help", tags=["teacher-help"])
app.include_router(practice.router, prefix="/practice", tags=["practice"])
app.include_router(questions.router, prefix="/questions", tags=["questions"])
app.include_router(students.router, prefix="/students", tags=["students"])
app.include_router(teachers.router, prefix="/teachers", tags=["teachers"])
app.include_router(tutors.router, prefix="/tutors", tags=["tutors"])
app.include_router(parents.router, prefix="/parents", tags=["parents"])
app.include_router(billing.router, prefix="/billing", tags=["billing"])
app.include_router(notifications.router, prefix="/notifications", tags=["notifications"])
app.include_router(notifications.admin_router, prefix="/admin", tags=["admin-notifications"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])
app.include_router(files.router, prefix="/files", tags=["files"])


@app.get("/health")
def health_check():
    return {"status": "ok", "version": "0.1.0"}


# AWS Lambda handler via Mangum
handler = Mangum(app, lifespan="off")
