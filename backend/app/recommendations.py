"""해지 추천 계산. 결과는 저장하지 않고 조회할 때마다 계산합니다.

추천 이유
- low_usage: 최근 N일 이용이 M회 이하 (설정값, 기본 90일 2회). 관찰 기간이 min(30일, N일)보다 짧으면 판단하지 않음
- duplicate_category: 같은 카테고리의 활성 구독이 3개 이상일 때, 최근 90일 이용이 가장 적은 1개
  (같으면 더 비싼 것). '기타'(etc)는 서로 다른 서비스 묶음이라 제외합니다.

이용 기록 대상이 아닌 구독(track_usage=false, 보험료·통신비 등)과 이미 '해지' 태그를 붙인 구독은
추천하지 않습니다. 미사용 구독의 이용 기록 메모에 부정 표현("안 봄" 등)이 있으면 negative_memo를 덧붙입니다.

사용자가 최근 RECOMMENDATION_SNOOZE_DAYS일 안에 유지(keep)나 보류(hold)를 결정한 구독은 제외합니다.
절약 금액은 월간 구독은 요금, 연간 구독은 요금/12(반올림)를 한 달 기준으로 씁니다.
"""
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.calculations import (
    BUSINESS_TZ, LOW_USAGE_MAX_COUNT, NEGATIVE_MEMO_KEYWORDS, LOW_USAGE_MIN_OBSERVATION_DAYS, LOW_USAGE_WINDOW_DAYS,
    RECOMMENDATION_SNOOZE_DAYS,
    business_date, monthly_amount, today,
)
from app.decision_state import cancel_tagged
from app.models import AppSettings, DecisionHistory, Subscription, UsageLog
from app.schemas import RecommendationItem


# 서로 다른 서비스를 모아둔 분류라 중복으로 보지 않습니다.
NON_GROUP_CATEGORIES = {"etc", "기타"}
# 같은 카테고리 구독이 이 개수 이상일 때만 중복으로 봅니다.
DUPLICATE_MIN_GROUP_SIZE = 3


def monthly_saving(subscription: Subscription) -> int:
    return monthly_amount(subscription)


def yearly_saving(subscription: Subscription) -> int:
    if subscription.billing_cycle == "yearly":
        return subscription.price_won
    return subscription.price_won * 12


def cost_per_use(subscription: Subscription, uses: int, window_days: int) -> int | None:
    """월 요금 ÷ 한 달(30일) 평균 이용 횟수. 90일이면 앱 엔진의 '월 요금 ÷ (90일 이용/3)'과 같습니다."""
    if uses == 0:
        return None
    return round(monthly_saving(subscription) / (uses * 30 / window_days))


def criteria(db: Session) -> tuple[int, int]:
    """(판단 기간 일수, 최대 이용 횟수). 설정이 없으면 기본값."""
    settings = db.get(AppSettings, 1)
    if settings is None:
        return LOW_USAGE_WINDOW_DAYS, LOW_USAGE_MAX_COUNT
    return settings.low_usage_window_days, settings.low_usage_max_count


def build_recommendations(db: Session, current: date | None = None) -> list[RecommendationItem]:
    current = current or today()
    window_days, max_count = criteria(db)
    min_observation = min(LOW_USAGE_MIN_OBSERVATION_DAYS, window_days)
    subscriptions = list(db.scalars(select(Subscription).where(
        Subscription.status == "active", Subscription.track_usage.is_(True)
    ).order_by(Subscription.id)))
    if not subscriptions:
        return []
    ids = [subscription.id for subscription in subscriptions]

    usage = {row[0]: (row[1], row[2]) for row in db.execute(select(
        UsageLog.subscription_id,
        func.count(case((UsageLog.used_date >= current - timedelta(days=window_days - 1), 1))),
        func.min(UsageLog.used_date),
    ).where(
        UsageLog.subscription_id.in_(ids), UsageLog.used_date <= current
    ).group_by(UsageLog.subscription_id))}

    # decided_at은 UTC로 저장되므로 한국 날짜 기준 경계를 UTC로 바꿔 비교합니다.
    snooze_from = datetime.combine(
        current - timedelta(days=RECOMMENDATION_SNOOZE_DAYS - 1), time.min, BUSINESS_TZ
    ).astimezone(timezone.utc).replace(tzinfo=None)
    tagged = cancel_tagged(db)
    negative = {
        sid for sid, memo in db.execute(select(UsageLog.subscription_id, UsageLog.memo).where(
            UsageLog.subscription_id.in_(ids), UsageLog.memo.is_not(None)
        )) if any(keyword in memo for keyword in NEGATIVE_MEMO_KEYWORDS)
    }
    snoozed = set(db.scalars(select(DecisionHistory.subscription_id).where(
        DecisionHistory.subscription_id.in_(ids),
        DecisionHistory.decision.in_(("keep", "hold")),
        DecisionHistory.decided_at >= snooze_from,
    )))

    reasons: dict[int, list[str]] = defaultdict(list)
    recent_count = {}
    for subscription in subscriptions:
        count, earliest = usage.get(subscription.id, (0, None))
        recent_count[subscription.id] = count
        start = business_date(subscription.created_at)
        if earliest is not None and earliest < start:
            start = earliest
        observation = (current - start).days + 1
        if observation >= min_observation and count <= max_count:
            reasons[subscription.id].append("low_usage")
            if subscription.id in negative:
                reasons[subscription.id].append("negative_memo")

    groups: dict[str, list[Subscription]] = defaultdict(list)
    for subscription in subscriptions:
        if subscription.id in tagged:
            continue
        key = (subscription.category or "").strip().casefold()
        if key and key not in NON_GROUP_CATEGORIES:
            groups[key].append(subscription)
    duplicate_with: dict[int, list[int]] = {}
    for members in groups.values():
        if len(members) < DUPLICATE_MIN_GROUP_SIZE:
            continue
        # 가장 적게 쓰는 1개만 추천. 이용 횟수가 같으면 더 비싼 것(절약이 큰 것), 그다음 나중에 등록한 것.
        least = min(members, key=lambda s: (recent_count[s.id], -s.price_won, -s.id))
        duplicate_with[least.id] = [other.id for other in members if other.id != least.id]
        reasons[least.id].append("duplicate_category")

    items = [
        RecommendationItem(
            subscription_id=subscription.id, name=subscription.name, category=subscription.category,
            price_won=subscription.price_won, billing_cycle=subscription.billing_cycle,
            reasons=reasons[subscription.id], recent_usage_count=recent_count[subscription.id],
            window_days=window_days,
            duplicate_with=duplicate_with.get(subscription.id, []),
            cost_per_use_won=cost_per_use(subscription, recent_count[subscription.id], window_days),
            monthly_saving_won=monthly_saving(subscription),
            yearly_saving_won=yearly_saving(subscription),
        )
        for subscription in subscriptions
        if reasons[subscription.id] and subscription.id not in snoozed | tagged
    ]
    items.sort(key=lambda item: (-item.monthly_saving_won, item.subscription_id))
    return items
