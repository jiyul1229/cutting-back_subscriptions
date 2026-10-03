from fastapi import APIRouter
from sqlalchemy import func, select

from app.decision_state import latest_decisions
from app.calculations import (
    cancel_window, month_bounds, month_shift, monthly_amount, next_renewal, today, yearly_amount,
)
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
    decisions = latest_decisions(db, [subscription.id for subscription in subscriptions])
    items = []
    total = 0
    for subscription in subscriptions:
        upcoming = next_renewal(subscription, current)
        # 통신비·보험료처럼 이용 기록 대상이 아닌 고정지출은 해지 기한을 보여주지 않습니다(문서 R2).
        window_start, window_end = cancel_window(subscription, current) if subscription.track_usage else (None, None)
        total += monthly_amount(subscription)
        items.append(DashboardSubscription(**{
            **SubscriptionResponse.model_validate(subscription).model_dump(),
            "next_renewal_date": upcoming, "d_day": (upcoming - current).days,
            "latest_decision": decisions.get(subscription.id),
            "cancel_window_start": window_start, "cancel_window_end": window_end,
        }))
    items.sort(key=lambda item: (item.next_renewal_date, item.id))
    # 이번 달 구독료는 월 환산 합계(연간은 /12). 전월 대비는 지난달 실제 결제액(분석 제외·해지·삭제 구독 포함)과 비교합니다.
    start, end = month_bounds(*month_shift(current.year, current.month, -1))
    previous = db.scalar(select(func.sum(PaymentRecord.amount_won)).where(
        PaymentRecord.paid_date >= start, PaymentRecord.paid_date <= end
    ))
    change_won, change_ratio = change(total, previous)
    return DashboardResponse(
        monthly_total_won=total, yearly_total_won=sum(yearly_amount(s) for s in subscriptions), previous_month_paid_won=previous or None,
        change_won=change_won, change_ratio=change_ratio,
        active_subscription_count=len(items), subscriptions=items,
    )
