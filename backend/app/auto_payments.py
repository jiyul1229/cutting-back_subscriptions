"""결제일이 지난 활성 구독의 결제 기록을 자동으로 만듭니다.

조회 API가 호출될 때 실행하므로 별도 스케줄러가 필요 없습니다.
구독마다 auto_payment_checked_on까지 확인했다고 기록해서
- 같은 결제일을 두 번 만들지 않고
- 사용자가 지운 자동 기록을 다시 만들지 않으며
- 일시정지·해지 상태였던 기간은 나중에 다시 활성화해도 소급하지 않습니다.

처음 확인 범위는 앱에 등록한 달의 1일부터입니다. 이미 쓰던 구독을 10월 3일에 등록했고
결제일이 1일이면 10월 1일 결제도 기록합니다. 실제 시작일(started_on)이 그보다 늦으면
시작일부터 기록합니다. 그 이전 달은 소급하지 않습니다.
"""
from datetime import date, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.calculations import billing_cycle_bounds, business_date, scheduled_dates, today
from app.models import PaymentRecord, Subscription


def due_dates(subscription: Subscription, after: date, until: date) -> list[date]:
    """after 초과 until 이하인 예정 결제일."""
    result = []
    year, month = after.year, after.month
    while (year, month) <= (until.year, until.month):
        result.extend(due for due in scheduled_dates(subscription, year, month) if after < due <= until)
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return result


def first_check_day(subscription: Subscription) -> date:
    """처음 자동 기록을 확인할 범위의 시작 전날."""
    registered = business_date(subscription.created_at)
    start = registered.replace(day=1)
    if subscription.started_on is not None and subscription.started_on > start:
        start = subscription.started_on
    return start - timedelta(days=1)


def already_paid(db: Session, subscription: Subscription, due: date) -> bool:
    """같은 결제 주기(월간=같은 달, 연간=같은 해, 매주=같은 주)에 이미 결제 기록이 있는지."""
    start, end = billing_cycle_bounds(subscription, due)
    return db.scalar(select(PaymentRecord.id).where(
        PaymentRecord.subscription_id == subscription.id,
        PaymentRecord.paid_date >= start, PaymentRecord.paid_date <= end,
    ).limit(1)) is not None


def ensure_auto_payments(db: Session) -> None:
    current = today()
    pending = db.scalars(select(Subscription).where(
        (Subscription.auto_payment_checked_on.is_(None))
        | (Subscription.auto_payment_checked_on < current)
    )).all()
    for subscription in pending:
        previous = subscription.auto_payment_checked_on
        # 동시에 들어온 요청 중 하나만 이 구간을 처리하도록 확인 날짜를 먼저 선점합니다.
        claimed = db.execute(
            update(Subscription)
            .where(
                Subscription.id == subscription.id,
                Subscription.auto_payment_checked_on.is_(None) if previous is None
                else Subscription.auto_payment_checked_on == previous,
            )
            .values(auto_payment_checked_on=current, updated_at=Subscription.updated_at)
            .execution_options(synchronize_session=False)
        ).rowcount
        if not claimed or subscription.status != "active":
            continue
        start = previous or first_check_day(subscription)
        for due in due_dates(subscription, start, current):
            if already_paid(db, subscription, due):
                continue
            db.add(PaymentRecord(
                subscription_id=subscription.id, amount_won=subscription.price_won,
                paid_date=due, category_snapshot=subscription.category, source="auto",
            ))
            db.flush()
    db.commit()
