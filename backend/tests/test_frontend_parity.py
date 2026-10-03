"""팀 앱(src/domain) 기준에 맞춘 기능: 해지 권장 기간, 해지 태그, 메모 부정 표현, 이용 단가, 전체 초기화."""
from contextlib import closing
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest

from app.calculations import BUSINESS_TZ, today
from app.migrate import migrate_database
from test_api import LiveApiTestCase


class FrontendParityTests(LiveApiTestCase):
    def setUp(self):
        with closing(sqlite3.connect(self.db_path)) as connection, connection:
            for table in ("decision_history", "usage_logs", "payment_records", "subscriptions"):
                connection.execute(f"DELETE FROM {table}")
            connection.execute("UPDATE app_settings SET notifications_enabled=1, recommendation_enabled=1, "
                               "usage_check_enabled=1, low_usage_window_days=90, low_usage_max_count=2")

    def age(self, sid, days):
        start = datetime.combine(today() - timedelta(days=days - 1), time.min, BUSINESS_TZ)
        with closing(sqlite3.connect(self.db_path)) as connection, connection:
            connection.execute("UPDATE subscriptions SET created_at=? WHERE id=?",
                               (start.astimezone(timezone.utc).replace(tzinfo=None).isoformat(" "), sid))

    def due_in(self, days):
        """d_day가 days가 되도록 결제일을 고릅니다(월말 보정이 없는 날짜만 사용)."""
        due = today() + timedelta(days=days)
        return due.day

    def notices(self, sid):
        return [n["type"] for n in self.request("GET", "/api/notifications") if n["subscription_id"] == sid]

    def test_defaults_match_app(self):
        created = self.create_subscription()
        self.assertEqual(created["renewal_reminder_days"], 3)

    def test_cancel_window(self):
        if (today() + timedelta(days=5)).month != today().month or today().day > 23:
            self.skipTest("월말 경계에서는 결제일 계산이 달라 건너뜁니다")
        four = self.create_subscription(name="four", category=None, billing_day=self.due_in(4))
        self.assertEqual(self.notices(four["id"]), ["cancel_window"])
        detail = self.request("GET", f"/api/subscriptions/{four['id']}")
        due = date.fromisoformat(detail["next_renewal_date"])
        self.assertEqual((detail["cancel_window_start"], detail["cancel_window_end"]),
                         ((due - timedelta(days=5)).isoformat(), (due - timedelta(days=1)).isoformat()))
        two = self.create_subscription(name="two", category=None, billing_day=self.due_in(2))
        self.assertEqual(self.notices(two["id"]), ["renewal"])  # 결제 알림이 우선
        six = self.create_subscription(name="six", category=None, billing_day=self.due_in(6))
        self.assertEqual(self.notices(six["id"]), [])
        home = self.request("GET", "/api/dashboard")["subscriptions"]
        self.assertTrue(all(item["cancel_window_start"] for item in home))

    def test_cancel_tag_hides_everywhere(self):
        current = today()
        sid = self.create_subscription(billing_day=28 if current.day < 28 else current.day,
                                       renewal_reminder_days=365)["id"]
        self.age(sid, 40)  # 이용 0회 → 미사용 추천 대상
        self.assertIn("renewal", self.notices(sid))
        self.assertIn(sid, [i["subscription_id"] for i in self.request("GET", "/api/analytics/recommendations")["items"]])
        self.request("POST", f"/api/subscriptions/{sid}/decisions", {"decision": "cancel"}, 201)
        self.assertEqual(self.notices(sid), [])
        self.assertEqual(self.request("GET", "/api/analytics/recommendations")["items"], [])
        self.assertNotIn(sid, [i["subscription_id"] for i in self.request("GET", "/api/usage-checks")["items"]])
        calendar = self.request("GET", f"/api/calendar?year={current.year}&month={current.month}")
        self.assertNotIn(sid, [row["subscription_id"] for row in calendar if row["type"] == "scheduled"])
        # 상태는 바뀌지 않고, 다시 유지로 바꾸면 돌아옵니다.
        self.assertEqual(self.request("GET", f"/api/subscriptions/{sid}")["status"], "active")
        self.request("POST", f"/api/subscriptions/{sid}/decisions", {"decision": "keep"}, 201)
        self.assertIn("renewal", self.notices(sid))

    def test_negative_memo_and_cost_per_use(self):
        sid = self.create_subscription(price_won=12000, category="ott")["id"]
        self.age(sid, 40)
        self.request("POST", f"/api/subscriptions/{sid}/usage-logs", {"memo": "요즘 재미없어서 안 봄"}, 201)
        item = self.request("GET", "/api/analytics/recommendations")["items"][0]
        self.assertEqual(item["reasons"], ["low_usage", "negative_memo"])
        self.assertEqual(item["cost_per_use_won"], 36000)  # 12000 / (1회 / 3)
        quiet = self.create_subscription(name="quiet", category="book")["id"]
        self.age(quiet, 40)
        quiet_item = [i for i in self.request("GET", "/api/analytics/recommendations")["items"]
                      if i["subscription_id"] == quiet][0]
        self.assertEqual((quiet_item["reasons"], quiet_item["cost_per_use_won"]), (["low_usage"], None))

    def sub_with_uses(self, name, category, price, uses):
        sid = self.create_subscription(name=name, category=category, price_won=price)["id"]
        for _ in range(uses):  # 3회 이상이면 미사용(2회 이하)이 아니어서 중복 이유만 확인됩니다
            self.request("POST", f"/api/subscriptions/{sid}/usage-logs", {}, 201)
        return sid

    def recommended(self):
        return {i["subscription_id"]: i for i in self.request("GET", "/api/analytics/recommendations")["items"]}

    def test_three_in_same_category_recommends_only_least_used(self):
        most = self.sub_with_uses("most", "ott", 17000, 9)
        middle = self.sub_with_uses("middle", "ott", 13900, 5)
        least = self.sub_with_uses("least", "ott", 9900, 3)
        items = self.recommended()
        self.assertEqual(set(items), {least})
        self.assertEqual(items[least]["reasons"], ["duplicate_category"])
        self.assertEqual(sorted(items[least]["duplicate_with"]), sorted([most, middle]))

    def test_two_in_same_category_is_not_duplicate(self):
        self.sub_with_uses("a", "ott", 17000, 9)
        self.sub_with_uses("b", "ott", 9900, 3)
        self.assertEqual(self.recommended(), {})

    def test_tie_recommends_more_expensive(self):
        self.sub_with_uses("a", "ott", 17000, 9)
        self.sub_with_uses("cheap", "ott", 9900, 3)
        pricey = self.sub_with_uses("pricey", "ott", 13900, 3)
        self.assertEqual(set(self.recommended()), {pricey})

    def test_clear_tag_with_none(self):
        sid = self.create_subscription(renewal_reminder_days=365)["id"]
        root = f"/api/subscriptions/{sid}"
        self.request("POST", root + "/decisions", {"decision": "cancel"}, 201)
        self.assertEqual(self.request("GET", root)["latest_decision"], "cancel")
        self.assertEqual(self.notices(sid), [])  # 해지 태그면 알림 없음
        cleared = self.request("POST", root + "/decisions", {"decision": "none"}, 201)
        self.assertEqual(cleared["decision"], "none")
        self.assertIsNone(self.request("GET", root)["latest_decision"])
        self.assertEqual(self.notices(sid), ["renewal"])  # 태그를 풀면 다시 알림
        self.assertEqual(len(self.request("GET", root + "/decisions")), 2)  # 이력은 남음

    def test_home_total_is_monthly_equivalent(self):
        self.create_subscription(price_won=10000)
        self.create_subscription(name="연간", price_won=120000, billing_cycle="yearly",
                                 billing_month=12, billing_day=1)
        self.assertEqual(self.request("GET", "/api/dashboard")["monthly_total_won"], 10000 + 10000)

    def test_low_usage_criteria_are_adjustable(self):
        def sub_with_uses(name, days_ago_list):
            sid = self.create_subscription(name=name, category=name, price_won=9000)["id"]
            self.age(sid, 120)
            for days_ago in days_ago_list:
                self.request("POST", f"/api/subscriptions/{sid}/usage-logs",
                             {"used_date": (today() - timedelta(days=days_ago)).isoformat()}, 201)
            return sid

        recent = sub_with_uses("recent", [1, 2, 3])        # 최근 30일에 3회
        old = sub_with_uses("old", [40, 50, 60])            # 31~90일 전에만 3회
        # 기본(90일 2회 이하): 둘 다 3회라 추천 없음
        self.assertEqual(self.recommended(), {})
        # 30일 1회 이하로 바꾸면 최근에 안 쓴 old만 추천
        settings = self.request("PATCH", "/api/settings", {"low_usage_window_days": 30, "low_usage_max_count": 1})
        self.assertEqual((settings["low_usage_window_days"], settings["low_usage_max_count"]), (30, 1))
        items = self.recommended()
        self.assertEqual(set(items), {old})
        self.assertEqual((items[old]["recent_usage_count"], items[old]["window_days"]), (0, 30))
        self.assertIsNone(items[old]["cost_per_use_won"])
        # 90일 3회 이하로 바꾸면 둘 다 추천, 이용 단가는 월 요금 ÷ (3회 × 30/90)
        self.request("PATCH", "/api/settings", {"low_usage_window_days": 90, "low_usage_max_count": 3})
        items = self.recommended()
        self.assertEqual(set(items), {recent, old})
        self.assertEqual(items[recent]["cost_per_use_won"], 9000)
        for bad in ({"low_usage_window_days": 6}, {"low_usage_window_days": 366},
                    {"low_usage_max_count": -1}, {"low_usage_max_count": "2"}, {"low_usage_window_days": None}):
            self.request("PATCH", "/api/settings", bad, 422)

    def test_short_window_needs_only_that_much_observation(self):
        sid = self.create_subscription(name="new")["id"]
        self.age(sid, 10)
        self.request("PATCH", "/api/settings", {"low_usage_window_days": 7, "low_usage_max_count": 0})
        self.assertEqual(set(self.recommended()), {sid})  # 7일 기준이면 7일만 지켜보면 됨
        self.request("PATCH", "/api/settings", {"low_usage_window_days": 14})
        self.assertEqual(self.recommended(), {})  # 10일밖에 안 돼 아직 판단하지 않음

    def test_reset_data(self):
        sid = self.create_subscription()["id"]
        self.request("POST", f"/api/subscriptions/{sid}/usage-logs", {}, 201)
        self.request("POST", f"/api/subscriptions/{sid}/decisions", {"decision": "keep"}, 201)
        self.request("POST", "/api/payments", {"subscription_id": sid, "amount_won": 1, "paid_date": "2026-01-01"}, 201)
        self.request("PATCH", "/api/settings", {"recommendation_enabled": False})
        self.request("POST", "/api/settings/reset-data", {}, 422)
        self.request("POST", "/api/settings/reset-data", {"confirm": False}, 422)
        self.request("POST", "/api/settings/reset-data", {"confirm": True}, 204)
        self.assertEqual(self.request("GET", "/api/subscriptions?include_deleted=true"), [])
        self.assertEqual(self.request("GET", "/api/payments"), [])
        self.assertFalse(self.request("GET", "/api/settings")["recommendation_enabled"])  # 설정은 유지


