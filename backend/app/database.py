from collections.abc import Generator
import os
from pathlib import Path
from sqlite3 import Connection

from sqlalchemy import URL, create_engine, event
from sqlalchemy.orm import Session, sessionmaker


# 실행 위치와 관계없이 프로젝트 루트의 DB 파일을 사용합니다.
DATABASE_PATH = Path(
    os.environ.get(
        "SUBSCRIPTION_DB_PATH",
        str(Path(__file__).resolve().parent.parent / "subscriptions.db"),
    )
).resolve()
DATABASE_URL = URL.create("sqlite", database=str(DATABASE_PATH))

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def enable_foreign_keys(connection: Connection, _connection_record) -> None:
    cursor = connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


SessionLocal = sessionmaker(bind=engine)


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session
