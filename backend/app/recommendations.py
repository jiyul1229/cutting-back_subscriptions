"""해지 추천 계산. 추천 자체는 조회할 때마다 계산하고, 보여준 기록(경고)만 저장합니다.

추천 이유 (규칙이 정하고, 메모 분석은 근거를 보탬 — 문서 R3)
- low_usage: 최근 N일 이용이 M회 이하 (설정값, 기본 90일 2회).
  관찰 기간이 min(30일, N일)보다 짧으면 판단하지 않고 '데이터 수집 중'(collecting)으로 돌려줍니다.
- duplicate_category: 같은 카테고리의 활성 구독이 3개 이상일 때, 최근 N일 이용이 가장 적은 1개
  (같으면 더 비싼 것). '기타'(etc)는 서로 다른 서비스 묶음이라 제외합니다.
- negative_memo: 미사용 구독의 이용 기록 메모가 '안 쓴다'는 신호일 때 (memo_analysis: AI 또는 키워드)

제외: 이용 기록 대상이 아닌 구독(track_usage=false, 보험료·통신비 등), '해지' 태그를 붙인 구독,
최근 RECOMMENDATION_SNOOZE_DAYS일 안에 유지(keep)나 보류(hold)를 결정한 구독.

"아직 쓰고 있어요"(F6 민감도 조정): 그 구독만의 기준을 낮추거나(지금 이용 횟수 - 1회 이하일 때만 추천),
이용 0회였다면 판단 기간 동안 미사용 추천을 멈추고, 중복 추천에서는 제외합니다.
절약 금액은 월 환산(연간 /12, 매주 ×52/12)과 연 환산 금액입니다.
"""
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.calculations import (
    BUSINESS_TZ, LOW_USAGE_MAX_COUNT, LOW_USAGE_MIN_OBSERVATION_DAYS, LOW_USAGE_WINDOW_DAYS,
    RECOMMENDATION_SNOOZE_DAYS,
    business_date, monthly_amount, today, yearly_amount,
)
from app.decision_state import cancel_tagged
from app.memo_analysis import keyword_negative
from app.models import AppSettings, DecisionHistory, RecommendationWarning, Subscription, UsageLog, utc_now
from app.schemas import CollectingItem, RecommendationItem


# 서로 다른 서비스를 모아둔 분류라 중복으로 보지 않습니다.
NON_GROUP_CATEGORIES = {"etc", "기타"}
# 같은 카테고리 구독이 이 개수 이상일 때만 중복으로 봅니다.
DUPLICATE_MIN_GROUP_SIZE = 3


def monthly_saving(subscription: Subscription) -> int:
    return monthly_amount(subscription)


def yearly_saving(subscription: Subscription) -> int:
    return yearly_amount(subscription)


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


def is_personalized(subscription: Subscription, current: date) -> bool:
    return (
        subscription.low_usage_max_count_override is not None
        or (subscription.low_usage_snooze_until is not None and current <= subscription.low_usage_snooze_until)
        or subscription.duplicate_exempt
    )


