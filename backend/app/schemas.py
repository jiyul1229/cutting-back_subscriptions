from datetime import date, datetime, timezone
from typing import Annotated, Literal

from pydantic import (
    AfterValidator, BaseModel, ConfigDict, Field, StrictBool, StringConstraints, field_validator, model_validator,
)

from app.calculations import today


BillingCycle = Literal["monthly", "yearly", "weekly"]
SubscriptionStatus = Literal["active", "canceled", "paused"]
UsageSource = Literal["manual", "mobile_auto", "notification"]
# mobile_auto는 /api/usage-logs/sync로만 만듭니다.
ManualUsageSource = Literal["manual", "notification"]
UsageDevice = Literal["phone", "tablet", "tv", "pc", "other"]
PaymentSource = Literal["manual", "auto"]
# none은 태그 해제. 기록은 남지만 최근 결정은 null이 됩니다.
Decision = Literal["keep", "cancel", "hold", "none"]
TagDecision = Literal["keep", "cancel", "hold"]
RecommendationReason = Literal["low_usage", "duplicate_category", "negative_memo"]
ReminderDays = Annotated[int, Field(ge=0, le=365, strict=True)]
PositiveId = Annotated[int, Field(gt=0, strict=True, le=9223372036854775807)]
PositiveWon = Annotated[int, Field(gt=0, strict=True, le=9223372036854775807)]
BillingDay = Annotated[int, Field(ge=1, le=31, strict=True)]
BillingMonth = Annotated[int, Field(ge=1, le=12, strict=True)]
# 매주 결제 요일. 0=월요일 ... 6=일요일
BillingWeekday = Annotated[int, Field(ge=0, le=6, strict=True)]
RegistrationSeconds = Annotated[int, Field(ge=0, le=3600, strict=True)]
SubscriptionName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
AndroidPackage = Annotated[str, StringConstraints(
    strip_whitespace=True, max_length=255,
    pattern=r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+$",
)]
OptionalText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
UsageMinutes = Annotated[int, Field(ge=1, le=1440, strict=True)]
SyncMinutes = Annotated[int, Field(ge=0, le=1440, strict=True)]
ClockTime = Annotated[str, StringConstraints(pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")]


def not_future(value: date | None) -> date | None:
    if value is not None and value > today():
        raise ValueError("date cannot be in the future")
    return value


PastDate = Annotated[date, AfterValidator(not_future)]


def as_utc(value: datetime) -> datetime:
    # DB의 시간대 없는 datetime은 이미 UTC로 저장된 값입니다.
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


UTCDateTime = Annotated[
    datetime, AfterValidator(as_utc),
    Field(description="UTC ISO 8601 timestamp ending in Z"),
]


class HealthResponse(BaseModel):
    status: Literal["ok"]


class SubscriptionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: SubscriptionName
    price_won: PositiveWon
    billing_cycle: BillingCycle = "monthly"
    # 월간·연간은 billing_day 필수, 매주는 billing_weekday 필수
    billing_day: BillingDay | None = None
    billing_month: BillingMonth | None = None
    billing_weekday: BillingWeekday | None = None
    category: str | None = None
    plan_name: OptionalText | None = None
    memo: OptionalText | None = None
    started_on: PastDate | None = None
    status: SubscriptionStatus = "active"
    notification_enabled: StrictBool = True
    renewal_reminder_days: ReminderDays = 3
    include_in_analysis: StrictBool = True
    track_usage: StrictBool = True
    android_package: AndroidPackage | None = None
    # 앱이 등록 화면을 연 뒤 저장까지 걸린 시간(초). 등록 부담 지표용, 선택
    registration_seconds: RegistrationSeconds | None = None

    @model_validator(mode="after")
    def validate_billing_schedule(self):
        if self.billing_cycle == "weekly":
            if self.billing_weekday is None:
                raise ValueError("billing_weekday (0=Mon..6=Sun) is required for weekly subscriptions")
            if self.billing_day is not None or self.billing_month is not None:
                raise ValueError("billing_day and billing_month must be null for weekly subscriptions")
            return self
        if self.billing_weekday is not None:
            raise ValueError("billing_weekday is only for weekly subscriptions")
        if self.billing_day is None:
            raise ValueError("billing_day is required for monthly and yearly subscriptions")
        if self.billing_cycle == "monthly":
            if self.billing_month is not None:
                raise ValueError("billing_month must be null for monthly subscriptions")
        else:
            if self.billing_month is None:
                raise ValueError("billing_month is required for yearly subscriptions")
            # 윤년의 2월 29일은 허용하되 2월 30일 등은 거부합니다.
            try:
                date(2000, self.billing_month, self.billing_day)
            except ValueError as exc:
                raise ValueError("Invalid yearly billing month/day") from exc
        return self


class SubscriptionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: SubscriptionName | None = None
    price_won: PositiveWon | None = None
    billing_cycle: BillingCycle | None = None
    billing_day: BillingDay | None = None
    billing_month: BillingMonth | None = None
    billing_weekday: BillingWeekday | None = None
    category: str | None = None
    plan_name: OptionalText | None = None
    memo: OptionalText | None = None
    started_on: PastDate | None = None
    status: SubscriptionStatus | None = None
    notification_enabled: StrictBool | None = None
    renewal_reminder_days: ReminderDays | None = None
    include_in_analysis: StrictBool | None = None
    track_usage: StrictBool | None = None
    android_package: AndroidPackage | None = None

    # billing_day는 매주 결제로 바꿀 때 null을 보내야 해서 null을 허용합니다(최종 규칙은 합쳐서 검증).
    @field_validator("name", "price_won", "billing_cycle", "status",
                     "notification_enabled", "renewal_reminder_days", "include_in_analysis", "track_usage")
    @classmethod
    def reject_null(cls, value):
        # 생략은 허용하지만 필수 필드의 명시적인 null은 거부합니다.
        if value is None:
            raise ValueError("This field cannot be null")
        return value


class SubscriptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    price_won: int
    billing_cycle: BillingCycle
    billing_day: int | None
    billing_month: int | None
    billing_weekday: int | None
    category: str | None
    plan_name: str | None
    memo: str | None
    started_on: date | None
    status: SubscriptionStatus
    notification_enabled: bool
    renewal_reminder_days: int
    include_in_analysis: bool
    track_usage: bool
    android_package: str | None
    deleted_at: UTCDateTime | None
    created_at: UTCDateTime
    updated_at: UTCDateTime
    # 활성 구독만 계산합니다. 해지·일시정지·삭제면 null.
    next_renewal_date: date | None = None
    d_day: int | None = None
    # 해지 권장 기간 (다음 결제일 5일 전 ~ 하루 전). 활성 구독만.
    cancel_window_start: date | None = None
    cancel_window_end: date | None = None
    # 가장 최근 결정(유지/해지/보류). 기록이 없으면 null. 구독 상태(status)를 바꾸지는 않습니다.
    latest_decision: TagDecision | None = None
    # "아직 쓰고 있어요"로 개인화된 해지 추천 기준 (null/false면 설정 기준 그대로)
    low_usage_max_count_override: int | None
    low_usage_snooze_until: date | None
    duplicate_exempt: bool


class LegacyCheckInCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # 구독 ID는 URL 경로에서만 받습니다.
    checked_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None)
    )
    memo: str | None = None

    @field_validator("checked_at")
    @classmethod
    def validate_checked_at(cls, value: datetime) -> datetime:
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        if value > datetime.now(timezone.utc).replace(tzinfo=None):
            raise ValueError("checked_at cannot be in the future")
        return value


class UsageLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    subscription_id: int
    used_date: date
    source: UsageSource
    duration_minutes: int | None
    device: UsageDevice | None
    memo: str | None
    # 메모가 '안 쓴다/돈값 못 한다'는 신호인지, 분석 방법(ai 또는 keyword). 메모가 없으면 null
    memo_negative: bool | None
    memo_analyzed_by: Literal["ai", "keyword"] | None
    created_at: UTCDateTime
    updated_at: UTCDateTime


class UsageSummaryResponse(BaseModel):
    subscription_id: int
    observation_days: int
    usage_count_7d: int
    usage_count_30d: int
    usage_count_90d: int
    total_usage_count: int
    usage_minutes_7d: int
    usage_minutes_30d: int
    total_usage_minutes: int
    previous_30d_usage_count: int | None
    usage_change_30d: int | None
    cost_per_use_30d: float | None
    cost_per_hour_30d: float | None
    tracking_started_at: UTCDateTime
    data_status: Literal["collecting", "sufficient"]


class PaymentRecordCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subscription_id: PositiveId
    amount_won: PositiveWon
    paid_date: date


class PaymentRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    subscription_id: int
    amount_won: int
    paid_date: date
    category_snapshot: str | None
    source: PaymentSource
    created_at: UTCDateTime


class PaymentRecordUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount_won: PositiveWon | None = None
    paid_date: date | None = None

    @field_validator("amount_won", "paid_date")
    @classmethod
    def not_null(cls, value):
        if value is None:
            raise ValueError("This field cannot be null")
        return value

class UsageLogCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    used_date: PastDate = Field(default_factory=today)
    source: ManualUsageSource = "manual"
    duration_minutes: UsageMinutes | None = None
    device: UsageDevice | None = None
    memo: str | None = None


class UsageLogUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    used_date: date | None = None
    duration_minutes: UsageMinutes | None = None
    device: UsageDevice | None = None
    memo: str | None = None

    @field_validator("used_date")
    @classmethod
    def validate_date(cls, value: date | None) -> date:
        if value is None or value > today():
            raise ValueError("used_date must be a non-null date no later than today")
        return value


class DecisionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Decision
    memo: str | None = None


class DecisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    subscription_id: int
    decision: Decision
    decided_at: UTCDateTime
    memo: str | None


class UsageSyncEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    package_name: AndroidPackage
    used_date: PastDate
    duration_minutes: SyncMinutes


class UsageSyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entries: list[UsageSyncEntry] = Field(max_length=1000)

    @model_validator(mode="after")
    def unique_days(self):
        keys = [(entry.package_name, entry.used_date) for entry in self.entries]
        if len(keys) != len(set(keys)):
            raise ValueError("Each package_name and used_date pair must appear once")
        return self


class UsageSyncResponse(BaseModel):
    created: int
    updated: int
    deleted: int
    unmatched_packages: list[str]


class UsageCheckItem(BaseModel):
    subscription_id: int
    name: str
    auto_tracked: bool
    today_auto_minutes: int | None


class UsageCheckResponse(BaseModel):
    enabled: bool
    check_time: str
    date: date
    items: list[UsageCheckItem]


class ResetDataRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # 실수 방지용. true를 보내야만 지웁니다.
    confirm: Literal[True]


class SettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    notifications_enabled: bool
    recommendation_enabled: bool
    auto_tracking_enabled: bool
    usage_check_enabled: bool
    usage_check_time: str
    low_usage_window_days: int
    low_usage_max_count: int


class SettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    notifications_enabled: StrictBool | None = None
    recommendation_enabled: StrictBool | None = None
    auto_tracking_enabled: StrictBool | None = None
    usage_check_enabled: StrictBool | None = None
    usage_check_time: ClockTime | None = None
    # 해지 추천 기준. 예: 30일 1회 이하 → {"low_usage_window_days": 30, "low_usage_max_count": 1}
    low_usage_window_days: Annotated[int, Field(ge=7, le=365, strict=True)] | None = None
    low_usage_max_count: Annotated[int, Field(ge=0, le=100, strict=True)] | None = None

    @field_validator("notifications_enabled", "recommendation_enabled",
                     "auto_tracking_enabled", "usage_check_enabled", "usage_check_time",
                     "low_usage_window_days", "low_usage_max_count")
    @classmethod
    def not_null(cls, value):
        if value is None:
            raise ValueError("This field cannot be null")
        return value


class DashboardSubscription(SubscriptionResponse):
    next_renewal_date: date
    d_day: int


class DashboardResponse(BaseModel):
    monthly_total_won: int
    # 연 환산 고정비 총액 (월간×12, 연간 그대로, 매주×52)
    yearly_total_won: int
    # 전월 대비: 지난달 실제 결제액과 비교. 지난달 결제가 없으면 세 값 모두 null.
    previous_month_paid_won: int | None
    change_won: int | None
    change_ratio: float | None
    active_subscription_count: int
    subscriptions: list[DashboardSubscription]


