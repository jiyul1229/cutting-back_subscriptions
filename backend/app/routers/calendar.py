from datetime import timedelta

from fastapi import APIRouter
from sqlalchemy import select

from app.auto_payments import already_paid
from app.calculations import month_bounds, month_shift, scheduled_dates, today
from app.decision_state import cancel_tagged
from app.models import PaymentRecord, Subscription
from app.routers.dependencies import SyncedSession, Month, Year
from app.schemas import CalendarItem

router = APIRouter(prefix="/api/calendar", tags=["calendar"])

# 같은 날짜에서는 실제 결제, 해지 기한, 예정 순으로 보여줍니다.
TYPE_ORDER = {"paid": 0, "cancel_deadline": 1, "scheduled": 2}


@router.get("", response_model=list[CalendarItem])
def get_calendar(year: Year, month: Month, db: SyncedSession):
    """선택한 달의 실제 결제(paid), 예정 결제(scheduled), 해지 기한(cancel_deadline).

    해지 기한은 결제일 하루 전이며, 다음 달 1일 결제의 기한은 이번 달 말일에 표시됩니다.
    이미 결제한 주기, '해지' 태그 구독, 이용 기록 대상이 아닌 고정지출(보험료·통신비)은 해지 기한을 표시하지 않습니다.
    """
    start, end = month_bounds(year, month)
    current = today()
    records = db.execute(select(PaymentRecord, Subscription.name).join(Subscription).where(
        PaymentRecord.paid_date >= start, PaymentRecord.paid_date <= end
    )).all()
    tagged = cancel_tagged(db)
    next_year, next_month = month_shift(year, month, 1)
    items = []
    for subscription in db.scalars(select(Subscription).where(Subscription.status == "active")):
        if subscription.id in tagged:
            continue
        for due in scheduled_dates(subscription, year, month):
            if due >= current and not already_paid(db, subscription, due):
                items.append(CalendarItem(
                    date=due, subscription_id=subscription.id, name=subscription.name,
                    amount_won=subscription.price_won, type="scheduled",
                ))
        if not subscription.track_usage:
            continue
        dues = scheduled_dates(subscription, year, month)
        if next_year <= 9999:
            dues += scheduled_dates(subscription, next_year, next_month)
        for due in dues:
            deadline = due - timedelta(days=1)
            if start <= deadline <= end and deadline >= current and not already_paid(db, subscription, due):
                items.append(CalendarItem(
                    date=deadline, subscription_id=subscription.id, name=subscription.name,
                    amount_won=subscription.price_won, type="cancel_deadline", renewal_date=due,
                ))
    for payment, name in records:
        items.append(CalendarItem(
            date=payment.paid_date, subscription_id=payment.subscription_id, name=name,
            amount_won=payment.amount_won, type="paid", payment_id=payment.id,
        ))
    return sorted(items, key=lambda item: (
        item.date, item.subscription_id, TYPE_ORDER[item.type], item.payment_id or 0,
    ))
