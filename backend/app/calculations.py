"""공유 날짜 정책과 반복 결제 계산. 화면별 저장 모델은 만들지 않습니다."""
import calendar
import os
from datetime import date, datetime, timedelta, timezone

from app.models import Subscription, utc_now

BUSINESS_TZ = timezone(timedelta(hours=9))  # 한국 날짜, 별도 tzdata 의존성 불필요
USAGE_WINDOWS = (7, 30, 90)
COMPARISON_DAYS = 30
# 해지 권장 기간: 다음 결제일 CANCEL_WINDOW_DAYS일 전부터 하루 전까지 (앱 코어 엔진과 같은 기준)
CANCEL_WINDOW_DAYS = 5
# 매주 결제는 주기가 짧아 해지 권장 기간을 이틀로 둡니다.
WEEKLY_CANCEL_WINDOW_DAYS = 2
# 결제·해지 기한 알림을 보낼 시각(한국 시간)
REMINDER_TIME = "09:00"
# 이 기간 동안 이용 기록이 없으면 "이번 주에 썼나요?"라고 묻습니다.
NO_RECORD_REMINDER_DAYS = 7
# 메모에 이런 표현이 있으면 해지 추천 이유로 덧붙입니다.
NEGATIVE_MEMO_KEYWORDS = ("안 봄", "안봄", "재미없", "안 씀", "안씀", "해지")
# 해지 추천(미사용): 관찰 30일 이상이고 최근 90일 이용이 2회 이하. 앱 코어 엔진과 같은 기준입니다.
# 기본값이며 사용자가 설정(low_usage_window_days, low_usage_max_count)에서 바꿀 수 있습니다.
LOW_USAGE_WINDOW_DAYS = 90
LOW_USAGE_MAX_COUNT = 2
# 판단 기간이 이보다 짧으면 판단 기간만큼만 관찰하면 됩니다.
LOW_USAGE_MIN_OBSERVATION_DAYS = 30
# 사용자가 유지/보류를 결정하면 이 기간 동안 같은 구독을 다시 추천하지 않습니다.
RECOMMENDATION_SNOOZE_DAYS = 30
USAGE_EVALUATION_DAYS = int(os.environ.get("USAGE_EVALUATION_DAYS", "30"))
if USAGE_EVALUATION_DAYS not in (30, 60, 90):
    raise ValueError("USAGE_EVALUATION_DAYS must be 30, 60 or 90")


def business_date(value: datetime) -> date:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(BUSINESS_TZ).date()


def today() -> date:
    return business_date(utc_now())


def month_shift(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def month_bounds(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def scheduled_date(subscription: Subscription, year: int, month: int) -> date | None:
    """월간·연간 구독의 그 달 결제일. 매주 결제는 scheduled_dates를 씁니다."""
    if subscription.billing_cycle == "weekly":
        raise ValueError("weekly subscriptions have several dates per month; use scheduled_dates")
    if subscription.billing_cycle == "yearly" and subscription.billing_month != month:
        return None
    day = min(subscription.billing_day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def scheduled_dates(subscription: Subscription, year: int, month: int) -> list[date]:
    """그 달의 모든 결제일. 매주 결제면 해당 요일 전부(4~5번)."""
    if subscription.billing_cycle == "weekly":
        first, last = month_bounds(year, month)
        offset = (subscription.billing_weekday - first.weekday()) % 7
        return [first + timedelta(days=d) for d in range(offset, (last - first).days + 1, 7)]
    due = scheduled_date(subscription, year, month)
    return [] if due is None else [due]


def billing_cycle_bounds(subscription: Subscription, due: date) -> tuple[date, date]:
    """결제일이 속한 결제 주기(월간=그 달, 연간=그 해, 매주=월~일)."""
    if subscription.billing_cycle == "weekly":
        start = due - timedelta(days=due.weekday())
        return start, start + timedelta(days=6)
    if subscription.billing_cycle == "yearly":
        return date(due.year, 1, 1), date(due.year, 12, 31)
    return month_bounds(due.year, due.month)


def monthly_amount(subscription: Subscription) -> int:
    """월 환산 금액. 연간은 요금/12, 매주는 요금×52/12(반올림). 앱의 monthlyAmount와 같은 기준입니다."""
    if subscription.billing_cycle == "yearly":
        return round(subscription.price_won / 12)
    if subscription.billing_cycle == "weekly":
        return round(subscription.price_won * 52 / 12)
    return subscription.price_won


def yearly_amount(subscription: Subscription) -> int:
    """연 환산 금액."""
    if subscription.billing_cycle == "yearly":
        return subscription.price_won
    if subscription.billing_cycle == "weekly":
        return subscription.price_won * 52
    return subscription.price_won * 12


def cancel_window_days(subscription: Subscription) -> int:
    return WEEKLY_CANCEL_WINDOW_DAYS if subscription.billing_cycle == "weekly" else CANCEL_WINDOW_DAYS


def cancel_window(subscription: Subscription, on_date: date) -> tuple[date, date]:
    due = next_renewal(subscription, on_date)
    return due - timedelta(days=cancel_window_days(subscription)), due - timedelta(days=1)


def next_renewal(subscription: Subscription, on_date: date) -> date:
    if subscription.billing_cycle == "weekly":
        return on_date + timedelta(days=(subscription.billing_weekday - on_date.weekday()) % 7)
    if subscription.billing_cycle == "yearly":
        candidate = scheduled_date(subscription, on_date.year, subscription.billing_month)
        if candidate < on_date:
            candidate = scheduled_date(subscription, on_date.year + 1, subscription.billing_month)
        return candidate
    candidate = scheduled_date(subscription, on_date.year, on_date.month)
    if candidate < on_date:
        year, month = (on_date.year + 1, 1) if on_date.month == 12 else (on_date.year, on_date.month + 1)
        candidate = scheduled_date(subscription, year, month)
    return candidate
