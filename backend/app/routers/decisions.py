from fastapi import APIRouter
from sqlalchemy import select

from app.models import DecisionHistory
from app.routers.dependencies import DatabaseSession, SubscriptionId, get_subscription_or_404
from app.schemas import DecisionCreate, DecisionResponse

router = APIRouter(prefix="/api/subscriptions", tags=["decisions"])


@router.post("/{id}/decisions", response_model=DecisionResponse, status_code=201)
def create_decision(id: SubscriptionId, payload: DecisionCreate, db: DatabaseSession):
    get_subscription_or_404(id, db)
    decision = DecisionHistory(subscription_id=id, **payload.model_dump())
    db.add(decision)
    db.commit()
    db.refresh(decision)
    return decision


@router.get("/{id}/decisions", response_model=list[DecisionResponse])
def list_decisions(id: SubscriptionId, db: DatabaseSession):
    get_subscription_or_404(id, db, allow_deleted=True)
    return list(db.scalars(select(DecisionHistory).where(
        DecisionHistory.subscription_id == id
    ).order_by(DecisionHistory.decided_at.desc(), DecisionHistory.id.desc())))
