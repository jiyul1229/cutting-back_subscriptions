from fastapi import APIRouter

from app.models import AppSettings
from app.routers.dependencies import DatabaseSession
from app.schemas import SettingsResponse, SettingsUpdate

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=SettingsResponse)
def get_settings(db: DatabaseSession):
    return db.get(AppSettings, 1)


@router.patch("", response_model=SettingsResponse)
def update_settings(payload: SettingsUpdate, db: DatabaseSession):
    settings = db.get(AppSettings, 1)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(settings, field, value)
    db.commit()
    db.refresh(settings)
    return settings
