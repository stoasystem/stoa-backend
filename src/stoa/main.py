from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from mangum import Mangum

from stoa.config import settings
from stoa.security.errors import redacted_validation_errors
from stoa.services import locale_service, runtime_budget_service
from stoa.security.route_inventory import (
    explicit_route_classification,
    install_authorization_openapi,
)
from stoa.routers import (
    adaptive,
    admin,
    analytics,
    auth,
    billing,
    conversations,
    files,
    notifications,
    parents,
    practice,
    questions,
    students,
    teacher_applications,
    teachers,
)

app = FastAPI(
    title="STOA API",
    description="STOA learning platform backend — Zurich, Switzerland",
    version="0.1.0",
    docs_url="/docs" if settings.environment != "production" else None,
)


class RequestLocaleMiddleware:
    """Bind the language the client is reading in, for the length of a request.

    Content projections (curriculum titles, question history, assistant answers)
    read it from locale_service instead of taking the language as a parameter on
    every route.

    Plain ASGI rather than a FastAPI dependency: an app-wide dependency lands in
    every route's signature, and the authorization route inventory checks those
    exactly. Rather than BaseHTTPMiddleware because the context set here has to
    be the one the endpoint runs in.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            header = next(
                (
                    value.decode("latin-1")
                    for key, value in scope.get("headers", ())
                    if key == b"accept-language"
                ),
                None,
            )
            locale_service.set_request_locale(
                locale_service.locale_from_accept_language(header)
            )
        await self.app(scope, receive, send)


app.add_middleware(RequestLocaleMiddleware)


class RequestBudgetMiddleware:
    """Bind when the request started and how long the Lambda has left.

    Mangum puts the Lambda context in the ASGI scope; read at the door, its
    remaining time is what every later deadline in the request is measured
    against. Plain ASGI for the same reasons as the locale middleware above.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            started = runtime_budget_service.time.monotonic()
            remaining = None
            context = scope.get("aws.context")
            reader = getattr(context, "get_remaining_time_in_millis", None)
            if callable(reader):
                try:
                    remaining = float(reader()) / 1000
                except (TypeError, ValueError):
                    remaining = None
            runtime_budget_service.begin_request(
                started_monotonic=started, remaining_seconds=remaining
            )
        await self.app(scope, receive, send)


app.add_middleware(RequestBudgetMiddleware)


@app.exception_handler(RequestValidationError)
async def handle_validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
    """Answer a 422 without echoing what was sent.

    FastAPI's default body repeats the offending input, which on the
    registration route meant returning the user's plaintext password to them.
    """
    return JSONResponse(
        status_code=422,
        content={"detail": redacted_validation_errors(exc.errors())},
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
app.include_router(conversations.router, prefix="/conversations", tags=["conversations"])
app.include_router(conversations.teacher_help_router, prefix="/teacher-help", tags=["teacher-help"])
app.include_router(practice.router, prefix="/practice", tags=["practice"])
app.include_router(questions.router, prefix="/questions", tags=["questions"])
app.include_router(students.router, prefix="/students", tags=["students"])
app.include_router(teachers.router, prefix="/teachers", tags=["teachers"])
app.include_router(
    teacher_applications.router,
    prefix="/teacher-applications",
    tags=["teacher-applications"],
)
app.include_router(parents.router, prefix="/parents", tags=["parents"])
app.include_router(billing.router, prefix="/billing", tags=["billing"])
app.include_router(notifications.router, prefix="/notifications", tags=["notifications"])
app.include_router(notifications.admin_router, prefix="/admin", tags=["admin-notifications"])
app.include_router(adaptive.router, prefix="/adaptive", tags=["adaptive"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])
app.include_router(files.router, prefix="/files", tags=["files"])


@app.get("/health")
@explicit_route_classification("public", "load-balancer health probe")
def health_check():
    return {"status": "ok", "version": "0.1.0"}


install_authorization_openapi(app)


# AWS Lambda handler via Mangum
handler = Mangum(app, lifespan="off")
