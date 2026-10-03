from fastapi import APIRouter
from sqlalchemy import select

from app.calculations import month_bounds, scheduled_date, today
from app.decision_state import cancel_tagged
from app.models import PaymentRecord, Subscription
from app.routers.dependencies import SyncedSession, Month, Year
from app.schemas import CalendarItem

router = APIRouter(prefix="/api/calendar", tags=["calendar"])


@router.get("", response_model=list[CalendarItem])
def get_calendar(year: Year, month: Month, db: SyncedSession):
    start, end = month_bounds(year, month)
    current = today()
    records = db.execute(select(PaymentRecord, Subscription.name).join(Subscription).where(
        PaymentRecord.paid_date >= start, PaymentRecord.paid_date <= end
    )).all()
    # 이번 달 결제 기록이 있거나 '해지' 태그를 붙인 구독은 예정 항목을 표시하지 않습니다.
    hidden_ids = {payment.subscription_id for payment, _ in records} | cancel_tagged(db)
    items = []
    for subscription in db.scalars(select(Subscription).where(Subscription.status == "active")):
        scheduled = scheduled_date(subscription, year, month)
        if scheduled is not None and scheduled >= current and subscription.id not in hidden_ids:
            items.append(CalendarItem(
                date=scheduled, subscription_id=subscription.id, name=subscription.name,
                amount_won=subscription.price_won, type="scheduled",
            ))
    for payment, name in records:
        items.append(CalendarItem(
            date=payment.paid_date, subscription_id=payment.subscription_id, name=name,
            amount_won=payment.amount_won, type="paid", payment_id=payment.id,
        ))
    return sorted(items, key=lambda item: (item.date, item.subscription_id, item.type, item.payment_id or 0))
