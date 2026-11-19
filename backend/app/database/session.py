from collections.abc import Generator

from sqlalchemy.orm import Session, sessionmaker

from backend.app.database.connection import get_engine


class BoundSessionMaker(sessionmaker):
    def __call__(self, **local_kw):
        if "bind" not in local_kw and self.kw.get("bind") is None:
            local_kw["bind"] = get_engine()
        return super().__call__(**local_kw)


SessionLocal = BoundSessionMaker(autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session

