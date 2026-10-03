from datetime import date, datetime, timezone
from typing import Annotated, Literal

from pydantic import (
    AfterValidator, BaseModel, ConfigDict, Field, StrictBool, StringConstraints, field_validator, model_validator,
)

from app.calculations import today


BillingCycle = Literal["monthly", "yearly"]
SubscriptionStatus = Literal["active", "canceled", "paused"]
UsageSource = Literal["manual", "mobile_auto", "notification"]
# mobile_auto는 /api/usage-logs/sync로만 만듭니다.
ManualUsageSource = Literal["manual", "notification"]
UsageDevice = Literal["phone", "tablet", "tv", "pc", "other"]
PaymentSource = Literal["manual", "auto"]
Decision = Literal["keep", "cancel", "postpone"]
RecommendationReason = Literal["low_usage", "duplicate_category"]
ReminderDays = Annotated[int, Field(ge=0, le=365, strict=True)]
PositiveId = Annotated[int, Field(gt=0, strict=True, le=9223372036854775807)]
PositiveWon = Annotated[int, Field(gt=0, strict=True, le=9223372036854775807)]
BillingDay = Annotated[int, Field(ge=1, le=31, strict=True)]
BillingMonth = Annotated[int, Field(ge=1, le=12, strict=True)]
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
    billing_day: BillingDay
    billing_month: BillingMonth | None = None
    category: str | None = None
    plan_name: OptionalText | None = None
    memo: OptionalText | None = None
    started_on: PastDate | None = None
    status: SubscriptionStatus = "active"
    notification_enabled: StrictBool = True
    renewal_reminder_days: ReminderDays = 7
    include_in_analysis: StrictBool = True
    track_usage: StrictBool = True
    android_package: AndroidPackage | None = None

    @model_validator(mode="after")
    def validate_billing_schedule(self):
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

    @field_validator("name", "price_won", "billing_cycle", "billing_day", "status",
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
    billing_day: int
    billing_month: int | None
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
    # 가장 최근 결정(유지/해지/보류). 기록이 없으면 null. 구독 상태(status)를 바꾸지는 않습니다.
    latest_decision: Decision | None = None


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


class SettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    notifications_enabled: bool
    recommendation_enabled: bool
    auto_tracking_enabled: bool
    usage_check_enabled: bool
    usage_check_time: str


class SettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    notifications_enabled: StrictBool | None = None
    recommendation_enabled: StrictBool | None = None
    auto_tracking_enabled: StrictBool | None = None
    usage_check_enabled: StrictBool | None = None
    usage_check_time: ClockTime | None = None

    @field_validator("notifications_enabled", "recommendation_enabled",
                     "auto_tracking_enabled", "usage_check_enabled", "usage_check_time")
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
    type: Literal["scheduled", "paid"]
    payment_id: int | None = None


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
    type: Literal["renewal", "no_usage", "recommendation"]
    next_renewal_date: date | None = None
    d_day: int | None = None
    days_without_usage: int | None = None
    reasons: list[RecommendationReason] | None = None


class RecommendationItem(BaseModel):
    subscription_id: int
    name: str
    category: str | None
    price_won: int
    billing_cycle: BillingCycle
    reasons: list[RecommendationReason]
    usage_count_90d: int
    # 같은 카테고리의 다른 활성 구독 (duplicate_category일 때)
    duplicate_with: list[int]
    monthly_saving_won: int
    yearly_saving_won: int


class RecommendationResponse(BaseModel):
    enabled: bool
    monthly_saving_won: int
    yearly_saving_won: int
    items: list[RecommendationItem]
