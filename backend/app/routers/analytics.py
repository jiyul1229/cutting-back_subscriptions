from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.calculations import month_bounds, month_shift
from app.models import AppSettings, PaymentRecord, Subscription
from app.recommendations import build_recommendations
from app.routers.dashboard import change
from app.routers.dependencies import DatabaseSession, Month, SyncedSession, Year
from app.schemas import (
    CategoryAnalysisResponse, MonthlyAnalysisResponse, RecommendationResponse, TrendPoint,
)

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def payment_filters(year: int, month: int):
    start, end = month_bounds(year, month)
    return (
        Subscription.include_in_analysis.is_(True),
        PaymentRecord.paid_date >= start, PaymentRecord.paid_date <= end,
    )


def month_total(db, year: int, month: int) -> int:
    if year < 1:
        return 0
    return db.scalar(select(func.sum(PaymentRecord.amount_won)).join(Subscription).where(
        *payment_filters(year, month)
    )) or 0


@router.get("/monthly", response_model=MonthlyAnalysisResponse)
def monthly_analysis(year: Year, month: Month, db: SyncedSession):
    total = month_total(db, year, month)
    previous = month_total(db, *month_shift(year, month, -1))
    change_won, change_ratio = change(total, previous)
    return MonthlyAnalysisResponse(
        total_won=total, previous_total_won=previous, change_won=change_won, change_ratio=change_ratio,
    )


@router.get("/trend", response_model=list[TrendPoint])
def monthly_trend(
    year: Year, month: Month, db: SyncedSession, months: Annotated[int, Query(ge=1, le=24)] = 5,
):
    """선택한 달을 포함해 최근 months개월의 실제 지출. 오래된 달부터."""
    points = []
    for offset in range(months - 1, -1, -1):
        y, m = month_shift(year, month, -offset)
        if y >= 1:
            points.append(TrendPoint(year=y, month=m, total_won=month_total(db, y, m)))
    return points


@router.get("/categories", response_model=list[CategoryAnalysisResponse])
def category_analysis(year: Year, month: Month, db: SyncedSession):
    rows = db.execute(select(
        PaymentRecord.category_snapshot, func.sum(PaymentRecord.amount_won)
    ).join(Subscription).where(*payment_filters(year, month))
      .group_by(PaymentRecord.category_snapshot)).all()
    total = sum(amount for _, amount in rows)
    return [
        CategoryAnalysisResponse(category=category, amount_won=amount, ratio=round(amount / total, 6))
        for category, amount in sorted(rows, key=lambda row: (-row[1], row[0] or ""))
    ]


@router.get("/recommendations", response_model=RecommendationResponse)
def recommendations(db: DatabaseSession):
    """해지 추천 목록과 추천대로 해지했을 때 절약 금액(이번 달 / 연간 최대)."""
    if not db.get(AppSettings, 1).recommendation_enabled:
        return RecommendationResponse(enabled=False, monthly_saving_won=0, yearly_saving_won=0, items=[])
    items = build_recommendations(db)
    return RecommendationResponse(
        enabled=True,
        monthly_saving_won=sum(item.monthly_saving_won for item in items),
        yearly_saving_won=sum(item.yearly_saving_won for item in items),
        items=items,
    )
