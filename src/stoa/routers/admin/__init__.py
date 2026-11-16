"""Admin routes, one module per domain, all mounted under `/admin` by `stoa.main` (#432).

Each module keeps its own `router`; this one only gathers them. Every route still
depends on `admin_operation` itself, so a module mounted here gains no access it
did not declare.
"""

from fastapi import APIRouter

from stoa.routers.admin import (
    account_support,
    curriculum,
    moderation,
    privileged_identities,
    recovery_jobs,
    reports,
    stats,
    subscriptions,
    teacher_support,
    usage,
    usage_periods,
    users,
)

router = APIRouter()

# In the order the routes stood in the single file. No two modules serve paths
# that could match the same request, so the order is kept for readability only.
for _domain in (
    teacher_support,
    privileged_identities,
    moderation,
    curriculum,
    users,
    usage_periods,
    subscriptions,
    usage,
    account_support,
    stats,
    reports,
    recovery_jobs,
):
    router.include_router(_domain.router)
