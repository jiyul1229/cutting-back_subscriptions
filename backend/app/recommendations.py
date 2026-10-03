"""해지 추천 계산. 결과는 저장하지 않고 조회할 때마다 계산합니다.

추천 이유
- low_usage: 관찰 30일 이상인데 최근 30일 이용이 LOW_USAGE_MAX_COUNT_30D회 이하
- duplicate_category: 같은 카테고리의 활성 구독이 2개 이상일 때, 가장 많이 쓰는 1개를 빼고 나머지
  (이용 횟수가 같으면 더 싼 것을 남깁니다). '기타'(etc)는 서로 다른 서비스 묶음이라 제외합니다.

이용 기록 대상이 아닌 구독(track_usage=false, 보험료·통신비 등)은 추천하지 않습니다.

사용자가 최근 RECOMMENDATION_SNOOZE_DAYS일 안에 유지(keep)나 보류(postpone)를 결정한 구독은 제외합니다.
절약 금액은 월간 구독은 요금, 연간 구독은 요금/12(반올림)를 한 달 기준으로 씁니다.
"""
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.calculations import (
    BUSINESS_TZ, COMPARISON_DAYS, LOW_USAGE_MAX_COUNT_30D, RECOMMENDATION_SNOOZE_DAYS,
    business_date, today,
)
from app.models import DecisionHistory, Subscription, UsageLog
from app.schemas import RecommendationItem


# 서로 다른 서비스를 모아둔 분류라 중복으로 보지 않습니다.
NON_GROUP_CATEGORIES = {"etc", "기타"}


def monthly_saving(subscription: Subscription) -> int:
    if subscription.billing_cycle == "yearly":
        return round(subscription.price_won / 12)
    return subscription.price_won


def yearly_saving(subscription: Subscription) -> int:
    if subscription.billing_cycle == "yearly":
        return subscription.price_won
    return subscription.price_won * 12


def build_recommendations(db: Session, current: date | None = None) -> list[RecommendationItem]:
    current = current or today()
    subscriptions = list(db.scalars(select(Subscription).where(
        Subscription.status == "active", Subscription.track_usage.is_(True)
    ).order_by(Subscription.id)))
    if not subscriptions:
        return []
    ids = [subscription.id for subscription in subscriptions]

    usage = {row[0]: (row[1], row[2]) for row in db.execute(select(
        UsageLog.subscription_id,
        func.count(case((UsageLog.used_date >= current - timedelta(days=COMPARISON_DAYS - 1), 1))),
        func.min(UsageLog.used_date),
    ).where(
        UsageLog.subscription_id.in_(ids), UsageLog.used_date <= current
    ).group_by(UsageLog.subscription_id))}

    # decided_at은 UTC로 저장되므로 한국 날짜 기준 경계를 UTC로 바꿔 비교합니다.
    snooze_from = datetime.combine(
        current - timedelta(days=RECOMMENDATION_SNOOZE_DAYS - 1), time.min, BUSINESS_TZ
    ).astimezone(timezone.utc).replace(tzinfo=None)
    snoozed = set(db.scalars(select(DecisionHistory.subscription_id).where(
        DecisionHistory.subscription_id.in_(ids),
        DecisionHistory.decision.in_(("keep", "postpone")),
        DecisionHistory.decided_at >= snooze_from,
    )))

    reasons: dict[int, list[str]] = defaultdict(list)
    count_30d = {}
    for subscription in subscriptions:
        count, earliest = usage.get(subscription.id, (0, None))
        count_30d[subscription.id] = count
        start = business_date(subscription.created_at)
        if earliest is not None and earliest < start:
            start = earliest
        observation = (current - start).days + 1
        if observation >= COMPARISON_DAYS and count <= LOW_USAGE_MAX_COUNT_30D:
            reasons[subscription.id].append("low_usage")

    groups: dict[str, list[Subscription]] = defaultdict(list)
    for subscription in subscriptions:
        key = (subscription.category or "").strip().casefold()
        if key and key not in NON_GROUP_CATEGORIES:
            groups[key].append(subscription)
    duplicate_with: dict[int, list[int]] = {}
    for members in groups.values():
        if len(members) < 2:
            continue
        keep = min(members, key=lambda s: (-count_30d[s.id], s.price_won, s.id))
        for member in members:
            duplicate_with[member.id] = [other.id for other in members if other.id != member.id]
            if member.id != keep.id:
                reasons[member.id].append("duplicate_category")

    items = [
        RecommendationItem(
            subscription_id=subscription.id, name=subscription.name, category=subscription.category,
            price_won=subscription.price_won, billing_cycle=subscription.billing_cycle,
            reasons=reasons[subscription.id], usage_count_30d=count_30d[subscription.id],
            duplicate_with=duplicate_with.get(subscription.id, []),
            monthly_saving_won=monthly_saving(subscription),
            yearly_saving_won=yearly_saving(subscription),
        )
        for subscription in subscriptions
        if reasons[subscription.id] and subscription.id not in snoozed
    ]
    items.sort(key=lambda item: (-item.monthly_saving_won, item.subscription_id))
    return items
