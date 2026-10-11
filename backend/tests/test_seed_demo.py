"""발표용 예시 데이터가 화면을 채우는지 확인."""
from datetime import date
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sqlalchemy import URL, create_engine, select
from sqlalchemy.orm import Session

from app.models import Subscription
from app.recommendations import build_recommendations
from app.routers.analytics import monthly_trend
from app.routers.dashboard import get_dashboard
from app.seed_demo import main


class SeedDemoTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="seed-demo-")
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "demo.db"

    def seed_on(self, current: date):
        with patch("app.seed_demo.today", return_value=current):
            main(["--database", str(self.path)])
        engine = create_engine(URL.create("sqlite", database=str(self.path)))
        self.addCleanup(engine.dispose)
        db = Session(engine)
        self.addCleanup(db.close)
        return db

    def test_fills_screens_like_figma(self):
        current = date(2026, 10, 3)
        db = self.seed_on(current)
        items = build_recommendations(db, current)
        names = {db.get(Subscription, item.subscription_id).name: item.reasons for item in items}
        self.assertEqual(names, {
            "넷플릭스": ["low_usage", "negative_memo", "duplicate_category"],
            "리디셀렉트": ["duplicate_category"],
        })
        self.assertEqual(sum(i.monthly_saving_won for i in items), 26900)
        self.assertEqual(sum(i.yearly_saving_won for i in items), 322800)

        trend = monthly_trend(2026, 10, db, months=5)
        self.assertEqual([p.month for p in trend], [6, 7, 8, 9, 10])
        self.assertTrue(all(p.total_won > 0 for p in trend), trend)
        self.assertNotEqual(len({p.total_won for p in trend}), 1)  # 달마다 금액이 달라 그래프가 의미 있음

        with patch("app.routers.dashboard.today", return_value=current):
            dashboard = get_dashboard(db)
        self.assertEqual(dashboard.active_subscription_count, 7)  # 해지한 왓챠 제외
        self.assertIsNotNone(dashboard.change_ratio)

    def test_refuses_when_data_exists(self):
        self.seed_on(date(2026, 10, 3))
        with self.assertRaises(SystemExit):
            main(["--database", str(self.path)])

    def test_month_end_and_year_boundary(self):
        db = self.seed_on(date(2027, 1, 31))
        self.assertEqual(len(db.scalars(select(Subscription)).all()), 8)
        self.assertEqual([p.month for p in monthly_trend(2027, 1, db, months=5)], [9, 10, 11, 12, 1])


if __name__ == "__main__":
    unittest.main()