def evaluate(db: Session, current: date | None = None) -> tuple[list[RecommendationItem], list[CollectingItem]]:
    """(추천 목록, 데이터 수집 중 목록)"""
    current = current or today()
    window_days, max_count = criteria(db)
    min_observation = min(LOW_USAGE_MIN_OBSERVATION_DAYS, window_days)
    tagged = cancel_tagged(db)
    subscriptions = [s for s in db.scalars(select(Subscription).where(
        Subscription.status == "active", Subscription.track_usage.is_(True)
    ).order_by(Subscription.id)) if s.id not in tagged]
    if not subscriptions:
        return [], []
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
    # 저장된 분석 결과(AI 또는 키워드)를 쓰고, 분석 전 기록(이전 DB)은 키워드로 판단합니다.
    negative = {
        sid for sid, memo, memo_negative in db.execute(
            select(UsageLog.subscription_id, UsageLog.memo, UsageLog.memo_negative).where(
                UsageLog.subscription_id.in_(ids), UsageLog.memo.is_not(None)
            ))
        if memo_negative or (memo_negative is None and keyword_negative(memo))
    }
    snoozed = set(db.scalars(select(DecisionHistory.subscription_id).where(
        DecisionHistory.subscription_id.in_(ids),
        DecisionHistory.decision.in_(("keep", "hold")),
        DecisionHistory.decided_at >= snooze_from,
    )))

    reasons: dict[int, list[str]] = defaultdict(list)
    recent_count = {}
    collecting = []
    for subscription in subscriptions:
        count, earliest = usage.get(subscription.id, (0, None))
        recent_count[subscription.id] = count
        start = business_date(subscription.created_at)
        if earliest is not None and earliest < start:
            start = earliest
        observation = (current - start).days + 1
        if observation < min_observation:
            collecting.append(CollectingItem(
                subscription_id=subscription.id, name=subscription.name,
                observation_days=observation, needed_days=min_observation,
            ))
            continue
        snooze_until = subscription.low_usage_snooze_until
        if snooze_until is not None and current <= snooze_until:
            continue
        limit = subscription.low_usage_max_count_override
        if count <= (max_count if limit is None else limit):
            reasons[subscription.id].append("low_usage")
            if subscription.id in negative:
                reasons[subscription.id].append("negative_memo")

    groups: dict[str, list[Subscription]] = defaultdict(list)
    for subscription in subscriptions:
        key = (subscription.category or "").strip().casefold()
        if key and key not in NON_GROUP_CATEGORIES:
            groups[key].append(subscription)
    duplicate_with: dict[int, list[int]] = {}
    for members in groups.values():
        candidates = [m for m in members if not m.duplicate_exempt]
        if len(members) < DUPLICATE_MIN_GROUP_SIZE or not candidates:
            continue
        # 가장 적게 쓰는 1개만 추천. 이용 횟수가 같으면 더 비싼 것(절약이 큰 것), 그다음 나중에 등록한 것.
        least = min(candidates, key=lambda s: (recent_count[s.id], -s.price_won, -s.id))
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
            personalized=is_personalized(subscription, current),
        )
        for subscription in subscriptions
        if reasons[subscription.id] and subscription.id not in snoozed
    ]
    items.sort(key=lambda item: (-item.monthly_saving_won, item.subscription_id))
    return items, collecting


def build_recommendations(db: Session, current: date | None = None) -> list[RecommendationItem]:
    return evaluate(db, current)[0]


def record_warnings(db: Session, items: list[RecommendationItem], current: date) -> None:
    """처음 보여주는 추천을 경고로 기록합니다(구독마다 응답 전인 경고는 하나)."""
    if not items:
        return
    open_ids = set(db.scalars(select(RecommendationWarning.subscription_id).where(
        RecommendationWarning.resolved_at.is_(None),
        RecommendationWarning.subscription_id.in_([item.subscription_id for item in items]),
    )))
    for item in items:
        if item.subscription_id not in open_ids:
            db.add(RecommendationWarning(
                subscription_id=item.subscription_id, reasons=",".join(item.reasons),
                recent_usage_count=item.recent_usage_count, window_days=item.window_days, shown_on=current,
            ))
    db.commit()


def resolve_warning(db: Session, subscription_id: int, resolution: str) -> None:
    """응답 전인 경고에 사용자 응답을 남깁니다. 커밋은 호출한 쪽에서 합니다."""
    warning = db.scalar(select(RecommendationWarning).where(
        RecommendationWarning.subscription_id == subscription_id,
        RecommendationWarning.resolved_at.is_(None),
    ))
    if warning is not None:
        warning.resolved_at = utc_now()
        warning.resolution = resolution


def apply_still_using(db: Session, subscription: Subscription, current: date | None = None) -> list[str]:
    """해지 추천에 '아직 쓰고 있어요'를 눌렀을 때 이 구독의 기준을 조정합니다. 바꾼 항목을 돌려줍니다."""
    current = current or today()
    item = next((i for i in build_recommendations(db, current) if i.subscription_id == subscription.id), None)
    if item is None:
        raise LookupError("Subscription is not currently recommended")
    applied = []
    if "low_usage" in item.reasons:
        if item.recent_usage_count >= 1:
            # 지금만큼 쓰는 건 괜찮다는 뜻 → 이보다 더 줄었을 때만 추천
            subscription.low_usage_max_count_override = item.recent_usage_count - 1
            applied.append("threshold")
        else:
            # 0회인데 쓰고 있다면 기록이 빠진 것(TV 시청 등) → 판단 기간 동안 미사용 추천을 멈춤
            subscription.low_usage_snooze_until = current + timedelta(days=item.window_days)
            applied.append("snooze")
    if "duplicate_category" in item.reasons:
        subscription.duplicate_exempt = True
        applied.append("duplicate_exempt")
    resolve_warning(db, subscription.id, "still_using")
    db.commit()
    return applied
