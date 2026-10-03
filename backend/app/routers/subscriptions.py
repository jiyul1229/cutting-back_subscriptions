from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Response, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.auto_payments import ensure_auto_payments
from app.calculations import cancel_window, monthly_amount, next_renewal, today
from app.decision_state import latest_decisions
from app.models import Subscription, utc_now
from app.routers.dependencies import DatabaseSession, SubscriptionId, get_subscription_or_404
from app.schemas import SubscriptionCreate, SubscriptionResponse, SubscriptionUpdate


router = APIRouter(prefix="/api/subscriptions", tags=["subscriptions"])


def to_response(subscription: Subscription, decision: str | None = None) -> SubscriptionResponse:
    response = SubscriptionResponse.model_validate(subscription)
    response.latest_decision = decision
    if subscription.status == "active":
        current = today()
        response.next_renewal_date = next_renewal(subscription, current)
        response.d_day = (response.next_renewal_date - current).days
        # 통신비·보험료처럼 이용 기록 대상이 아닌 고정지출은 해지 기한을 보여주지 않습니다(문서 R2).
        if subscription.track_usage:
            response.cancel_window_start, response.cancel_window_end = cancel_window(subscription, current)
    return response


# 정렬 키: (응답, 월 환산 금액) 쌍을 받습니다.
SORT_KEYS = {
    "id": lambda pair: pair[0].id,
    "name": lambda pair: (pair[0].name, pair[0].id),
    "price": lambda pair: (pair[1], pair[0].id),
    "category": lambda pair: (pair[0].category or "~", pair[0].name, pair[0].id),
    # 해지·일시정지 구독(다음 결제일 없음)은 뒤로
    "next_renewal": lambda pair: (
        pair[0].next_renewal_date is None, pair[0].next_renewal_date or pair[0].created_at.date(), pair[0].id,
    ),
}


def commit_or_conflict(db: DatabaseSession) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if "android_package" in str(exc.orig):
            raise HTTPException(409, "android_package is already linked to another subscription") from exc
        raise


@router.post("", response_model=SubscriptionResponse, status_code=status.HTTP_201_CREATED)
def create_subscription(payload: SubscriptionCreate, db: DatabaseSession):
    subscription = Subscription(**payload.model_dump())
    db.add(subscription)
    commit_or_conflict(db)
    db.refresh(subscription)
    return to_response(subscription)


def respond(db, subscription: Subscription) -> SubscriptionResponse:
    return to_response(subscription, latest_decisions(db, [subscription.id]).get(subscription.id))


@router.get("", response_model=list[SubscriptionResponse])
def list_subscriptions(
    db: DatabaseSession,
    include_deleted: Annotated[bool, Query()] = False,
    category: Annotated[str | None, Query(description="이 카테고리만")] = None,
    sort: Annotated[Literal["id", "name", "price", "category", "next_renewal"], Query()] = "id",
    order: Annotated[Literal["asc", "desc"], Query()] = "asc",
):
    """구독 목록. sort=price는 월 환산 금액, next_renewal은 다음 결제일 순입니다."""
    query = select(Subscription)
    if not include_deleted:
        query = query.where(Subscription.deleted_at.is_(None))
    if category is not None:
        query = query.where(Subscription.category == category)
    subscriptions = list(db.scalars(query.order_by(Subscription.id)))
    decisions = latest_decisions(db, [subscription.id for subscription in subscriptions])
    pairs = [
        (to_response(subscription, decisions.get(subscription.id)), monthly_amount(subscription))
        for subscription in subscriptions
    ]
    pairs.sort(key=SORT_KEYS[sort], reverse=order == "desc")
    return [response for response, _ in pairs]


@router.get("/{id}", response_model=SubscriptionResponse)
def get_subscription(id: SubscriptionId, db: DatabaseSession):
    return respond(db, get_subscription_or_404(id, db, allow_deleted=True))


@router.patch("/{id}", response_model=SubscriptionResponse)
def update_subscription(id: SubscriptionId, payload: SubscriptionUpdate, db: DatabaseSession):
    # 가격·결제일·상태를 바꾸기 전에 지난 결제일을 기존 조건으로 먼저 기록합니다.
    ensure_auto_payments(db)
    subscription = get_subscription_or_404(id, db)
    changes = payload.model_dump(exclude_unset=True)
    # PATCH도 기존 값과 합친 최종 상태로 월/연 결제 규칙을 검증합니다.
    merged = {field: getattr(subscription, field) for field in SubscriptionCreate.model_fields}
    try:
        SubscriptionCreate.model_validate({**merged, **changes})
    except ValidationError as exc:
        errors = exc.errors(include_context=False)
        for error in errors:
            error["loc"] = ("body", *error["loc"])
        raise RequestValidationError(errors) from exc
    for field, value in changes.items():
        setattr(subscription, field, value)
    commit_or_conflict(db)
    db.refresh(subscription)
    return respond(db, subscription)


@router.delete("/{id}", status_code=204)
def delete_subscription(id: SubscriptionId, db: DatabaseSession) -> Response:
    """목록·홈·캘린더 예정·알림·추천에서 숨깁니다.

    결제·이용·결정 기록은 지우지 않아 과거 지출 분석에 계속 남습니다.
    해지 상태로 바꾸고 앱 연결(android_package)은 풀어서 같은 앱을 새 구독에 연결할 수 있게 합니다.
    """
    ensure_auto_payments(db)
    subscription = get_subscription_or_404(id, db)
    subscription.status = "canceled"
    subscription.android_package = None
    subscription.deleted_at = utc_now()
    db.commit()
    return Response(status_code=204)


@router.post("/{id}/restore", response_model=SubscriptionResponse)
def restore_subscription(id: SubscriptionId, db: DatabaseSession):
    """삭제한 구독을 목록에 되살립니다. 상태는 해지(canceled)로 남으므로 다시 쓰려면 PATCH로 active로 바꿉니다."""
    subscription = get_subscription_or_404(id, db, allow_deleted=True)
    if subscription.deleted_at is None:
        raise HTTPException(409, "Subscription is not deleted")
    subscription.deleted_at = None
    db.commit()
    db.refresh(subscription)
    return respond(db, subscription)
