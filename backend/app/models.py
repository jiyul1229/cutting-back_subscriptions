from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    """SQLite에는 시간대 정보가 없는 UTC 시각으로 저장합니다."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        CheckConstraint("price_won > 0", name="ck_subscription_price_positive"),
        CheckConstraint(
            "billing_cycle IN ('monthly', 'yearly')",
            name="ck_subscription_billing_cycle",
        ),
        CheckConstraint(
            "status IN ('active', 'canceled', 'paused')",
            name="ck_subscription_status",
        ),
        CheckConstraint("billing_day BETWEEN 1 AND 31", name="ck_billing_day"),
        CheckConstraint("deleted_at IS NULL OR status = 'canceled'", name="ck_deleted_is_canceled"),
        CheckConstraint("renewal_reminder_days BETWEEN 0 AND 365", name="ck_reminder_days"),
        CheckConstraint(
            "(billing_cycle = 'monthly' AND billing_month IS NULL) OR "
            "(billing_cycle = 'yearly' AND billing_month IS NOT NULL "
            "AND billing_month BETWEEN 1 AND 12)",
            name="ck_billing_month",
        ),
        CheckConstraint(
            "billing_month IS NULL OR billing_day <= CASE "
            "WHEN billing_month = 2 THEN 29 "
            "WHEN billing_month IN (4, 6, 9, 11) THEN 30 ELSE 31 END",
            name="ck_yearly_billing_date",
        ),
        # 자동 측정 결과를 한 구독에만 연결하도록 앱 패키지는 중복될 수 없습니다.
        Index("ux_subscription_android_package", "android_package", unique=True,
              sqlite_where=text("android_package IS NOT NULL")),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    price_won: Mapped[int] = mapped_column(Integer, nullable=False)
    billing_cycle: Mapped[str] = mapped_column(String, nullable=False)
    billing_day: Mapped[int] = mapped_column(Integer, nullable=False)
    billing_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    plan_name: Mapped[str | None] = mapped_column(String, nullable=True)
    memo: Mapped[str | None] = mapped_column(String, nullable=True)
    # 실제로 구독을 시작한 날(사용자 입력). 앱에 등록한 시각은 created_at입니다.
    started_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String, default="active", nullable=False)
    notification_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    renewal_reminder_days: Mapped[int] = mapped_column(Integer, default=3)
    include_in_analysis: Mapped[bool] = mapped_column(Boolean, default=True)
    # 이용 기록 대상 여부. 보험료·통신비처럼 이용 횟수가 의미 없는 고정지출은 false로 두어
    # 미사용 알림·해지 추천·이용 확인에서 뺍니다.
    track_usage: Mapped[bool] = mapped_column(Boolean, default=True)
    # Android 앱 패키지명. 예: com.netflix.mediaclient
    android_package: Mapped[str | None] = mapped_column(String, nullable=True)
    # 자동 결제 기록을 이 날짜(한국 날짜)까지 확인했습니다. null이면 등록 전날부터 확인합니다.
    auto_payment_checked_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    # 삭제(숨김) 시각. 기록은 남겨 과거 지출 분석에 계속 포함하고, 되살릴 수 있습니다.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )

    usage_logs: Mapped[list[UsageLog]] = relationship(back_populates="subscription")
    payments: Mapped[list[PaymentRecord]] = relationship(back_populates="subscription")
    decisions: Mapped[list[DecisionHistory]] = relationship(back_populates="subscription")


class UsageLog(Base):
    __tablename__ = "usage_logs"
    __table_args__ = (
        Index("ix_usage_subscription_date", "subscription_id", "used_date"),
        CheckConstraint("source IN ('manual', 'mobile_auto', 'notification')", name="ck_usage_source"),
        CheckConstraint(
            "duration_minutes IS NULL OR duration_minutes BETWEEN 0 AND 1440", name="ck_usage_duration"
        ),
        CheckConstraint(
            "device IS NULL OR device IN ('phone', 'tablet', 'tv', 'pc', 'other')", name="ck_usage_device"
        ),
        # 자동 측정은 구독·날짜마다 1건이며 다시 동기화하면 덮어씁니다.
        Index("ux_usage_auto_daily", "subscription_id", "used_date", unique=True,
              sqlite_where=text("source = 'mobile_auto'")),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("subscriptions.id"), nullable=False
    )
    used_date: Mapped[date] = mapped_column(Date, nullable=False)
    source: Mapped[str] = mapped_column(String, default="manual")
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    device: Mapped[str | None] = mapped_column(String, nullable=True)
    memo: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    subscription: Mapped[Subscription] = relationship(back_populates="usage_logs")


class PaymentRecord(Base):
    """실제 결제 기록. 구독 정보 변경 시에도 금액과 분류를 보존합니다."""

    __tablename__ = "payment_records"
    __table_args__ = (
        CheckConstraint("amount_won > 0", name="ck_payment_amount_positive"),
        CheckConstraint("source IN ('manual', 'auto')", name="ck_payment_source"),
        Index("ix_payment_subscription_date", "subscription_id", "paid_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subscription_id: Mapped[int] = mapped_column(ForeignKey("subscriptions.id"))
    amount_won: Mapped[int] = mapped_column(Integer, nullable=False)
    paid_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    category_snapshot: Mapped[str | None] = mapped_column(String, nullable=True)
    # auto는 결제일이 지나 서버가 구독 요금으로 만든 기록입니다.
    source: Mapped[str] = mapped_column(String, default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    subscription: Mapped[Subscription] = relationship(back_populates="payments")


class DecisionHistory(Base):
    __tablename__ = "decision_history"
    __table_args__ = (
        CheckConstraint("decision IN ('keep', 'cancel', 'hold', 'none')", name="ck_decision"),
        Index("ix_decision_subscription_time", "subscription_id", "decided_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subscription_id: Mapped[int] = mapped_column(ForeignKey("subscriptions.id"))
    decision: Mapped[str] = mapped_column(String)
    decided_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    memo: Mapped[str | None] = mapped_column(String, nullable=True)

    subscription: Mapped[Subscription] = relationship(back_populates="decisions")


class AppSettings(Base):
    __tablename__ = "app_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_single_settings"),
        CheckConstraint(
            "length(usage_check_time) = 5 AND substr(usage_check_time, 3, 1) = ':'",
            name="ck_usage_check_time",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    recommendation_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # 폰에서 Android 앱 사용 시간을 읽어 올릴지 여부. 권한이 필요해 기본은 꺼짐입니다.
    auto_tracking_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # TV·태블릿 시청을 기록하기 위한 매일 이용 확인 알림.
    usage_check_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    usage_check_time: Mapped[str] = mapped_column(String, default="21:00")