class DecisionMigrationTests(unittest.TestCase):
    def test_postpone_becomes_hold(self):
        with tempfile.TemporaryDirectory(prefix="migration-hold-") as temp:
            path = Path(temp) / "old.db"
            with closing(sqlite3.connect(path)) as connection, connection:
                connection.executescript("""
                    CREATE TABLE subscriptions (
                        id INTEGER PRIMARY KEY, name TEXT, price_won INTEGER, billing_cycle TEXT,
                        billing_day INTEGER, billing_month INTEGER, category TEXT, status TEXT,
                        created_at DATETIME, updated_at DATETIME
                    );
                    INSERT INTO subscriptions VALUES (1, 'n', 1000, 'monthly', 1, NULL, NULL, 'active',
                        '2026-09-01 00:00:00', '2026-09-01 00:00:00');
                    CREATE TABLE decision_history (
                        id INTEGER PRIMARY KEY, subscription_id INTEGER, decision TEXT, decided_at DATETIME, memo TEXT
                    );
                    INSERT INTO decision_history VALUES (1, 1, 'postpone', '2026-09-02 00:00:00', NULL);
                """)
            migrate_database(path)
            with closing(sqlite3.connect(path)) as connection:
                self.assertEqual(connection.execute("SELECT decision FROM decision_history").fetchall(), [("hold",)])


if __name__ == "__main__":
    unittest.main()
