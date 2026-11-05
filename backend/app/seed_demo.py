from sqlmodel import Session

from app import crud
from app.core.config import settings
from app.core.db import engine, init_db
from app.models import UserCreate, UserRole


def main() -> None:
    if settings.FASTAPI_ENV != "development":
        raise RuntimeError("Demo accounts can only be seeded in development")

    with Session(engine) as session:
        init_db(session)
        for role in (UserRole.manager, UserRole.member):
            email = f"{role.value}@example.com"
            if not crud.get_user_by_email(session=session, email=email):
                crud.create_user(
                    session=session,
                    user_create=UserCreate(
                        email=email,
                        password="DemoPassword123!",
                        full_name=f"Demo {role.value.title()}",
                        role=role,
                    ),
                )


if __name__ == "__main__":
    main()
