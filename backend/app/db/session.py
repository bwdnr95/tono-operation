# backend/app/db/session.py

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.base import Base


engine = create_engine(settings.DATABASE_URL, future=True)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def init_db() -> None:
    """
    애플리케이션 시작 시 한 번 호출해서 테이블 생성.
    모든 도메인 모델을 메타데이터에 등록한 뒤 create_all 을 수행한다.
    """
    # ✅ 모든 도메인 모델을 한 번에 import
    import app.domain.models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
