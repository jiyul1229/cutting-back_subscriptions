"""공유 날짜 정책과 반복 결제 계산. 화면별 저장 모델은 만들지 않습니다."""
import calendar
import os
from datetime import date, datetime, timedelta, timezone

from app.models import Subscription, utc_now

BUSINESS_TZ = timezone(timedelta(hours=9))  # 한국 날짜, 별도 tzdata 의존성 불필요
USAGE_WINDOWS = (7, 30, 90)
COMPARISON_DAYS = 30
INACTIVITY_DAYS = 7
# 해지 권장 기간: 다음 결제일 CANCEL_WINDOW_DAYS일 전부터 하루 전까지 (앱 코어 엔진과 같은 기준)
CANCEL_WINDOW_DAYS = 5
# 메모에 이런 표현이 있으면 해지 추천 이유로 덧붙입니다.
NEGATIVE_MEMO_KEYWORDS = ("안 봄", "안봄", "재미없", "안 씀", "안씀", "해지")
# 해지 추천(미사용): 관찰 30일 이상이고 최근 90일 이용이 2회 이하. 앱 코어 엔진과 같은 기준입니다.
LOW_USAGE_WINDOW_DAYS = 90
LOW_USAGE_MAX_COUNT = 2
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
    if subscription.billing_cycle == "yearly" and subscription.billing_month != month:
        return None
    day = min(subscription.billing_day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def cancel_window(subscription: Subscription, on_date: date) -> tuple[date, date]:
    due = next_renewal(subscription, on_date)
    return due - timedelta(days=CANCEL_WINDOW_DAYS), due - timedelta(days=1)


def next_renewal(subscription: Subscription, on_date: date) -> date:
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
