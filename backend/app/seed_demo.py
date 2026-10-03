"""발표용 예시 데이터. 빈 DB에만 넣습니다.

    python -m app.seed_demo                      # 기본 DB(subscriptions.db)
    python -m app.seed_demo --database demo.db   # 다른 DB 파일 (없으면 새로 만듦)

오늘 날짜를 기준으로 최근 5개월 결제 기록과 최근 90일 이용 기록을 만듭니다.
해지 추천은 넷플릭스(이용 1회·부정 메모·OTT 중 최저 이용)와 리디셀렉트(도서 중 최저 이용)가 나오고,
절약 가능 금액은 월 26,900원 / 연 322,800원입니다(Figma 시안과 같은 값).
"""
import argparse
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from sqlalchemy import URL, create_engine, event, func, select
from sqlalchemy.orm import Session

from app.calculations import BUSINESS_TZ, month_shift, scheduled_date, today
from app.database import DATABASE_PATH, enable_foreign_keys
from app.models import AppSettings, Base, PaymentRecord, Subscription, UsageLog


@dataclass
class DemoSubscription:
    name: str
    price_won: int
    billing_day: int
    category: str
    started_months_ago: int
    # 최근 90일 이용 횟수. 기록 날짜는 고르게 나눕니다.
    uses_90d: int
    memo: str | None = None
    usage_memo: str | None = None
    device: str | None = None
    duration_minutes: int | None = None
    # 해지한 구독이면 몇 달 전까지 결제했는지
    canceled_months_ago: int | None = None
    track_usage: bool = True
    plan_name: str | None = None


DEMO = [
    DemoSubscription("넷플릭스", 17000, 15, "ott", 5, uses_90d=1, plan_name="프리미엄",
                     usage_memo="요즘 재미없어서 안 봄", device="tv", duration_minutes=50),
    DemoSubscription("유튜브 프리미엄", 14900, 22, "ott", 5, uses_90d=40, device="phone", duration_minutes=35),
    DemoSubscription("티빙", 13900, 8, "ott", 2, uses_90d=9, device="tablet", duration_minutes=70),
    DemoSubscription("리디셀렉트", 9900, 28, "book", 5, uses_90d=3, memo="출퇴근용"),
    DemoSubscription("밀리의서재", 9900, 3, "book", 4, uses_90d=12),
    DemoSubscription("예스24 북클럽", 5500, 18, "book", 3, uses_90d=6),
    DemoSubscription("네이버플러스 멤버십", 4900, 12, "shopping", 5, uses_90d=8),
    DemoSubscription("왓챠", 7900, 5, "ott", 5, uses_90d=0, canceled_months_ago=2),
]


def usage_days(count: int, current: date) -> list[date]:
    """최근 90일 안에 count번을 고르게 나눈 날짜. 1번이면 20일 전."""
    if count == 1:
        return [current - timedelta(days=20)]
    return [current - timedelta(days=round(i * 88 / (count - 1))) for i in range(count)]


def kst_noon_utc(day: date) -> datetime:
    return datetime.combine(day, time(12), BUSINESS_TZ).astimezone(timezone.utc).replace(tzinfo=None)


def seed(db: Session, current: date) -> list[Subscription]:
    created = []
    for demo in DEMO:
        start_year, start_month = month_shift(current.year, current.month, -demo.started_months_ago)
        started = date(start_year, start_month, 1)
        canceled = demo.canceled_months_ago is not None
        subscription = Subscription(
            name=demo.name, price_won=demo.price_won, billing_cycle="monthly", billing_day=demo.billing_day,
            category=demo.category, plan_name=demo.plan_name, memo=demo.memo, started_on=started,
            status="canceled" if canceled else "active", track_usage=demo.track_usage,
            # 결제 기록은 아래에서 직접 만들므로 오늘까지 확인한 것으로 둡니다.
            auto_payment_checked_on=current, created_at=kst_noon_utc(started),
        )
        db.add(subscription)
        db.flush()

        last_offset = demo.canceled_months_ago or 0
        for offset in range(demo.started_months_ago, last_offset - 1, -1):
            year, month = month_shift(current.year, current.month, -offset)
            due = scheduled_date(subscription, year, month)
            if due is not None and due <= current:
                db.add(PaymentRecord(
                    subscription_id=subscription.id, amount_won=demo.price_won, paid_date=due,
                    category_snapshot=demo.category, source="auto", created_at=kst_noon_utc(due),
                ))

        for index, used in enumerate(usage_days(demo.uses_90d, current)):
            # 메모는 가장 최근 기록에만
            db.add(UsageLog(
                subscription_id=subscription.id, used_date=used, source="manual",
                device=demo.device, duration_minutes=demo.duration_minutes,
                memo=demo.usage_memo if index == 0 else None,
                created_at=kst_noon_utc(used), updated_at=kst_noon_utc(used),
            ))
        created.append(subscription)
    db.commit()
    return created


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--database", type=Path, default=DATABASE_PATH)
    args = parser.parse_args(argv)
    engine = create_engine(URL.create("sqlite", database=str(args.database.resolve())))
    event.listen(engine, "connect", enable_foreign_keys)
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            if db.get(AppSettings, 1) is None:
                db.add(AppSettings(id=1))
                db.commit()
            if db.scalar(select(func.count(Subscription.id))):
                raise SystemExit(
                    "이미 구독 데이터가 있어 예시 데이터를 넣지 않았습니다. "
                    "새 DB 파일을 쓰거나 POST /api/settings/reset-data로 비운 뒤 다시 실행하세요."
                )
            created = seed(db, today())
            print(f"예시 구독 {len(created)}개를 넣었습니다: {args.database.resolve()}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
