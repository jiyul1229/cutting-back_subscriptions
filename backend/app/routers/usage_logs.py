from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import case, func, select

from app.calculations import (
    BUSINESS_TZ, COMPARISON_DAYS, USAGE_EVALUATION_DAYS, USAGE_WINDOWS, business_date, today,
)
from app.decision_state import cancel_tagged
from app.models import AppSettings, PaymentRecord, Subscription, UsageLog
from app.routers.dependencies import (
    DatabaseSession, SubscriptionId, SyncedSession, get_subscription_or_404, validate_date_range,
)
from app.schemas import (
    LegacyCheckInCreate, UsageCheckItem, UsageCheckResponse, UsageLogCreate, UsageLogResponse,
    UsageLogUpdate, UsageSource, UsageSummaryResponse, UsageSyncRequest, UsageSyncResponse,
)

router = APIRouter(prefix="/api", tags=["usage"])


def save_log(subscription_id: int, payload: UsageLogCreate, db: DatabaseSession) -> UsageLog:
    get_subscription_or_404(subscription_id, db)
    log = UsageLog(subscription_id=subscription_id, **payload.model_dump())
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


@router.post("/subscriptions/{id}/usage-logs", response_model=UsageLogResponse, status_code=201)
def create_usage_log(id: SubscriptionId, payload: UsageLogCreate, db: DatabaseSession):
    return save_log(id, payload, db)


@router.post("/subscriptions/{id}/check-ins", response_model=UsageLogResponse, status_code=201, deprecated=True)
def create_check_in(id: SubscriptionId, payload: LegacyCheckInCreate, db: DatabaseSession):
    # 이전 입력 경로만 유지합니다. 응답은 새 UsageLog 계약으로 통일합니다.
    return save_log(id, UsageLogCreate(
        used_date=business_date(payload.checked_at), memo=payload.memo
    ), db)


@router.post("/usage-logs/sync", response_model=UsageSyncResponse)
def sync_auto_usage(payload: UsageSyncRequest, db: DatabaseSession):
    """폰에서 읽은 Android 앱별 하루 사용 시간을 올립니다.

    구독·날짜마다 자동 기록 1건을 유지합니다. 같은 날을 다시 보내면 시간을 덮어쓰고,
    0분이면 그날 자동 기록을 지웁니다. 수기·알림 기록은 건드리지 않습니다.
    """
    if not db.get(AppSettings, 1).auto_tracking_enabled:
        raise HTTPException(409, "Auto tracking is disabled in settings")
    packages = {entry.package_name for entry in payload.entries}
    linked = {
        subscription.android_package: subscription.id
        for subscription in db.scalars(select(Subscription).where(Subscription.android_package.in_(packages)))
    }
    created = updated = deleted = 0
    for entry in payload.entries:
        subscription_id = linked.get(entry.package_name)
        if subscription_id is None:
            continue
        log = db.scalar(select(UsageLog).where(
            UsageLog.subscription_id == subscription_id, UsageLog.used_date == entry.used_date,
            UsageLog.source == "mobile_auto",
        ))
        if entry.duration_minutes == 0:
            if log is not None:
                db.delete(log)
                deleted += 1
        elif log is None:
            db.add(UsageLog(
                subscription_id=subscription_id, used_date=entry.used_date, source="mobile_auto",
                duration_minutes=entry.duration_minutes, device="phone",
            ))
            created += 1
        elif log.duration_minutes != entry.duration_minutes:
            log.duration_minutes = entry.duration_minutes
            updated += 1
    db.commit()
    return UsageSyncResponse(
        created=created, updated=updated, deleted=deleted,
        unmatched_packages=sorted(packages - linked.keys()),
    )


@router.get("/usage-checks", response_model=UsageCheckResponse)
def get_usage_checks(db: DatabaseSession):
    """이용 확인 알림("오늘 OO 보셨나요?")에 띄울 구독 목록.

    오늘 수기·알림 기록이 없는 활성 구독이 대상입니다. 폰 자동 측정이 있어도 TV·태블릿 시청은
    따로 확인해야 하므로 제외하지 않고 auto_tracked와 오늘 자동 측정 시간을 함께 줍니다.
    """
    settings = db.get(AppSettings, 1)
    current = today()
    enabled = settings.notifications_enabled and settings.usage_check_enabled
    items = []
    if enabled:
        logs = db.execute(select(UsageLog.subscription_id, UsageLog.source, UsageLog.duration_minutes)
                          .where(UsageLog.used_date == current)).all()
        answered = {sid for sid, source, _ in logs if source != "mobile_auto"} | cancel_tagged(db)
        auto_minutes = {sid: minutes for sid, source, minutes in logs if source == "mobile_auto"}
        for subscription in db.scalars(select(Subscription).where(
            Subscription.status == "active", Subscription.track_usage.is_(True)
        ).order_by(Subscription.id)):
            if subscription.id in answered:
                continue
            items.append(UsageCheckItem(
                subscription_id=subscription.id, name=subscription.name,
                auto_tracked=subscription.android_package is not None,
                today_auto_minutes=auto_minutes.get(subscription.id),
            ))
    return UsageCheckResponse(
        enabled=enabled, check_time=settings.usage_check_time, date=current, items=items,
    )


