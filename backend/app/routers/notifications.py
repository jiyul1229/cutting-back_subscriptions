from datetime import date, datetime, time, timedelta
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.auto_payments import already_paid
from app.calculations import (
    BUSINESS_TZ, NO_RECORD_REMINDER_DAYS, REMINDER_TIME, business_date, cancel_window_days, next_renewal, today,
)
from app.decision_state import cancel_tagged
from app.models import AppSettings, Subscription, UsageLog
from app.recommendations import build_recommendations, record_warnings
from app.routers.dependencies import DatabaseSession
from app.schemas import NotificationCandidate, ReminderScheduleItem

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def notifiable(db: DatabaseSession) -> list[Subscription]:
    """알림 대상: 활성 + 구독별 알림 켜짐 + '해지' 태그 아님."""
    tagged = cancel_tagged(db)
    return [s for s in db.scalars(select(Subscription).where(
        Subscription.status == "active", Subscription.notification_enabled.is_(True)
    ).order_by(Subscription.id)) if s.id not in tagged]


def last_record_dates(db: DatabaseSession, current: date) -> dict[int, date]:
    """구독별 마지막 이용 기록 날짜(수기·알림·자동 측정 모두)."""
    return dict(db.execute(select(UsageLog.subscription_id, func.max(UsageLog.used_date)).where(
        UsageLog.used_date <= current
    ).group_by(UsageLog.subscription_id)).all())


def record_baseline(subscription: Subscription, last_records: dict[int, date]) -> date:
    """기록이 없으면 등록일부터 셉니다."""
    return last_records.get(subscription.id) or business_date(subscription.created_at)


@router.get("", response_model=list[NotificationCandidate])
def notification_candidates(db: DatabaseSession):
    """지금 보여줄 알림 목록."""
    settings = db.get(AppSettings, 1)
    if not settings.notifications_enabled:
        return []
    current = today()
    last_records = last_record_dates(db, current)
    recommended = {}
    if settings.recommendation_enabled:
        items = build_recommendations(db, current)
        record_warnings(db, items, current)
        recommended = {item.subscription_id: item.reasons for item in items}
    result = []
    for subscription in notifiable(db):
        upcoming = next_renewal(subscription, current)
        d_day = (upcoming - current).days
        if d_day <= subscription.renewal_reminder_days:
            result.append(NotificationCandidate(
                subscription_id=subscription.id, name=subscription.name, type="renewal",
                next_renewal_date=upcoming, d_day=d_day,
            ))
        elif subscription.track_usage and 1 <= d_day <= cancel_window_days(subscription):
            # 결제 알림 기간 전이면서 해지 권장 기간이면 해지 여부를 정하라고 알립니다.
            # 통신비·보험료(track_usage=false)는 결제 알림만 보냅니다(문서 R2).
            result.append(NotificationCandidate(
                subscription_id=subscription.id, name=subscription.name, type="cancel_window",
                next_renewal_date=upcoming, d_day=d_day,
            ))
        if subscription.track_usage and settings.usage_check_enabled:
            days = (current - record_baseline(subscription, last_records)).days
            if days >= NO_RECORD_REMINDER_DAYS:
                result.append(NotificationCandidate(
                    subscription_id=subscription.id, name=subscription.name, type="weekly_check",
                    days_without_record=days,
                ))
        if subscription.id in recommended:
            result.append(NotificationCandidate(
                subscription_id=subscription.id, name=subscription.name,
                type="recommendation", reasons=recommended[subscription.id],
            ))
    return result


def at(day: date, clock: str) -> datetime:
    hour, minute = map(int, clock.split(":"))
    return datetime.combine(day, time(hour, minute), BUSINESS_TZ)


@router.get("/schedule", response_model=list[ReminderScheduleItem])
def reminder_schedule(db: DatabaseSession, days: Annotated[int, Query(ge=1, le=90)] = 30):
    """폰이 미리 예약할 알림 일정(앞으로 days일). 앱을 열 때마다 받아 기존 예약을 지우고 다시 넣습니다.

    - renewal: 결제일 renewal_reminder_days일 전 09:00
    - cancel_window: 해지 권장 기간이 시작되는 날 09:00 (결제 알림보다 먼저일 때만, 이용 기록 대상만)
    - weekly_check: 마지막 기록 7일 뒤(이후 7일마다) 이용 확인 시각. 이용 확인 알림이 켜져 있을 때만
    이미 지난 시각은 넣지 않습니다. 이미 결제한 주기의 결제일은 건너뜁니다.
    """
    settings = db.get(AppSettings, 1)
    if not settings.notifications_enabled:
        return []
    now = datetime.now(BUSINESS_TZ)
    current = now.date()
    horizon = current + timedelta(days=days)
    last_records = last_record_dates(db, current)
    items = []

    def add(kind: str, subscription: Subscription, fire_at: datetime, due: date | None = None):
        if now < fire_at and fire_at.date() <= horizon:
            items.append(ReminderScheduleItem(
                id=f"kood-{kind}-{subscription.id}-{fire_at.date().isoformat()}",
                subscription_id=subscription.id, name=subscription.name, type=kind, fire_at=fire_at,
                renewal_date=due, d_day_at_fire=None if due is None else (due - fire_at.date()).days,
                amount_won=None if due is None else subscription.price_won,
            ))

    for subscription in notifiable(db):
        due = next_renewal(subscription, current)
        while due <= horizon + timedelta(days=subscription.renewal_reminder_days):
            if not already_paid(db, subscription, due):
                reminder_day = due - timedelta(days=subscription.renewal_reminder_days)
                add("renewal", subscription, at(reminder_day, REMINDER_TIME), due)
                window_start = due - timedelta(days=cancel_window_days(subscription))
                if subscription.track_usage and window_start < reminder_day:
                    add("cancel_window", subscription, at(window_start, REMINDER_TIME), due)
            due = next_renewal(subscription, due + timedelta(days=1))
        if subscription.track_usage and settings.usage_check_enabled:
            fire_day = record_baseline(subscription, last_records) + timedelta(days=NO_RECORD_REMINDER_DAYS)
            # 이미 물어봤는데 아직 기록이 없으면 일주일 뒤에 다시 묻습니다.
            while at(fire_day, settings.usage_check_time) <= now:
                fire_day += timedelta(days=NO_RECORD_REMINDER_DAYS)
            add("weekly_check", subscription, at(fire_day, settings.usage_check_time))
    items.sort(key=lambda item: (item.fire_at, item.subscription_id, item.type))
    return items
