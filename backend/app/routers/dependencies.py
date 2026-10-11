from typing import Annotated
from datetime import date

from fastapi import Depends, HTTPException, Path, Query
from fastapi.exceptions import RequestValidationError
from sqlalchemy.orm import Session

from app.auto_payments import ensure_auto_payments
from app.database import get_db
from app.models import Subscription


DatabaseSession = Annotated[Session, Depends(get_db)]


def get_synced_db(db: DatabaseSession) -> Session:
    """결제 기록을 읽는 API는 지난 결제일의 자동 기록을 먼저 만듭니다."""
    ensure_auto_payments(db)
    return db


SyncedSession = Annotated[Session, Depends(get_synced_db)]
SubscriptionId = Annotated[int, Path(gt=0, le=9223372036854775807)]
Year = Annotated[int, Query(ge=1, le=9998)]
Month = Annotated[int, Query(ge=1, le=12)]


def validate_date_range(start_date: date | None, end_date: date | None) -> None:
    if start_date is not None and end_date is not None and start_date > end_date:
        raise RequestValidationError([{
            "type": "value_error", "loc": ("query", "end_date"),
            "msg": "end_date must be on or after start_date", "input": end_date.isoformat(),
        }])


def get_subscription_or_404(
    subscription_id: int, db: Session, allow_deleted: bool = False
) -> Subscription:
    """삭제(숨김)된 구독은 조회 API에서만 allow_deleted=True로 읽을 수 있습니다."""
    subscription = db.get(Subscription, subscription_id)
    if subscription is None or (subscription.deleted_at is not None and not allow_deleted):
        raise HTTPException(status_code=404, detail="Subscription not found")
    return subscription