@router.get("/subscriptions/{id}/usage-logs", response_model=list[UsageLogResponse])
def list_usage_logs(
    id: SubscriptionId, db: DatabaseSession,
    start_date: date | None = None,
    end_date: date | None = None,
    source: UsageSource | None = None,
):
    validate_date_range(start_date, end_date)
    get_subscription_or_404(id, db, allow_deleted=True)
    query = select(UsageLog).where(UsageLog.subscription_id == id)
    if start_date is not None:
        query = query.where(UsageLog.used_date >= start_date)
    if end_date is not None:
        query = query.where(UsageLog.used_date <= end_date)
    if source is not None:
        query = query.where(UsageLog.source == source)
    return list(db.scalars(query.order_by(UsageLog.used_date.desc(), UsageLog.id.desc())))


@router.patch("/usage-logs/{log_id}", response_model=UsageLogResponse)
def update_usage_log(log_id: SubscriptionId, payload: UsageLogUpdate, db: DatabaseSession):
    log = db.get(UsageLog, log_id)
    if log is None:
        raise HTTPException(404, "Usage log not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(log, field, value)
    db.commit()
    db.refresh(log)
    return log


@router.delete("/usage-logs/{log_id}", status_code=204)
def delete_usage_log(log_id: SubscriptionId, db: DatabaseSession):
    log = db.get(UsageLog, log_id)
    if log is None:
        raise HTTPException(404, "Usage log not found")
    db.delete(log)
    db.commit()
    return Response(status_code=204)


@router.get("/subscriptions/{id}/usage-summary", response_model=UsageSummaryResponse)
def get_usage_summary(id: SubscriptionId, db: SyncedSession) -> UsageSummaryResponse:
    subscription = get_subscription_or_404(id, db, allow_deleted=True)
    current = today()
    counts = db.execute(select(
        *[func.count(case((UsageLog.used_date >= current - timedelta(days=days - 1), 1)))
          for days in USAGE_WINDOWS],
        func.count(UsageLog.id),
        func.min(UsageLog.used_date),
        func.count(case((
            (UsageLog.used_date >= current - timedelta(days=2 * COMPARISON_DAYS - 1))
            & (UsageLog.used_date <= current - timedelta(days=COMPARISON_DAYS)), 1
        ))),
        *[func.coalesce(func.sum(case((
            UsageLog.used_date >= current - timedelta(days=days - 1), UsageLog.duration_minutes
        ))), 0) for days in (7, COMPARISON_DAYS)],
        func.coalesce(func.sum(UsageLog.duration_minutes), 0),
    ).where(UsageLog.subscription_id == id, UsageLog.used_date <= current)).one()
    count_7, count_30, count_90, total, earliest_use, previous, minutes_7, minutes_30, minutes_total = counts
    tracking = subscription.created_at
    if earliest_use is not None and earliest_use < business_date(tracking):
        tracking = datetime.combine(earliest_use, time.min, BUSINESS_TZ).astimezone(timezone.utc).replace(tzinfo=None)
    observation = max(1, (current - business_date(tracking)).days + 1)
    previous_count = previous if observation >= 2 * COMPARISON_DAYS else None
    cost = cost_per_hour = None
    if observation >= COMPARISON_DAYS and count_30:
        paid_count, paid_sum = db.execute(select(
            func.count(PaymentRecord.id), func.sum(PaymentRecord.amount_won)
        ).where(
            PaymentRecord.subscription_id == id,
            PaymentRecord.paid_date >= current - timedelta(days=COMPARISON_DAYS - 1),
            PaymentRecord.paid_date <= current,
        )).one()
        if paid_count:
            cost = round(paid_sum / count_30, 2)
            if minutes_30:
                cost_per_hour = round(paid_sum / (minutes_30 / 60), 2)
    return UsageSummaryResponse(
        subscription_id=id, observation_days=observation,
        usage_count_7d=count_7, usage_count_30d=count_30, usage_count_90d=count_90,
        total_usage_count=total, usage_minutes_7d=minutes_7, usage_minutes_30d=minutes_30,
        total_usage_minutes=minutes_total, previous_30d_usage_count=previous_count,
        usage_change_30d=None if previous_count is None else count_30 - previous_count,
        cost_per_use_30d=cost, cost_per_hour_30d=cost_per_hour, tracking_started_at=tracking,
        data_status="sufficient" if observation >= USAGE_EVALUATION_DAYS else "collecting",
    )
