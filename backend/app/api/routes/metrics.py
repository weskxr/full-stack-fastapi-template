from fastapi import APIRouter, Depends
from sqlmodel import func, select

from app.api.deps import SessionDep, require_roles
from app.models import Item, MetricsPublic, User, UserRole

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get(
    "/",
    dependencies=[Depends(require_roles(UserRole.admin, UserRole.manager))],
    response_model=MetricsPublic,
)
def read_metrics(session: SessionDep) -> MetricsPublic:
    return MetricsPublic(
        total_users=session.exec(select(func.count()).select_from(User)).one(),
        total_items=session.exec(select(func.count()).select_from(Item)).one(),
    )
