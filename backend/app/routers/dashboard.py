from fastapi import APIRouter
from sqlalchemy import func, select

from app.calculations import month_bounds, month_shift, next_renewal, scheduled_date, today
from app.models import PaymentRecord, Subscription
from app.routers.dependencies import SyncedSession
from app.schemas import DashboardResponse, DashboardSubscription, SubscriptionResponse

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def change(current: int, previous: int | None) -> tuple[int | None, float | None]:
    if not previous:
        return None, None
    return current - previous, round((current - previous) / previous, 6)


@router.get("", response_model=DashboardResponse)
def get_dashboard(db: SyncedSession):
    current = today()
    subscriptions = list(db.scalars(select(Subscription).where(Subscription.status == "active")))
    items = []
    total = 0
    for subscription in subscriptions:
        upcoming = next_renewal(subscription, current)
        if scheduled_date(subscription, current.year, current.month) is not None:
            total += subscription.price_won
        items.append(DashboardSubscription(**{
            **SubscriptionResponse.model_validate(subscription).model_dump(),
            "next_renewal_date": upcoming, "d_day": (upcoming - current).days,
        }))
    items.sort(key=lambda item: (item.next_renewal_date, item.id))
    # 전월 대비: 이번 달 예상 구독료와 지난달 실제 결제액(분석 제외·해지·삭제 구독 포함)을 비교합니다.
    start, end = month_bounds(*month_shift(current.year, current.month, -1))
    previous = db.scalar(select(func.sum(PaymentRecord.amount_won)).where(
        PaymentRecord.paid_date >= start, PaymentRecord.paid_date <= end
    ))
    change_won, change_ratio = change(total, previous)
    return DashboardResponse(
        monthly_total_won=total, previous_month_paid_won=previous or None,
        change_won=change_won, change_ratio=change_ratio,
        active_subscription_count=len(items), subscriptions=items,
    )
