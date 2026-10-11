"""Figma 대조 후 추가한 기능: 구독 필드, 삭제, 전월 대비, 월별 추이, 해지 추천."""
from contextlib import closing
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from sqlalchemy import URL, create_engine, event, select
from sqlalchemy.orm import Session

from app.auto_payments import ensure_auto_payments
from app.calculations import BUSINESS_TZ, month_shift, today
from app.database import enable_foreign_keys
from app.models import Base, PaymentRecord, Subscription
from test_api import LiveApiTestCase


class FigmaGapApiTests(LiveApiTestCase):
    def setUp(self):
        with closing(sqlite3.connect(self.db_path)) as connection, connection:
            for table in ("decision_history", "usage_logs", "payment_records", "subscriptions"):
                connection.execute(f"DELETE FROM {table}")
            connection.execute("UPDATE app_settings SET notifications_enabled=1, recommendation_enabled=1")

    def age(self, sid, days):
        start = datetime.combine(today() - timedelta(days=days - 1), time.min, BUSINESS_TZ)
        with closing(sqlite3.connect(self.db_path)) as connection, connection:
            connection.execute("UPDATE subscriptions SET created_at=? WHERE id=?",
                               (start.astimezone(timezone.utc).replace(tzinfo=None).isoformat(" "), sid))

    def pay(self, sid, amount, paid_date):
        return self.request("POST", "/api/payments",
                            {"subscription_id": sid, "amount_won": amount, "paid_date": paid_date.isoformat()}, 201)

    def test_subscription_detail_fields(self):
        created = self.create_subscription(plan_name=" 프리미엄 플랜 ", memo="가족 공유", started_on="2023-03-15")
        self.assertEqual((created["plan_name"], created["memo"], created["started_on"]),
                         ("프리미엄 플랜", "가족 공유", "2023-03-15"))
        # 상세에도 다음 결제일과 D-day가 들어 있습니다.
        detail = self.request("GET", f"/api/subscriptions/{created['id']}")
        self.assertIsNotNone(detail["next_renewal_date"])
        self.assertGreaterEqual(detail["d_day"], 0)
        self.request("POST", "/api/subscriptions", {
            "name": "x", "price_won": 1, "billing_day": 1, "started_on": (today() + timedelta(days=1)).isoformat(),
        }, 422)
        cleared = self.request("PATCH", f"/api/subscriptions/{created['id']}",
                               {"memo": None, "plan_name": None, "status": "paused"})
        self.assertEqual((cleared["memo"], cleared["plan_name"]), (None, None))
        self.assertIsNone(cleared["next_renewal_date"])  # 활성 구독만 계산

    def test_delete_keeps_history_and_hides_everywhere(self):
        current = today()
        sid = self.create_subscription(android_package="com.netflix.mediaclient", category="OTT")["id"]
        self.pay(sid, 17000, current)
        self.request("DELETE", f"/api/subscriptions/{sid}", expected=204)
        self.assertEqual(self.request("GET", "/api/dashboard")["subscriptions"], [])
        self.assertEqual(self.request("GET", "/api/notifications"), [])
        calendar = self.request("GET", f"/api/calendar?year={current.year}&month={current.month}")
        self.assertEqual([row["type"] for row in calendar], ["paid"])  # 실제 결제는 남음
        monthly = self.request("GET", f"/api/analytics/monthly?year={current.year}&month={current.month}")
        self.assertEqual(monthly["total_won"], 17000)
        self.assertEqual(len(self.request("GET", f"/api/payments?subscription_id={sid}")), 1)
        self.request("POST", f"/api/subscriptions/{sid}/usage-logs", {}, 404)
        self.request("POST", "/api/payments", {"subscription_id": sid, "amount_won": 1, "paid_date": "2026-01-01"}, 404)
        # 앱 연결이 풀려 같은 앱을 새 구독에 연결할 수 있습니다.
        self.create_subscription(android_package="com.netflix.mediaclient")

    def test_month_comparison_and_trend(self):
        current = today()
        sid = self.create_subscription(price_won=10000)["id"]
        y, m = month_shift(current.year, current.month, -1)
        self.pay(sid, 8000, date(y, m, 1))
        self.pay(sid, 10000, current.replace(day=1))
        dashboard = self.request("GET", "/api/dashboard")
        self.assertEqual((dashboard["monthly_total_won"], dashboard["previous_month_paid_won"]), (10000, 8000))
        self.assertEqual((dashboard["change_won"], dashboard["change_ratio"]), (2000, 0.25))
        monthly = self.request("GET", f"/api/analytics/monthly?year={current.year}&month={current.month}")
        self.assertEqual((monthly["previous_total_won"], monthly["change_won"], monthly["change_ratio"]),
                         (8000, 2000, 0.25))
        trend = self.request("GET", f"/api/analytics/trend?year={current.year}&month={current.month}")
        self.assertEqual(len(trend), 5)
        self.assertEqual([(p["year"], p["month"]) for p in trend][-1], (current.year, current.month))
        self.assertEqual([p["total_won"] for p in trend][-2:], [8000, 10000])
        self.assertEqual(len(self.request("GET", "/api/analytics/trend?year=2026&month=3&months=12")), 12)
        self.request("GET", "/api/analytics/trend?year=2026&month=3&months=0", expected=422)
        self.assertEqual(len(self.request("GET", "/api/analytics/trend?year=1&month=2")), 2)

    def test_recommendations(self):
        netflix = self.create_subscription(name="넷플릭스", price_won=17000, category="OTT")["id"]
        tving = self.create_subscription(name="티빙", price_won=13900, category="ott ")["id"]
        ridi = self.create_subscription(name="리디셀렉트", price_won=118800, billing_cycle="yearly",
                                        billing_month=3, billing_day=1, category="도서")["id"]
        youtube = self.create_subscription(name="유튜브", price_won=14900, category="영상")["id"]
        for sid in (netflix, tving, ridi, youtube):
            self.age(sid, 40)
        for days_ago in range(5):  # OTT는 2개뿐이라 중복 추천 대상 아님(3개 이상부터)
            self.request("POST", f"/api/subscriptions/{tving}/usage-logs",
                         {"used_date": (today() - timedelta(days=days_ago)).isoformat()}, 201)
        for days_ago in range(3):
            self.request("POST", f"/api/subscriptions/{youtube}/usage-logs",
                         {"used_date": (today() - timedelta(days=days_ago)).isoformat()}, 201)
        result = self.request("GET", "/api/analytics/recommendations")
        items = {item["subscription_id"]: item for item in result["items"]}
        self.assertEqual(set(items), {netflix, ridi})
        self.assertEqual(items[netflix]["reasons"], ["low_usage"])
        self.assertEqual(items[netflix]["duplicate_with"], [])
        self.assertEqual(items[ridi]["reasons"], ["low_usage"])
        self.assertEqual((items[ridi]["monthly_saving_won"], items[ridi]["yearly_saving_won"]), (9900, 118800))
        self.assertEqual((result["monthly_saving_won"], result["yearly_saving_won"]), (26900, 322800))
        notices = [n for n in self.request("GET", "/api/notifications") if n["type"] == "recommendation"]
        self.assertEqual({n["subscription_id"] for n in notices}, {netflix, ridi})
        # 유지를 결정하면 30일 동안 추천하지 않습니다.
        self.request("POST", f"/api/subscriptions/{ridi}/decisions", {"decision": "keep"}, 201)
        self.assertEqual([i["subscription_id"] for i in self.request("GET", "/api/analytics/recommendations")["items"]],
                         [netflix])
        self.request("PATCH", "/api/settings", {"recommendation_enabled": False})
        self.assertEqual(self.request("GET", "/api/analytics/recommendations"),
                         {"enabled": False, "monthly_saving_won": 0, "yearly_saving_won": 0, "items": [],
                          "collecting": []})
        self.assertNotIn("recommendation", [n["type"] for n in self.request("GET", "/api/notifications")])

    def test_fixed_expense_is_not_tracked(self):
        # 보험료처럼 이용 기록 대상이 아니면 미사용 알림·추천·이용 확인에서 빠집니다.
        insurance = self.create_subscription(name="보험료", category="etc", track_usage=False)
        self.assertFalse(insurance["track_usage"])
        # 이용 기록 대상인 '기타' 구독 2개: 서로 중복으로 추천하지 않아야 합니다.
        other_etc = self.create_subscription(name="통신비", category="etc")["id"]
        third_etc = self.create_subscription(name="클라우드", category="etc", price_won=3000)["id"]
        for sid in (other_etc, third_etc):
            for _ in range(3):  # 미사용(90일 2회 이하)이 아니게 해서 중복 여부만 확인
                self.request("POST", f"/api/subscriptions/{sid}/usage-logs", {}, 201)
        for sid in (insurance["id"], other_etc, third_etc):
            self.age(sid, 40)
        self.assertEqual(self.request("GET", "/api/analytics/recommendations")["items"], [])
        notice_types = {(n["subscription_id"], n["type"]) for n in self.request("GET", "/api/notifications")}
        self.assertNotIn((insurance["id"], "recommendation"), notice_types)
        checks = [i["subscription_id"] for i in self.request("GET", "/api/usage-checks")["items"]]
        self.assertNotIn(insurance["id"], checks)
        self.request("PATCH", f"/api/subscriptions/{insurance['id']}", {"track_usage": None}, 422)
        self.assertTrue(self.request("PATCH", f"/api/subscriptions/{insurance['id']}", {"track_usage": True})["track_usage"])

    def test_latest_decision_in_responses(self):
        sid = self.create_subscription()["id"]
        detail = f"/api/subscriptions/{sid}"
        self.assertIsNone(self.request("GET", detail)["latest_decision"])
        self.request("POST", detail + "/decisions", {"decision": "hold"}, 201)
        self.request("POST", detail + "/decisions", {"decision": "postpone"}, 422)  # 앱과 같은 이름 hold만
        self.request("POST", detail + "/decisions", {"decision": "keep"}, 201)
        self.assertEqual(self.request("GET", detail)["latest_decision"], "keep")
        self.assertEqual(self.request("GET", "/api/subscriptions")[0]["latest_decision"], "keep")
        self.assertEqual(self.request("GET", "/api/dashboard")["subscriptions"][0]["latest_decision"], "keep")
        self.assertEqual(self.request("PATCH", detail, {"memo": "x"})["latest_decision"], "keep")

    def test_low_usage_is_two_uses_in_90_days(self):
        def sub_with_uses(name, days_ago_list):
            sid = self.create_subscription(name=name, category=name)["id"]  # 카테고리 달리해서 중복 제외
            self.age(sid, 120)
            for days_ago in days_ago_list:
                self.request("POST", f"/api/subscriptions/{sid}/usage-logs",
                             {"used_date": (today() - timedelta(days=days_ago)).isoformat()}, 201)
            return sid
        two = sub_with_uses("two", [0, 89])           # 2회 → 미사용
        three = sub_with_uses("three", [0, 1, 89])    # 3회 → 아님
        outside = sub_with_uses("outside", [0, 1, 90])  # 90일 전 기록은 기간 밖 → 2회 → 미사용
        items = {i["subscription_id"]: i for i in self.request("GET", "/api/analytics/recommendations")["items"]}
        self.assertEqual(set(items), {two, outside})
        self.assertEqual((items[two]["recent_usage_count"], items[outside]["recent_usage_count"]), (2, 2))
        self.assertNotIn(three, items)

    def test_new_subscription_is_not_low_usage(self):
        self.create_subscription()
        self.assertEqual(self.request("GET", "/api/analytics/recommendations")["items"], [])


class RegistrationMonthPaymentTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="registration-month-")
        self.addCleanup(temp.cleanup)
        engine = create_engine(URL.create("sqlite", database=str(Path(temp.name) / "test.db")))
        self.addCleanup(engine.dispose)
        event.listen(engine, "connect", enable_foreign_keys)
        Base.metadata.create_all(engine)
        self.db = Session(engine)
        self.addCleanup(self.db.close)

    def paid_dates(self, **values):
        self.db.add(Subscription(**{"name": "s", "price_won": 1000, "billing_cycle": "monthly",
                                    "billing_day": 1, "created_at": datetime(2026, 10, 3), **values}))
        self.db.commit()
        with patch("app.auto_payments.today", return_value=date(2026, 10, 3)):
            ensure_auto_payments(self.db)
        return [p.paid_date for p in self.db.scalars(select(PaymentRecord))]

    def test_includes_earlier_billing_day_in_registration_month(self):
        self.assertEqual(self.paid_dates(), [date(2026, 10, 1)])

    def test_started_on_after_billing_day_skips_it(self):
        self.assertEqual(self.paid_dates(started_on=date(2026, 10, 2)), [])

    def test_older_started_on_does_not_backfill_previous_months(self):
        self.assertEqual(self.paid_dates(started_on=date(2023, 3, 15)), [date(2026, 10, 1)])


if __name__ == "__main__":
    unittest.main()
