from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import select

from app.models import PaymentRecord
from app.routers.dependencies import (
    DatabaseSession, SubscriptionId, SyncedSession, get_subscription_or_404, validate_date_range,
)
from app.schemas import PaymentRecordCreate, PaymentRecordResponse, PaymentRecordUpdate


router = APIRouter(prefix="/api/payments", tags=["payments"])


def get_payment_or_404(payment_id: int, db: DatabaseSession) -> PaymentRecord:
    payment = db.get(PaymentRecord, payment_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="Payment not found")
    return payment


@router.post("", response_model=PaymentRecordResponse, status_code=status.HTTP_201_CREATED)
def create_payment(payload: PaymentRecordCreate, db: DatabaseSession) -> PaymentRecord:
    subscription = get_subscription_or_404(payload.subscription_id, db)
    payment = PaymentRecord(
        **payload.model_dump(), category_snapshot=subscription.category, source="manual"
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return payment


@router.get("", response_model=list[PaymentRecordResponse])
def list_payments(
    db: SyncedSession,
    subscription_id: Annotated[int | None, Query(gt=0, le=9223372036854775807)] = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[PaymentRecord]:
    validate_date_range(start_date, end_date)
    statement = select(PaymentRecord)
    if subscription_id is not None:
        get_subscription_or_404(subscription_id, db, allow_deleted=True)
        statement = statement.where(PaymentRecord.subscription_id == subscription_id)
    if start_date is not None:
        statement = statement.where(PaymentRecord.paid_date >= start_date)
    if end_date is not None:
        statement = statement.where(PaymentRecord.paid_date <= end_date)
    return list(db.scalars(statement.order_by(PaymentRecord.paid_date.desc(), PaymentRecord.id.desc())))


@router.patch("/{payment_id}", response_model=PaymentRecordResponse)
def update_payment(
    payment_id: SubscriptionId, payload: PaymentRecordUpdate, db: DatabaseSession
) -> PaymentRecord:
    # 자동 기록의 금액이 실제 청구액과 다를 때 고칩니다. source는 바뀌지 않습니다.
    payment = get_payment_or_404(payment_id, db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(payment, field, value)
    db.commit()
    db.refresh(payment)
    return payment


@router.delete("/{payment_id}", status_code=204)
def delete_payment(payment_id: SubscriptionId, db: DatabaseSession) -> Response:
    # 지운 자동 기록은 다시 만들어지지 않습니다.
    db.delete(get_payment_or_404(payment_id, db))
    db.commit()
    return Response(status_code=204)
