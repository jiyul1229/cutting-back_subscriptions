from fastapi import APIRouter
from sqlalchemy import func, select

from app.calculations import CANCEL_WINDOW_DAYS, INACTIVITY_DAYS, business_date, next_renewal, today
from app.decision_state import cancel_tagged
from app.models import AppSettings, Subscription, UsageLog
from app.recommendations import build_recommendations
from app.routers.dependencies import DatabaseSession
from app.schemas import NotificationCandidate

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationCandidate])
def notification_candidates(db: DatabaseSession):
    settings = db.get(AppSettings, 1)
    if not settings.notifications_enabled:
        return []
    current = today()
    last_usage = select(
        UsageLog.subscription_id, func.max(UsageLog.used_date).label("last_used")
    ).where(UsageLog.used_date <= current).group_by(UsageLog.subscription_id).subquery()
    rows = db.execute(select(Subscription, last_usage.c.last_used).outerjoin(
        last_usage, last_usage.c.subscription_id == Subscription.id
    ).where(
        Subscription.status == "active", Subscription.notification_enabled.is_(True)
    ).order_by(Subscription.id)).all()
    result = []
    tagged = cancel_tagged(db)
    recommended = {}
    if settings.recommendation_enabled:
        recommended = {item.subscription_id: item.reasons for item in build_recommendations(db, current)}
    for subscription, last_used in rows:
        if subscription.id in tagged:  # 앱에서 '해지' 태그를 붙인 구독은 알리지 않음
            continue
        upcoming = next_renewal(subscription, current)
        d_day = (upcoming - current).days
        if d_day <= subscription.renewal_reminder_days:
            result.append(NotificationCandidate(
                subscription_id=subscription.id, name=subscription.name, type="renewal",
                next_renewal_date=upcoming, d_day=d_day,
            ))
        elif 1 <= d_day <= CANCEL_WINDOW_DAYS:
            # 결제 알림 기간 전이면서 해지 권장 기간이면 해지 여부를 정하라고 알립니다.
            result.append(NotificationCandidate(
                subscription_id=subscription.id, name=subscription.name, type="cancel_window",
                next_renewal_date=upcoming, d_day=d_day,
            ))
        baseline = last_used if last_used is not None else business_date(subscription.created_at)
        days = (current - baseline).days
        if subscription.track_usage and days >= INACTIVITY_DAYS:
            result.append(NotificationCandidate(
                subscription_id=subscription.id, name=subscription.name,
                type="no_usage", days_without_usage=days,
            ))
        if subscription.id in recommended:
            result.append(NotificationCandidate(
                subscription_id=subscription.id, name=subscription.name,
                type="recommendation", reasons=recommended[subscription.id],
            ))
    return result
