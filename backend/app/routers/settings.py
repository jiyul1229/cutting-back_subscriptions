from fastapi import APIRouter, Response
from sqlalchemy import delete

from app.models import (
    AppSettings, DecisionHistory, PaymentRecord, RecommendationWarning, Subscription, UsageLog,
)
from app.routers.dependencies import DatabaseSession
from app.schemas import ResetDataRequest, SettingsResponse, SettingsUpdate

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


@router.post("/reset-data", status_code=204)
def reset_data(payload: ResetDataRequest, db: DatabaseSession) -> Response:
    """설정 화면의 '전체 초기화'. 구독·이용 기록·결제·결정·추천 기록을 모두 지웁니다. 설정값은 유지합니다.

    되돌릴 수 없으므로 {"confirm": true}를 보내야만 실행합니다.
    """
    for model in (RecommendationWarning, DecisionHistory, UsageLog, PaymentRecord, Subscription):
        db.execute(delete(model))
    db.commit()
    return Response(status_code=204)