class CalendarItem(BaseModel):
    date: date
    subscription_id: int
    name: str
    amount_won: int
    # cancel_deadline: 다음 결제를 피하려면 이 날까지 해지 (결제일 하루 전)
    type: Literal["scheduled", "paid", "cancel_deadline"]
    payment_id: int | None = None
    # cancel_deadline 항목의 결제일
    renewal_date: date | None = None


class MonthlyAnalysisResponse(BaseModel):
    total_won: int
    previous_total_won: int
    # 지난달 지출이 0원이면 비교할 수 없어 null.
    change_won: int | None
    change_ratio: float | None


class TrendPoint(BaseModel):
    year: int
    month: int
    total_won: int


class CategoryAnalysisResponse(BaseModel):
    category: str | None
    amount_won: int
    ratio: float


class NotificationCandidate(BaseModel):
    subscription_id: int
    name: str
    # weekly_check: 일주일 동안 이용 기록이 없어 "이번 주에 썼나요?"라고 묻는 알림
    type: Literal["renewal", "cancel_window", "weekly_check", "recommendation"]
    next_renewal_date: date | None = None
    d_day: int | None = None
    days_without_record: int | None = None
    reasons: list[RecommendationReason] | None = None


class ReminderScheduleItem(BaseModel):
    """폰에서 미리 예약할 알림. id가 같으면 같은 알림이므로 다시 예약할 때 기존 것을 지우고 넣습니다."""
    id: str
    subscription_id: int
    name: str
    type: Literal["renewal", "cancel_window", "weekly_check"]
    # 한국 시간 기준 발송 시각 (+09:00)
    fire_at: datetime
    renewal_date: date | None = None
    d_day_at_fire: int | None = None
    amount_won: int | None = None


class ServicePreset(BaseModel):
    name: str
    plan_name: str | None
    price_won: int
    billing_cycle: BillingCycle
    category: str
    android_package: str | None


class RecommendationItem(BaseModel):
    subscription_id: int
    name: str
    category: str | None
    price_won: int
    billing_cycle: BillingCycle
    reasons: list[RecommendationReason]
    # 설정한 판단 기간(window_days일) 동안의 이용 횟수
    recent_usage_count: int
    window_days: int
    # 같은 카테고리의 다른 활성 구독 (duplicate_category일 때)
    duplicate_with: list[int]
    # 월 요금 ÷ 월평균 이용 횟수(기간 이용 횟수를 30일 기준으로 환산). 이용 0회면 null
    cost_per_use_won: int | None
    monthly_saving_won: int
    yearly_saving_won: int
    # "아직 쓰고 있어요"로 이 구독만의 기준이 적용 중인지
    personalized: bool


class CollectingItem(BaseModel):
    """관찰 기간이 짧아 아직 판단하지 않는 구독 ('데이터 수집 중')."""
    subscription_id: int
    name: str
    observation_days: int
    needed_days: int


class RecommendationResponse(BaseModel):
    enabled: bool
    monthly_saving_won: int
    yearly_saving_won: int
    items: list[RecommendationItem]
    collecting: list[CollectingItem]


class RecommendationFeedbackCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # 해지 추천 카드의 "아직 쓰고 있어요"
    response: Literal["still_using"]


class RecommendationFeedbackResponse(BaseModel):
    subscription_id: int
    # 무엇을 바꿨는지: threshold(이 구독 기준 횟수 낮춤), snooze(기간 동안 미사용 추천 멈춤),
    # duplicate_exempt(중복 추천 제외)
    applied: list[Literal["threshold", "snooze", "duplicate_exempt"]]
    low_usage_max_count_override: int | None
    low_usage_snooze_until: date | None
    duplicate_exempt: bool


class WeeklyCheckins(BaseModel):
    week_start: date
    count: int


class MetricsResponse(BaseModel):
    """문서 R1·R3 판단 지표."""
    registration_count: int
    registration_seconds_avg: float | None
    registration_seconds_median: float | None
    # 사용자가 직접 남긴 체크인(수기·알림 응답). 자동 측정은 제외
    checkins_by_week: list[WeeklyCheckins]
    checkins_per_week_avg: float
    warnings_shown: int
    warnings_answered: int
    still_using_count: int
    # 응답한 경고 중 "아직 쓰고 있어요" 비율 (오탐률). 응답이 없으면 null
    false_positive_rate: float | None
    # 보여준 경고 중 유지·해지·보류를 결정한 비율
    decision_rate: float | None
