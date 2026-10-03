from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import select

from app.models import DecisionHistory
from app.recommendations import apply_still_using, resolve_warning
from app.routers.dependencies import DatabaseSession, SubscriptionId, get_subscription_or_404
from app.schemas import (
    DecisionCreate, DecisionResponse, RecommendationFeedbackCreate, RecommendationFeedbackResponse,
)

router = APIRouter(prefix="/api/subscriptions", tags=["decisions"])


@router.post("/{id}/decisions", response_model=DecisionResponse, status_code=201)
def create_decision(id: SubscriptionId, payload: DecisionCreate, db: DatabaseSession):
    get_subscription_or_404(id, db)
    decision = DecisionHistory(subscription_id=id, **payload.model_dump())
    db.add(decision)
    if payload.decision != "none":
        # 해지 추천을 보고 유지·해지·보류를 정했으면 그 경고에 응답한 것으로 기록합니다.
        resolve_warning(db, id, payload.decision)
    db.commit()
    db.refresh(decision)
    return decision


@router.get("/{id}/decisions", response_model=list[DecisionResponse])
def list_decisions(id: SubscriptionId, db: DatabaseSession):
    get_subscription_or_404(id, db, allow_deleted=True)
    return list(db.scalars(select(DecisionHistory).where(
        DecisionHistory.subscription_id == id
    ).order_by(DecisionHistory.decided_at.desc(), DecisionHistory.id.desc())))


def feedback_response(subscription, applied) -> RecommendationFeedbackResponse:
    return RecommendationFeedbackResponse(
        subscription_id=subscription.id, applied=applied,
        low_usage_max_count_override=subscription.low_usage_max_count_override,
        low_usage_snooze_until=subscription.low_usage_snooze_until,
        duplicate_exempt=subscription.duplicate_exempt,
    )


@router.post("/{id}/recommendation-feedback", response_model=RecommendationFeedbackResponse)
def give_recommendation_feedback(id: SubscriptionId, payload: RecommendationFeedbackCreate, db: DatabaseSession):
    """해지 추천 카드의 "아직 쓰고 있어요". 이 구독의 추천 기준을 조정합니다(F6 민감도 조정).

    - 미사용으로 추천됐고 이용이 1회 이상이면: 지금 횟수보다 더 줄었을 때만 추천
    - 이용 0회면(기록이 빠진 경우): 판단 기간 동안 미사용 추천을 멈춤
    - 중복으로 추천됐으면: 중복 추천에서 제외
    지금 추천 대상이 아니면 409입니다.
    """
    subscription = get_subscription_or_404(id, db)
    try:
        applied = apply_still_using(db, subscription)
    except LookupError as exc:
        raise HTTPException(409, "Subscription is not currently recommended") from exc
    db.refresh(subscription)
    return feedback_response(subscription, applied)


@router.delete("/{id}/recommendation-feedback", status_code=204)
def reset_recommendation_feedback(id: SubscriptionId, db: DatabaseSession) -> Response:
    """이 구독의 개인화된 추천 기준을 지우고 설정 기준으로 되돌립니다."""
    subscription = get_subscription_or_404(id, db)
    subscription.low_usage_max_count_override = None
    subscription.low_usage_snooze_until = None
    subscription.duplicate_exempt = False
    db.commit()
    return Response(status_code=204)
