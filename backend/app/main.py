from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import os
from urllib.parse import urlsplit

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect
from sqlalchemy.dialects.sqlite import insert

from app.database import engine
from app.models import AppSettings, Base
from app.routers import (
    analytics, calendar, dashboard, decisions, notifications, payments,
    settings, subscriptions, usage_logs,
)
from app.schemas import HealthResponse


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    try:
        inspector = inspect(engine)
        for table in Base.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            columns = {column["name"] for column in inspector.get_columns(table.name)}
            if columns != set(table.columns.keys()):
                raise RuntimeError(
                    "Legacy subscription schema detected or incompatible table: " + table.name
                    + ". Stop the server, then run python -m app.migrate. See README.md."
                )
        Base.metadata.create_all(bind=engine)
        with engine.begin() as connection:
            connection.execute(insert(AppSettings).values(id=1).on_conflict_do_nothing(index_elements=["id"]))
        yield
    finally:
        engine.dispose()


def read_cors_origins() -> list[str]:
    """브라우저의 정확한 Origin만 허용합니다. 빈 설정은 CORS 허용을 끕니다."""
    raw = os.environ.get(
        "CORS_ALLOW_ORIGINS", "http://localhost:8081,http://127.0.0.1:8081"
    )
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    for origin in origins:
        parsed = urlsplit(origin)
        if (
            parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.path or parsed.query or parsed.fragment
            or parsed.username or parsed.password or "*" in origin
        ):
            raise ValueError("CORS_ALLOW_ORIGINS must contain exact http(s) origins without paths")
    return origins


app = FastAPI(title="구독 다이어트 플래너 API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=read_cors_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
)
app.include_router(subscriptions.router)
app.include_router(usage_logs.router)
app.include_router(payments.router)
app.include_router(dashboard.router)
app.include_router(calendar.router)
app.include_router(analytics.router)
app.include_router(decisions.router)
app.include_router(settings.router)
app.include_router(notifications.router)


@app.get("/health", response_model=HealthResponse, tags=["health"])
def health_check() -> HealthResponse:
    return HealthResponse(status="ok")
