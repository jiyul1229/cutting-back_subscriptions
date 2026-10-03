"""구독별 최근 결정(유지/해지/보류 태그).

앱에서 '해지' 태그를 붙인 구독은 상태(status)가 아직 active여도 캘린더 예정·알림·추천·이용 확인에서
뺍니다. 실제로 해지했으면 PATCH status=canceled로 바꿉니다.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DecisionHistory


def latest_decisions(db: Session, ids: list[int] | None = None) -> dict[int, str]:
    """구독별 가장 최근 결정. 결정 시각, 같으면 나중에 기록한 순서로 정렬해 마지막 값을 씁니다."""
    if ids is not None and not ids:
        return {}
    query = select(DecisionHistory.subscription_id, DecisionHistory.decision)
    if ids is not None:
        query = query.where(DecisionHistory.subscription_id.in_(ids))
    rows = db.execute(query.order_by(DecisionHistory.decided_at, DecisionHistory.id))
    latest = {subscription_id: decision for subscription_id, decision in rows}
    # 마지막 기록이 none(태그 해제)이면 태그가 없는 것으로 봅니다.
    return {subscription_id: decision for subscription_id, decision in latest.items() if decision != "none"}


def cancel_tagged(db: Session) -> set[int]:
    return {sid for sid, decision in latest_decisions(db).items() if decision == "cancel"}
