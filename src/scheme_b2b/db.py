from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .config import Settings
from .models import Base


def create_session_factory(settings: Settings):
    connect_args = ({"check_same_thread": False, "timeout": 30} if settings.local_db_url.startswith("sqlite") else {})
    engine = create_engine(
        settings.local_db_url,
        future=True,
        pool_pre_ping=True,
        connect_args=connect_args,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
