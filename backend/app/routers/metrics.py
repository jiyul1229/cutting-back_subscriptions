from datetime import timedelta
from statistics import mean, median
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.calculations import today
from app.models import RecommendationWarning, Subscription, UsageLog
from app.routers.dependencies import DatabaseSession
from app.schemas import MetricsResponse, WeeklyCheckins

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


@router.get("", response_model=MetricsResponse)
def get_metrics(db: DatabaseSession, weeks: Annotated[int, Query(ge=1, le=52)] = 4):
    """문서의 판단 지표.

    - R1: 등록에 걸린 시간(앱이 registration_seconds를 보낸 구독만), 최근 weeks주 동안 주당 체크인 횟수
      (수기 기록과 알림 응답만. 자동 측정은 사용자가 한 일이 아니라 제외)
    - R3: 해지 추천 경고 중 "아직 쓰고 있어요" 비율(오탐률), 유지·해지·보류를 결정한 비율
    """
    seconds = list(db.scalars(select(Subscription.registration_seconds).where(
        Subscription.registration_seconds.is_not(None)
    )))

    current = today()
    this_week = current - timedelta(days=current.weekday())
    first_week = this_week - timedelta(weeks=weeks - 1)
    counts = dict(db.execute(select(UsageLog.used_date, func.count(UsageLog.id)).where(
        UsageLog.source.in_(("manual", "notification")),
        UsageLog.used_date >= first_week, UsageLog.used_date <= current,
    ).group_by(UsageLog.used_date)).all())
    by_week = []
    for index in range(weeks):
        start = first_week + timedelta(weeks=index)
        by_week.append(WeeklyCheckins(
            week_start=start,
            count=sum(n for day, n in counts.items() if start <= day < start + timedelta(days=7)),
        ))

    resolutions = list(db.scalars(select(RecommendationWarning.resolution)))
    answered = [r for r in resolutions if r is not None]
    still_using = answered.count("still_using")
    decided = len(answered) - still_using
    return MetricsResponse(
        registration_count=len(seconds),
        registration_seconds_avg=round(mean(seconds), 1) if seconds else None,
        registration_seconds_median=float(median(seconds)) if seconds else None,
        checkins_by_week=by_week,
        checkins_per_week_avg=round(sum(w.count for w in by_week) / weeks, 2),
        warnings_shown=len(resolutions),
        warnings_answered=len(answered),
        still_using_count=still_using,
        false_positive_rate=round(still_using / len(answered), 4) if answered else None,
        decision_rate=round(decided / len(resolutions), 4) if resolutions else None,
    )
